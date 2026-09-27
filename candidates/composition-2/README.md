# Rail Dispatch Chain (candidate composition-2)

Four chained exact-reasoning stages on a seeded 26-station freight network: day-dependent shortest-path routing -> crew-rule arrival timing -> two-dock FIFO queueing -> demurrage billing, 14 shipments, no tools.

## What it tests and why

The model receives a random planar rail network (26 named stations, 44 undirected segments with km
lengths), a maintenance calendar closing 10 segments on specific dates, a tariff, and 14 shipments
(origin, destination hub, ready timestamp, tonnage, hazardous flag, customer). It must produce, for
every shipment, in one shot:

1. **Routes** - the shortest open path by km on the shipment's departure date, ties broken by the
   alphabetically-first station sequence (rule stated). This is genuine graph search on a random
   instance: 12 of the 14 reference routes differ from the closure-free shortest path, 12 routes
   pass a segment that is closed on a *different* date (distractors), and 2 shipments have an exact
   km tie that only the tie-break rule resolves. Nothing here can be recalled; it must be searched.
2. **Arrivals** - 60 km/h (1 km = 1 min), a 20-minute dwell at every intermediate station, and a
   crew rule (45-minute rest before any segment once completed driving reaches 360 min). The
   generator guarantees rest checks that land just over (373 min) and just under (346, 358 min)
   the boundary, several trips with rests, and midnight crossings.
3. **Docks** - each hub has 2 docks; shipments are served FIFO by arrival, unloading takes
   ceil(t/25)*30 min. The generator forces at least 3 consecutive arrivals at a hub to be <= 15
   minutes apart, and checks that swapping at least two of those pairs changes a wait: small
   timing errors upstream visibly reorder the queue.
4. **Billing** - first 90 min free, $85 per started 30-min block, x2 hazardous, cap $900, rolled
   up per customer and in total. At least 5 shipments are billable, at least one hits the cap.

Each stage consumes only the previous stage's output plus static prompt data, so the task measures
four separable skills (search, timestamp arithmetic with an interrupting rule, discrete-event
queue simulation, tariff arithmetic) and the conditional grading below says *which* one failed.
Existing MERC tasks contain no search on a random graph with time-dependent constraints and no
chained simulation; the judges' concern that max-effort frontier may saturate Stage 1 is why the
default is 14 shipments over 26 stations with engineered ties and closures (see knobs).

**Difficulty knobs** (`generator.py --difficulty easy|medium|hard|extreme`, every field overridable,
e.g. `--shipments 20 --docks 1 --closures 14`): station count (<= 26), edge count, shipment count,
hubs, docks per hub, closure count, number of engineered near-tie arrivals, number of dates. The
default (`hard`, seed 20261005) is the shipped `prompt.txt` (10.3 KB).

**Ground truth**: `generator.py` (Dijkstra + greedy lexicographic walk, closed-form timing,
event-driven dock simulator) writes `key.json`; `oracle.py` recomputes everything *from
prompt.txt* with different algorithms (brute-force DFS enumeration of all simple paths keeping
ties, minute-by-minute tick simulators for both the trains and the docks, integer-arithmetic
tariff) and must agree exactly - it does for the shipped seed and for the fuzzed seeds. The
generator rejects any instance with an exact same-minute arrival tie at a hub, so the stated
shipment-id tie rule is never load-bearing.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`; total is 100.

| Stage | Points | Absolute credit | Conditional credit (max with absolute) |
|---|---|---|---|
| 1 Routes | 25 | per shipment: 60% for the exact station sequence, 40% for exact km | - |
| 2 Arrivals | 25 | per shipment: full if exact, half if within 20 min | arrival recomputed from the model's *own* Stage-1 path (if it is a valid origin->destination walk) |
| 3 Docks | 25 | per shipment: full if wait exact, half if within 15 min | dock simulator re-run on the model's *own* Stage-2 arrivals |
| 4 Billing | 15 + 10 | per customer exact (15 split evenly); grand total exact 10 / within 2% 5 | tariff applied to the model's *own* Stage-3 waits |

Conditional credit is withheld when the model's own chain is degenerate (no queueing at all or
no billable wait), so "every wait is 0" cannot buy Stage 4. `detail` reports per-stage
absolute vs conditional scores, the miss lists, and `first_divergence`, the first shipment (id
order) and stage at which the model's chain leaves the reference chain - Stage-1 misses are search
errors, Stage-2-conditional misses are crew-rule placement errors, Stage-3-conditional misses are
queue-order errors. Answers are parsed tolerantly (prose-wrapped JSON, `S1` for `S01`, paths as
strings, timestamps with seconds); format deviations are recorded in `detail.format`, not punished.
Ground truth is embedded in `key.json` next to the grader.
