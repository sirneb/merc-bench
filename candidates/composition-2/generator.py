#!/usr/bin/env python3
"""Generator for candidate composition-2: Rail Dispatch Chain.

Deterministic given --seed and --difficulty (or explicit knobs). Writes prompt.txt,
key.json and schema.json into --out (default: this directory).

Reference pipeline (the *reference* implementation; oracle.py is the independent one):
  Stage 1  Dijkstra from the destination + greedy alphabetical walk (lexicographically
           smallest shortest path), closures filtered by departure date.
  Stage 2  closed-form timing: 1 km = 1 minute, 20-min dwell at intermediates, 45-min
           rest inserted before a segment whenever completed driving >= 360 min.
  Stage 3  event-driven multi-dock FIFO simulator (earliest-free dock).
  Stage 4  tariff arithmetic + per-customer rollup.

Rejection sampling guarantees the engineered features (closure-affected routes,
distractor closures, a km tie, near-boundary crew-rest checks, near-tie dock arrivals,
a midnight crossing, a spread of billable / capped / free waits).
"""
import argparse
import heapq
import itertools
import json
import math
import os
import random
from datetime import date, datetime, time, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

STATION_NAMES = [
    "Ashford", "Belmont", "Corwen", "Dunmore", "Elsmere", "Fairlie", "Garston",
    "Halcott", "Ilford", "Jarrow", "Kelso", "Lindale", "Morley", "Naseby", "Oakham",
    "Penrith", "Quorn", "Radlett", "Selby", "Thirsk", "Uppingham", "Ventnor",
    "Wetherby", "Xenia", "Yarm", "Zeals",
]

PRESETS = {
    "easy":    dict(stations=16, edges=24, shipments=8,  hubs=2, docks=2, closures=5,  near_ties=2, dates=2, customers=4),
    "medium":  dict(stations=20, edges=32, shipments=10, hubs=3, docks=2, closures=8,  near_ties=3, dates=3, customers=5),
    "hard":    dict(stations=26, edges=44, shipments=14, hubs=3, docks=2, closures=10, near_ties=3, dates=3, customers=5),
    "extreme": dict(stations=26, edges=52, shipments=20, hubs=4, docks=1, closures=14, near_ties=5, dates=3, customers=6),
}

RULES = dict(speed_kmh=60, dwell_min=20, rest_after_driving_min=360, rest_min=45,
             unload_tonnes_per_block=25, unload_block_min=30)
TARIFF = dict(free_minutes=90, block_minutes=30, rate_per_block=85,
              hazardous_multiplier=2, cap_per_shipment=900)
BASE_DATE = date(2026, 10, 5)
FMT = "%Y-%m-%dT%H:%M"


# ----------------------------------------------------------------------------- stage functions
def dijkstra(adj, src, closed):
    dist = {src: 0}
    pq = [(0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in adj[u].items():
            if frozenset((u, v)) in closed:
                continue
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return dist


def shortest_path(adj, origin, dest, closed):
    """Lexicographically smallest shortest simple path, or None if unreachable."""
    to_dest = dijkstra(adj, dest, closed)
    if origin not in to_dest:
        return None
    path, cur = [origin], origin
    while cur != dest:
        nxt = sorted(v for v, w in adj[cur].items()
                     if frozenset((cur, v)) not in closed and v in to_dest
                     and to_dest[v] + w == to_dest[cur])
        cur = nxt[0]
        path.append(cur)
    return path, to_dest[origin]


def count_shortest_paths(adj, origin, dest, closed):
    to_dest = dijkstra(adj, dest, closed)
    if origin not in to_dest:
        return 0
    memo = {dest: 1}

    def cnt(u):
        if u in memo:
            return memo[u]
        memo[u] = sum(cnt(v) for v, w in adj[u].items()
                      if frozenset((u, v)) not in closed and v in to_dest
                      and to_dest[v] + w == to_dest[u])
        return memo[u]
    return cnt(origin)


def timing(adj, path, ready, rules=RULES):
    """Return (arrival datetime, rests, list of driving-counter values at each check)."""
    t, counter, rests, checks = ready, 0, 0, []
    for i in range(len(path) - 1):
        if i > 0:
            t += timedelta(minutes=rules["dwell_min"])
            checks.append(counter)
            if counter >= rules["rest_after_driving_min"]:
                t += timedelta(minutes=rules["rest_min"])
                rests += 1
                counter = 0
        w = adj[path[i]][path[i + 1]]
        t += timedelta(minutes=w * 60 // rules["speed_kmh"])
        counter += w
    return t, rests, checks


def unload_minutes(tonnage, rules=RULES):
    return math.ceil(tonnage / rules["unload_tonnes_per_block"]) * rules["unload_block_min"]


def dock_schedule(arrivals, ships, docks):
    """arrivals: {sid: datetime}; ships: {sid: shipment dict}. Returns {sid: (start, wait)}."""
    out = {}
    hubs = sorted({s["dest"] for s in ships.values()})
    for hub in hubs:
        order = sorted((arrivals[sid], sid) for sid, s in ships.items() if s["dest"] == hub)
        free = [None] * docks
        for arr, sid in order:
            k = min(range(docks), key=lambda i: (free[i] is not None, free[i] or arr))
            start = arr if free[k] is None else max(arr, free[k])
            free[k] = start + timedelta(minutes=unload_minutes(ships[sid]["tonnage"]))
            out[sid] = (start, int((start - arr).total_seconds() // 60))
    return out


def fee_for(wait, hazardous, tariff=TARIFF):
    billable = max(0, wait - tariff["free_minutes"])
    blocks = math.ceil(billable / tariff["block_minutes"])
    fee = blocks * tariff["rate_per_block"] * (tariff["hazardous_multiplier"] if hazardous else 1)
    return min(fee, tariff["cap_per_shipment"])


def billing(waits, ships, customers, tariff=TARIFF):
    fees = {sid: fee_for(waits[sid], ships[sid]["hazardous"], tariff) for sid in ships}
    per_cust = {c: 0 for c in customers}
    for sid, f in fees.items():
        per_cust[ships[sid]["customer"]] += f
    return fees, per_cust, sum(fees.values())


# ----------------------------------------------------------------------------- graph generation
def gen_graph(rng, n, m, deg_cap=5):
    """Gabriel graph on random points (planar, many near-equal alternatives), pruned or
    padded to exactly m edges while keeping connectivity and min degree 2."""
    names = STATION_NAMES[:n]
    order = names[:]
    rng.shuffle(order)
    pts = {}
    for nm in order:
        for _ in range(500):
            p = (rng.uniform(0, 330), rng.uniform(0, 215))
            if all(math.dist(p, q) >= 27 for q in pts.values()):
                break
        pts[nm] = p

    def d(a, b):
        return math.dist(pts[a], pts[b])

    gabriel = []
    for a, b in itertools.combinations(names, 2):
        mx, my = (pts[a][0] + pts[b][0]) / 2, (pts[a][1] + pts[b][1]) / 2
        r2 = (d(a, b) / 2) ** 2
        if all((pts[c][0] - mx) ** 2 + (pts[c][1] - my) ** 2 > r2 + 1e-9 for c in names if c not in (a, b)):
            gabriel.append(frozenset((a, b)))
    edges = {e: 0 for e in gabriel}
    deg = {nm: 0 for nm in names}
    for e in edges:
        for x in e:
            deg[x] += 1

    def connected(es):
        seen, stack = {names[0]}, [names[0]]
        while stack:
            u = stack.pop()
            for e in es:
                if u in e:
                    v = next(iter(e - {u}))
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
        return len(seen) == len(names)

    if not connected(edges):
        return None
    # give branch-line termini a second link (nearest non-Gabriel neighbour)
    for a in names:
        if deg[a] < 2:
            for b in sorted((x for x in names if x != a and frozenset((a, x)) not in edges), key=lambda x: d(a, x)):
                if deg[b] < deg_cap:
                    edges[frozenset((a, b))] = 0
                    deg[a] += 1
                    deg[b] += 1
                    break
    cand = list(edges)
    rng.shuffle(cand)
    for e in cand:
        if len(edges) <= m:
            break
        a, b = tuple(e)
        if deg[a] <= 2 or deg[b] <= 2:
            continue
        del edges[e]
        if connected(edges):
            deg[a] -= 1
            deg[b] -= 1
        else:
            edges[e] = 0
    if len(edges) < m:
        missing = sorted((d(a, b), a, b) for a, b in itertools.combinations(names, 2)
                         if frozenset((a, b)) not in edges)
        for _, a, b in missing:
            if len(edges) >= m:
                break
            if deg[a] < deg_cap and deg[b] < deg_cap:
                edges[frozenset((a, b))] = 0
                deg[a] += 1
                deg[b] += 1
    if len(edges) != m or max(deg.values()) > deg_cap + 1:
        return None
    for e in edges:
        a, b = tuple(e)
        edges[e] = max(15, round(d(a, b) * rng.uniform(1.06, 1.38)))
    adj = {nm: {} for nm in names}
    for e, km in edges.items():
        a, b = tuple(e)
        adj[a][b] = km
        adj[b][a] = km
    return names, adj, pts, edges


# ----------------------------------------------------------------------------- instance attempt
def attempt(rng, P):
    G = gen_graph(rng, P["stations"], P["edges"])
    if G is None:
        return (None, 'r1')
    names, adj, pts, edges = G
    M, K = P["shipments"], P["customers"]
    dates = [BASE_DATE + timedelta(days=i) for i in range(P["dates"])]

    hub_cands = [n for n in names if len(adj[n]) >= 3]
    for _ in range(60):
        hubs = sorted(rng.sample(hub_cands, P["hubs"]))
        if all(math.dist(pts[a], pts[b]) >= 105 for a, b in itertools.combinations(hubs, 2)):
            break
    else:
        return (None, 'r2')

    hub_of = [hubs[i % len(hubs)] for i in range(M)]
    rng.shuffle(hub_of)
    ships, used = [], set()
    for i in range(M):
        hub = hub_of[i]
        dist = dijkstra(adj, hub, set())
        pool_long = [n for n in names if n != hub and 340 <= dist.get(n, 0) <= 720 and (n, hub) not in used]
        pool_any = [n for n in names if n != hub and 180 <= dist.get(n, 0) <= 720 and (n, hub) not in used]
        pool = pool_long if (i % 2 == 0 and pool_long) else pool_any
        if not pool:
            return (None, 'r3')
        origin = rng.choice(pool)
        used.add((origin, hub))
        ships.append(dict(id=f"S{i + 1:02d}", origin=origin, dest=hub,
                          tonnage=rng.randint(20, 200), hazardous=rng.random() < 0.3))
    ia, ib = rng.sample(range(M), 2)
    ships[ia]["tonnage"] = rng.choice([50, 75, 100, 125, 150])
    ships[ib]["tonnage"] = rng.choice([51, 76, 101, 126, 152])
    customers = [f"CU-{k + 1:02d}" for k in range(K)]
    assign = [customers[i % K] for i in range(M)]
    rng.shuffle(assign)
    for s, c in zip(ships, assign):
        s["customer"] = c
    by_id = {s["id"]: s for s in ships}

    # target arrivals: per-hub windows, engineered near-tie gaps
    hours = rng.sample([2, 5, 9, 13, 17, 20], len(hubs))
    windows = {h: datetime.combine(rng.choice(dates[1:] if (hr < 12 and len(dates) > 1) else dates),
                                   time(hr, rng.randint(0, 59)))
               for h, hr in zip(hubs, hours)}
    groups = {h: [s for s in ships if s["dest"] == h] for h in hubs}
    for g in groups.values():
        rng.shuffle(g)
    pair_slots = [(h, j) for h, g in groups.items() for j in range(len(g) - 1)]
    rng.shuffle(pair_slots)
    tie_slots = set(pair_slots[:P["near_ties"] + 1])
    for h, g in groups.items():
        off = 0
        for j, s in enumerate(g):
            s["target"] = windows[h] + timedelta(minutes=off)
            off += rng.randint(3, 14) if (h, j) in tie_slots else rng.randint(16, 45)

    # unrestricted routes -> provisional ready times
    for s in ships:
        r = shortest_path(adj, s["origin"], s["dest"], set())
        if r is None:
            return (None, 'r4')
        s["path0"], s["km0"] = r
        arr0, _, _ = timing(adj, s["path0"], s["target"])
        s["ready"] = s["target"] - (arr0 - s["target"])
        s["dep0"] = s["ready"].date()

    # closures: affecting, distractor, filler
    closures = set()
    order = list(range(M))
    rng.shuffle(order)
    n_aff = max(4, M // 2)
    for i in order[:n_aff]:
        s = ships[i]
        segs = [frozenset((s["path0"][k], s["path0"][k + 1])) for k in range(len(s["path0"]) - 1)]
        seg = rng.choice(segs[1:-1]) if len(segs) >= 3 else rng.choice(segs)
        closures.add((s["dep0"], seg))
    for i in order[n_aff:n_aff + 3]:
        s = ships[i]
        segs = [frozenset((s["path0"][k], s["path0"][k + 1])) for k in range(len(s["path0"]) - 1)]
        arr_date = s["target"].date()
        others = [d for d in dates if d != s["dep0"]]
        if not others:
            continue
        d = arr_date if arr_date != s["dep0"] else rng.choice(others)
        closures.add((d, rng.choice(segs)))
    edge_list = sorted(edges, key=lambda e: sorted(e))
    guard = 0
    while len(closures) < P["closures"] and guard < 1000:
        guard += 1
        closures.add((rng.choice(dates), rng.choice(edge_list)))
    if len(closures) != P["closures"]:
        return (None, 'r5')

    # fixed point: ready = target - duration(route on departure date); after the loop the
    # stored route/arrival are always recomputed from the final ready time, so the chain is
    # self-consistent even if the target arrival was not reached exactly.
    for it in range(8):
        changed = False
        for s in ships:
            dep = s["ready"].date()
            closed = {e for (d, e) in closures if d == dep}
            r = shortest_path(adj, s["origin"], s["dest"], closed)
            if r is None:
                return (None, 'r6')
            path, km = r
            arr, rests, checks = timing(adj, path, s["ready"])
            new_ready = s["target"] - (arr - s["ready"])
            if it < 7 and new_ready != s["ready"]:
                changed = True
                s["ready"] = new_ready
                continue
            s.update(path=path, km=km, arrival=arr, rests=rests, checks=checks,
                     n_short=count_shortest_paths(adj, s["origin"], s["dest"], closed))
        if not changed:
            break
    for s in ships:
        if s["ready"].date() not in dates:
            return (None, 'r8')
        if not (2 <= len(s["path"]) - 2 <= 10):
            return (None, 'r9')

    arrivals = {s["id"]: s["arrival"] for s in ships}
    sched = dock_schedule(arrivals, by_id, P["docks"])
    waits = {sid: w for sid, (st, w) in sched.items()}
    fees, per_cust, grand = billing(waits, by_id, customers)

    # ---- constraints
    diag = {}
    diag["closure_affected"] = [s["id"] for s in ships if s["path"] != s["path0"]]
    if len(diag["closure_affected"]) < max(4, M // 3):
        return (None, 'r10')
    distract = []
    for s in ships:
        segs = {frozenset((s["path"][k], s["path"][k + 1])) for k in range(len(s["path"]) - 1)}
        dep = s["ready"].date()
        if any(e in segs and d != dep for (d, e) in closures):
            distract.append(s["id"])
    diag["distractor_closure_on_route"] = distract
    if len(distract) < 2:
        return (None, 'r11')
    diag["km_tie_shipments"] = [s["id"] for s in ships if s["n_short"] >= 2]
    if not 1 <= len(diag["km_tie_shipments"]) <= 2:
        return (None, 'r12')
    diag["shipments_with_rest"] = [s["id"] for s in ships if s["rests"] >= 1]
    if len(diag["shipments_with_rest"]) < 5:
        return (None, 'r13')
    over = [s["id"] for s in ships if any(360 <= c <= 380 for c in s["checks"])]
    under = [s["id"] for s in ships if any(340 <= c <= 359 for c in s["checks"])]
    diag["rest_boundary_just_over"], diag["rest_boundary_just_under"] = over, under
    if not over or not under:
        return (None, 'r14')
    diag["midnight_crossing"] = [s["id"] for s in ships if s["arrival"].date() != s["ready"].date()]
    if not diag["midnight_crossing"]:
        return (None, 'r15')
    near = []
    for h in hubs:
        seq = sorted((arrivals[s["id"]], s["id"]) for s in ships if s["dest"] == h)
        for (a1, i1), (a2, i2) in zip(seq, seq[1:]):
            gap = int((a2 - a1).total_seconds() // 60)
            if gap == 0:
                return (None, 'r16')
            if gap <= 15:
                near.append([i1, i2, gap])
    diag["near_tie_arrivals"] = near
    if len(near) < P["near_ties"]:
        return (None, 'r17')
    # dock-order sensitivity: does a near tie actually change downstream results?
    billable = [sid for sid, w in waits.items() if w > TARIFF["free_minutes"]]
    capped = [sid for sid, f in fees.items() if f == TARIFF["cap_per_shipment"]]
    hz_bill = [sid for sid in billable if by_id[sid]["hazardous"]]
    zero = [sid for sid, w in waits.items() if w == 0]
    freewait = [sid for sid, w in waits.items() if 0 < w <= TARIFF["free_minutes"]]
    diag.update(billable=billable, capped=capped, hazardous_billable=hz_bill, zero_wait=zero, free_nonzero_wait=freewait)
    if len(billable) < 5 or not capped or not hz_bill or not 2 <= len(zero) <= P['docks'] * len(hubs) + 1 or not freewait:
        return (None, 'r18')
    if len({v for v in per_cust.values() if v > 0}) < 3:
        return (None, 'r19')
    # near ties must matter: swapping the order of at least one near-tie pair changes a wait
    flips = 0
    for i1, i2, gap in near:
        alt = dict(arrivals)
        alt[i1], alt[i2] = arrivals[i2], arrivals[i1]
        sched2 = dock_schedule(alt, by_id, P["docks"])
        if any(sched2[sid][1] != waits[sid] for sid in (i1, i2)):
            flips += 1
    diag["near_ties_that_change_waits"] = flips
    if flips < 2:
        return (None, 'r20')

    return (dict(names=names, adj=adj, edges=edges, hubs=hubs, ships=ships, closures=closures,
                customers=customers, sched=sched, waits=waits, fees=fees, per_cust=per_cust,
                grand=grand, diag=diag), 'ok')


# ----------------------------------------------------------------------------- rendering
def render_prompt(inst, P):
    names, adj, edges = inst["names"], inst["adj"], inst["edges"]
    seg_rows = sorted((sorted(e)[0], sorted(e)[1], km) for e, km in edges.items())
    L = []
    A = L.append
    A("IMPORTANT: Solve without any tools — no Bash, no Python, no code execution, no files, no web. Work it out yourself.")
    A("")
    A("You are the dispatcher of a small freight rail network. Work through the four stages below EXACTLY as specified and report every stage's results. Each stage uses only the static data in this prompt and the results of the previous stage, so be precise: a wrong route changes the arrival time, which changes the dock queue, which changes the bills.")
    A("")
    A("======================================================================")
    A("RULES")
    A("======================================================================")
    A("")
    A("General")
    A("- Every shipment travels as its own train. Trains never interact on the track (no capacity limits, no meets).")
    A("- All timestamps are local depot time in one time zone with no daylight-saving change, written YYYY-MM-DDTHH:MM (24-hour clock). Every duration in this problem is a whole number of minutes, so no rounding is ever needed.")
    A("- Track segments are undirected (usable in either direction) with the km length listed.")
    A("- Station names are compared as plain strings; every station name starts with a different letter, so alphabetical order is simply the order of first letters.")
    A("")
    A("Stage 1 - ROUTES")
    A("- A shipment's departure date is the date part of its ready timestamp.")
    A("- A maintenance-calendar entry '<date>  X -- Y' means segment X--Y is closed for the whole of that date: NO train whose departure date is that date may use that segment anywhere on its route, even if the train would only reach the segment on a later date. Closures listed for other dates are irrelevant to that train. Closures never delay a train; they only restrict which segments its route may use.")
    A("- The route is the simple path (no station visited twice) from origin to destination that minimises total km using only segments open on the departure date. Trains may pass through hub stations as intermediate stops.")
    A("- Tie-break: if two or more paths have the same minimum km, choose the one whose station sequence is alphabetically first, comparing station names position by position (the origin is the same for all, so the first differing position decides; e.g. [Ashford, Belmont, Kelso, Zeals] beats [Ashford, Corwen, Belmont, Zeals]).")
    A("- Report the full station sequence including origin and destination, and the total km.")
    A("")
    A("Stage 2 - ARRIVALS")
    A(f"- The train departs the origin at exactly the ready timestamp. There is no dwell at the origin.")
    A(f"- Speed is exactly {RULES['speed_kmh']} km/h on every segment, so a segment of k km takes exactly k minutes. A segment is never interrupted once started.")
    A(f"- At every intermediate station (each station on the route except origin and destination) the train dwells {RULES['dwell_min']} minutes. There is no dwell at the destination: the arrival time is the minute the train reaches the destination station.")
    A(f"- Crew rule: the crew keeps a driving counter that starts at 0 at the origin and increases by a segment's minutes when that segment is completed. Dwell and rest minutes do NOT count. Immediately before the train departs on any segment other than the first (i.e. after the {RULES['dwell_min']}-minute dwell), if the counter is {RULES['rest_after_driving_min']} or more, the crew takes a {RULES['rest_min']}-minute rest at that station (so that departure is delayed by {RULES['dwell_min']}+{RULES['rest_min']} minutes in total) and the counter resets to 0. The check uses completed driving only: a segment is never split even if it pushes the counter far past {RULES['rest_after_driving_min']}. No rest is taken at the destination. A long trip may include more than one rest.")
    A("- Report the arrival timestamp and the number of rests taken.")
    A("")
    A("Stage 3 - DOCKS")
    A(f"- Each destination hub has {P['docks']} identical unloading docks, dedicated to that hub. All docks are free from the start and operate around the clock. Only the shipments in this problem use them.")
    A(f"- Unloading a shipment takes ceil(tonnage / {RULES['unload_tonnes_per_block']}) x {RULES['unload_block_min']} minutes (e.g. 100 t -> 4 x {RULES['unload_block_min']} = {4 * RULES['unload_block_min']} min; 101 t -> 5 x {RULES['unload_block_min']} = {5 * RULES['unload_block_min']} min).")
    A("- Shipments bound for the same hub are served strictly in service order: earlier arrival first; if two arrive in the same minute, the smaller shipment id first. Process them one at a time in that order: take the dock that becomes free earliest (any free dock if several are idle); dock_start = the later of the shipment's arrival and that dock's free time; that dock is then busy until dock_start + unloading minutes, and is free again in that very minute (a new shipment may start in the same minute another finishes).")
    A("- wait_minutes = dock_start - arrival (in minutes).")
    A("")
    A("Stage 4 - DEMURRAGE BILLING")
    A(f"- Per shipment: the first {TARIFF['free_minutes']} minutes of wait are free. billable = max(0, wait_minutes - {TARIFF['free_minutes']}). blocks = ceil(billable / {TARIFF['block_minutes']}) (a started block counts in full). fee = blocks x ${TARIFF['rate_per_block']}; if the shipment is hazardous the fee is multiplied by {TARIFF['hazardous_multiplier']}; finally the fee is capped at ${TARIFF['cap_per_shipment']} per shipment (the cap applies after the hazardous multiplier). All fees are whole dollars.")
    A("- Per customer: the sum of that customer's shipment fees (report every customer, including those with $0). Grand total: the sum over all shipments.")
    A("")
    A("======================================================================")
    A("DATA")
    A("======================================================================")
    A("")
    A(f"PARAMETERS: speed_kmh={RULES['speed_kmh']} dwell_min={RULES['dwell_min']} rest_after_driving_min={RULES['rest_after_driving_min']} rest_min={RULES['rest_min']} docks_per_hub={P['docks']} unload_tonnes_per_block={RULES['unload_tonnes_per_block']} unload_block_min={RULES['unload_block_min']}")
    A(f"TARIFF: free_minutes={TARIFF['free_minutes']} block_minutes={TARIFF['block_minutes']} rate_per_block={TARIFF['rate_per_block']} hazardous_multiplier={TARIFF['hazardous_multiplier']} cap_per_shipment={TARIFF['cap_per_shipment']}")
    A("")
    A(f"STATIONS ({len(names)}): " + ", ".join(names))
    A("")
    A(f"HUBS ({len(inst['hubs'])}): " + ", ".join(inst["hubs"]))
    A("")
    A(f"SEGMENTS ({len(seg_rows)}; undirected; km):")
    for i, (a, b, km) in enumerate(seg_rows, 1):
        A(f"  SEG-{i:02d}  {a} -- {b}  {km} km")
    A("")
    cl = sorted(((d, sorted(e)[0], sorted(e)[1]) for d, e in inst["closures"]))
    A(f"MAINTENANCE CALENDAR ({len(cl)} closures; segment closed for the whole date shown):")
    for d, a, b in cl:
        A(f"  {d.isoformat()}  {a} -- {b}")
    A("")
    A(f"CUSTOMERS ({len(inst['customers'])}): " + ", ".join(inst["customers"]))
    A("")
    A(f"SHIPMENTS ({len(inst['ships'])}):")
    for s in inst["ships"]:
        A(f"  {s['id']}  origin={s['origin']}  dest={s['dest']}  ready={s['ready'].strftime(FMT)}  tonnage={s['tonnage']}  hazardous={'yes' if s['hazardous'] else 'no'}  customer={s['customer']}")
    A("")
    A("======================================================================")
    A("OUTPUT FORMAT")
    A("======================================================================")
    A("")
    A("Return ONLY a single JSON object (no prose, no markdown fences) with exactly this shape. Include every shipment in every list, in shipment-id order, and every customer in per_customer. Timestamps as strings YYYY-MM-DDTHH:MM; km, rests, wait_minutes, fee, total and grand_total as integers.")
    A("")
    A(json.dumps({
        "routes": [{"id": "S01", "path": ["Origin", "Intermediate", "Destination"], "km": 0}, {"id": "S02", "path": ["..."], "km": 0}],
        "arrivals": [{"id": "S01", "arrival": "2026-10-05T12:34", "rests": 0}, {"id": "S02", "arrival": "...", "rests": 0}],
        "docks": [{"id": "S01", "dock_start": "2026-10-05T12:34", "wait_minutes": 0}, {"id": "S02", "dock_start": "...", "wait_minutes": 0}],
        "billing": {
            "per_shipment": [{"id": "S01", "fee": 0}, {"id": "S02", "fee": 0}],
            "per_customer": [{"customer": "CU-01", "total": 0}, {"customer": "CU-02", "total": 0}],
            "grand_total": 0,
        },
    }, indent=1))
    A("")
    A("Do not include any keys other than those shown. Do not explain your work.")
    return "\n".join(L) + "\n"


SCHEMA = {
    "type": "object",
    "properties": {
        "routes": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "path": {"type": "array", "items": {"type": "string"}},
            "km": {"type": "integer"}}, "required": ["id", "path", "km"]}},
        "arrivals": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "arrival": {"type": "string"}, "rests": {"type": "integer"}},
            "required": ["id", "arrival"]}},
        "docks": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "dock_start": {"type": "string"}, "wait_minutes": {"type": "integer"}},
            "required": ["id", "dock_start", "wait_minutes"]}},
        "billing": {"type": "object", "properties": {
            "per_shipment": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "fee": {"type": "integer"}}, "required": ["id", "fee"]}},
            "per_customer": {"type": "array", "items": {"type": "object", "properties": {
                "customer": {"type": "string"}, "total": {"type": "integer"}}, "required": ["customer", "total"]}},
            "grand_total": {"type": "integer"}},
            "required": ["per_customer", "grand_total"]},
    },
    "required": ["routes", "arrivals", "docks", "billing"],
}


def build_key(inst, P, seed, difficulty, attempts):
    ships = inst["ships"]
    seg_rows = sorted((sorted(e)[0], sorted(e)[1], km) for e, km in inst["edges"].items())
    reference = {
        "routes": [{"id": s["id"], "path": s["path"], "km": s["km"]} for s in ships],
        "arrivals": [{"id": s["id"], "arrival": s["arrival"].strftime(FMT), "rests": s["rests"]} for s in ships],
        "docks": [{"id": s["id"], "dock_start": inst["sched"][s["id"]][0].strftime(FMT),
                   "wait_minutes": inst["waits"][s["id"]]} for s in ships],
        "billing": {
            "per_shipment": [{"id": s["id"], "fee": inst["fees"][s["id"]]} for s in ships],
            "per_customer": [{"customer": c, "total": inst["per_cust"][c]} for c in inst["customers"]],
            "grand_total": inst["grand"],
        },
    }
    instance = {
        "stations": inst["names"],
        "hubs": inst["hubs"],
        "segments": [{"id": f"SEG-{i:02d}", "a": a, "b": b, "km": km} for i, (a, b, km) in enumerate(seg_rows, 1)],
        "closures": [{"date": d.isoformat(), "a": sorted(e)[0], "b": sorted(e)[1]}
                     for d, e in sorted(inst["closures"], key=lambda x: (x[0], sorted(x[1])))],
        "customers": inst["customers"],
        "shipments": [{"id": s["id"], "origin": s["origin"], "dest": s["dest"], "ready": s["ready"].strftime(FMT),
                       "tonnage": s["tonnage"], "hazardous": s["hazardous"], "customer": s["customer"]} for s in ships],
        "docks": P["docks"],
        "rules": RULES,
        "tariff": TARIFF,
    }
    diag = dict(inst["diag"])
    diag["unrestricted_routes"] = {s["id"]: {"path": s["path0"], "km": s["km0"]} for s in ships}
    diag["rest_checks"] = {s["id"]: s["checks"] for s in ships}
    diag["n_shortest_paths"] = {s["id"]: s["n_short"] for s in ships}
    diag["generator_attempts"] = attempts
    return {"task": "composition-2", "seed": seed, "difficulty": difficulty, "params": P,
            "instance": instance, "reference": reference, "diagnostics": diag}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261005)
    ap.add_argument("--difficulty", choices=sorted(PRESETS), default="hard")
    for k in PRESETS["hard"]:
        ap.add_argument(f"--{k.replace('_', '-')}", type=int, default=None, help=f"override preset {k}")
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    P = dict(PRESETS[args.difficulty])
    for k in PRESETS["hard"]:
        v = getattr(args, k)
        if v is not None:
            P[k] = v
    if P["stations"] > len(STATION_NAMES):
        raise SystemExit(f"stations <= {len(STATION_NAMES)}")
    P["difficulty"] = args.difficulty
    inst, attempts, reasons = None, 0, {}
    while inst is None:
        attempts += 1
        if attempts > 40000:
            raise SystemExit(f"could not satisfy constraints; loosen knobs. reasons={reasons}")
        rng = random.Random(f"{args.seed}:{attempts}")
        inst, why = attempt(rng, P)
        reasons[why] = reasons.get(why, 0) + 1
    if os.environ.get("GEN_DEBUG"):
        print("rejection reasons:", dict(sorted(reasons.items(), key=lambda kv: -kv[1])))
    os.makedirs(args.out, exist_ok=True)
    prompt = render_prompt(inst, P)
    key = build_key(inst, P, args.seed, args.difficulty, attempts)
    with open(os.path.join(args.out, "prompt.txt"), "w") as f:
        f.write(prompt)
    with open(os.path.join(args.out, "key.json"), "w") as f:
        json.dump(key, f, indent=1)
    with open(os.path.join(args.out, "schema.json"), "w") as f:
        json.dump(SCHEMA, f, indent=1)
    d = key["diagnostics"]
    print(f"seed={args.seed} difficulty={args.difficulty} attempts={attempts} prompt_bytes={len(prompt.encode())}")
    print(f"closure_affected={d['closure_affected']} distractors={d['distractor_closure_on_route']} km_ties={d['km_tie_shipments']}")
    print(f"rests={d['shipments_with_rest']} just_over={d['rest_boundary_just_over']} just_under={d['rest_boundary_just_under']} midnight={d['midnight_crossing']}")
    print(f"near_ties={d['near_tie_arrivals']} flips={d['near_ties_that_change_waits']} billable={d['billable']} capped={d['capped']} zero={d['zero_wait']}")
    print(f"grand_total={key['reference']['billing']['grand_total']} per_customer={key['reference']['billing']['per_customer']}")


if __name__ == "__main__":
    main()
