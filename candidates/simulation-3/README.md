# Cold-chain depot network (S3, candidate simulation-3)

30-day, 5-node perishable-inventory simulation from a written operating manual: lead times, FEFO lot expiry, backorders, (s, S) ordering and ratio-based central rationing with cancel-not-backlog; 60 independently graded output fields.

## What it tests and why

The model receives a ~14 KB operating manual, a day-0 state (lots with expiry days at
CENTRAL and four depots, plus two shipments already in transit), a nine-line supplier
delivery schedule and a 30 x 4 demand table, and must run the network day by day
through five fixed phases (receive, expire, serve, review/order, allocate/ship). It
reports depot state at days 10/20/30, per-depot horizon totals, CENTRAL totals and the
network same-day fill rate.

Nothing is recallable: policies, lead times, demands, lot expiries and delivery sizes
are generated. What separates configurations is doing exactly what the text says for
30 days across five coupled nodes, in the face of rules that contradict "how inventory
systems usually work":

- **phase order** — expire *before* serve, so stock arriving already expired counts as
  received *and* as waste (this happens on day 4 of the shipped scenario: CENTRAL's
  FEFO rule ships its oldest lot to depot B and it dies on arrival);
- **inventory position** includes in-transit and subtracts backorders, so a depot with
  open backorders may place no order at all;
- **FEFO across lots** at both depots and CENTRAL, with shipments carrying several lots;
- **rationing by shortfall ratio** (backorders / S, exact fractions) with alphabetical
  tie-break, processed sequentially against a dwindling CENTRAL balance;
- **cancel, never backlog** at CENTRAL; a depot simply re-orders the next day;
- **same-day fill rate** — backorders served late do not count, and stockout days are
  defined by end-of-phase-3 backorders, not by demand.

Every one of these fires repeatedly: the generator only accepts a scenario in which
partial fills, full cancellations, depot expiry, CENTRAL expiry, ratio-decided
priority under shortage, negative inventory positions, multi-lot shipments and
expired-on-arrival deliveries all occur, rationing binds on between 4 and 12 of the 30
days, every depot has between 1 and 15 stockout days, and the fill rate lies in
[0.70, 0.97]. The shipped seed (3, sub-seed 15) has 11 cancelled orders on 9 days (6
partial, 5 full), 5 depot expiry events (120 units), 26 depot-stockout-days across all
four depots, 4 negative-IP orders, and a fill rate of 0.8647.

Depots are coupled only through CENTRAL's allocation, so a slip at one depot
contaminates others only on the days CENTRAL is short (about a third of days); the
remaining fields stay independently gradable, and the three checkpoints record how
far a configuration gets before diverging.

**Difficulty knob** (`generator.py --difficulty`): `easy` 15 days / 3 depots,
`medium` 20 / 4, `hard` 30 / 4 (shipped), `extreme` 60 / 6 with a shorter shelf life.
Horizon, depot count, shelf life, delivery-size variance, demand variance and the
reorder safety factor are module constants; the total score scales with checkpoints
and depots (48 / 60 / 60 / 138 points).

**Ground truth.** `generator.py` renders prompt and key from one parameter object with
a lot-dictionary simulator that asserts unit conservation (start stock + deliveries =
served + expired + on hand + in transit) at the end of every day. `oracle.py` is a
second implementation written from the manual text only: it parses `prompt.txt` with
regular expressions, represents every unit individually, sorts for FEFO, orders
priorities by integer cross-multiplication, and agrees with `key.json` exactly on the
shipped seed and on 315 further generated scenarios (300 hard seeds, plus easy,
medium and extreme). Days 1-3 of the shipped scenario were also checked by hand:

```
Day 1  P1 CENTRAL +151 (exp 19) -> 363; A +28 (exp 9) -> 60; C +42 (exp 6) -> 91
       P2 nothing expires
       P3 A serves 14 from exp-5 lot (46 left) | B 7 (32) | C 6 from exp-3 lot (85) | D 5 (54)
       P4 IPs 46/32/85/54 all >= s (18/24/39/44) -> no orders
Day 2  P3 A 12 (5 exp5 + 7 exp7 -> 34) | B 20 (18 exp5 + 2 exp10 -> 12) | C 21 (exp3 -> 64) | D 38 (27 exp5 + 11 exp8 -> 16)
       P4 B IP 12 < 24 -> orders 44 | D IP 16 < 44 -> orders 58
       P5 ratios 0/56, 0/74 -> B then D; both filled from CENTRAL's exp-4 lot; CENTRAL 261
Day 3  P2 C discards 3 (exp 3)
       P3 A 16 (6 exp7 + 10 exp9 -> 18) | B 9 -> 3 | C 15 -> 46 | D 4 -> 12
       P4 A IP 18 >= 18, B 3+44 = 47, C 46, D 12+58 = 70 -> no orders
Day 4  P1 B receives 44 exp 4  P2 CENTRAL discards 19, B discards 44 (received AND expired)
```

The full phase-by-phase log is in `trace.txt`; the parameter object is `scenario.json`.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Total 60:

| block | fields | points |
|---|---|---|
| checkpoints (days 10, 20, 30 x depots A-D x on_hand / backorders / in_transit) | 36 | 1 each, exact |
| per-depot totals (total_expired, stockout_days, units_received) | 12 | 1 each, exact |
| CENTRAL (final_on_hand, total_cancelled, total_expired) | 3 | 2 each, exact |
| fill_rate | 1 | 6 if within 0.0005, 3 if within 0.01, else 0 |

Parsing is tolerant (JSON strings, Python-repr strings, fenced or prose-wrapped JSON,
`day_10`/lowercase depot keys, percentage fill rates); missing fields score 0.
`detail` also reports `first_checkpoint_with_error` and `depots_fully_correct_final`
as diagnostics. Self-test: the key scores 60/60; corrupting depot D from day 20 on plus
the fill rate scores 48/60; an empty answer 0; an all-zeros guess scores 15/60 (the
chance floor — many checkpoint backorder cells are legitimately zero), so meaningful
scores start around 20.
