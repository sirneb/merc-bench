"""Reference RRULE-lite implementation (grading oracle A)."""
import calendar
from datetime import date, timedelta

DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _parse_monthly_byday(tok):
    if not isinstance(tok, str) or len(tok) < 3 or tok[-2:] not in DAYS:
        raise ValueError(f"bad BYDAY token {tok!r}")
    try:
        n = int(tok[:-2])
    except Exception:
        raise ValueError(f"bad BYDAY ordinal in {tok!r}")
    if n == 0 or abs(n) > 5:
        raise ValueError(f"BYDAY ordinal out of range in {tok!r}")
    return n, DAYS[tok[-2:]]


def _nth_weekday(year, month, weekday, n):
    ndays = calendar.monthrange(year, month)[1]
    ds = [d for d in range(1, ndays + 1)
          if date(year, month, d).weekday() == weekday]
    if n > 0:
        return date(year, month, ds[n - 1]) if n <= len(ds) else None
    return date(year, month, ds[n]) if -n <= len(ds) else None


def _month_days(year, month, mdays):
    ndays = calendar.monthrange(year, month)[1]
    out = []
    for md in mdays:
        if md > 0 and md <= ndays:
            out.append(date(year, month, md))
        elif md < 0 and ndays + 1 + md >= 1:
            out.append(date(year, month, ndays + 1 + md))
    return out


def expand(rule, dtstart, limit):
    freq = rule.get("FREQ")
    interval = rule.get("INTERVAL", 1)
    count = rule.get("COUNT")
    until = rule.get("UNTIL")
    bymonth = rule.get("BYMONTH")
    bymonthday = rule.get("BYMONTHDAY")
    byday = rule.get("BYDAY")

    if freq not in ("DAILY", "WEEKLY", "MONTHLY"):
        raise ValueError("unknown FREQ")
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        raise ValueError("bad INTERVAL")
    if bymonthday is not None:
        for md in bymonthday:
            if not (1 <= md <= 31 or -31 <= md <= -1):
                raise ValueError("bad BYMONTHDAY")
    if freq == "MONTHLY" and bymonthday and byday:
        raise ValueError("BYMONTHDAY and BYDAY are exclusive for MONTHLY")
    if freq == "WEEKLY" and byday:
        for tok in byday:
            if tok not in DAYS:
                raise ValueError(f"bad WEEKLY BYDAY token {tok!r}")
    if freq == "MONTHLY" and byday:
        for tok in byday:
            _parse_monthly_byday(tok)

    n_target = limit if count is None else min(limit, count)
    out = []

    if freq == "DAILY":
        cur = dtstart
        for _ in range(200000):
            if len(out) >= n_target:
                break
            if until and cur > until:
                break
            if not bymonth or cur.month in bymonth:
                out.append(cur)
            cur += timedelta(days=interval)

    elif freq == "WEEKLY":
        days = sorted(DAYS[t] for t in (byday or [CODES[dtstart.weekday()]]))
        anchor = dtstart - timedelta(days=dtstart.weekday())
        stop = False
        for w in range(20000):
            if len(out) >= n_target or stop:
                break
            week_start = anchor + timedelta(weeks=w * interval)
            for wd in days:
                d = week_start + timedelta(days=wd)
                if d < dtstart:
                    continue
                if until and d > until:
                    stop = True
                    break
                if bymonth and d.month not in bymonth:
                    continue
                out.append(d)
                if len(out) >= n_target:
                    break

    else:  # MONTHLY
        y0, m0 = dtstart.year, dtstart.month
        for k in range(12000):
            if len(out) >= n_target:
                break
            mm = (m0 - 1) + k * interval
            yy, mo = y0 + mm // 12, mm % 12 + 1
            if until and date(yy, mo, 1) > until:
                break
            if bymonth and mo not in bymonth:
                continue
            if byday:
                cands = []
                for tok in byday:
                    n, wd = _parse_monthly_byday(tok)
                    d = _nth_weekday(yy, mo, wd, n)
                    if d:
                        cands.append(d)
            elif bymonthday:
                cands = _month_days(yy, mo, bymonthday)
            else:
                cands = _month_days(yy, mo, [dtstart.day])
            done = False
            for d in sorted(set(cands)):
                if d < dtstart:
                    continue
                if until and d > until:
                    done = True
                    break
                out.append(d)
                if len(out) >= n_target:
                    break
            if done:
                break

    return out
