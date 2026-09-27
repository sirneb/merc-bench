#!/usr/bin/env python3
"""Independent oracle for candidate simulation-3.

Reads ONLY prompt.txt (the text the model sees), parses the scenario out of it
with regular expressions, and re-simulates the network with a deliberately
different representation from generator.py:

  * every unit is an individual record (its expiry day) held in a plain list per
    location, so FEFO is "sort the list and pop from the front" rather than a
    dict keyed by expiry day;
  * shipments in transit are individual unit records tagged with (depot, arrival
    day) in one flat list, so in-transit totals are counted, not summed per lot;
  * priority comparison uses integer cross-multiplication instead of Fraction;
  * the daily loop is written from the manual text, not copied from the
    generator.

Usage: python oracle.py [--prompt prompt.txt] [--key key.json]
Prints the recomputed answer and exits 0 iff it equals key.json exactly.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_prompt(text):
    # keep only the part after the worked example: "## 6." onwards
    body = text[text.index("## 6. Starting state"):]
    days = int(re.search(r"Days are numbered 1 to (\d+)", text).group(1))
    depots = re.findall(r"^Depot ([A-Z]): lead time (\d+) days, s = (\d+), S = (\d+)\.", body, re.M)
    params = {d: dict(lead=int(l), s=int(s), S=int(S)) for d, l, s, S in depots}
    names = sorted(params)

    def lots(segment):
        return [(int(q), int(e)) for q, e in re.findall(r"(\d+) units expiring day (\d+)", segment)]

    central0 = lots(re.search(r"^CENTRAL lots: (.*)$", body, re.M).group(1))
    depot0 = {}
    for d in names:
        m = re.search(rf"^Depot {d} lots: (.*)$", body, re.M)
        depot0[d] = lots(m.group(1))
    transit0 = []
    for d, arrive, rest in re.findall(r"^In transit at day 0: to depot ([A-Z]), arriving day (\d+): (.*)$", body, re.M):
        transit0.append((d, int(arrive), lots(rest)))
    # each supplier delivery carries its own expiry day (shelf lives differ per delivery)
    deliveries = [(int(dd), int(q), int(e))
                  for dd, q, e in re.findall(r"^  Day (\d+): (\d+) units \(expiry day (\d+)\)", body, re.M)]
    demand = {d: {} for d in names}
    for line in re.findall(r"^Day (\d+): (.*)$", body, re.M):
        t = int(line[0])
        for d, q in re.findall(r"([A-Z])=(\d+)", line[1]):
            demand[d][t] = int(q)
    for d in names:
        assert len(demand[d]) == days, (d, len(demand[d]))
    ck = [int(x) for x in re.search(r"Checkpoint days are ([\d, ]+)\.", text).group(1).split(",")]
    return dict(days=days, names=names, params=params, central0=central0,
                depot0=depot0, transit0=transit0, deliveries=deliveries, demand=demand,
                checkpoints=ck)


def simulate(P):
    names = P["names"]
    days = P["days"]
    # unit-level state ---------------------------------------------------
    central = []                       # list of expiry days, one per unit
    for q, e in P["central0"]:
        central += [e] * q
    stock = {d: [] for d in names}
    for d in names:
        for q, e in P["depot0"][d]:
            stock[d] += [e] * q
    transit = []                       # list of (depot, arrival_day, expiry)
    for d, arrive, lts in P["transit0"]:
        for q, e in lts:
            transit += [(d, arrive, e)] * q
    backlog = {d: 0 for d in names}
    # tallies
    expired = {d: 0 for d in names}
    expired_c = 0
    stockout = {d: 0 for d in names}
    received = {d: 0 for d in names}
    cancelled = 0
    same_day = 0
    demanded = 0
    checkpoints = {}

    for today in range(1, days + 1):
        # ---- phase 1: receive
        for dd, q, e in P["deliveries"]:
            if dd == today:
                central += [e] * q
        still = []
        for rec in transit:
            d, arrive, e = rec
            if arrive == today:
                stock[d].append(e)
                received[d] += 1
            else:
                still.append(rec)
        transit = still
        # ---- phase 2: expire
        n0 = len(central)
        central = [e for e in central if e > today]
        expired_c += n0 - len(central)
        for d in names:
            n0 = len(stock[d])
            stock[d] = [e for e in stock[d] if e > today]
            expired[d] += n0 - len(stock[d])
        # ---- phase 3: serve
        for d in names:
            stock[d].sort()
            # step 1: old backorders
            k = min(backlog[d], len(stock[d]))
            del stock[d][:k]
            backlog[d] -= k
            # step 2: today's demand
            dem = P["demand"][d][today]
            demanded += dem
            k = min(dem, len(stock[d]))
            del stock[d][:k]
            same_day += k
            backlog[d] += dem - k
            if backlog[d] > 0:
                stockout[d] += 1
        # ---- phase 4: review & order
        orders = []
        for d in names:
            in_transit = sum(1 for (dd, _, _) in transit if dd == d)
            ip = len(stock[d]) + in_transit - backlog[d]
            if ip < P["params"][d]["s"]:
                orders.append((d, P["params"][d]["S"] - ip))
        # ---- phase 5: allocate & ship
        # priority: higher backlog/S first; compare a/Sa > b/Sb via a*Sb > b*Sa; ties alphabetical
        def before(x, y):
            a, Sa = backlog[x], P["params"][x]["S"]
            b, Sb = backlog[y], P["params"][y]["S"]
            if a * Sb != b * Sa:
                return a * Sb > b * Sa
            return x < y
        # insertion sort with the custom comparator (no key function, on purpose)
        ordered = []
        for d, q in orders:
            i = 0
            while i < len(ordered) and before(ordered[i][0], d):
                i += 1
            ordered.insert(i, (d, q))
        central.sort()
        for d, q in ordered:
            ship = min(q, len(central))
            units = central[:ship]
            del central[:ship]
            arrive = today + P["params"][d]["lead"]
            for e in units:
                transit.append((d, arrive, e))
            cancelled += q - ship
        # ---- end of day
        if today in P["checkpoints"]:
            checkpoints[str(today)] = {
                d: {"on_hand": len(stock[d]), "backorders": backlog[d],
                    "in_transit": sum(1 for (dd, _, _) in transit if dd == d)}
                for d in names}

    return {
        "checkpoints": checkpoints,
        "depots": {d: {"total_expired": expired[d], "stockout_days": stockout[d],
                       "units_received": received[d]} for d in names},
        "central": {"final_on_hand": len(central), "total_cancelled": cancelled,
                    "total_expired": expired_c},
        "same_day_served": same_day,
        "total_demand": demanded,
        "fill_rate": round(same_day / demanded, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=os.path.join(HERE, "prompt.txt"))
    ap.add_argument("--key", default=os.path.join(HERE, "key.json"))
    args = ap.parse_args()
    P = parse_prompt(open(args.prompt).read())
    got = simulate(P)
    key = json.load(open(args.key))
    same = json.dumps(got, sort_keys=True) == json.dumps(key, sort_keys=True)
    print(json.dumps(got, indent=1))
    print("ORACLE MATCHES KEY" if same else "ORACLE DISAGREES WITH KEY")
    if not same:
        for section in got:
            if got[section] != key[section]:
                print("  differs:", section, "oracle=", got[section], "key=", key[section])
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
