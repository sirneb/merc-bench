# Crew roster across fictional DST (Q2, candidate "quantitative-2")

40 independently graded arrival conversions across 12 fictional time zones (:30/:45 offsets, a 30-minute shift, southern-style rules, a mid-roster decree, skipped and repeated hours), chained into 10 duty periods, no tools.

## What it tests and why

Nothing in `tasks/` touches calendar or time-zone arithmetic, and it is a documented
frontier blind spot: counting "the second Sunday of October" from a calendar anchor,
keeping :45 offsets straight across a midnight, knowing which offset is in force at the
*arrival* instant when the zone changes mid-flight, and resolving departures printed
inside a skipped or repeated hour. Every zone here is fictional and fully specified in
the prompt, so memorised IANA facts are useless and actively misleading (a model that
"knows" DST ends at 02:00 on the first Sunday of November will misapply the
southern-style zones, the 30-minute zone and the zone whose government abolished
daylight time by decree three weeks before the scheduled change).

The roster is built so that every one of its 10 duty periods is anchored on a trap:
eight real transitions (one per DST zone), the *phantom* transition the decree
cancelled, and the September/October month boundary in home-base local time. Each
anchored leg lands within +/-100 min of its anchor and the next leg departs from that
zone shortly after, so roughly 12 of the 40 legs interact with an offset change; three
departures are printed inside a repeated or non-existent hour and must be resolved by
the stated policy. Duty lengths hug the 14-hour limit (several within +/-40 min of
840), so a single one-hour slip flips a violation.

Why it should separate models and effort levels: each leg is an independent exact
computation (a smooth 0-40 gradient), the correct method is a disciplined UTC round
trip that low-effort runs skip in favour of adding offsets naively, and the errors are
self-detectable (re-derive the transition date by counting weekdays; check that
arrival minus departure equals block). Systematic wrong strategies score well below
full marks on the shipped seed (computed with the engine, not a model):

| strategy | score /60 | near-transition legs | other legs |
|---|---|---|---|
| ignore DST entirely (standard offsets) | 34.4 | 4.5/12 | 19.5/28 |
| assume DST on for the whole window | 38.5 | 7.5/12 | 15.5/28 |
| treat southern-style zones as northern | 40.9 | 8.5/12 | 16.5/28 |
| correct rules but ignore the decree | 51.5 | 12/12 | 20.5/28 |
| every nth-Sunday one week late | 54.0 | 8.5/12 | 26/28 |
| correct rules, wrong skipped/repeated policy | 57.0 | 9/12 | 28/28 |

`detail.legs.near_transition` vs `detail.legs.other` in every grade lets the report
verify that the transition knob is what bites.

Expected (proposal): Haiku 20-30, Sonnet 30-45, Opus 5 / Opus 5.5 / Fable 5.1 spread
38-56 with a visible effort slope; 60/60 replicated by nobody.

## Files

- `generator.py` — deterministic given `--seed` and `--difficulty` (easy / medium /
  **hard** (shipped) / extreme) with knobs `--legs N`, `--transition-proximity F`
  (fraction of duty periods anchored on a transition), `--odd-offsets/--no-odd-offsets`,
  `--decree/--no-decree`, `--chain/--no-chain` (duty section), `--ambiguity N`
  (departures inside skipped/repeated hours). Writes `prompt.txt`, `key.json`,
  `schema.json`. Shipped: `--seed 20270914 --difficulty hard` (40 legs, 10 duties,
  4 violations, 12 transition-proximate legs, 3 engineered departures, 9.5 KB prompt).
- `oracle.py` — independent second implementation: parses `prompt.txt` (not the key),
  encodes every zone as a POSIX TZ string evaluated by `dateutil.tz.tzstr`, splits the
  decree zone into two tzstr objects at the decree instant, and resolves local times by
  candidate-offset validation through the library's `fromutc`. Must print `ORACLE OK`.
  Needs `python-dateutil`. Note: dateutil misplaces an end-of-DST rule whose time is
  smaller than the shift (e.g. "back at 00:00") by one day (it applies the negative
  standard-time offset before the weekday jump); the oracle encodes those rules as
  POSIX `Jn` day-of-year rules computed with the `calendar` module instead.
- `fuzz.py N` — generates N rosters across all presets/knobs and diffs engine vs oracle.
  2,000/2,000 agree, 0 unbuildable.
- `selftest.py` — key answer scores 60/60 through the CLI; controlled corruptions
  lose the expected points; tolerant parsing (ISO `T`, seconds, `Z`, `l7`, prose-wrapped
  JSON) still grades.
- `grade.py`, `schema.json`, `prompt.txt`, `key.json` — the task package proper.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. 60 points:

- **Legs, 40.** Per leg 1.0 when both `arr_local` and `arr_utc` are exact to the
  minute, 0.5 when exactly one is (separates "right instant, wrong rendering" from
  "wrong instant"). Datetimes parsed tolerantly; ids normalised (`L1`, `l01`).
- **Duty periods, 10.** Model periods are matched to key periods by nearest
  `start_utc` within 3 h (so one wrong split does not zero the rest); 1.0 when
  `minutes` is exact, 0.5 when within +/-60 min (one DST-hour slip). `minutes` is
  recomputed from start/end when missing.
- **Violations, 4.** 4 x Jaccard similarity between the model's set and the key's.
- **home_base_month_minutes, 6.** 6 exact, 3 within 1 %.

`detail` lists per-leg want/got with the leg's `near_transition` flag, per-duty
want/got, the violation sets, and the near-transition vs other-leg split. Ground truth
was generated and verified (oracle + fuzz) before any model ran.
