#!/usr/bin/env python3
"""Independent oracle for quantitative-2.

Re-derives the full answer key from prompt.txt ALONE (zone table sentences +
roster rows) using a completely different implementation from generator.py:

  * every fictional zone is encoded as a POSIX TZ string and evaluated with
    dateutil.tz.tzstr (a library implementation the generator never touches);
  * the decree zone is two tzstr objects split at the decree instant;
  * local -> UTC uses candidate-offset validation through tz.fromutc plus the
    stated policy (repeated -> earlier instant, skipped -> shift forward);
  * calendar arithmetic is datetime/timedelta, not integer day counts.

Usage:  python oracle.py [DIR]      (DIR holds prompt.txt and key.json)
Exit status 0 and "ORACLE OK" when every leg, duty period, violation and the
home-base total agree with key.json; otherwise prints the differences.

Requires python-dateutil (pip install python-dateutil).
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

try:
    from dateutil import tz
except ImportError:                                  # pragma: no cover
    sys.stderr.write("oracle.py needs python-dateutil: pip install "
                     "python-dateutil\n")
    sys.exit(2)

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}
NTH = {"first": 1, "second": 2, "third": 3, "fourth": 4, "last": 5}
# POSIX day numbers: 0 = Sunday
WD = {"Sunday": 0, "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
      "Friday": 5, "Saturday": 6}
UTC = timezone.utc

ZONE_RE = re.compile(r"^([A-Z]{3})\s+(.+?)\s+UTC([+-])(\d{1,2}):(\d{2})\s+(.*)$")
RULE_RE = re.compile(
    r"Clocks go forward (\d+) min at (\d{2}):(\d{2}) on the (\w+) (\w+) of (\w+) "
    r"and back (\d+) min at (\d{2}):(\d{2}) on the (\w+) (\w+) of (\w+)\.")
DECREE_RE = re.compile(
    r"DECREE: .*?At (\d{2}):(\d{2}) on (\w+) (\d{1,2}) (\w+) (\d{4}) clocks are "
    r"set back (\d+) min")
LEG_RE = re.compile(
    r"^(L\d+)\s+([A-Z]{3})\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+([A-Z]{3})\s+(\d+)$")
HOME_RE = re.compile(r"Home base: ([A-Z]{3})\.")


def posix_off(td):
    """timedelta east-of-UTC -> POSIX offset field (sign inverted)."""
    secs = int(td.total_seconds())
    sign = "-" if secs > 0 else ""
    secs = abs(secs)
    return "%s%d:%02d" % (sign, secs // 3600, (secs % 3600) // 60)


def rule_field(mon, nth, wd, hh, mm, negative_std_time):
    """POSIX rule field. Normally Mm.n.d/hh:mm (dateutil computes the nth
    weekday itself). dateutil has a known defect when an END-of-DST time
    expressed in standard time is negative (e.g. 'back at 00:00'): it applies
    the negative offset before the weekday jump and lands one day late. For
    those rules encode the concrete day-of-year (Jn, computed with the
    calendar module) so the library is only asked to handle the offset."""
    if not negative_std_time:
        return "M%d.%d.%d/%s:%s" % (MONTHS[mon], NTH[nth], WD[wd], hh, mm)
    import calendar
    pywd = (WD[wd] - 1) % 7                      # Monday=0 convention
    m = MONTHS[mon]
    days = [d for d in range(1, calendar.monthrange(2027, m)[1] + 1)
            if calendar.weekday(2027, m, d) == pywd]
    day = days[-1] if NTH[nth] == 5 else days[NTH[nth] - 1]
    doy = datetime(2027, m, day).timetuple().tm_yday
    return "J%d/%s:%s" % (doy, hh, mm)


class OZone:
    def __init__(self, code, std, rule_txt):
        self.code = code
        self.std = std
        self.tz_a = self.tz_b = None
        self.split = None
        self.dst = std
        m = RULE_RE.search(rule_txt)
        if not m:
            assert "No daylight time" in rule_txt, rule_txt
            self.tz_a = tz.tzstr("%s%s" % (code, posix_off(std)))
            return
        (f_shift, fh, fm, f_nth, f_wd, f_mon, b_shift, bh, bm, b_nth, b_wd,
         b_mon) = m.groups()
        assert f_shift == b_shift
        self.dst = std + timedelta(minutes=int(f_shift))
        s = "%s%s%sD%s,%s,%s" % (
            code, posix_off(std), code[:2], posix_off(self.dst),
            rule_field(f_mon, f_nth, f_wd, fh, fm, False),
            rule_field(b_mon, b_nth, b_wd, bh, bm,
                       int(bh) * 60 + int(bm) < int(f_shift)))
        self.tz_a = tz.tzstr(s)
        d = DECREE_RE.search(rule_txt)
        if d:
            hh, mm, wdname, day, mon, year, shift = d.groups()
            assert int(shift) == int(f_shift)
            wall_dt = datetime(int(year), MONTHS[mon], int(day), int(hh),
                               int(mm))
            # sanity: the stated weekday matches the date
            assert wall_dt.strftime("%A") == wdname, (wall_dt, wdname)
            # the decree instant is expressed in daylight time (clocks go back)
            self.split = (wall_dt - self.dst).replace(tzinfo=UTC)
            assert self.tz_a.utcoffset(wall_dt - timedelta(hours=6)) == self.dst
            self.tz_b = tz.tzstr("%s%s" % (code, posix_off(std)))

    def utc_to_local(self, u):
        """u: aware UTC datetime -> naive local wall time."""
        t = self.tz_a if (self.split is None or u < self.split) else self.tz_b
        return u.astimezone(t).replace(tzinfo=None)

    def local_to_utc(self, w):
        """Naive wall time -> aware UTC per the stated policy."""
        def cands(wall):
            out = []
            for off in sorted({self.std, self.dst}, key=lambda x: x):
                u = (wall - off).replace(tzinfo=UTC)
                if self.utc_to_local(u) == wall:
                    out.append(u)
            return out
        c = cands(w)
        if len(c) >= 1:
            return min(c)                      # repeated -> first occurrence
        gap = self.dst - self.std
        c = cands(w + gap)                     # skipped -> forward by the gap
        assert len(c) == 1, (self.code, w)
        return c[0]


def parse_prompt(text):
    zones, legs, home = {}, [], None
    for line in text.splitlines():
        m = ZONE_RE.match(line)
        if m and not line.startswith("ZONE"):
            code, _name, sgn, hh, mm = m.groups()[:5]
            std = timedelta(hours=int(hh), minutes=int(mm))
            if sgn == "-":
                std = -std
            zones[code] = OZone(code, std, m.group(6))
            continue
        m = LEG_RE.match(line)
        if m:
            legs.append(m.groups())
            continue
        m = HOME_RE.search(line)
        if m:
            home = m.group(1)
    assert zones and legs and home
    return zones, legs, home


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def compute(text):
    zones, rows, home = parse_prompt(text)
    legs, duties, viol = [], [], []
    sept = 0
    prev_arr = None
    cur = None
    for lid, dz, dep_local, az, block in rows:
        w = datetime.strptime(dep_local, "%Y-%m-%d %H:%M")
        dep_u = zones[dz].local_to_utc(w)
        arr_u = dep_u + timedelta(minutes=int(block))
        arr_l = zones[az].utc_to_local(arr_u)
        legs.append(dict(id=lid, arr_utc=fmt(arr_u.replace(tzinfo=None)),
                         arr_local=fmt(arr_l)))
        home_l = zones[home].utc_to_local(arr_u)
        if home_l < datetime(2027, 10, 1):
            sept += int(block)
        if prev_arr is None or (dep_u - prev_arr) >= timedelta(minutes=600):
            if cur is not None:
                cur["end"] = prev_arr + timedelta(minutes=30)
                duties.append(cur)
            cur = dict(start=dep_u - timedelta(minutes=60))
        prev_arr = arr_u
    cur["end"] = prev_arr + timedelta(minutes=30)
    duties.append(cur)
    out_d = []
    for i, d in enumerate(duties, 1):
        mins = int((d["end"] - d["start"]).total_seconds() // 60)
        out_d.append(dict(id="D%d" % i, start_utc=fmt(d["start"]),
                          end_utc=fmt(d["end"]), minutes=mins))
        if mins > 840:
            viol.append("D%d" % i)
    return dict(legs=legs, duty_periods=out_d, violations=viol,
                home_base_month_minutes=sept)


def compare(mine, key):
    diffs = []
    for a, b in zip(mine["legs"], key["legs"]):
        for f in ("arr_utc", "arr_local"):
            if a[f] != b[f]:
                diffs.append("%s %s: oracle %s key %s" % (a["id"], f, a[f], b[f]))
    if len(mine["legs"]) != len(key["legs"]):
        diffs.append("leg count %d vs %d" % (len(mine["legs"]), len(key["legs"])))
    if key.get("config", {}).get("chain", True):
        kd = [(d["start_utc"], d["end_utc"], d["minutes"])
              for d in key["duty_periods"]]
        md = [(d["start_utc"], d["end_utc"], d["minutes"])
              for d in mine["duty_periods"]]
        if kd != md:
            diffs.append("duty periods differ:\n  oracle %s\n  key    %s" % (md, kd))
        if mine["violations"] != key["violations"]:
            diffs.append("violations %s vs %s" % (mine["violations"],
                                                  key["violations"]))
    if mine["home_base_month_minutes"] != key["home_base_month_minutes"]:
        diffs.append("home_base_month_minutes %d vs %d" % (
            mine["home_base_month_minutes"], key["home_base_month_minutes"]))
    return diffs


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.abspath(__file__))
    text = open(os.path.join(d, "prompt.txt")).read()
    key = json.load(open(os.path.join(d, "key.json")))
    mine = compute(text)
    diffs = compare(mine, key)
    if diffs:
        print("ORACLE MISMATCH (%d):" % len(diffs))
        for x in diffs:
            print("  " + x)
        sys.exit(1)
    print("ORACLE OK: %d legs, %d duty periods, violations %s, "
          "home_base_month_minutes %d all agree with key.json" % (
              len(mine["legs"]), len(mine["duty_periods"]), mine["violations"],
              mine["home_base_month_minutes"]))


if __name__ == "__main__":
    main()
