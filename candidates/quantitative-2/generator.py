#!/usr/bin/env python3
"""Generator for candidate task "quantitative-2":
Crew Roster Across Fictional DST (timezone and duty-time arithmetic).

Usage:
  python generator.py --seed 20270914 --difficulty hard [--out DIR]
  python generator.py --seed S --legs 60 --ambiguity 6 --transition-proximity 1.0

Writes prompt.txt, key.json and schema.json into --out (default: this directory).

Deterministic given (seed, difficulty, overrides). Ground truth is computed by a
hand-written rule engine below (integer minutes since epoch, nth-weekday
transitions, offset lookup by instant, explicit skipped/repeated-time policy).
oracle.py re-derives the key from prompt.txt with dateutil POSIX TZ strings and
shares no code with this file.
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
YEAR = 2027
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday"]
MONTH_NAMES = [None, "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
NTH_WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}
DAY_MIN = 1440

# ----------------------------------------------------------------------------
# Calendar primitives (integer arithmetic only; no datetime module)
# ----------------------------------------------------------------------------


def days_from_civil(y, m, d):
    """Days since 1970-01-01 (Howard Hinnant's algorithm)."""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    mp = (m + 9) % 12
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y + (m <= 2), m, d)


def weekday_of_days(days):
    """Monday=0 .. Sunday=6. 1970-01-01 was a Thursday (3)."""
    return (days + 3) % 7


def days_in_month(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30


def nth_weekday(y, m, wd, n):
    """Day-of-month of the n-th weekday `wd` (Mon=0) in month m; n=-1 = last."""
    if n > 0:
        first = weekday_of_days(days_from_civil(y, m, 1))
        return 1 + (wd - first) % 7 + 7 * (n - 1)
    dim = days_in_month(y, m)
    last = weekday_of_days(days_from_civil(y, m, dim))
    return dim - (last - wd) % 7


def wall(y, m, d, hh, mm):
    """Naive wall time expressed as minutes since epoch (as if UTC)."""
    return days_from_civil(y, m, d) * DAY_MIN + hh * 60 + mm


def fmt_minutes(t):
    days, rem = divmod(t, DAY_MIN)
    y, m, d = civil_from_days(days)
    return "%04d-%02d-%02d %02d:%02d" % (y, m, d, rem // 60, rem % 60)


def fmt_offset(off):
    sign = "+" if off >= 0 else "-"
    off = abs(off)
    return "UTC%s%d:%02d" % (sign, off // 60, off % 60)


def fmt_hm(mins):
    return "%02d:%02d" % (mins // 60, mins % 60)


# ----------------------------------------------------------------------------
# Zone rule engine
# ----------------------------------------------------------------------------


class Zone:
    """A fictional zone: standard offset (minutes east of UTC) plus optional DST.

    rule: None or dict(shift, start=(month, nth, wd, time_min), end=(month, nth,
    wd, time_min)). Transition times are the wall-clock time showing immediately
    before the change (POSIX semantics). decree: None or the wall-clock
    (y, m, d, time_min) at which DST is switched off for good (clocks go back).
    """

    def __init__(self, code, name, std, rule=None, decree=None):
        self.code, self.name, self.std = code, name, std
        self.rule, self.decree = rule, decree

    @property
    def shift(self):
        return self.rule["shift"] if self.rule else 0

    @property
    def dst_off(self):
        return self.std + self.shift

    def rule_transitions(self, year):
        """Scheduled transitions for a year (ignoring the decree)."""
        if not self.rule:
            return []
        out = []
        m, n, wd, t = self.rule["start"]
        out.append((wall(year, m, nth_weekday(year, m, wd, n), 0, 0) + t
                    - self.std, "start"))
        m, n, wd, t = self.rule["end"]
        out.append((wall(year, m, nth_weekday(year, m, wd, n), 0, 0) + t
                    - self.dst_off, "end"))
        return out

    def decree_instant(self):
        if not self.decree:
            return None
        y, m, d, t = self.decree
        return wall(y, m, d, 0, 0) + t - self.dst_off

    def transitions(self, years):
        tr = []
        for yr in years:
            tr += self.rule_transitions(yr)
        tr.sort()
        di = self.decree_instant()
        if di is not None:
            tr = [x for x in tr if x[0] < di] + [(di, "end")]
        return tr

    def is_dst_at(self, instant):
        if not self.rule:
            return False
        y = civil_from_days(instant // DAY_MIN)[0]
        tr = self.transitions((y - 1, y, y + 1))
        last = None
        for t, kind in tr:
            if t <= instant:
                last = kind
            else:
                if last is None:
                    # before every known transition: opposite of the first one
                    return kind == "end"
                break
        if last is None:
            return False
        return last == "start"

    def offset_at(self, instant):
        return self.dst_off if self.is_dst_at(instant) else self.std

    def to_local(self, instant):
        return instant + self.offset_at(instant)

    def from_local(self, local_wall):
        """Resolve a local wall time to an instant using the stated policy:
        repeated -> first occurrence (earlier instant); skipped -> shift forward
        by the size of the gap. Returns (instant, kind) with kind in
        {"normal", "repeated", "skipped"}."""
        cands = []
        for off in sorted({self.std, self.dst_off}):
            inst = local_wall - off
            if self.offset_at(inst) == off:
                cands.append(inst)
        if len(cands) == 1:
            return cands[0], "normal"
        if len(cands) == 2:
            return min(cands), "repeated"
        # skipped: move forward by the gap and resolve again
        shifted = local_wall + self.shift
        for off in sorted({self.std, self.dst_off}):
            inst = shifted - off
            if self.offset_at(inst) == off:
                return inst, "skipped"
        raise RuntimeError("unresolvable local time in %s" % self.code)

    def posix(self):
        """POSIX TZ string (for the record; oracle derives its own)."""
        def p(off):
            s = "-" if off > 0 else ""
            off = abs(off)
            return "%s%d:%02d" % (s, off // 60, off % 60)
        if not self.rule:
            return "%s%s" % (self.code, p(self.std))
        def r(x):
            m, n, wd, t = x
            return "M%d.%d.%d/%d:%02d" % (m, 5 if n == -1 else n, (wd + 1) % 7,
                                         t // 60, t % 60)
        return "%s%s%sD%s,%s,%s" % (self.code, p(self.std), self.code[:2],
                                     p(self.dst_off), r(self.rule["start"]),
                                     r(self.rule["end"]))


# ----------------------------------------------------------------------------
# Configuration / difficulty
# ----------------------------------------------------------------------------

PRESETS = {
    "easy": dict(legs=24, proximity=0.5, odd_offsets=False, decree=False,
                 chain=True, ambiguity=0),
    "medium": dict(legs=32, proximity=0.75, odd_offsets=True, decree=False,
                   chain=True, ambiguity=1),
    "hard": dict(legs=40, proximity=1.0, odd_offsets=True, decree=True,
                 chain=True, ambiguity=3),
    "extreme": dict(legs=60, proximity=1.0, odd_offsets=True, decree=True,
                    chain=True, ambiguity=6),
}

ZONE_NAMES = [
    ("ARB", "Arbolen"), ("BEL", "Belmara"), ("CAS", "Cassiovar"),
    ("DOR", "Dorrindale"), ("ELM", "Elmhaven"), ("FAR", "Farrowgate"),
    ("GRW", "Greywick"), ("HAL", "Halvern"), ("ISK", "Iskarra"),
    ("JUR", "Jurelle"), ("KOV", "Kovaris"), ("LUM", "Lumenport"),
]

# window in which every transition (and the whole roster) must sit
WIN_START = wall(YEAR, 9, 4, 0, 0)
WIN_END = wall(YEAR, 11, 1, 0, 0)
MIN_SPACING = 40 * 60        # between anchors (minutes)
SUN, SAT, FRI = 6, 5, 4


def nth_for_day(r, y, m, day):
    """Rule wording for a concrete date: 1..4 or -1 ('last')."""
    n = (day - 1) // 7 + 1
    if n == 5:
        return -1
    if n == 4 and day + 7 > days_in_month(y, m):
        return r.choice([4, -1])
    return n


def build_zones(rng, cfg):
    """Choose 12 zones (8 DST roles + 4 fixed) whose in-window transitions,
    plus the month-boundary and phantom anchors, are pairwise >= MIN_SPACING
    apart. Constructive: transitions are placed on concrete weekend dates and
    the nth-weekday wording is derived from the date."""
    odd = cfg["odd_offsets"]
    names = ZONE_NAMES[:]
    rng.shuffle(names)
    tpool = [0, 60, 120, 120, 150, 180]
    first_day = WIN_START // DAY_MIN + 1
    last_day = WIN_END // DAY_MIN - 2
    for attempt in range(2000):
        r = random.Random(rng.random())
        used = set()

        def pick(pool):
            pool = [x for x in pool if x not in used]
            v = r.choice(pool)
            used.add(v)
            return v

        specs = []
        # role: (std offset pool, shift, hemisphere, weekday choices)
        specs.append(("HOME", pick([345, 330, 585] if odd else [300, 360, 600]),
                      60, "N", [SUN]))
        specs.append(("DATELINE", pick([825, 780, 840] if odd else [780, 840]),
                      60, "S", [SUN]))
        specs.append(("HALF", pick([510, 180, 630] if odd else [180, 480]),
                      30 if odd else 60, r.choice("NS"), [SUN, SAT]))
        specs.append(("DECREE", pick([-420, -360, -300, -480]), 60, "N", [SUN]))
        specs.append(("NEGHALF", pick([-210, -150, -570] if odd
                                      else [-180, -120, -540]), 60, "N", [SUN]))
        specs.append(("SAT", pick([120, 180, -240]), 60, r.choice("NS"),
                      [SAT, FRI]))
        specs.append(("NORTH", pick([60, 120, -60]), 60, "N", [SUN]))
        specs.append(("SOUTH", pick([-600, 660, 600, -180]), 60, "S", [SUN]))
        fixed_pool = [0, 270, -570, 720, 540, -420, 420, -180, 180, 60]
        if not odd:
            fixed_pool = [x for x in fixed_pool if x % 60 == 0]
        fixed = [pick(fixed_pool) for _ in range(4)]

        placed = []          # anchor instants

        def spaced(inst):
            return (WIN_START + 12 * 60 <= inst <= WIN_END - 36 * 60 and
                    all(abs(inst - p) >= MIN_SPACING for p in placed))

        def out_rule(wd):
            return (r.choice([3, 4]), r.choice([1, 2, 3, -1]), wd,
                    r.choice(tpool))

        zones, anchors, roles = [], [], {}
        ok = True
        order = list(range(len(specs)))
        order.remove(0)
        r.shuffle(order)
        for i in [0] + order:            # HOME first (boundary depends on it)
            role, std, shift, hemi, wds = specs[i]
            code, nm = names[i]
            roles[role] = code
            dst_off = std + shift
            z = None
            if role == "DECREE" and cfg["decree"]:
                for _t in range(60):
                    sched = r.choice([24, 31])
                    t_end = r.choice([60, 120, 120, 180])
                    phantom = wall(YEAR, 10, sched, 0, 0) + t_end - dst_off
                    dec_day = days_from_civil(YEAR, 10, sched) \
                        - 7 * r.choice([2, 3, 4])
                    dy, dm, dd = civil_from_days(dec_day)
                    t_dec = r.choice([60, 120, 180])
                    dec = dec_day * DAY_MIN + t_dec - dst_off
                    if (spaced(phantom) and spaced(dec)
                            and abs(phantom - dec) >= MIN_SPACING
                            and dec_day >= first_day):
                        end = (10, nth_for_day(r, YEAR, 10, sched), SUN, t_end)
                        z = Zone(code, nm + " Time", std,
                                 dict(shift=shift, start=out_rule(SUN), end=end),
                                 decree=(dy, dm, dd, t_dec))
                        placed += [phantom, dec]
                        anchors.append(dict(instant=phantom, zone=code,
                                            kind="phantom", shift=shift))
                        anchors.append(dict(instant=dec, zone=code, kind="end",
                                            shift=shift))
                        break
            else:
                for _t in range(80):
                    wd = r.choice(wds)
                    day = r.randint(first_day, last_day)
                    day += (wd - weekday_of_days(day)) % 7
                    if day > last_day:
                        continue
                    y, m, d = civil_from_days(day)
                    t = r.choice(tpool + ([165] if shift == 60 and odd else []))
                    if hemi == "N":                   # DST ends in window
                        inst = day * DAY_MIN + t - dst_off
                        rule = dict(shift=shift, start=out_rule(wd),
                                    end=(m, nth_for_day(r, y, m, d), wd, t))
                        kind = "end"
                    else:                             # DST starts in window
                        inst = day * DAY_MIN + t - std
                        rule = dict(shift=shift,
                                    start=(m, nth_for_day(r, y, m, d), wd, t),
                                    end=out_rule(wd))
                        kind = "start"
                    if not spaced(inst):
                        continue
                    z = Zone(code, nm + " Time", std, rule)
                    # sanity: engine agrees with the constructed instant
                    tr = [x for x in z.transitions((YEAR,))
                          if WIN_START <= x[0] < WIN_END]
                    if tr != [(inst, kind)]:
                        z = None
                        continue
                    placed.append(inst)
                    anchors.append(dict(instant=inst, zone=code, kind=kind,
                                        shift=shift))
                    break
            if z is None:
                ok = False
                break
            zones.append(z)
            if role == "HOME":
                b_inst, _ = z.from_local(wall(YEAR, 10, 1, 0, 0))
                if not spaced(b_inst):
                    ok = False
                    break
                placed.append(b_inst)
                anchors.append(dict(instant=b_inst, zone=None, kind="boundary",
                                    shift=0))
        if not ok:
            continue
        for j, std in enumerate(fixed):
            code, nm = names[8 + j]
            zones.append(Zone(code, nm + " Time", std))
        zones.sort(key=lambda z: z.code)
        return zones, anchors, roles
    raise RuntimeError("could not place anchors; try another seed")


# ----------------------------------------------------------------------------
# Roster builder
# ----------------------------------------------------------------------------


def split_sum(rng, total, parts, lo):
    """Random composition of `total` into `parts` integers each >= lo."""
    if total < parts * lo:
        return None
    cuts = sorted(rng.sample(range(1, total - parts * lo + parts), parts - 1)) \
        if parts > 1 else []
    vals, prev = [], 0
    for c in cuts + [total - parts * lo + parts]:
        vals.append(c - prev - 1 + lo)
        prev = c
    return vals


def duty_targets(rng, n):
    """Duty lengths (minutes) with ~35% violations and boundary-huggers."""
    n_viol = max(1, round(0.35 * n))
    t = []
    for i in range(n):
        if i < n_viol:
            t.append(rng.randint(845, 930) if i >= 2 else rng.randint(842, 875))
        elif i < n_viol + 2:
            t.append(rng.randint(800, 838))          # just under 14 h
        else:
            t.append(rng.randint(540, 790))
    rng.shuffle(t)
    return t


def build_duty(rng, zones_by_code, codes, anchor, n_legs, start_code,
               prev_end, target, amb):
    """Return list of leg dicts or None if constraints fail for this draw."""
    Z = anchor["zone"]
    kind = anchor["kind"]
    T = anchor["instant"]
    shift = anchor["shift"]
    if amb:
        k = rng.randint(1, n_legs - 1)
    else:
        k = rng.randint(1, n_legs)
    long_sit = rng.random() < 0.15 and n_legs >= 3
    turns = [rng.randint(40, 170) for _ in range(n_legs - 1)]
    if k < n_legs:
        turns[k - 1] = rng.randint(40, 110)      # keep leg k+1 near the anchor
    if long_sit:
        j = rng.randrange(n_legs - 1)
        if j != k - 1:
            turns[j] = rng.randint(300, 570)
    rem = target - 90 - sum(turns)
    blocks = split_sum(rng, rem, n_legs, 45)
    if blocks is None:
        return None
    # arrival zone of leg k is Z (or random for boundary/filler anchors)
    arr_zone_k = Z if Z else rng.choice([c for c in codes if c != start_code])
    zone = zones_by_code[arr_zone_k]
    dep, arr = [None] * n_legs, [None] * n_legs
    engineered_wall = {}
    if amb:
        r = rng.randint(5, shift - 5)
        if kind == "end":                # repeated hour: first occurrence
            dep[k] = T - shift + r
            # wall time printed = local of first occurrence
            engineered_wall[k] = ("repeated", zone.to_local(dep[k]))
        else:                            # skipped hour
            dep[k] = T + r
            # the non-existent wall time = (post-shift local) - shift
            engineered_wall[k] = ("skipped", zone.to_local(dep[k]) - shift)
        arr[k - 1] = dep[k] - turns[k - 1]
    else:
        delta = rng.randint(-100, 100)
        if kind == "boundary" and abs(delta) < 10:
            delta = 10 if delta >= 0 else -10
        if kind == "filler":
            delta = rng.randint(-600, 600)
        arr[k - 1] = T + delta
    i = k - 1
    dep[i] = arr[i] - blocks[i]
    for j in range(i - 1, -1, -1):
        arr[j] = dep[j + 1] - turns[j]
        dep[j] = arr[j] - blocks[j]
    for j in range(i + 1, n_legs):
        dep[j] = arr[j - 1] + turns[j - 1]
        arr[j] = dep[j] + blocks[j]
    if prev_end is not None and dep[0] - prev_end < 600:
        return None
    if dep[0] - 60 < WIN_START or arr[-1] + 30 > WIN_END:
        return None
    # zones along the chain
    dep_codes = [start_code]
    for j in range(1, n_legs):
        dep_codes.append(None)
    arr_codes = [None] * n_legs
    arr_codes[k - 1] = arr_zone_k
    bias = anchor.get("bias")
    for j in range(n_legs):
        if arr_codes[j] is None:
            pool = [c for c in codes if c != dep_codes[j]]
            if bias and bias in pool and rng.random() < 0.45:
                arr_codes[j] = bias        # visit the decree zone while it bites
            else:
                arr_codes[j] = rng.choice(pool)
        if j + 1 < n_legs:
            dep_codes[j + 1] = arr_codes[j]
    if dep_codes[k - 1] == arr_codes[k - 1]:
        return None
    legs = []
    for j in range(n_legs):
        dz = zones_by_code[dep_codes[j]]
        if j in engineered_wall:
            akind, w = engineered_wall[j]
        else:
            w = dz.to_local(dep[j])
            akind = "normal"
        # the printed wall time must resolve to the true instant under policy
        inst, rk = dz.from_local(w)
        if inst != dep[j]:
            return None
        if akind == "normal" and rk != "normal":
            return None       # accidental ambiguity: redraw
        if akind != "normal" and rk != akind:
            return None
        legs.append(dict(dep_zone=dep_codes[j], dep_wall=w, dep_utc=dep[j],
                         arr_zone=arr_codes[j], arr_utc=arr[j],
                         block=blocks[j], dep_kind=akind))
    return legs


def place_fillers(existing, n, rng):
    """Put n filler anchors into the largest free gaps, >= MIN_SPACING apart."""
    pts = sorted(existing)
    out = []
    for _ in range(n):
        bounds = [WIN_START + 18 * 60] + pts + [WIN_END - 36 * 60]
        gaps = [(b - a, a, b) for a, b in zip(bounds, bounds[1:])]
        g, a, b = max(gaps)
        if g < 2 * MIN_SPACING:
            raise RuntimeError("no room for filler duty; reduce --legs")
        x = rng.randint(a + MIN_SPACING, b - MIN_SPACING)
        out.append(x)
        pts = sorted(pts + [x])
    return out


def build_roster(rng, zones, anchors, roles, cfg):
    codes = [z.code for z in zones]
    zbc = {z.code: z for z in zones}
    n_legs = cfg["legs"]
    n_duties = max(1, round(n_legs / 4))
    sizes = [n_legs // n_duties] * n_duties
    for i in range(n_legs - sum(sizes)):
        sizes[i] += 1
    rng.shuffle(sizes)
    # choose anchors: boundary and decree/phantom first, then transitions
    n_anch = min(len(anchors), round(cfg["proximity"] * n_duties))
    pri = sorted(anchors, key=lambda a: (
        0 if a["kind"] == "boundary" else 1 if a["zone"] == roles.get("DECREE")
        and cfg["decree"] else 2, rng.random()))
    chosen = pri[:n_anch]
    fill = place_fillers([a["instant"] for a in chosen], n_duties - n_anch, rng)
    chosen += [dict(instant=x, zone=None, kind="filler", shift=0) for x in fill]
    chosen.sort(key=lambda a: a["instant"])
    # duties falling between the decree and the abolished transition are
    # steered through the decree zone so ignoring the decree costs points
    if cfg["decree"]:
        dz = roles["DECREE"]
        span = sorted(a["instant"] for a in anchors if a["zone"] == dz)
        if len(span) == 2:
            for a in chosen:
                if span[0] <= a["instant"] <= span[1] and a["zone"] != dz:
                    a["bias"] = dz
    # which duties carry an engineered skipped/repeated departure
    eligible = [i for i, a in enumerate(chosen) if a["kind"] in ("start", "end")
                and sizes[i] >= 2]
    rng.shuffle(eligible)
    amb_set = set(eligible[:cfg["ambiguity"]])
    targets = duty_targets(rng, n_duties)
    for attempt in range(400):
        r2 = random.Random(rng.random())
        duties = []
        prev_end = None
        start_code = roles["HOME"]
        ok = True
        for d, a in enumerate(chosen):
            legs = None
            tgt = targets[d]
            for tries in range(300):
                legs = build_duty(r2, zbc, codes, a, sizes[d], start_code,
                                  prev_end, tgt, d in amb_set)
                if legs:
                    break
            if not legs:
                ok = False
                break
            duties.append(legs)
            prev_end = legs[-1]["arr_utc"]
            start_code = legs[-1]["arr_zone"]
        if ok:
            return duties
    raise RuntimeError("could not build roster for this seed/config")


# ----------------------------------------------------------------------------
# Key computation
# ----------------------------------------------------------------------------


def compute_key(zones, duties, roles, cfg):
    zbc = {z.code: z for z in zones}
    home = zbc[roles["HOME"]]
    legs, duty_periods, violations = [], [], []
    month_minutes = 0
    n = 0
    for d, dl in enumerate(duties):
        start = dl[0]["dep_utc"] - 60
        end = dl[-1]["arr_utc"] + 30
        mins = end - start
        duty_periods.append(dict(id="D%d" % (d + 1), start_utc=fmt_minutes(start),
                                 end_utc=fmt_minutes(end), minutes=mins,
                                 leg_ids=[]))
        if mins > 840:
            violations.append("D%d" % (d + 1))
        for lg in dl:
            n += 1
            lid = "L%02d" % n
            duty_periods[-1]["leg_ids"].append(lid)
            az = zbc[lg["arr_zone"]]
            dz = zbc[lg["dep_zone"]]
            arr_local = az.to_local(lg["arr_utc"])
            home_arr = home.to_local(lg["arr_utc"])
            in_sep = civil_from_days(home_arr // DAY_MIN)[1] == 9
            if in_sep:
                month_minutes += lg["block"]
            # transition interaction flag (real transitions only)
            near = False
            for z in (dz, az):
                for t, _k in z.transitions((YEAR,)):
                    if lg["dep_utc"] - 120 <= t <= lg["arr_utc"] + 120:
                        near = True
            legs.append(dict(
                id=lid, dep_zone=lg["dep_zone"], dep_local=fmt_minutes(lg["dep_wall"]),
                dep_utc=fmt_minutes(lg["dep_utc"]), arr_zone=lg["arr_zone"],
                block=lg["block"], arr_local=fmt_minutes(arr_local),
                arr_utc=fmt_minutes(lg["arr_utc"]), dep_kind=lg["dep_kind"],
                near_transition=near, arr_in_home_september=in_sep,
                duty="D%d" % (d + 1)))
    return dict(legs=legs, duty_periods=duty_periods, violations=violations,
                home_base_month_minutes=month_minutes)


# ----------------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------------


def rule_sentence(z):
    if not z.rule:
        return "No daylight time (fixed offset all year)."
    s = z.rule["start"]
    e = z.rule["end"]
    txt = ("Clocks go forward %d min at %s on the %s %s of %s and back %d min "
           "at %s on the %s %s of %s." % (
               z.shift, fmt_hm(s[3]), NTH_WORDS[s[1]], WEEKDAY_NAMES[s[2]],
               MONTH_NAMES[s[0]], z.shift, fmt_hm(e[3]), NTH_WORDS[e[1]],
               WEEKDAY_NAMES[e[2]], MONTH_NAMES[e[0]]))
    if z.decree:
        y, m, d, t = z.decree
        wd = WEEKDAY_NAMES[weekday_of_days(days_from_civil(y, m, d))]
        txt += (" DECREE: daylight time is abolished this year. At %s on %s %d "
                "%s %d clocks are set back %d min to standard time, and the zone "
                "stays on standard time permanently from then on (the change "
                "scheduled for the %s %s of %s does NOT happen)." % (
                    fmt_hm(t), wd, d, MONTH_NAMES[m], y, z.shift,
                    NTH_WORDS[e[1]], WEEKDAY_NAMES[e[2]], MONTH_NAMES[e[0]]))
    return txt


def make_prompt(zones, key, roles, cfg):
    home = roles["HOME"]
    n_legs = len(key["legs"])
    sep1 = WEEKDAY_NAMES[weekday_of_days(days_from_civil(YEAR, 9, 1))]
    L = []
    L.append("IMPORTANT: Solve without any tools - no Bash, no Python, no code "
             "execution, no calculators, no files, no web. Work it out yourself.")
    L.append("")
    L.append("You are the crew-scheduling officer of a fictional airline. Every "
             "time zone below is FICTIONAL: their offsets and daylight-time rules "
             "are defined ONLY by this document. Real-world time-zone knowledge "
             "does not apply and will mislead you. Compute every answer from the "
             "rules and data given here.")
    L.append("")
    L.append("== CALENDAR ==")
    L.append("All dates are in %d, which is not a leap year. %d-09-01 is a %s. "
             "September has 30 days, October has 31 days. 'Second Sunday of "
             "October' means the second Sunday that occurs in October; 'last "
             "Sunday of October' means the final Sunday in October." % (
                 YEAR, YEAR, sep1))
    L.append("")
    L.append("== TIME ZONES ==")
    L.append("Offsets are relative to UTC: 'UTC+5:45' means local time = UTC + 5 h "
             "45 min; 'UTC-3:30' means local = UTC - 3 h 30 min. Where a zone has "
             "daylight time, the STANDARD offset is listed and daylight time ADDS "
             "the stated shift to it (e.g. standard UTC+5:45 with a 60-min shift "
             "is UTC+6:45 during daylight time). The time stated in each rule is "
             "the local wall-clock time showing immediately BEFORE the change: "
             "'forward 60 min at 02:00' means the clocks jump from 02:00 to 03:00 "
             "(02:00-02:59 does not exist that day); 'back 60 min at 02:00' "
             "means that at 02:00 daylight time the clocks return to 01:00 "
             "standard time (01:00-01:59 occurs twice that day). Northern-style "
             "zones go forward in March/April and back in September/October; "
             "southern-style zones do the opposite - read each rule literally.")
    L.append("")
    L.append("ZONE  NAME                STANDARD   DAYLIGHT RULE")
    for z in zones:
        L.append("%-5s %-19s %-10s %s" % (z.code, z.name, fmt_offset(z.std),
                                          rule_sentence(z)))
    L.append("")
    L.append("== POLICY FOR SKIPPED AND REPEATED LOCAL TIMES ==")
    L.append("Some scheduled DEPARTURE times fall inside a skipped or a repeated "
             "hour. Resolve them exactly like this:")
    L.append("  * Skipped (non-existent) time: move the wall-clock time FORWARD by "
             "the size of the gap, then convert with the new (post-change) "
             "offset. Example: if clocks jump from 02:00 to 03:00, a departure "
             "printed as 02:20 actually happens at 03:20 in the new offset - "
             "which is the same instant as 02:20 in the OLD offset.")
    L.append("  * Repeated (ambiguous) time: use the FIRST occurrence, i.e. the "
             "earlier instant (the one still in the pre-change offset).")
    L.append("ARRIVALS are never ambiguous: an arrival is a definite instant. Its "
             "local time is that instant converted with whichever offset is in "
             "force in the arrival zone AT THAT INSTANT (if the arrival zone "
             "changes offset while the aircraft is in the air, use the new "
             "offset).")
    L.append("")
    L.append("== WORKED EXAMPLE (an example zone, not in the table) ==")
    L.append("Zone XMP: standard UTC+2:30; clocks go forward 60 min at 02:00 on the "
             "first Sunday of April and back 60 min at 02:00 on the last Sunday "
             "of October. Zone FIX: UTC-4:00, no daylight time. Suppose 2027-10-31 "
             "is the last Sunday of October (it is).")
    L.append("  Leg X1: departs XMP 2027-10-31 01:30, arrives FIX, block 300 min.")
    L.append("    01:30 occurs twice in XMP that day (clocks go 02:00 -> 01:00). "
             "First occurrence = daylight offset UTC+3:30, so dep_utc = "
             "2027-10-30 22:00. arr_utc = 22:00 + 300 min = 2027-10-31 03:00. "
             "arr_local (FIX, UTC-4:00) = 2027-10-30 23:00.")
    L.append("  Leg X2: departs FIX 2027-04-03 20:20, arrives XMP, block 405 min.")
    L.append("    dep_utc = 2027-04-04 00:20. arr_utc = 2027-04-04 07:05. XMP goes "
             "forward at 02:00 local on Sunday 2027-04-04 (first Sunday of "
             "April); 02:00 standard = 2027-04-03 23:30 UTC, which is before "
             "the arrival, so daylight offset UTC+3:30 applies: arr_local = "
             "2027-04-04 10:35.")
    L.append("  Leg X3: departs XMP 2027-04-04 02:40 (a skipped time), arrives FIX, "
             "block 120 min.")
    L.append("    Move forward by the 60-min gap: 03:40 daylight (UTC+3:30) -> "
             "dep_utc = 2027-04-04 00:10. arr_utc = 02:10; arr_local (FIX) = "
             "2027-04-03 22:10.")
    L.append("")
    L.append("== ROSTER ==")
    L.append("Home base: %s. One crew flies all %d legs below, listed in "
             "chronological order. DEP_LOCAL is the scheduled departure in the "
             "LOCAL time of the departure zone on that date. BLOCK is the elapsed "
             "flight time in minutes from departure to arrival. Arrival = "
             "departure instant + block." % (home, n_legs))
    L.append("")
    L.append("ID   DEP  DEP_LOCAL          ARR  BLOCK")
    for lg in key["legs"]:
        L.append("%-4s %-4s %-18s %-4s %d" % (lg["id"], lg["dep_zone"],
                                              lg["dep_local"], lg["arr_zone"],
                                              lg["block"]))
    L.append("")
    L.append("== REQUIRED ANSWERS ==")
    L.append("1. For EVERY leg: arr_utc (arrival instant in UTC) and arr_local "
             "(arrival wall-clock time in the ARRIVAL zone). Format both as "
             "'YYYY-MM-DD HH:MM' (24-hour clock).")
    if cfg["chain"]:
        L.append("2. Duty periods. The first duty period begins 60 minutes before "
                 "the departure of L01. A leg belongs to the current duty period "
                 "unless the gap from the PREVIOUS leg's arrival instant to this "
                 "leg's departure instant is 600 minutes (10 h) or more; in that "
                 "case the current duty period ends 30 minutes after the "
                 "previous leg's arrival and a new duty period begins 60 minutes "
                 "before this leg's departure. The last duty period ends 30 "
                 "minutes after the arrival of the final leg. Number them D1, "
                 "D2, ... in order. For each report start_utc, end_utc "
                 "('YYYY-MM-DD HH:MM') and minutes = end - start in real elapsed "
                 "minutes (work in UTC; wall-clock changes never alter elapsed "
                 "time).")
        L.append("3. violations: the ids of every duty period whose minutes is "
                 "STRICTLY greater than 840 (14 h), in order; [] if none.")
        L.append("4. home_base_month_minutes: the sum of BLOCK minutes over all "
                 "legs whose arrival, expressed in %s local time (the home "
                 "base, applying its own daylight rule at the arrival instant), "
                 "falls in September %d - i.e. strictly before %d-10-01 00:00 %s "
                 "local. The arrival zone's own calendar date is irrelevant "
                 "here." % (home, YEAR, YEAR, home))
    else:
        L.append("2. home_base_month_minutes: the sum of BLOCK minutes over all "
                 "legs whose arrival, expressed in %s local time (the home "
                 "base, applying its own daylight rule at the arrival instant), "
                 "falls in September %d - i.e. strictly before %d-10-01 00:00 %s "
                 "local." % (home, YEAR, YEAR, home))
    L.append("")
    L.append("Hint on method: convert each departure to UTC with the offset in "
             "force at departure (after applying the skipped/repeated policy), "
             "add the block minutes, then convert to the arrival zone with the "
             "offset in force at the ARRIVAL instant. Check every transition "
             "date by counting weekdays from the calendar anchor above. Be "
             "careful with the date when an offset crosses midnight and with "
             "zones east of UTC+12.")
    L.append("")
    L.append("== OUTPUT FORMAT ==")
    L.append("Return ONLY a single JSON object - no prose, no markdown fences, no "
             "comments - with exactly this shape (all %d legs, in roster "
             "order):" % n_legs)
    ex = {"legs": [{"id": "L01", "arr_utc": "YYYY-MM-DD HH:MM",
                    "arr_local": "YYYY-MM-DD HH:MM"},
                   {"id": "L02", "arr_utc": "...", "arr_local": "..."}]}
    if cfg["chain"]:
        ex["duty_periods"] = [{"id": "D1", "start_utc": "YYYY-MM-DD HH:MM",
                               "end_utc": "YYYY-MM-DD HH:MM", "minutes": 0}]
        ex["violations"] = ["D1"]
    ex["home_base_month_minutes"] = 0
    L.append(json.dumps(ex, indent=1))
    L.append("Use integers for minutes. Do not add any other keys.")
    return "\n".join(L) + "\n"


def make_schema(cfg):
    dt = {"type": "string", "description": "YYYY-MM-DD HH:MM"}
    props = {
        "legs": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "arr_utc": dt, "arr_local": dt},
            "required": ["id", "arr_utc", "arr_local"]}},
        "home_base_month_minutes": {"type": "integer"},
    }
    req = ["legs", "home_base_month_minutes"]
    if cfg["chain"]:
        props["duty_periods"] = {"type": "array", "items": {
            "type": "object", "properties": {
                "id": {"type": "string"}, "start_utc": dt, "end_utc": dt,
                "minutes": {"type": "integer"}},
            "required": ["id", "start_utc", "end_utc", "minutes"]}}
        props["violations"] = {"type": "array", "items": {"type": "string"}}
        req = ["legs", "duty_periods", "violations", "home_base_month_minutes"]
    return {"type": "object", "properties": props, "required": req}


# ----------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20270914)
    ap.add_argument("--difficulty", choices=sorted(PRESETS), default="hard")
    ap.add_argument("--legs", type=int)
    ap.add_argument("--transition-proximity", type=float, dest="proximity")
    ap.add_argument("--odd-offsets", dest="odd_offsets", action="store_true",
                    default=None)
    ap.add_argument("--no-odd-offsets", dest="odd_offsets", action="store_false")
    ap.add_argument("--decree", dest="decree", action="store_true", default=None)
    ap.add_argument("--no-decree", dest="decree", action="store_false")
    ap.add_argument("--chain", dest="chain", action="store_true", default=None)
    ap.add_argument("--no-chain", dest="chain", action="store_false")
    ap.add_argument("--ambiguity", type=int)
    ap.add_argument("--out", default=HERE)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    cfg = dict(PRESETS[a.difficulty])
    for k in ("legs", "proximity", "odd_offsets", "decree", "chain",
              "ambiguity"):
        if getattr(a, k) is not None:
            cfg[k] = getattr(a, k)
    cfg["seed"], cfg["difficulty"] = a.seed, a.difficulty
    rng = random.Random(a.seed)
    zones, anchors, roles = build_zones(rng, cfg)
    duties = build_roster(rng, zones, anchors, roles, cfg)
    key = compute_key(zones, duties, roles, cfg)
    # assertions: the traps are present
    near = sum(1 for lg in key["legs"] if lg["near_transition"])
    amb = sum(1 for lg in key["legs"] if lg["dep_kind"] != "normal")
    if cfg["proximity"] >= 1.0 and cfg["legs"] >= 40:
        assert near >= 8, "only %d transition-proximate legs" % near
    assert amb >= min(cfg["ambiguity"], 2) or cfg["ambiguity"] < 2, \
        "only %d skipped/repeated departures" % amb
    if cfg["chain"]:
        assert 1 <= len(key["violations"]) < len(key["duty_periods"])
    key.update(dict(
        config=cfg, home_base=roles["HOME"], roles=roles,
        zones=[dict(code=z.code, name=z.name, std=z.std, shift=z.shift,
                    rule=z.rule, decree=z.decree, posix=z.posix())
               for z in zones],
        anchors=[dict(a, instant=fmt_minutes(a["instant"])) for a in anchors],
        stats=dict(near_transition_legs=near, engineered_departures=amb,
                   violations=len(key["violations"]),
                   duty_periods=len(key["duty_periods"])),
    ))
    prompt = make_prompt(zones, key, roles, cfg)
    os.makedirs(a.out, exist_ok=True)
    open(os.path.join(a.out, "prompt.txt"), "w").write(prompt)
    json.dump(key, open(os.path.join(a.out, "key.json"), "w"), indent=1)
    json.dump(make_schema(cfg), open(os.path.join(a.out, "schema.json"), "w"),
              indent=1)
    if not a.quiet:
        print("wrote %s: %d legs, %d duty periods, %d violations, %d "
              "transition-proximate legs, %d skipped/repeated departures, "
              "prompt %d bytes" % (a.out, len(key["legs"]),
                                    len(key["duty_periods"]),
                                    len(key["violations"]), near, amb,
                                    len(prompt.encode())))


if __name__ == "__main__":
    main()
