#!/usr/bin/env python3
"""Generator for candidate task "simulation-3": cold-chain depot network,
multi-day multi-depot inventory simulation with lead times, FEFO lot expiry,
backorders and central rationing.

Usage: python generator.py [--seed N] [--difficulty easy|medium|hard|extreme] [--out DIR]

Deterministic given (seed, difficulty). Writes prompt.txt, key.json, schema.json,
scenario.json (the parameter object the prompt was rendered from) and trace.txt
(the reference simulator's phase-by-phase log, for auditing).

The prompt text and the answer key are rendered from ONE parameter object, and the
reference simulator asserts unit-conservation invariants at the end of every day.
oracle.py (a separate, per-unit implementation that reads only prompt.txt) must
reproduce key.json exactly.
"""
import argparse
import json
import math
import os
import random
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))

DIFFICULTY = {
    # days, number of depots, central shelf life (days), checkpoint spacing
    "easy": dict(days=15, n_depots=3, shelf=18, ckpt=5),
    "medium": dict(days=20, n_depots=4, shelf=18, ckpt=10),
    "hard": dict(days=30, n_depots=4, shelf=18, ckpt=10),
    "extreme": dict(days=60, n_depots=6, shelf=14, ckpt=10),
}
WEEK = [1.0, 1.1, 0.9, 1.2, 1.0, 0.7, 0.8]
DEM_LO, DEM_HI, N_SPIKES = 0.4, 1.6, 3
FACTORS = [0.4, 0.7, 1.0, 1.0, 1.3, 1.6]
S_FACTOR = 1.0  # reorder point = S_FACTOR x mean lead-time demand


# --------------------------------------------------------------------------
# Reference simulator (lots stored as {expiry_day: qty} per location)
# --------------------------------------------------------------------------
class Sim:
    def __init__(self, sc, trace=False):
        self.sc = sc
        self.depots = sc["depots"]
        self.days = sc["days"]
        self.central = {}
        for q, e in sc["central_lots"]:
            self.central[e] = self.central.get(e, 0) + q
        self.stock = {d: {} for d in self.depots}
        for d in self.depots:
            for q, e in sc["depot_lots"][d]:
                self.stock[d][e] = self.stock[d].get(e, 0) + q
        self.bo = {d: 0 for d in self.depots}
        # pipeline: list of (arrive_day, depot, {exp: qty})
        self.pipe = []
        for sh in sc["in_transit0"]:
            lots = {}
            for q, e in sh["lots"]:
                lots[e] = lots.get(e, 0) + q
            self.pipe.append((sh["arrive"], sh["depot"], lots))
        self.exp_d = {d: 0 for d in self.depots}
        self.so_days = {d: 0 for d in self.depots}
        self.recv = {d: 0 for d in self.depots}
        self.exp_c = 0
        self.cancelled = 0
        self.served = 0
        self.served_same_day = 0
        self.demanded = 0
        self.checkpoints = {}
        self.trace_on = trace
        self.trace = []
        # trap counters (for seed selection / reporting)
        self.ev = dict(cancel_orders=0, cancel_days=set(), partial=0,
                       full_cancel=0, depot_expiry_events=0, depot_expired_units=0,
                       bo_depot_days=0, bo_depots=set(), priority_days=0,
                       arrive_expired_units=0, central_expiry_events=0,
                       multi_lot_shipments=0, negative_ip_orders=0, order_count=0)
        self.total_in = (sum(q for q, _ in sc["central_lots"])
                         + sum(q for d in self.depots for q, _ in sc["depot_lots"][d])
                         + sum(q for sh in sc["in_transit0"] for q, _ in sh["lots"]))

    def log(self, s):
        if self.trace_on:
            self.trace.append(s)

    @staticmethod
    def take_fefo(lots, n):
        """Remove n units from lots (dict exp->qty) earliest expiry first. Returns {exp: qty} taken."""
        taken = {}
        for e in sorted(lots):
            if n <= 0:
                break
            k = min(n, lots[e])
            taken[e] = k
            lots[e] -= k
            n -= k
            if lots[e] == 0:
                del lots[e]
        return taken

    @staticmethod
    def fmt_lots(lots):
        if not lots:
            return "nothing"
        return ", ".join(f"{q} exp d{e}" for e, q in sorted(lots.items()))

    def on_hand(self, d):
        return sum(self.stock[d].values())

    def in_transit(self, d):
        return sum(sum(l.values()) for a, dd, l in self.pipe if dd == d)

    def run(self):
        sc = self.sc
        for t in range(1, self.days + 1):
            self.log(f"=== Day {t} ===")
            # Phase 1: receive
            p1 = []
            for day, qty in sc["deliveries"]:
                if day == t:
                    e = t + sc["shelf"]
                    self.central[e] = self.central.get(e, 0) + qty
                    self.total_in += qty
                    p1.append(f"CENTRAL receives supplier delivery {qty} exp d{e}")
            arriving = [x for x in self.pipe if x[0] == t]
            self.pipe = [x for x in self.pipe if x[0] != t]
            for a, d, lots in sorted(arriving, key=lambda x: x[1]):
                for e, q in lots.items():
                    self.stock[d][e] = self.stock[d].get(e, 0) + q
                    self.recv[d] += q
                    if e <= t:
                        self.ev["arrive_expired_units"] += q
                p1.append(f"{d} receives shipment: {self.fmt_lots(lots)}")
            self.log("  P1 RECEIVE: " + ("; ".join(p1) if p1 else "nothing arrives"))
            # Phase 2: expire
            p2 = []
            gone = {e: q for e, q in self.central.items() if e <= t}
            if gone:
                n = sum(gone.values())
                self.exp_c += n
                self.ev["central_expiry_events"] += 1
                for e in gone:
                    del self.central[e]
                p2.append(f"CENTRAL discards {n} ({self.fmt_lots(gone)})")
            for d in self.depots:
                gone = {e: q for e, q in self.stock[d].items() if e <= t}
                if gone:
                    n = sum(gone.values())
                    self.exp_d[d] += n
                    self.ev["depot_expiry_events"] += 1
                    self.ev["depot_expired_units"] += n
                    for e in gone:
                        del self.stock[d][e]
                    p2.append(f"{d} discards {n} ({self.fmt_lots(gone)})")
            self.log("  P2 EXPIRE: " + ("; ".join(p2) if p2 else "nothing expires"))
            # Phase 3: serve (old backorders first, then today's demand; FEFO)
            p3 = []
            for d in self.depots:
                dem = sc["demand"][d][t - 1]
                old_bo = self.bo[d]
                oh = self.on_hand(d)
                srv_bo = min(old_bo, oh)
                srv_dem = min(dem, oh - srv_bo)
                srv = srv_bo + srv_dem
                taken = self.take_fefo(self.stock[d], srv)
                self.served_same_day += srv_dem
                self.served += srv
                self.demanded += dem
                self.bo[d] = (old_bo - srv_bo) + (dem - srv_dem)
                so = self.bo[d] > 0
                if so:
                    self.so_days[d] += 1
                    self.ev["bo_depot_days"] += 1
                    self.ev["bo_depots"].add(d)
                p3.append(f"{d}: on hand {oh}, backorders {old_bo} -> serves {srv_bo}, demand {dem} -> serves {srv_dem}"
                          f" (taken {self.fmt_lots(taken)}), backorders now {self.bo[d]}"
                          f"{' STOCKOUT DAY' if so else ''}, left {self.fmt_lots(self.stock[d])}")
            self.log("  P3 SERVE: " + " | ".join(p3))
            # Phase 4: review & order
            orders = {}
            p4 = []
            for d in self.depots:
                oh = self.on_hand(d)
                it = self.in_transit(d)
                ip = oh + it - self.bo[d]
                if ip < sc["s"][d]:
                    orders[d] = sc["S"][d] - ip
                    self.ev["order_count"] += 1
                    if ip < 0:
                        self.ev["negative_ip_orders"] += 1
                    p4.append(f"{d}: IP={oh}+{it}-{self.bo[d]}={ip} < s={sc['s'][d]} -> orders {orders[d]}")
                else:
                    p4.append(f"{d}: IP={oh}+{it}-{self.bo[d]}={ip} >= s={sc['s'][d]} -> no order")
            self.log("  P4 REVIEW: " + " | ".join(p4))
            # Phase 5: allocate & ship
            p5 = []
            if orders:
                prio = sorted(orders, key=lambda d: (-Fraction(self.bo[d], sc["S"][d]), d))
                ratios = ", ".join(f"{d}={self.bo[d]}/{sc['S'][d]}" for d in prio)
                p5.append(f"priority {'>'.join(prio)} (ratios {ratios}); CENTRAL on hand {sum(self.central.values())}")
                if prio != sorted(prio):
                    self.ev["_prio_nonalpha_today"] = True
                day_cancel = False
                for d in prio:
                    q = orders[d]
                    avail = sum(self.central.values())
                    ship = min(q, avail)
                    canc = q - ship
                    if ship > 0:
                        lots = self.take_fefo(self.central, ship)
                        if len(lots) > 1:
                            self.ev["multi_lot_shipments"] += 1
                        arr = t + sc["lead"][d]
                        self.pipe.append((arr, d, lots))
                        s = f"{d}: ships {ship} ({self.fmt_lots(lots)}) arriving d{arr}"
                    else:
                        s = f"{d}: ships 0"
                    if canc > 0:
                        self.cancelled += canc
                        self.ev["cancel_orders"] += 1
                        day_cancel = True
                        if ship > 0:
                            self.ev["partial"] += 1
                        else:
                            self.ev["full_cancel"] += 1
                        s += f", cancels {canc}"
                    p5.append(s)
                if day_cancel:
                    self.ev["cancel_days"].add(t)
                    if self.ev.pop("_prio_nonalpha_today", False):
                        self.ev["priority_days"] += 1
                self.ev.pop("_prio_nonalpha_today", None)
            self.log("  P5 ALLOCATE: " + ("; ".join(p5) if p5 else "no orders"))
            # end of day
            eod = " | ".join(f"{d}: on_hand {self.on_hand(d)} bo {self.bo[d]} in_transit {self.in_transit(d)}"
                             for d in self.depots)
            self.log(f"  END: {eod} | CENTRAL {sum(self.central.values())} "
                     f"| cum same-day served {self.served_same_day}/{self.demanded}, cancelled {self.cancelled}")
            if t in sc["checkpoints"]:
                self.checkpoints[str(t)] = {
                    d: {"on_hand": self.on_hand(d), "backorders": self.bo[d],
                        "in_transit": self.in_transit(d)} for d in self.depots}
            # conservation invariant
            held = (sum(self.central.values()) + sum(self.on_hand(d) for d in self.depots)
                    + sum(sum(l.values()) for _, _, l in self.pipe))
            out = self.served + self.exp_c + sum(self.exp_d.values())
            assert held + out == self.total_in, (t, held, out, self.total_in)
        return self.key()

    def key(self):
        return {
            "checkpoints": self.checkpoints,
            "depots": {d: {"total_expired": self.exp_d[d], "stockout_days": self.so_days[d],
                           "units_received": self.recv[d]} for d in self.depots},
            "central": {"final_on_hand": sum(self.central.values()),
                        "total_cancelled": self.cancelled, "total_expired": self.exp_c},
            "fill_rate": round(self.served_same_day / self.demanded, 4) if self.demanded else 0.0,
        }


# --------------------------------------------------------------------------
# Scenario sampling + seed selection
# --------------------------------------------------------------------------
def sample_scenario(rng, cfg):
    n, days, shelf = cfg["n_depots"], cfg["days"], cfg["shelf"]
    depots = [chr(ord("A") + i) for i in range(n)]
    mus = rng.sample(range(5, 15), n)
    while True:
        lead = {d: rng.choice([2, 3, 4]) for d in depots}
        if len(set(lead.values())) >= 2:
            break
    s = {d: math.ceil(mus[i] * lead[d] * S_FACTOR) for i, d in enumerate(depots)}
    S = {d: s[d] + round(mus[i] * rng.uniform(2.5, 3.5)) for i, d in enumerate(depots)}
    demand = {}
    for i, d in enumerate(depots):
        row = []
        for t in range(1, days + 1):
            v = mus[i] * WEEK[(t - 1) % 7] * rng.uniform(DEM_LO, DEM_HI)
            if rng.random() < 0.05:
                v = 0
            row.append(int(round(v)))
        for t in rng.sample(range(days), N_SPIKES):
            row[t] = int(round(row[t] * 2.2)) + 1
        demand[d] = row
    depot_lots, in_transit0 = {}, []
    for i, d in enumerate(depots):
        depot_lots[d] = [[int(round(S[d] * rng.uniform(0.35, 0.5))), rng.randint(3, 5)],
                         [int(round(S[d] * rng.uniform(0.25, 0.4))), rng.randint(7, 10)]]
        if rng.random() < 0.5:
            in_transit0.append({"depot": d, "arrive": rng.randint(1, 2),
                                "lots": [[int(round(mus[i] * rng.uniform(2, 3.5))), rng.randint(6, 9)]]})
    ck = cfg["ckpt"]
    checkpoints = list(range(ck, days + 1, ck))
    if checkpoints[-1] != days:
        checkpoints.append(days)
    c_e1, c_e2 = rng.randint(3, 4), rng.randint(9, 11)
    # supplier schedule: alternating 3/4-day gaps, per-delivery size factors
    sched_days, t, gap = [], 1, rng.choice([3, 4])
    while t <= days:
        sched_days.append(t)
        t += gap
        gap = 7 - gap
    factors = [rng.choice(FACTORS) for _ in sched_days]
    sc = dict(days=days, depots=depots, shelf=shelf, deliveries=None, lead=lead, s=s, S=S,
              central_lots=None, depot_lots=depot_lots, in_transit0=in_transit0,
              demand=demand, checkpoints=checkpoints)
    # Choose the supplier base quantity by a deterministic scan so that central
    # rationing binds on roughly a third of the days while the same-day fill rate
    # stays in a non-trivial band and CENTRAL does not end empty. This keeps the
    # trap rules firing without collapsing the network into permanent starvation.
    per_gap = sum(sum(v) for v in demand.values()) / days * 3.5
    target = days / 3.3
    best = None
    for base in range(int(per_gap * 0.6), int(per_gap * 1.8) + 1, 1):
        sc["deliveries"] = [[dd, int(round(base * f))] for dd, f in zip(sched_days, factors)]
        sc["central_lots"] = [[round(base * 0.8), c_e1], [round(base * 0.6), c_e2]]
        sim = Sim(sc)
        key = sim.run()
        cd = len(sim.ev["cancel_days"])
        pen = abs(cd - target) + (0 if 0.70 <= key["fill_rate"] <= 0.97 else 100) \
            + (0 if key["central"]["final_on_hand"] > 0 else 50) \
            + max(0, 4 - sim.ev["partial"]) * 3 + max(0, 2 - sim.ev["priority_days"]) * 4
        if best is None or pen < best[0]:
            best = (pen, base)
    base = best[1]
    sc["deliveries"] = [[dd, int(round(base * f))] for dd, f in zip(sched_days, factors)]
    sc["central_lots"] = [[round(base * 0.8), c_e1], [round(base * 0.6), c_e2]]
    return sc


def passes(sc, sim, key):
    ev = sim.ev
    days = sc["days"]
    scale = days / 30.0
    checks = {
        "cancel_orders>=4": ev["cancel_orders"] >= 4 * scale,
        "partial>=4": ev["partial"] >= 4 * scale,
        "full_cancel>=1": ev["full_cancel"] >= 1,
        "cancel_days in [4, 0.4*days]": 4 * scale <= len(ev["cancel_days"]) <= 0.4 * days,
        "depot_expiry_events>=4": ev["depot_expiry_events"] >= 4 * scale,
        "depot_expired_units>=20": ev["depot_expired_units"] >= 20 * scale,
        "central_expiry>=1": ev["central_expiry_events"] >= 1,
        "bo_depot_days>=6": ev["bo_depot_days"] >= 6 * scale,
        "bo_depots>=3": len(ev["bo_depots"]) >= min(3, len(sc["depots"])),
        "priority_days>=2": ev["priority_days"] >= 2 * scale,
        "arrive_expired>=1": ev["arrive_expired_units"] >= 1,
        "multi_lot_shipments>=3": ev["multi_lot_shipments"] >= 3,
        "negative_ip_orders>=1": ev["negative_ip_orders"] >= 1,
        "every depot stockout_days in [1, days/2]": all(
            1 <= v <= days / 2 for v in key["depots"].values() for v in [v["stockout_days"]]),
        "fill_rate in [0.70,0.97]": 0.70 <= key["fill_rate"] <= 0.97,
        "some checkpoint backorders>0": sum(
            1 for c in key["checkpoints"].values() for v in c.values() if v["backorders"] > 0) >= 2,
        "some checkpoint in_transit>0": sum(
            1 for c in key["checkpoints"].values() for v in c.values() if v["in_transit"] > 0) >= 3,
        "central final_on_hand>0": key["central"]["final_on_hand"] > 0,
    }
    return checks


def build(seed, difficulty):
    cfg = DIFFICULTY[difficulty]
    for k in range(5000):
        rng = random.Random(seed * 1000003 + k * 7919 + hash(difficulty) % 1)
        rng = random.Random(f"{seed}:{difficulty}:{k}")
        sc = sample_scenario(rng, cfg)
        sim = Sim(sc, trace=True)
        key = sim.run()
        checks = passes(sc, sim, key)
        if all(checks.values()):
            sc["_subseed"] = k
            return sc, sim, key, checks
    raise SystemExit("no scenario passed the selection criteria; loosen them")


# --------------------------------------------------------------------------
# Worked mini-example (fixed, hand-chosen so every rule fires within 3 days)
# --------------------------------------------------------------------------
EXAMPLE = dict(days=3, depots=["A", "B"], shelf=12, deliveries=[[1, 36]],
               lead={"A": 1, "B": 3}, s={"A": 10, "B": 12}, S={"A": 20, "B": 20},
               central_lots=[[10, 2], [12, 5]],
               depot_lots={"A": [[6, 1], [8, 4]], "B": [[5, 3]]},
               in_transit0=[{"depot": "B", "arrive": 1, "lots": [[4, 2]]}],
               demand={"A": [5, 9, 11], "B": [7, 6, 3]}, checkpoints=[3])


# --------------------------------------------------------------------------
# Prompt rendering
# --------------------------------------------------------------------------
def render_prompt(sc, ex_sc, ex_key, ex_trace):
    D = sc["depots"]
    n = len(D)
    days = sc["days"]
    deliv = sc["deliveries"]
    lines = []
    A = lines.append
    A("IMPORTANT: Solve without any tools — no Bash, no Python, no code execution, no files, no web. Work it out yourself.")
    A("")
    A(f"You are the operations analyst of a small cold-chain distribution network. Below are the complete "
      f"operating manual, the day-0 starting state and the full {days}-day demand table. Simulate the network "
      f"EXACTLY as the manual specifies, day by day and phase by phase, and report the requested figures as a "
      f"single JSON object. Nothing in this scenario follows 'industry defaults' — every rule you need is written "
      f"below, and where your intuition about inventory systems disagrees with the text, the text wins.")
    A("")
    A("## 1. Network and stock")
    A(f"- One central warehouse (CENTRAL) and {n} depots: {', '.join(D)}.")
    A("- CENTRAL receives supplier deliveries and ships to depots. Depots serve customer demand and order from CENTRAL. Depots never ship to each other.")
    A("- All stock is held in LOTS. A lot is a quantity of units that share one expiry day. Lots at the same location with the same expiry day are interchangeable and may be treated as one lot.")
    A("")
    A("## 2. Timeline")
    A(f"- Days are numbered 1 to {days}. Each day, the five phases in section 3 are executed in order (1, 2, 3, 4, 5) for the whole network before the next day begins.")
    A("- Section 6 gives the state at the end of day 0. All reported checkpoint values are the state at the END of the named day, after phase 5.")
    A("")
    A("## 3. Daily phases")
    A("PHASE 1 — RECEIVE.")
    A(f"  (a) CENTRAL: on each supplier delivery day listed in section 7, a lot of the listed quantity with expiry day = (delivery day + {sc['shelf']}) is added to CENTRAL's stock. There are no other sources of stock.")
    A("  (b) DEPOTS: every shipment whose arrival day equals today is added to the destination depot's stock lot by lot, keeping each lot's expiry day. Every unit that arrives counts toward that depot's units_received — even if the lot is discarded in phase 2 of the same day.")
    A("PHASE 2 — EXPIRE.")
    A("  At every location (CENTRAL and each depot) every lot whose expiry day is LESS THAN OR EQUAL TO today is discarded in full. Discarded units count toward that location's total_expired. Consequently a lot with expiry day E can be used to serve or ship on days up to and including E-1, and is destroyed at phase 2 of day E. Nothing else expires at any other point of the day.")
    A("PHASE 3 — SERVE (depots only).")
    A("  For each depot, in two steps, both taking units from the lot with the EARLIEST expiry day first, then the next-earliest, and so on (FEFO):")
    A("  Step 1 — old backorders: serve as many of the outstanding backorders (carried from previous days) as on-hand allows.")
    A("  Step 2 — today's demand: from whatever on-hand remains, serve as much of today's demand (from the table) as possible. The unserved part of today's demand is added to the backorders.")
    A("  So after phase 3: backorders = (old backorders not served in step 1) + (today's demand not served in step 2). Only units served in step 2 — today's demand served today — count toward the network's SAME-DAY SERVED total used by fill_rate; backorders served late in step 1 do not. Today's demand counts toward the network's demanded total whether or not it was served. If backorders > 0 at the end of phase 3, today is a STOCKOUT DAY for that depot (a day with zero demand but unserved old backorders is still a stockout day; a day where all backorders and demand are cleared is not).")
    A("PHASE 4 — REVIEW & ORDER (depots only).")
    A("  For each depot compute the inventory position IP = on-hand (after phase 3) + in-transit − backorders, where in-transit is the total number of units in shipments already dispatched to this depot that have not yet arrived (arrival day > today). If IP < s (the depot's reorder point) the depot places an order for exactly (S − IP) units, where S is its order-up-to level; the quantity may exceed S when IP is negative. If IP >= s no order is placed. Orders are handled in phase 5 of the SAME day and never persist: there is no such thing as an open order from a previous day.")
    A("PHASE 5 — ALLOCATE & SHIP (CENTRAL only).")
    A("  CENTRAL processes today's orders one at a time in priority order: highest shortfall ratio first, where shortfall ratio = (the depot's backorders at the end of today's phase 3) ÷ (that depot's S). Compare ratios exactly (as fractions). Ties — including several depots all at ratio 0 — are broken alphabetically by depot name (A before B before C ...). For each order in turn: shipped = min(order quantity, CENTRAL's on-hand at that moment). The shipped units are taken from CENTRAL's lots in FEFO order (earliest expiry first) and travel as lots that keep their expiry days (one shipment may therefore contain several lots). The shipment is dispatched today and arrives in phase 1 of day (today + that depot's lead time). Any unfilled remainder (order quantity − shipped) is CANCELLED on the spot and counts toward CENTRAL's total_cancelled; it is never back-ordered, retried, queued or remembered. If CENTRAL has no stock left the whole order is cancelled. Shipments are dispatched even if they would arrive after day " + str(days) + "; they simply stay in transit.")
    A("")
    A("## 4. Definitions of the reported figures")
    A("Checkpoints (for each checkpoint day and each depot, state at the END of that day):")
    A("- on_hand: total units in the depot's lots.")
    A("- backorders: outstanding backorders.")
    A("- in_transit: total units in shipments dispatched to the depot on any day up to and including the checkpoint day whose arrival day is later than the checkpoint day.")
    A("Per-depot totals over the whole horizon:")
    A(f"- total_expired: units discarded at that depot in phase 2 (days 1–{days}).")
    A("- stockout_days: number of days that were stockout days for that depot (see phase 3).")
    A(f"- units_received: units that arrived at the depot in phase 1 on days 1–{days} (units already in transit at day 0 count when they arrive; day-0 on-hand stock does not).")
    A("CENTRAL:")
    A(f"- final_on_hand: units in CENTRAL's lots at the end of day {days}.")
    A("- total_cancelled: total units of orders cancelled in phase 5 over the horizon.")
    A("- total_expired: units discarded at CENTRAL in phase 2 over the horizon.")
    A("Network:")
    A(f"- fill_rate: (total units of demand served on the day it arose, i.e. the sum of phase-3 step-2 quantities over all depots and days 1–{days}) ÷ (total demand of all depots on days 1–{days}), rounded to 4 decimal places. Backorders served on a later day do NOT count toward the numerator.")
    A("")
    A("## 5. Worked mini-example (different, tiny scenario — same rules)")
    A("To pin down every rule, here is a complete 3-day run of a toy network with 2 depots. It is NOT the scenario you must solve.")
    ex = ex_sc
    A(f"  Toy parameters: one supplier delivery of {ex['deliveries'][0][1]} units on day 1 with expiry day = delivery day + {ex['shelf']} = 13. "
      f"Depot A: lead time {ex['lead']['A']}, s={ex['s']['A']}, S={ex['S']['A']}. Depot B: lead time {ex['lead']['B']}, s={ex['s']['B']}, S={ex['S']['B']}.")
    A(f"  Day-0 state: CENTRAL lots: 10 units exp day 2, 12 units exp day 5. Depot A lots: 6 units exp day 1, 8 units exp day 4. "
      f"Depot B lots: 5 units exp day 3. In transit at day 0: 4 units exp day 2 to depot B, arriving day 1. No backorders.")
    A(f"  Demand: day 1 A=5 B=7; day 2 A=9 B=6; day 3 A=11 B=3.")
    A("  Trace ('exp d4' means expiry day 4; 'IP=a+b-c' is on-hand + in-transit − backorders):")
    for ln in ex_trace:
        A("  " + ln)
    A("  Toy answer JSON (checkpoint day 3):")
    A("  " + json.dumps(ex_key, separators=(",", ":")))
    A(f"  Note in particular: the 10 units that reached depot A on day 2 with expiry day 2 count as received AND as expired; "
      f"on day 2 depot B ordered nothing because its in-transit units kept IP >= s even though it had backorders; on day 3 depot B's backorders were served before its new demand and only the new demand served counts for fill_rate; "
      f"on day 3 the order priority was B before A because B's shortfall ratio was higher, so B got the last units and A's whole order was cancelled; and cancelled quantities were never carried over.")
    A("")
    A("## 6. Starting state of THIS scenario (end of day 0)")
    A("CENTRAL lots: " + "; ".join(f"{q} units expiring day {e}" for q, e in sc["central_lots"]) + ".")
    for d in D:
        A(f"Depot {d} lots: " + "; ".join(f"{q} units expiring day {e}" for q, e in sc["depot_lots"][d]) + ".")
    if sc["in_transit0"]:
        for sh in sc["in_transit0"]:
            A(f"In transit at day 0: to depot {sh['depot']}, arriving day {sh['arrive']}: "
              + "; ".join(f"{q} units expiring day {e}" for q, e in sh["lots"]) + ".")
    else:
        A("In transit at day 0: nothing.")
    A("Backorders at day 0: none at any depot.")
    A("")
    A("## 7. Depot parameters")
    for d in D:
        A(f"Depot {d}: lead time {sc['lead'][d]} days, s = {sc['s'][d]}, S = {sc['S'][d]}.")
    A(f"CENTRAL supplier deliveries (each arrives in phase 1 of the listed day as one lot expiring on delivery day + {sc['shelf']}):")
    for dd, q in deliv:
        A(f"  Day {dd:02d}: {q} units (expiry day {dd + sc['shelf']})")
    A("")
    A(f"## 8. Demand table (units demanded per depot per day, days 1–{days})")
    A("Each cell is labelled depot=units.")
    for t in range(1, days + 1):
        A(f"Day {t:02d}: " + "  ".join(f"{d}={sc['demand'][d][t-1]}" for d in D))
    A("")
    A("## 9. Output format")
    ck = sc["checkpoints"]
    A(f"Return ONLY one JSON object (no prose, no markdown fences, no comments) with exactly this shape. "
      f"Checkpoint days are {', '.join(map(str, ck))}. All values except fill_rate are non-negative integers; fill_rate is a number with 4 decimal places.")
    shape = {
        "checkpoints": {str(c): {d: {"on_hand": 0, "backorders": 0, "in_transit": 0} for d in D} for c in ck},
        "depots": {d: {"total_expired": 0, "stockout_days": 0, "units_received": 0} for d in D},
        "central": {"final_on_hand": 0, "total_cancelled": 0, "total_expired": 0},
        "fill_rate": 0.0,
    }
    A(json.dumps(shape, indent=1))
    A("")
    A("Scoring is per field with partial credit, so fill in every field with your best value even if you are unsure of some. Do not output anything except the JSON object.")
    return "\n".join(lines) + "\n"


def make_schema(sc):
    D = sc["depots"]
    nn = {"type": "integer", "minimum": 0}
    ck_depot = {"type": "object",
                "properties": {"on_hand": nn, "backorders": nn, "in_transit": nn},
                "required": ["on_hand", "backorders", "in_transit"]}
    return {
        "type": "object",
        "properties": {
            "checkpoints": {
                "type": "object",
                "properties": {str(c): {"type": "object", "properties": {d: ck_depot for d in D},
                                        "required": D} for c in sc["checkpoints"]},
                "required": [str(c) for c in sc["checkpoints"]],
            },
            "depots": {
                "type": "object",
                "properties": {d: {"type": "object",
                                   "properties": {"total_expired": nn, "stockout_days": nn, "units_received": nn},
                                   "required": ["total_expired", "stockout_days", "units_received"]} for d in D},
                "required": D,
            },
            "central": {"type": "object",
                        "properties": {"final_on_hand": nn, "total_cancelled": nn, "total_expired": nn},
                        "required": ["final_on_hand", "total_cancelled", "total_expired"]},
            "fill_rate": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["checkpoints", "depots", "central", "fill_rate"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--difficulty", choices=list(DIFFICULTY), default="hard")
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()

    sc, sim, key, checks = build(args.seed, args.difficulty)
    ex_sim = Sim(EXAMPLE, trace=True)
    ex_key = ex_sim.run()
    prompt = render_prompt(sc, EXAMPLE, ex_key, ex_sim.trace)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "prompt.txt"), "w") as f:
        f.write(prompt)
    with open(os.path.join(args.out, "key.json"), "w") as f:
        json.dump(key, f, indent=1)
    with open(os.path.join(args.out, "schema.json"), "w") as f:
        json.dump(make_schema(sc), f, indent=1)
    with open(os.path.join(args.out, "scenario.json"), "w") as f:
        json.dump({"seed": args.seed, "difficulty": args.difficulty, **sc}, f, indent=1)
    with open(os.path.join(args.out, "trace.txt"), "w") as f:
        f.write("\n".join(sim.trace) + "\n")
    ev = {k: (sorted(v) if isinstance(v, set) else v) for k, v in sim.ev.items()}
    print(json.dumps({"seed": args.seed, "difficulty": args.difficulty, "subseed": sc["_subseed"],
                      "prompt_bytes": len(prompt.encode()), "events": ev,
                      "checks": checks, "key_summary": {"fill_rate": key["fill_rate"],
                                                        "central": key["central"],
                                                        "depots": key["depots"]}}, indent=1))


if __name__ == "__main__":
    main()
