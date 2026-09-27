#!/usr/bin/env python3
"""Independent oracle for candidate composition-2. Recomputes the whole chain from prompt.txt
with DIFFERENT algorithms from generator.py and checks it against key.json:

  Stage 1  brute-force DFS enumeration of all simple paths (pruned only when strictly longer than
           the best so far, so ties are kept), then min by (km, station list) - Python's list
           comparison IS the stated lexicographic rule.  (generator: Dijkstra + greedy walk)
  Stage 2  minute-by-minute tick simulation of drive / dwell / rest phases.  (generator: closed form)
  Stage 3  minute-by-minute tick simulation of the dock queues.  (generator: event-driven)
  Stage 4  integer arithmetic with (x + b - 1) // b blocks.  (generator: math.ceil)

Usage: python oracle.py [--dir DIR] [--quiet]   -> exit 0 iff every field agrees with key.json
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
EPOCH = datetime(2026, 1, 1)
FMT = "%Y-%m-%dT%H:%M"


def to_min(s):
    return int((datetime.strptime(s, FMT) - EPOCH).total_seconds() // 60)


def from_min(m):
    return (EPOCH + timedelta(minutes=m)).strftime(FMT)


def parse_prompt(text):
    P = {}
    for line in text.splitlines():
        if line.startswith("PARAMETERS:") or line.startswith("TARIFF:"):
            P.update({k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)})
    stations = re.search(r"^STATIONS \(\d+\): (.+)$", text, re.M).group(1).split(", ")
    segs = [(a, b, int(km)) for a, b, km in re.findall(r"^\s+SEG-\d+\s+(\w+) -- (\w+)\s+(\d+) km$", text, re.M)]
    closures = re.findall(r"^\s+(\d{4}-\d{2}-\d{2})\s+(\w+) -- (\w+)$", text, re.M)
    customers = re.search(r"^CUSTOMERS \(\d+\): (.+)$", text, re.M).group(1).split(", ")
    ships = []
    for m in re.finditer(r"^\s+(S\d+)\s+origin=(\w+)\s+dest=(\w+)\s+ready=(\S+)\s+tonnage=(\d+)\s+hazardous=(yes|no)\s+customer=(\S+)$", text, re.M):
        sid, o, d, ready, ton, hz, cu = m.groups()
        ships.append(dict(id=sid, origin=o, dest=d, ready=ready, tonnage=int(ton), hazardous=(hz == "yes"), customer=cu))
    return P, stations, segs, closures, customers, ships


def all_shortest(nbrs, o, d, closed):
    best, found = [float("inf")], []

    def dfs(u, visited, path, dist):
        if dist > best[0]:
            return
        if u == d:
            if dist < best[0]:
                best[0] = dist
                found.clear()
            found.append(list(path))
            return
        for v, w in nbrs[u]:
            if v in visited or (u, v) in closed:
                continue
            visited.add(v)
            path.append(v)
            dfs(v, visited, path, dist + w)
            path.pop()
            visited.discard(v)
    dfs(o, {o}, [o], 0)
    return best[0], sorted(found)


def tick_arrival(seg_minutes, ready, P):
    t, counter, rests, idx = ready, 0, 0, 0
    phase, remaining = "drive", seg_minutes[0]
    while True:
        t += 1
        remaining -= 1
        if remaining > 0:
            continue
        if phase == "drive":
            counter += seg_minutes[idx]
            idx += 1
            if idx == len(seg_minutes):
                return t, rests
            phase, remaining = "dwell", P["dwell_min"]
        elif phase == "dwell":
            if counter >= P["rest_after_driving_min"]:
                phase, remaining, counter, rests = "rest", P["rest_min"], 0, rests + 1
            else:
                phase, remaining = "drive", seg_minutes[idx]
        else:
            phase, remaining = "drive", seg_minutes[idx]


def tick_docks(entries, docks):
    """entries: list of (arrival_min, sid, unload_min) for one hub -> {sid: start_min}"""
    pending = sorted(entries)
    busy = [None] * docks
    started = {}
    t = pending[0][0]
    while pending:
        for k in range(docks):
            if busy[k] is not None and busy[k] <= t:
                busy[k] = None
        while pending and pending[0][0] <= t and None in busy:
            arr, sid, unload = pending.pop(0)
            k = busy.index(None)
            busy[k] = t + unload
            started[sid] = t
        t += 1
    return started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    text = open(os.path.join(args.dir, "prompt.txt")).read()
    key = json.load(open(os.path.join(args.dir, "key.json")))
    P, stations, segs, closures, customers, ships = parse_prompt(text)
    nbrs = {s: [] for s in stations}
    for a, b, km in segs:
        nbrs[a].append((b, km))
        nbrs[b].append((a, km))
    assert 60 % P["speed_kmh"] == 0 or P["speed_kmh"] == 60
    out_routes, out_arr, ties = [], [], []
    for s in ships:
        dep_date = s["ready"][:10]
        closed = set()
        for d, a, b in closures:
            if d == dep_date:
                closed.add((a, b))
                closed.add((b, a))
        km, paths = all_shortest(nbrs, s["origin"], s["dest"], closed)
        assert paths, f"{s['id']} unreachable"
        path = paths[0]
        if len(paths) > 1:
            ties.append(s["id"])
        out_routes.append({"id": s["id"], "path": path, "km": km})
        segmin = []
        for u, v in zip(path, path[1:]):
            w = dict(nbrs[u])[v]
            assert (w * 60) % P["speed_kmh"] == 0
            segmin.append(w * 60 // P["speed_kmh"])
        arr, rests = tick_arrival(segmin, to_min(s["ready"]), P)
        out_arr.append({"id": s["id"], "arrival": from_min(arr), "rests": rests, "_min": arr})
    arr_min = {a["id"]: a["_min"] for a in out_arr}
    starts = {}
    for hub in sorted({s["dest"] for s in ships}):
        entries = [(arr_min[s["id"]], s["id"], ((s["tonnage"] + P["unload_tonnes_per_block"] - 1) // P["unload_tonnes_per_block"]) * P["unload_block_min"])
                   for s in ships if s["dest"] == hub]
        starts.update(tick_docks(entries, P["docks_per_hub"]))
    out_docks = [{"id": s["id"], "dock_start": from_min(starts[s["id"]]), "wait_minutes": starts[s["id"]] - arr_min[s["id"]]} for s in ships]
    fees, per_cust = [], {c: 0 for c in customers}
    for s, d in zip(ships, out_docks):
        billable = d["wait_minutes"] - P["free_minutes"]
        blocks = (billable + P["block_minutes"] - 1) // P["block_minutes"] if billable > 0 else 0
        fee = blocks * P["rate_per_block"]
        if s["hazardous"]:
            fee *= P["hazardous_multiplier"]
        fee = min(fee, P["cap_per_shipment"])
        fees.append({"id": s["id"], "fee": fee})
        per_cust[s["customer"]] += fee
    mine = {"routes": out_routes, "arrivals": [{k: v for k, v in a.items() if k != "_min"} for a in out_arr],
            "docks": out_docks, "billing": {"per_shipment": fees,
                                            "per_customer": [{"customer": c, "total": per_cust[c]} for c in customers],
                                            "grand_total": sum(f["fee"] for f in fees)}}
    ref = key["reference"]
    diffs = []
    for stage in ("routes", "arrivals", "docks"):
        for a, b in zip(mine[stage], ref[stage]):
            if a != b:
                diffs.append((stage, a, b))
    if mine["billing"] != ref["billing"]:
        diffs.append(("billing", mine["billing"], ref["billing"]))
    if sorted(ties) != sorted(key["diagnostics"]["km_tie_shipments"]):
        diffs.append(("km_ties", ties, key["diagnostics"]["km_tie_shipments"]))
    if diffs:
        print("ORACLE DISAGREES with key.json:")
        for d in diffs:
            print("  ", json.dumps(d, default=str))
        sys.exit(1)
    if not args.quiet:
        print(f"ORACLE AGREES with key.json on all {len(ships)} shipments x 4 stages "
              f"(routes, km, arrivals, rests, dock starts, waits, fees, per-customer totals, grand total; km ties={ties}).")


if __name__ == "__main__":
    main()
