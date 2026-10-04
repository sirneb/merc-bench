#!/usr/bin/env python3
"""Grader for candidate composition-2 (Rail Dispatch Chain).
Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth (key.json) in this directory.

Scoring (100 points, 25 per stage; every shipment weighs 25/M in stages 1-3):
  Stage 1 routes    : per shipment 60% of its share for the exact station sequence, 40% for exact km.
  Stage 2 arrivals  : per shipment full share if the arrival timestamp is exact, half if within 20 min.
                      CONDITIONAL: the same test against the arrival recomputed from the model's OWN
                      Stage-1 path (if it is a valid walk origin->destination on the network).
  Stage 3 docks     : per shipment full share for exact wait_minutes, half if within 15 min.
                      CONDITIONAL: the dock simulator is re-run on the model's OWN Stage-2 arrivals.
  Stage 4 billing   : 15 points split across customers (exact or 0), 10 points for the grand total
                      (exact 10, within 2% 5). CONDITIONAL: the tariff is applied to the model's OWN waits.
  Each stage-2/3/4 component is credited max(absolute, conditional) so the detail isolates WHERE the
  chain first broke; `detail.first_divergence` names the first shipment (id order) and stage that
  departs from the reference chain.
"""
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "tasks")):
    if os.path.exists(os.path.join(_p, "_common.py")):
        sys.path.insert(0, _p)
        break
try:
    from _common import load_answer, emit
except ImportError:  # minimal local copies of tasks/_common.py helpers
    def load_answer(path):
        rec = json.load(open(path))
        ans = rec.get("answer")
        if isinstance(ans, str):
            try:
                ans = json.loads(ans)
            except Exception:
                ans = {"_text": ans}
        return rec, (ans if isinstance(ans, dict) else {})

    def emit(task, score, total, detail):
        print(json.dumps({"task": task, "score": score, "total": total, "detail": detail}))

TASK = "composition-2"
FMT = "%Y-%m-%dT%H:%M"
ARRIVAL_TOL_MIN = 20
WAIT_TOL_MIN = 15
GRAND_TOL = 0.02
CONDITIONAL_WEIGHT = 1.0   # knob: <1.0 makes propagated errors cost something even when the downstream work is right


# ----------------------------------------------------------------------------- stage functions (reference copies)
def timing(adj, path, ready, rules):
    t, counter, rests = ready, 0, 0
    for i in range(len(path) - 1):
        if i > 0:
            t += timedelta(minutes=rules["dwell_min"])
            if counter >= rules["rest_after_driving_min"]:
                t += timedelta(minutes=rules["rest_min"])
                rests += 1
                counter = 0
        w = adj[path[i]][path[i + 1]]
        t += timedelta(minutes=w * 60 // rules["speed_kmh"])
        counter += w
    return t, rests


def unload_minutes(tonnage, rules):
    return math.ceil(tonnage / rules["unload_tonnes_per_block"]) * rules["unload_block_min"]


def dock_schedule(arrivals, ships, docks, rules):
    out = {}
    for hub in sorted({s["dest"] for s in ships.values()}):
        order = sorted((arrivals[sid], sid) for sid, s in ships.items() if s["dest"] == hub)
        free = [None] * docks
        for arr, sid in order:
            k = min(range(docks), key=lambda i: (free[i] is not None, free[i] or arr))
            start = arr if free[k] is None else max(arr, free[k])
            free[k] = start + timedelta(minutes=unload_minutes(ships[sid]["tonnage"], rules))
            out[sid] = (start, int((start - arr).total_seconds() // 60))
    return out


def fee_for(wait, hazardous, tariff):
    billable = max(0, wait - tariff["free_minutes"])
    blocks = math.ceil(billable / tariff["block_minutes"])
    fee = blocks * tariff["rate_per_block"] * (tariff["hazardous_multiplier"] if hazardous else 1)
    return min(fee, tariff["cap_per_shipment"])


def billing(waits, ships, customers, tariff):
    fees = {sid: fee_for(waits[sid], ships[sid]["hazardous"], tariff) for sid in ships}
    per = {c: 0 for c in customers}
    for sid, f in fees.items():
        per[ships[sid]["customer"]] += f
    return fees, per, sum(fees.values())


# ----------------------------------------------------------------------------- tolerant parsing
TS_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T\s]+(\d{1,2}):(\d{2})")


def parse_ts(v):
    if isinstance(v, datetime):
        return v
    m = TS_RE.search(str(v)) if v is not None else None
    if not m:
        return None
    try:
        return datetime(*map(int, m.groups()))
    except ValueError:
        return None


def parse_int(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return int(round(float(m.group(0).replace(",", ""))))
    except ValueError:
        return None


def norm_id(v):
    m = re.search(r"S\s*-?\s*0*(\d+)", str(v).upper())
    return f"S{int(m.group(1)):02d}" if m else str(v).strip().upper()


def norm_cust(v):
    m = re.search(r"CU\s*-?\s*0*(\d+)", str(v).upper())
    return f"CU-{int(m.group(1)):02d}" if m else str(v).strip().upper()


def norm_path(v, canon):
    if isinstance(v, str):
        toks = re.findall(r"[A-Za-z]+", v)
    elif isinstance(v, list):
        toks = [x.get("station", x.get("name", "")) if isinstance(x, dict) else str(x) for x in v]
    else:
        return None
    out = [canon[t.strip().lower()] for t in toks if t.strip().lower() in canon]
    return out or None


def extract_json(text):
    text = re.sub(r"```(?:json)?", "", text)
    dec, best = json.JSONDecoder(), None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and (best is None or len(obj) > len(best)):
            best = obj
    return best or {}


def get_list(d, *keys):
    if not isinstance(d, dict):
        return []
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        v = low.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):  # {"S01": {...}, ...}
            return [dict(x, id=k2) if isinstance(x, dict) else {"id": k2, "value": x} for k2, x in v.items()]
    return []


FIELDS = {
    "path": ["path", "route", "stations", "sequence", "station_sequence"],
    "km": ["km", "total_km", "distance_km", "distance", "length_km"],
    "arrival": ["arrival", "arrival_time", "arrive", "eta", "arrival_timestamp"],
    "rests": ["rests", "rest_count"],
    "dock_start": ["dock_start", "start", "start_time", "dock_start_time", "unload_start"],
    "wait": ["wait_minutes", "wait", "wait_min", "wait_mins", "demurrage_minutes"],
    "fee": ["fee", "demurrage", "amount", "charge"],
}


def collect(ans, inst):
    """Pull per-shipment fields out of any of the accepted layouts."""
    ids = [s["id"] for s in inst["shipments"]]
    per = {sid: {} for sid in ids}
    canon = {n.lower(): n for n in inst["stations"]}

    def merge(items, wanted):
        for it in items:
            if not isinstance(it, dict):
                continue
            low = {str(k).lower(): v for k, v in it.items()}
            sid = norm_id(low.get("id", low.get("shipment", low.get("shipment_id", ""))))
            if sid not in per:
                continue
            for tgt in wanted:
                for src in FIELDS[tgt]:
                    if src in low and low[src] is not None:
                        per[sid].setdefault(tgt, low[src])
                        break

    merge(get_list(ans, "routes", "stage1", "stage_1"), ["path", "km"])
    merge(get_list(ans, "arrivals", "stage2", "stage_2"), ["arrival", "rests"])
    merge(get_list(ans, "docks", "dock_schedule", "stage3", "stage_3"), ["dock_start", "wait"])
    bill = ans.get("billing") if isinstance(ans.get("billing"), dict) else ans
    merge(get_list(bill, "per_shipment", "fees", "shipments"), ["fee"])
    merge(get_list(ans, "shipments", "results"), list(FIELDS))  # merged single-list layout
    out = {}
    for sid in ids:
        g = per[sid]
        path = norm_path(g.get("path"), canon)
        arrival = parse_ts(g.get("arrival"))
        dock_start = parse_ts(g.get("dock_start"))
        wait = parse_int(g.get("wait"))
        if wait is None and dock_start is not None and arrival is not None:
            wait = int((dock_start - arrival).total_seconds() // 60)
        out[sid] = dict(path=path, km=parse_int(g.get("km")), arrival=arrival, rests=parse_int(g.get("rests")),
                        dock_start=dock_start, wait=wait, fee=parse_int(g.get("fee")))
    per_cust = {}
    pc = get_list(bill, "per_customer", "customers", "customer_totals")
    for it in pc:
        if isinstance(it, dict):
            low = {str(k).lower(): v for k, v in it.items()}
            cid = low.get("customer", low.get("id", low.get("customer_id", low.get("name"))))
            tot = None
            for k in ("total", "amount", "fee", "demurrage", "value"):
                if k in low:
                    tot = parse_int(low[k])
                    break
            if cid is not None:
                per_cust[norm_cust(cid)] = tot
    grand = None
    for src in (bill, ans):
        if isinstance(src, dict):
            low = {str(k).lower(): v for k, v in src.items()}
            for k in ("grand_total", "total", "grand"):
                if k in low and not isinstance(low[k], (list, dict)):
                    grand = parse_int(low[k])
                    break
        if grand is not None:
            break
    return out, per_cust, grand


# ----------------------------------------------------------------------------- scoring
def pts(got, want, share, tol):
    if got is None or want is None:
        return 0.0
    diff = abs((got - want).total_seconds() / 60) if isinstance(want, datetime) else abs(got - want)
    if diff == 0:
        return share
    return share / 2 if diff <= tol else 0.0


def valid_walk(path, s, adj):
    return (path is not None and len(path) >= 2 and path[0] == s["origin"] and path[-1] == s["dest"]
            and all(path[i + 1] in adj[path[i]] for i in range(len(path) - 1)))


def grade(ans):
    key = json.load(open(os.path.join(HERE, "key.json")))
    inst, ref = key["instance"], key["reference"]
    rules, tariff, docks = inst["rules"], inst["tariff"], inst["docks"]
    fmt = "json"
    if "_text" in ans:
        ans = extract_json(ans["_text"])
        fmt = "text"
    if not ans:
        fmt = "empty"
    adj = {n: {} for n in inst["stations"]}
    for e in inst["segments"]:
        adj[e["a"]][e["b"]] = e["km"]
        adj[e["b"]][e["a"]] = e["km"]
    ships = {s["id"]: dict(s, ready=datetime.strptime(s["ready"], FMT)) for s in inst["shipments"]}
    ids = [s["id"] for s in inst["shipments"]]
    M, customers = len(ids), inst["customers"]
    ref_route = {r["id"]: r for r in ref["routes"]}
    ref_arr = {a["id"]: datetime.strptime(a["arrival"], FMT) for a in ref["arrivals"]}
    ref_wait = {d["id"]: d["wait_minutes"] for d in ref["docks"]}
    ref_cust = {c["customer"]: c["total"] for c in ref["billing"]["per_customer"]}
    ref_grand = ref["billing"]["grand_total"]

    got, got_cust, got_grand = collect(ans, inst)
    share = 25.0 / M
    cw = CONDITIONAL_WEIGHT

    # Stage 1
    s1 = 0.0
    path_ok, km_ok, path_miss = 0, 0, []
    for sid in ids:
        g, r = got[sid], ref_route[sid]
        if g["path"] == r["path"]:
            path_ok += 1
            s1 += 0.6 * share
        else:
            path_miss.append(sid)
        if g["km"] == r["km"]:
            km_ok += 1
            s1 += 0.4 * share

    # Stage 2
    s2_abs = s2_cond = s2 = 0.0
    abs2_miss, cond2_miss, cond2_na = [], [], []
    for sid in ids:
        g, s = got[sid], ships[sid]
        a = pts(g["arrival"], ref_arr[sid], share, ARRIVAL_TOL_MIN)
        c = 0.0
        if valid_walk(g["path"], s, adj):
            arr_c, _ = timing(adj, g["path"], s["ready"], rules)
            c = pts(g["arrival"], arr_c, share, ARRIVAL_TOL_MIN)
        else:
            cond2_na.append(sid)
        s2_abs += a
        s2_cond += c
        s2 += max(a, cw * c)
        if a < share:
            abs2_miss.append(sid)
        if c < share:
            cond2_miss.append(sid)

    # Stage 3
    arr_model = {sid: (got[sid]["arrival"] or ref_arr[sid]) for sid in ids}
    sched_c = dock_schedule(arr_model, ships, docks, rules)
    # non-degeneracy guard: conditional credit only when the model's own chain actually exercises
    # the stage (otherwise "every wait is 0" would earn a free 25 points downstream)
    cond3_ok = any(w for _, w in sched_c.values())
    s3_abs = s3_cond = s3 = 0.0
    abs3_miss, cond3_miss = [], []
    for sid in ids:
        g = got[sid]
        a = pts(g["wait"], ref_wait[sid], share, WAIT_TOL_MIN)
        c = pts(g["wait"], sched_c[sid][1], share, WAIT_TOL_MIN) if cond3_ok else 0.0
        s3_abs += a
        s3_cond += c
        s3 += max(a, cw * c)
        if a < share:
            abs3_miss.append(sid)
        if c < share:
            cond3_miss.append(sid)

    # Stage 4
    waits_model = {sid: (got[sid]["wait"] if got[sid]["wait"] is not None else ref_wait[sid]) for sid in ids}
    fees_c, cust_c, grand_c = billing(waits_model, ships, customers, tariff)
    cond4_ok = any(fees_c.values())
    cshare = 15.0 / len(customers)
    s4_abs = s4_cond = s4 = 0.0
    cust_abs_miss, cust_cond_miss = [], []
    for cid in customers:
        g = got_cust.get(cid)
        a = cshare if (g is not None and g == ref_cust[cid]) else 0.0
        c = cshare if (cond4_ok and g is not None and g == cust_c[cid]) else 0.0
        s4_abs += a
        s4_cond += c
        s4 += max(a, cw * c)
        if not a:
            cust_abs_miss.append(cid)
        if not c:
            cust_cond_miss.append(cid)

    def grand_pts(g, want):
        if g is None:
            return 0.0
        if g == want:
            return 10.0
        return 5.0 if abs(g - want) <= GRAND_TOL * max(1, abs(want)) else 0.0
    ga, gc = grand_pts(got_grand, ref_grand), (grand_pts(got_grand, grand_c) if cond4_ok else 0.0)
    s4_abs += ga
    s4_cond += gc
    s4 += max(ga, cw * gc)

    first = None
    for sid in ids:
        g = got[sid]
        if g["path"] != ref_route[sid]["path"]:
            first = {"id": sid, "stage": 1}
        elif g["arrival"] != ref_arr[sid]:
            first = {"id": sid, "stage": 2}
        elif g["wait"] != ref_wait[sid]:
            first = {"id": sid, "stage": 3}
        if first:
            break
    if first is None and (cust_abs_miss or ga < 10):
        first = {"id": None, "stage": 4}

    r2 = lambda x: round(x, 2)
    score = r2(s1 + s2 + s3 + s4)
    detail = {
        "format": fmt,
        "stage1": {"score": r2(s1), "path_ok": path_ok, "km_ok": km_ok, "of": M, "path_miss": path_miss},
        "stage2": {"score": r2(s2), "absolute": r2(s2_abs), "conditional": r2(s2_cond),
                   "abs_miss": abs2_miss, "cond_miss": cond2_miss, "cond_not_computable": cond2_na},
        "stage3": {"score": r2(s3), "absolute": r2(s3_abs), "conditional": r2(s3_cond),
                   "abs_miss": abs3_miss, "cond_miss": cond3_miss, "cond_degenerate": not cond3_ok},
        "stage4": {"score": r2(s4), "absolute": r2(s4_abs), "conditional": r2(s4_cond),
                   "customer_abs_miss": cust_abs_miss, "customer_cond_miss": cust_cond_miss, "cond_degenerate": not cond4_ok,
                   "grand": {"got": got_grand, "want": ref_grand, "cond_want": grand_c}},
        "first_divergence": first,
    }
    return score, 100, detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit(TASK, s, t, d)
