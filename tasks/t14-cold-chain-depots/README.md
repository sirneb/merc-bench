# Cold-chain depot network (T14)

30-day, 5-node perishable-inventory simulation from a written operating manual: lead times, FEFO lot expiry with per-delivery shelf lives, backorders, (s, S) ordering and ratio-based central rationing with cancel-not-backlog; 60 points over 51 independently graded items.

**Revision note (post-critic).** This package was revised after the breaker and statistician
reports in `../TOURNAMENT.md`. The shipped scenario is a NEW one (seed 3, sub-seed 36) — the
pilot in `pilot/` was run on the previous scenario (seed 3, sub-seed 15, checkpoints 10/20/30)
under the previous grader and is kept only as history; its scores are not comparable to the
current key. Section "What changed" at the end lists every fix.

## What it tests and why

The model receives a ~14.8 KB operating manual, a day-0 state (lots with expiry days at
CENTRAL and four depots, plus one shipment already in transit), a nine-line supplier
delivery schedule (each delivery with its own expiry day) and a 30 x 4 demand table, and
must run the network day by day through five fixed phases (receive, expire, serve,
review/order, allocate/ship). It reports depot state at days 15/22/30, per-depot horizon
totals, CENTRAL totals, and the network's same-day served units, total demand and fill rate.

Nothing is recallable: policies, lead times, demands, lot expiries and delivery sizes
are generated. What separates configurations is doing exactly what the text says for
30 days across five coupled nodes, in the face of rules that contradict "how inventory
systems usually work":

- **phase order** — expire *before* serve, so stock arriving already expired counts as
  received *and* as waste (day 4 of the shipped scenario: CENTRAL's FEFO rule ships its
  oldest lot to B and D and both shipments die on arrival);
- **FEFO is not FIFO at CENTRAL** — supplier deliveries carry different remaining shelf
  lives, so a later delivery can expire before an earlier one (the day-15 bulk delivery
  of 284 units expires on day 21, before the day-8 and day-12 deliveries);
- **inventory position** includes in-transit and subtracts backorders, so a depot with
  open backorders may place no order at all;
- **FEFO across lots** at both depots and CENTRAL, with shipments carrying several lots;
- **rationing by shortfall ratio** (backorders / S, exact fractions) with alphabetical
  tie-break, processed sequentially against a dwindling CENTRAL balance;
- **cancel, never backlog** at CENTRAL; a depot simply re-orders the next day;
- **same-day fill rate** — backorders served late do not count, and stockout days are
  defined by end-of-phase-3 backorders, not by demand and not by empty shelves.

### The generator only accepts scenarios in which every one of these rules binds

`generator.passes()` rejects a sampled scenario unless (30-day thresholds; the counts
scale with the horizon):

| gate | shipped seed |
|---|---|
| >= 4 cancelled orders, >= 4 partial fills, >= 1 full cancellation, rationing binds on 4-12 of 30 days | 14 cancels on 7 days (4 partial, 10 full) |
| >= 4 depot expiry events, >= 20 expired units, >= 1 unit expired on arrival | 14 events, 336 units, 183 on arrival |
| >= 2 CENTRAL expiry events | 2 (109 units) |
| >= 6 depot-stockout-days across >= 3 depots; every depot 1-15 stockout days | 34 across all four (7 / 8 / 13 / 6) |
| >= 5 cancel days on which the priority order is not alphabetical | 6 |
| >= 1 cancel day on which the exact-ratio order ships different quantities than BOTH "rank by absolute backorders" and "alphabetical" would | day 22 |
| ranking by absolute backorders instead of backorders/S changes >= 3 graded items of the final answer | 9 items |
| >= 1 order-day pair of nonzero ratios whose order is the reverse of their absolute backorders (a near-tie only cross-multiplication settles) | 2 |
| >= 1 depot-day with zero demand but unserved old backorders (the "still a stockout day" clause) | 2 |
| "days with on_hand == 0" differs from stockout_days for >= 2 depots and by >= 3 days in total | A 7 vs 7, B 9 vs 8, C 15 vs 13, D 6 vs 6 |
| >= 1 negative inventory position, >= 3 multi-lot shipments, fill rate in [0.70, 0.97], CENTRAL not empty at the end | 14, 3, 0.7396, 19 |

Measured on 40 regenerated hard seeds (1-40) with an instrumented copy of the simulator,
the three misreadings the prompt is written to trap change the graded answer on every
seed but one: absolute-backorder ranking changes 0-24 items (mean 13.3; zero on 1/40 —
that seed is rejected by the >= 3 gate, which was added afterwards, and the shipped seed
changes 9), alphabetical priority 11-34 (mean 22.9), "stockout = empty shelf" 2-4 (mean
2.5), "zero-demand day is never a stockout day" 1-3 (mean 1.6).

Depots are coupled only through CENTRAL's allocation, so a slip at one depot
contaminates others only on the days CENTRAL is short (7 of 30 days here); the
remaining fields stay independently gradable, and the three checkpoints record how
far a configuration gets before diverging. The first checkpoint is day 15, past the
point where every frontier model was still perfect in the pilot (day 10).

**Difficulty knob** (`generator.py --difficulty`): `easy` 15 days / 3 depots
(checkpoints 8, 15; 39 points), `medium` 20 / 4 (12, 20; 48 points), `hard` 30 / 4
(15, 22, 30; 60 points, shipped, shelf life 14), `extreme` 60 / 6 (20, 30, 40, 50, 60;
120 points, shelf life 14). `easy` and `medium` are calibration rungs: the
rule-binding gates in the table above are enforced only for horizons >= 30 days
(`STRICT_DAYS`), because with 15-20 days 0 of 300 sub-seeds satisfied them together.
Horizon, depot count, checkpoint days, shelf life, per-delivery shelf-life offsets,
delivery-size variance, the designed short-dated bulk delivery, demand variance and the
reorder safety factor are module constants.

**Ground truth.** `generator.py` renders prompt and key from one parameter object with
a lot-dictionary simulator that asserts unit conservation (start stock + deliveries =
served + expired + on hand + in transit) at the end of every day. `oracle.py` is a
second implementation written from the manual text only: it parses `prompt.txt` with
regular expressions, represents every unit individually, sorts for FEFO, orders
priorities by integer cross-multiplication, and agrees with `key.json` exactly on the
shipped seed, on hard seeds 1-40, and on the `easy`, `medium` and `extreme` presets
(seed 3). An independent lot-level simulator written by the breaker from `prompt.txt`
alone also matched the previous key on all fields. Days 1-4 of the shipped scenario
were checked by hand:

```
Day 1  P1 CENTRAL +52 (exp 15) -> 232; A +30 (exp 8) -> 93
       P3 A 15 (exp5 -> 78) | B 4 (exp4 -> 21) | C 6 (exp4 -> 17) | D 7 (exp3 -> 37)
       P4 IPs 78/21/17/37 all >= s (39/14/15/24) -> no orders
Day 2  P3 A 14 -> 64 | B 8 -> 13 | C 4 -> 13 | D 15 -> 22
       P4 B IP 13 < 14 -> orders 22 | C 13 < 15 -> orders 17 | D 22 < 24 -> orders 33
       P5 ratios all 0 -> B, C, D alphabetical; all filled from CENTRAL's exp-4 lot; CENTRAL 160
Day 3  P3 A 7 -> 57 | B 7 (1 exp4 + 6 exp9 -> 6) | C 3 -> 10 | D 7 -> 15
       P4 B 6+22 = 28, C 10+17 = 27, D 15+33 = 48 -> no orders
Day 4  P1 B receives 22 exp 4, D receives 33 exp 4
       P2 CENTRAL discards 31, B 22, C 1, D 33 (B and D: received AND expired)
       P3 A 10 -> 47 | B 6 of 13 -> bo 7 STOCKOUT | C 9 of 9 -> on hand 0, bo 0 (NOT a stockout day) | D 15 of 34 -> bo 19 STOCKOUT
       P4 B IP 0+0-7 = -7 -> orders 42 | D IP -19 -> orders 74 | C IP 0+17 = 17 >= 15 -> no order
       P5 ratios D 19/55 > B 7/35 -> D first: 74 (exp 10); B: 42 (3 exp 10 + 39 exp 15); CENTRAL 13
```

The full phase-by-phase log is in `trace.txt`; the parameter object is `scenario.json`.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`;
`python grade.py --selftest` runs the checks listed below. Total 60:

| block | items | points |
|---|---|---|
| checkpoints (days 15, 22, 30 x depots A-D): on_hand AND backorders as one paired item | 12 | 2 each, both exact |
| checkpoints: in_transit | 12 | 1 each, exact |
| per-depot totals (total_expired, stockout_days, units_received) | 12 | 1 each, exact |
| CENTRAL (final_on_hand, total_cancelled, total_expired) | 3 | 2 each, exact |
| same_day_served | 1 | 3, exact |
| total_demand | 1 | 1, exact (a plain sum of the demand table) |
| fill_rate | 1 | 2 if within 0.0005 of the key (i.e. the 4-dp value); no wider band |

Why paired: in this system `on_hand > 0` and `backorders > 0` are mutually exclusive
(backorders can only remain when the shelf is empty), so scoring them as two items gave
an all-zeros answer one of the two for free in every cell. Paired, the all-zeros
chance floor is **5/60 on the shipped seed** and 1-7 (mean 3.5) over hard seeds 1-40
(previously 15/60 and 12-18). `detail.chance_floor` reports the floor for the key in
use and `detail.floor_adjusted` = (score - floor) / (total - floor), clipped at 0, so
downstream tables need not recompute it.

Why the integer fields: fill_rate used to carry 6 points with a +/-0.01 half-credit
band, which paid the same 3 points to a run with 10 wrong fields and to a run with 0
wrong fields and a single addition slip. Now the simulation-dependent numerator is
worth 3, the denominator (checkable without simulating) 1, and the quotient 2, all
exact. `detail.network.fill_rate_consistent` says whether the reported fill_rate equals
the reported same_day_served / total_demand, so arithmetic slips are distinguishable
from simulation errors.

Parsing is tolerant (JSON strings, Python-repr strings, fenced or prose-wrapped JSON,
`{"answer": {...}}` wrappers, `day_15` / `d15` / `Day 15` / `checkpoint 15` checkpoint
keys, lowercase depot keys, `demand_total` / `same_day_served_total` aliases,
percentage fill rates, stringified integers); missing fields score 0. When the answer
has to be recovered from text, the LAST balanced object carrying `checkpoints` wins
(so a draft followed by a correction is graded on the correction) and
`detail.format_deviation` is set. Note that `runner/run.py`'s `extract_json` still
takes the FIRST balanced object; `candidates/pilot.py` grades the runner-extracted
dict, so the grader's text path is only reached for records whose `answer` is a
string. Hedging does not pay: lists of alternatives, duplicate keys or trailing prose
score no better than a single committed value. `detail` also reports
`first_checkpoint_with_error`, `depots_fully_correct_final` and the wrong fields.

Self-test (`--selftest`, all asserted): the key scores 60/60; corrupting depot D from
the day-22 checkpoint on plus one unit of same_day_served scores 48/60 with
`first_checkpoint_with_error = 22`; an empty answer 0; the all-zeros answer scores
exactly `chance_floor` (5); a fill_rate 0.004 off scores 58 (no band); alias keys and a
percentage fill rate score 60; draft-then-final text scores 60 and final-then-draft
58; a hedged list in a cell scores as wrong.

## Runner caveats (outside this directory, not fixed here)

- `runner/run.py run_claude_code` and `pilot/pilot_run.py` call `claude -p` without
  `--tools ""` / a `--disallowedTools` list and without an empty temp cwd, so
  `key.json`, `trace.txt` and `scenario.json` sit next to the prompt; the only guard is
  the prompt's "no tools" sentence. The four pilot records show `num_turns = 1` and no
  permission denials, so no leak occurred, but a record that used tools is not
  invalidated automatically. Apply the lockdown recommended in TOURNAMENT.md 4.1 in
  `runner/run.py` before the replication.
- `runner.extract_json` (first balanced object) and this grader (last object with
  `checkpoints`) disagree on multi-object responses; align the runner as 4.1 asks.
- Replicate at n >= 3 on this `hard` seed and on `extreme` in the same batch: Opus 5.5
  reached 60/60 on the previous, easier scenario at n=1.

## What changed (critic fixes applied in this revision)

- Grader: paired (on_hand, backorders) items; fill-rate block replaced by
  same_day_served (3) / total_demand (1) / fill_rate exact (2); `chance_floor`,
  `floor_adjusted`, `fill_rate_consistent`, `format_deviation` in `detail`; last-object
  text extraction; `d15`-style keys; wrapper unwrapping; `--selftest`.
- Generator: explicit checkpoint days 15/22/30 (no day-10 freebie); hard shelf life 14;
  per-delivery shelf lives plus one designed short-dated bulk delivery followed by a
  small one (this is what makes >= 2 CENTRAL expiry events attainable alongside
  frequent rationing); zero-demand probability 0.05 -> 0.08; the base-quantity scan
  now minimises the number of failed gates; new gates: priority_days >= 5,
  ratio-order binds on >= 1 cancel day AND changes >= 3 graded items under the
  absolute-backorder misreading, >= 1 ratio inversion, >= 1 zero-demand stockout day,
  on_hand==0 days != stockout_days for >= 2 depots (total gap >= 3), >= 2 CENTRAL
  expiry events. Key gains `same_day_served` and `total_demand`.
- Prompt: section 3 phase 1(a) and section 7 describe per-delivery expiry days;
  section 4 defines the two new fields; section 9 shape and scoring note updated; the
  toy example's answer JSON carries the new fields.
- Oracle: parses per-delivery expiry days and emits the two new fields.
- Not applied here (outside `candidates/simulation-3/` or in the replication step):
  runner tool/cwd lockdown and `num_turns` assertion, runner extractor alignment,
  copying `thinking_tokens` / `maxOutputTokens` / `total_cost_usd` into pilot records,
  the n >= 3 replication itself. The statistician's "gap >= 2 for each of two depots"
  gate was relaxed to "gap >= 1 for two depots and >= 3 in total" (the literal form
  passed ~5 % of sub-seeds on its own and 0 % jointly). The nonzero-ratio exact tie is
  counted (`nonzero_ratio_ties` in the generator summary) but not gated: it is rare
  and the near-tie inversion gate covers the cross-multiplication requirement.

## What we found

The grid's real separator: replicated-clean for only 9 of 41 configs — Opus 5.5 at high, xhigh and max; Fable 5.1 at xhigh and max; Sonnet 5.5 at medium, xhigh and max; Haiku 5.5 at xhigh and max. Opus 5 and Opus 4.8 score 100 % in one replicate and 20–50 % in the other at nearly every effort (P(clean) 0.33–0.5); Fable 5 never holds it twice (best 70 % mean at max); Sonnet 5 tops out at 75 % (medium); Haiku 4.5 10–22 %. Haiku 5.5 climbs the ladder the task was built to show: 0–10 % at low, 48–100 % at medium, 68–100 % at high, then 60/60 twice at xhigh and max. The failure mode is always one bookkeeping slip around a stockout or expiry day — usually at the day-18/20 demand spike — that propagates through every later checkpoint. Cheapest clean: Haiku 5.5 @ xhigh at $0.04 a run and under five minutes, then Sonnet 5.5 @ medium at $0.20 and under two minutes.
