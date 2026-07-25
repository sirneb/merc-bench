"""Independent brute-force oracle for RRULE-lite: day-by-day membership scan.

Written independently of ref_d.py (different algorithm) so agreement between
the two is strong evidence both encode the spec correctly.
"""
import calendar
from datetime import date, timedelta

DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _monday(d):
    return d - timedelta(days=d.weekday())


def _matches(d, rule, dtstart):
    freq = rule["FREQ"]
    interval = rule.get("INTERVAL", 1)
    bymonth = rule.get("BYMONTH")
    bymonthday = rule.get("BYMONTHDAY")
    byday = rule.get("BYDAY")
    if bymonth and d.month not in bymonth:
        return False
    if freq == "DAILY":
        return (d - dtstart).days % interval == 0
    if freq == "WEEKLY":
        weeks = (_monday(d) - _monday(dtstart)).days // 7
        if weeks % interval != 0:
            return False
        wanted = ([DAYS[t] for t in byday] if byday
                  else [dtstart.weekday()])
        return d.weekday() in wanted
    # MONTHLY
    mdelta = (d.year - dtstart.year) * 12 + (d.month - dtstart.month)
    if mdelta % interval != 0:
        return False
    ndays = calendar.monthrange(d.year, d.month)[1]
    if byday:
        for tok in byday:
            n, wd = int(tok[:-2]), DAYS[tok[-2:]]
            if d.weekday() != wd:
                continue
            same_wd = [x for x in range(1, ndays + 1)
                       if date(d.year, d.month, x).weekday() == wd]
            idx = same_wd.index(d.day)
            if n > 0 and idx == n - 1:
                return True
            if n < 0 and idx == len(same_wd) + n:
                return True
        return False
    mdays = bymonthday if bymonthday else [dtstart.day]
    for md in mdays:
        if md > 0 and d.day == md:
            return True
        if md < 0 and d.day == ndays + 1 + md:
            return True
    return False


def expand(rule, dtstart, limit):
    count = rule.get("COUNT")
    until = rule.get("UNTIL")
    n_target = limit if count is None else min(limit, count)
    out = []
    d = dtstart
    horizon = dtstart + timedelta(days=366 * 40)
    while len(out) < n_target and d <= horizon:
        if until and d > until:
            break
        if _matches(d, rule, dtstart):
            out.append(d)
        d += timedelta(days=1)
    return out
