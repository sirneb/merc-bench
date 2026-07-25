# Task D spec: recurrence rule expander (RRULE-lite)

Implement a Python module (standard library only) exposing one function:

    expand(rule: dict, dtstart: datetime.date, limit: int) -> list[datetime.date]

It returns, in ascending order, the first occurrences of the recurrence
described by `rule`, starting at `dtstart`.

## Rule keys

- `FREQ` (required): `"DAILY"`, `"WEEKLY"`, or `"MONTHLY"`.
- `INTERVAL` (optional, default 1): int >= 1. Cadence multiplier: every
  INTERVAL days / weeks / months. The cadence is anchored at `dtstart`:
  for DAILY, candidate days are dtstart, dtstart+INTERVAL, ...; for
  WEEKLY, active weeks are dtstart's week, then every INTERVAL-th week
  after it (weeks start on Monday); for MONTHLY, active months are
  dtstart's month, then every INTERVAL-th month after it.
- `COUNT` (optional): int >= 1, maximum number of occurrences overall.
- `UNTIL` (optional): datetime.date, last allowed date (INCLUSIVE).
- `BYMONTH` (optional): list of ints 1..12. Occurrences whose month is
  not listed are filtered out (they do NOT consume COUNT).
- `BYMONTHDAY` (optional, MONTHLY only): list of ints, each in 1..31 or
  -31..-1. Positive n = the n-th day of the month; negative n = counted
  from the end (-1 = last day of the month, -2 = second-to-last, ...).
  If the resulting day does not exist in a given month (e.g. day 31 in
  April, day 29 in a non-leap February, -31 in a 30-day month), that
  month simply contributes no occurrence for that entry — NO clamping
  to the nearest valid day.
- `BYDAY` (optional): list of strings.
  - For WEEKLY: plain two-letter weekday codes `"MO","TU","WE","TH",
    "FR","SA","SU"`. Occurrences fall on those weekdays of each active
    week, in chronological order.
  - For MONTHLY: ordinal weekday tokens like `"2TU"` (second Tuesday of
    the month) or `"-1FR"` (last Friday). The ordinal part is required
    and must be a non-zero integer in -5..5. If the requested ordinal
    weekday does not exist in a month (e.g. `"5MO"` in a month with only
    four Mondays), that month contributes no occurrence for that entry.

## Semantics

- The result contains only dates `>= dtstart` that match the pattern.
  `dtstart` itself is included only if it matches the pattern.
- For WEEKLY with no BYDAY, the weekday of `dtstart` is used.
  For MONTHLY with no BYDAY and no BYMONTHDAY, the day-of-month of
  `dtstart` is used (months lacking that day are skipped, no clamping).
- Multiple BYDAY / BYMONTHDAY entries in the same period produce
  multiple occurrences, in ascending date order. If two entries resolve
  to the same date (e.g. BYMONTHDAY [5, -26] in a 30-day month), that
  date appears only once.
- Stop conditions: the result has at most `limit` dates; at most `COUNT`
  dates if COUNT is given; and contains no date after `UNTIL` if UNTIL
  is given. COUNT counts occurrences that survive all filters.
- MONTHLY may not combine BYMONTHDAY and BYDAY (raise ValueError).

## Errors

Raise `ValueError` for: unknown FREQ; INTERVAL < 1 (or non-int);
malformed BYDAY tokens (unknown weekday code; for MONTHLY a missing,
zero, or out-of-range ordinal; for WEEKLY an ordinal present at all);
BYMONTHDAY values outside 1..31 / -31..-1; combining BYMONTHDAY and
BYDAY in MONTHLY.

## Notes

- Dates only — no times or timezones.
- You may assume `limit` is a small positive int (<= 100).
- The module must define `expand`; you may add helpers.
