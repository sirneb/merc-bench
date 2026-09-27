# MERC hard-tier tournament — report

Date: 2026-09-26. Repository: `merc-bench` (Model x Effort, Reliability & Cost). Candidate packages under `candidates/`.

**Why this tournament ran.** The 12 shipped tasks are saturated: in `results/summary.json` every config above Haiku scores 98-100 % on the 10 core tasks; only T3 (6 points) and T4 (10 points) move at all, and at the top only by one point (e.g. Opus 5, Opus 5.5 and Fable 5.1 all hold T3 6/6 from `medium` up; T4 differs by a single point across replicates). The goal was tasks where `claude-sonnet-5`, `claude-opus-5`, `claude-opus-5-5` and `claude-fable-5-1` land at clearly different scores and where effort visibly moves the outcome, measured on success (graded score / total), wall-clock, input tokens, output tokens and list-price cost.

**Pipeline.** 8 domain proposers (exactness, deduction, reading, simulation, language, adversarial, quantitative, composition) x 3 proposals = 24 proposals -> 3 judges (skeptic, grader, operator) -> the top 8 by judge average were built (generator, prompt, schema, grader, key, oracle) -> each built package was piloted on 4 configs through the `claude-code` harness (Haiku 4.5@low, Sonnet 5@medium, Opus 5.5@medium, Fable 5.1@medium; single run each, up to 3 corrective retries) -> 6 of the 8 received two independent critic passes ("breaker": key/grader/prompt attack; "statistician": lost-point classification, difficulty placement, cost accounting). `composition-3` and `simulation-3` were piloted but no critic pass was recorded for them. `claude-opus-5` was not piloted on any task.

Judge averages below are reproduced as recorded; the judge scale itself is not recorded in the stage data handed to this report.

---

## 1. Bracket

| Rank | Id | Task | Judge avg | Built | Piloted | Critiqued | Frontier scores (Sonnet 5 / Opus 5.5 / Fable 5.1 @medium) | Separates? |
|---|---|---|---|---|---|---|---|---|
| 1 | quantitative-2 | Crew Roster Across Fictional DST (timezone / duty-time arithmetic) | 36.83 | yes | yes | yes (2) | 59 / 60 / 60 of 60 | tier only; top two tie |
| 2 | simulation-2 | TALLY-12: execute two programs on a made-up 12-bit register machine | 35.75 | yes | yes | yes (2) | 44.5 / 80 / 80 of 80 | **yes** (Sonnet vs Opus/Fable, 35.5 pts); top two tie |
| 3 | simulation-1 | Quarry Duel: play both sides of a deterministic card-and-track game | 35.25 | yes | yes | yes (2) | 100 / 100 / 31 of 100 | bimodal; n=1 cannot rank |
| 4 | composition-2 | Rail Dispatch Chain (routing -> crew timing -> dock queue -> demurrage) | 35.08 | yes | yes | yes (2) | 100 / 100 / 100 of 100 | **no** |
| 5 | composition-3 | Novel-ISA Assemble-Execute-Decrypt (QX-16) | 34.33 | yes | yes | no | 100 / 100 / 100 of 100 | **no** |
| 6 | deduction-3 | Crib Slide: recover a polyalphabetic key from cribs | 34.00 | yes | yes | yes (2) | 54 / 60 / (60*) of 60 | tier only; *Fable row invalid (see 3.5) |
| 7 | simulation-3 | Cold-chain depot network: 30-day multi-depot inventory simulation | 33.00 | yes | yes | no | 50 / 60 / 57 of 60 | **yes — the only task where all three frontier configs scored differently** |
| 8 | adversarial-3 | Chess Open Standings With Arbiter Errata | 33.00 | yes | yes | yes (2) | 126 / 125 / 126 of 126 | 1 point (one SB arithmetic slip) |
| 9 | language-1 | Conlang Rosetta: translation into a generated language | 32.58 | no | – | – | – | – |
| 10 | quantitative-1 | Valdoria Tax Return Prep (synthetic tax code) | 32.17 | no | – | – | – | – |
| 11 | deduction-1 | Ward Roster: feasible schedule + infeasibility diagnosis | 31.75 | no | – | – | – | – |
| 12 | exactness-2 | FIFO Inventory Ledger across Warehouses (1,200 events) | 31.50 | no | – | – | – | – |
| 13 | reading-3 | Protocol Eligibility & Dosing (clinical protocol with errata, 24 patients) | 30.67 | no | – | – | – | – |
| 14 | language-3 | Sound-change induction (150 word pairs -> 40 unseen words) | 30.33 | no | – | – | – | – |
| 15 | quantitative-3 | Process Plant Balance Chain (stoichiometry, units, energy cost) | 30.17 | no | – | – | – | – |
| 16 | reading-1 | Amendment Chain: operative terms of an MSA | 29.83 | no | – | – | – | – |
| 17 | composition-1 | Contract-to-Settlement Pipeline | 29.75 | no | – | – | – | – |
| 18 | adversarial-1 | Amended Policy Claims Adjudication | 29.58 | no | – | – | – | – |
| 19 | deduction-2 | Liar's Grid: 7x7 logic grids with one false clue | 29.25 | no | – | – | – | – |
| 19 | language-2 | Continuity audit: planted contradictions in a 15,000-word narrative | 29.25 | no | – | – | – | – |
| 21 | adversarial-2 | Three-System Shipment Reconciliation | 28.83 | no | – | – | – | – |
| 22 | exactness-1 | Bank Reconciliation with Decoys | 28.50 | no | – | – | – | – |
| 22 | exactness-3 | Shift Roster Compliance and Payroll Audit (2,000 shifts, 14 rules) | 28.50 | no | – | – | – | – |
| 24 | reading-2 | Thread Reconciliation: final state of a 90-message email chain | 26.75 | no | – | – | – | – |

Reading the bracket:

- **Haiku 4.5@low vs the frontier is separated by every one of the 8 built tasks** (Haiku: 84 %, 10 %, 16 %, 78 %, 26 %, 0.4 %, 20 %, 42 % of total, in bracket order). That was never the hard part.
- **Only two tasks put daylight between frontier configs at medium effort on a single run**: `simulation-2` (Sonnet 5 at 55.6 % vs Opus 5.5 / Fable 5.1 at 100 %) and `simulation-3` (Sonnet 5 83.3 %, Fable 5.1 95 %, Opus 5.5 100 %). `simulation-1` produced a 69-point Fable drop, but the critics show a single early bookkeeping slip explains all 69 points and the pattern {100, 100, 31} has probability 0.44 under equal P(clean) = 2/3 — it is not evidence of a ranking.
- **Three of the eight (`composition-2`, `composition-3`, `adversarial-3` within 1 point) are already saturated at the shipped preset**, exactly like T1-T10 in the current grid.
- The judge ranking did not predict discrimination: the judges' #1 (`quantitative-2`) compressed to 59/60/60, while their #7 (`simulation-3`, not even sent to critics) is the only package that spread all three frontier configs.
- Where the two top models tied on score, the cost axes did not tie: on `simulation-2` Fable 5.1 spent 2.6x the wall-clock, 2x the output tokens and 4.9x the dollars of Opus 5.5 for the same 80/80.

---

## 2. Discrimination tables

All rows: `claude-code` harness, single valid attempt unless noted, list-price cost from `runner/run.py` `DEFAULT_PRICES` (haiku 1/1.25/0.1/5; sonnet 3/3.75/0.3/15; opus55 4/5/0.2/20; fable51 10/12.5/0.25/50 $/MTok for input/cache-write/cache-read/output). "Input tokens" = uncached input + cache write + cache read as recorded; under this harness ~25k of every input figure is Claude Code's own system prompt, not the task (the task prompts are 5-27 KB). Recomputing every cost from the recorded usage with `DEFAULT_PRICES` reproduces the record values to 4 decimals. Frontier = Sonnet 5, Opus 5.5, Fable 5.1 at medium.

### 2.1 quantitative-2 — Crew Roster Across Fictional DST (total 60; prompt 9.5 KB)

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) |
|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 50.5 | 84.2 | 261.6 | 23,276 | 41,392 | 0.2189 |
| Sonnet 5 @medium | 59 | 98.3 | 62.6 | 26,251 | 8,537 | 0.1871 |
| Opus 5.5 @medium | 60 | 100 | 58.7 | 25,094 | 7,985 | 0.2308 |
| Fable 5.1 @medium | 60 | 100 | 81.0 | 28,787 | 8,777 | 0.6372 |

**Frontier spread: 1 point (1.7 %); Opus 5.5 = Fable 5.1.** Sonnet's two half-point misses were arr_local values with correct arr_utc (one on a near-transition leg). Haiku's 9.5 lost points: 7 of 9 leg misses are the same +20-min block-minutes-to-h:mm slip, one midnight carry, one missed transition — not the transition trap the design targeted (near-transition 9.5/12 = 79 % vs other legs 22/28 = 79 %). Cost per point at the top: Sonnet $0.0032, Opus 5.5 $0.0038, Fable 5.1 $0.0106.

### 2.2 simulation-2 — TALLY-12 register machine (total 80; prompt 6.0 KB)

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) |
|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 8.25 | 10.3 | 338.5 | 21,646 | 52,982 | 0.2749 |
| Sonnet 5 @medium | 44.5 | 55.6 | 255.5 | 24,025 | 34,803 | 0.5727 |
| Opus 5.5 @medium | 80 | 100 | 254.1 | 25,850 | 34,194 | 0.7588 |
| Fable 5.1 @medium | 80 | 100 | 660.8 | 27,668 | 70,242 | 3.6965 |

**Frontier spread: 35.5 points (44.4 %) Sonnet vs Opus/Fable; Opus 5.5 = Fable 5.1 on score, but Fable took 2.6x the time, 2.05x the output tokens and 4.87x the cost.** Sonnet ran Program A perfectly and got 36/40 of Program B's OUT values, 7/8 registers, 16/16 memory, 929/930 steps; the longest-correct-prefix rule turned four isolated non-propagating slips into a 34-point loss (blended prefix+pointwise rescoring: 8.25 / 59.5 / 80 / 80; pure pointwise ~74.5 for Sonnet). 98-99 % of every run's output tokens were thinking (Fable 69,756 of 70,242). Haiku diverged at the second loop iteration of both programs. A zero-execution "static read" of the listing scores 10.5/80, above Haiku's 8.25.

### 2.3 simulation-1 — Quarry Duel, 100 turns (total 100; prompt 8.0 KB)

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) |
|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 16 | 16 | 203.7 | 22,477 | 31,843 | 0.1714 |
| Sonnet 5 @medium | 100 | 100 | 176.1 | 25,381 | 24,828 | 0.4316 |
| Opus 5.5 @medium | 100 | 100 | 131.4 | 26,099 | 18,301 | 0.4469 |
| Fable 5.1 @medium | 31 | 31 | 178.2 | 27,917 | 21,033 | 1.2739 |

**Frontier spread: 69 points — but from one run each and a step-function grader.** Fable was perfect through turn 20, then one stale-position slip in turns 37-40 (P1 treated as still on space 10 after the t36 SWAP / t37 capture+WELL+hand-limit sequence) cascaded: ~10 points primary error, ~59 cascade. A "repeat the correct turn-20 state at every checkpoint" answer scores 33, i.e. above Fable's genuine 100-turn attempt. Haiku used 31,843 of a 32,000 output cap (30.6k thinking) and its visible answer admits it summarised. Opus 5.5 was the most efficient perfect run (17.5k thinking tokens, 131 s).

### 2.4 composition-2 — Rail Dispatch Chain, `hard` preset (total 100; prompt 10.3 KB)

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) |
|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 77.68 | 77.7 | 341 | 23,526 | 44,170 | 0.2331 |
| Sonnet 5 @medium | 100 | 100 | 81 | 26,570 | 10,819 | 0.2225 |
| Opus 5.5 @medium | 100 | 100 | 76 | 27,288 | 9,788 | 0.2779 |
| Fable 5.1 @medium | 100 | 100 | 111 | 27,231 | 11,866 | 0.7722 |

**Frontier spread: 0.** Three perfect chains in 76-111 s with 8-10k thinking tokens — saturation, not luck. Haiku's 22.3 lost points are real (8/14 shortest paths wrong, four +/-60-min hour-carry slips), but its *absolute* end-to-end score is 29.46; conditional credit at weight 1.0 lifts it to 77.68, and an answer that does no graph search at all (fewest-hops paths ignoring closures, correct downstream arithmetic) grades 78.57.

### 2.5 deduction-3 — Crib Slide (total 60; prompt 5.1 KB)

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) | Note |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 0.21 | 0.35 | 389.6 | 21,830 | 59,728 | 0.3088 | never placed a crib; invented dictionary key |
| Sonnet 5 @medium | 54 | 90 | 335.2 | 24,431 | 41,996 | 0.6821 | key 11/11 correct; Q2 (SEALNO boundary) + Q7 (dropped letter) |
| Opus 5.5 @medium | 60 | 100 | 325.8 | 73,691 | 38,727 | 0.9800 | attempt 1 = API safety-classifier refusal (94 s, 9.9k tokens wasted); usage includes both attempts |
| Fable 5.1 @medium | (60) | (100) | 1,255.5 | 54,001 | 107,544 | 5.7293 | **INVALID as a Fable measurement**: Fable stopped with `stop_reason=refusal` (category `bio`) after 25,949 thinking tokens; Claude Code's `model_refusal_fallback` switched to `claude-opus-5`, which produced the 81,595-token perfect answer; runner recorded it as Fable at Fable prices |

**Frontier spread as recorded: 6 points; after discarding the Fable row the frontier evidence is Sonnet 54 vs Opus 5.5 60**, and 3 of Sonnet's 6 lost points sit on a label/value boundary (`SEALNO|EQBLYS` vs `SEAL|NOEQBLYS`) that the prompt does not make derivable. The verdict's "Fable 3.9x slower / 5.8x costlier than Opus 5.5" comparison is retracted. Both top-tier first attempts (2 of 2) were cut off by the API safety classifier.

### 2.6 adversarial-3 — Chess Open Standings, `hard` preset 20 players x 9 rounds (total 126; prompt 27.0 KB)

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) |
|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 53.5 | 42.5 | 428.1 | 123,481 | 65,377 | 0.4300 |
| Sonnet 5 @medium | 126 | 100 | 94.8 | 34,318 | 14,551 | 0.3075 |
| Opus 5.5 @medium | 125 | 99.2 | 77.8 | 35,036 | 10,644 | 0.3337 |
| Fable 5.1 @medium | 126 | 100 | 106.7 | 36,854 | 11,809 | 0.8897 |

**Frontier spread: 1 point (0.8 %)** — one Sonneborn-Berger cell (P01: 20.5 vs 21.0), verified by hand as a genuine slip: 1 error in 240 frontier numeric cells (~0.4 %/cell). All three frontier models navigated all 18 planted traps. Haiku's 123k input tokens are a continuation artefact (63.9k thinking exceeded the 32k output cap, forcing a second turn that re-sent the context). No player pair ties on (points, BH, SB) in the shipped key, so two of the tie-break regulations are never exercised.

### 2.7 simulation-3 — Cold-chain depot network, `hard` preset 30 days x 4 depots (total 60; prompt 14.2 KB) — piloted, not critiqued

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) | CLI `total_cost_usd` |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 12 | 20 | 387.0 | 26,278 | 61,181 | 0.3216 | 0.3302 |
| Sonnet 5 @medium | 50 | 83.3 | 111.4 | 29,985 | 13,430 | 0.2745 | 0.2108 |
| Opus 5.5 @medium | 60 | 100 | 90.0 | 30,703 | 11,115 | 0.3215 | 0.3796 |
| Fable 5.1 @medium | 57 | 95 | 115.2 | 32,521 | 12,361 | 0.8631 | 1.0082 |

**Frontier spread: 10 points (16.7 %), and all three frontier configs distinct (50 < 57 < 60).** Sonnet's first error is at the day-20 checkpoint (depot B backorders 13 vs 17, B in-transit 65 vs 69, C on-hand 46 vs 50), plus stockout-day counts for A (9 vs 6) and B (5 vs 8), CENTRAL total_cancelled 368 vs 361 and a fill rate inside the loose band (0.8668 vs 0.8647: 3 of 6 points). Fable lost only the fill-rate precision (0.8691 vs 0.8647, within 0.01 but not 0.0005: 3 of 6 points) with every one of the other 54 fields exact. Haiku's 12/60 is near the all-zeros chance floor of 15/60 stated in the package README. Caveat: these are single runs, no critic has attacked the key, grader or prompt, and the Sonnet-Fable-Opus gaps rest on 1-5 field errors each. The CLI's own list-basis cost disagrees with the runner's table in both directions (Sonnet -23 %, Opus 5.5 +18 %, Fable +17 %).

### 2.8 composition-3 — QX-16 assemble/execute/decrypt, `hard` preset ~325 steps (total 100; prompt 13.2 KB) — piloted, not critiqued

| Config | Score | % | Duration (s) | Input tok | Output tok | Cost ($) |
|---|---|---|---|---|---|---|
| Haiku 4.5 @low | 25.85 | 25.9 | 736.9 | 48,923 | 107,149 | 0.5627 |
| Sonnet 5 @medium | 100 | 100 | 237.7 | 27,636 | 32,190 | 0.5471 |
| Opus 5.5 @medium | 100 | 100 | 203.1 | 28,354 | 28,380 | 0.6550 |
| Fable 5.1 @medium | 100 | 100 | 330.4 | 30,172 | 36,550 | 2.0432 |

**Frontier spread: 0.** All three frontier runs assembled 58/58 words, matched all 7 checkpoints and 325 instructions, reproduced the keystream exactly and answered the embedded question. Haiku assembled 57/58 (first wrong address 027), diverged at step 100 against the key (step 41 against its own words), 6.8 % character accuracy on the plaintext, wrong final answer.

---

## 3. Per-finalist verdicts

Format: separates? | critics fatal? | what the critics established | recommended difficulty change. "Lost-point classification" follows the statistician critic's categories: (a) genuine error, (b) format/parsing, (c) ambiguous spec, (d) grader bug.

### 3.1 quantitative-2 — Crew Roster Across Fictional DST
- **Separates?** Tier only. 50.5 / 59 / 60 / 60. Frontier at 98-100 % (target band 60-95 %); Opus 5.5 = Fable 5.1.
- **Critics: not fatal (2/2).** Key independently reproduced from `prompt.txt` semantics (40 legs, 3 repeated-hour departures, 10 duty periods, violations [D1, D2, D5, D9], 1,646 home-base minutes; oracle OK, selftest passes). All 11 lost points across four runs are (a) genuine; 0 in (b)/(c)/(d). Structural weakness verified with `grade.py`: correct UTC pipeline with arrival-side DST ignored entirely scores 55/60; copying arr_utc into arr_local scores 42.5/60, because duty (10), violations (4) and home-base (6) points need no arrival-zone reasoning and 20 of 40 arrivals are fixed-offset or post-decree-standard; no departure is in a skipped hour despite the README. The 1-point Sonnet gap is single-run binomial noise (P(tie or reversal) ~53 % for p = 2.5 % vs 1.25 %). Minor grader gaps: integer violation IDs score 0; invalid dates alias (2027-09-31 = 10-01); trailing comma in pretty JSON falls to a 6/60 regex path; duty periods matched by start only. DOR decree wording admits a retroactive reading. Cost defect: Sonnet 5 priced at $3/$15 and 1-h cache writes priced at the 5-min rate (critics' recomputation matching Claude Code's own costUSD: Haiku $0.225, Sonnet $0.147, Opus 5.5 $0.272, Fable 5.1 $0.754 — Sonnet, not Opus 5.5, cheapest per point).
- **Difficulty change:** raise per-item difficulty, not leg count (the knob adds volume: `--legs 100` gives only 17 near-transition legs; `--legs 160` fails to build). Two or more transitions per zone inside the window, blocks > 1,440 min with arrivals in UTC+13/+14, turnarounds given in arrival-zone local (chained within a duty), duties placed within +/-20 min of 840, and a `hard` variant without the worked example / method hint. Regrade legs as two 1-point items (arr_utc, arr_local), cut duty/violations/home-base to ~10 points.

### 3.2 simulation-2 — TALLY-12
- **Separates?** Yes: 8.25 / 44.5 / 80 / 80. Sonnet vs Opus 5.5 gap 35.5 points; Opus 5.5 vs Fable 5.1 tie on score, 4.9x apart on cost.
- **Critics: not fatal (2/2).** Ground truth solid: three independent interpreters agree, `oracle.py --fuzz 300` clean, no exploitable ambiguity found (ST operand order, unsigned floor DIV, ROT, LD rd==ra, untaken-jump/HLT step counting, JLT signedness all explicit). Every lost point (Haiku -71.75, Sonnet -35.5) is (a) genuine; Sonnet's five root arithmetic errors share one signature (dropped negation after complement-multiply) and injecting its wrong r3 at OUT#6 into the reference interpreter reproduces its 929-step count — so values after the first error are genuine execution, which falsifies the prefix rule's rationale: 9 of 20 OUT r3 positions mask a random error 60-98 % of the time and the other 20 OUTs are raw memory reads. Monte-Carlo at a 5 % slip rate: prefix score SD 13.3 (10th-90th pct 2-40 of 40) vs pointwise SD 1.4. Two high-severity operational defects: the README's "fits the 64k output budget" claim is false (Fable 70,242 tokens at medium) and `runner/run.py::run_api` hard-codes `max_tokens=64000`, so under the API harness the strongest configs would be truncated and recorded invalid. Grader robustness gaps confirmed: first-JSON-object extraction grades a draft over a corrected final (20/80); float-formatted ints zero a component (54/80); string-typed program values score 0; alias order dependence; `_common` import path breaks on promotion to `tasks/`.
- **Difficulty change:** replicate Opus 5.5 and Fable 5.1 at medium (n=3) first — per-item accuracy 0.954 is still consistent with 64/64; then ship the `hard` preset (A 390 steps / 20 OUTs, B 1,088 / 40, mask 7; generated and oracle-fuzzed; projected ~41k output tokens for Opus/Sonnet, ~85k for Fable). Do not jump to `extreme` (3,600 steps, projected 99-204k output tokens): it converts capability differences into truncation failures.

### 3.3 simulation-1 — Quarry Duel
- **Separates?** Not demonstrably. {Sonnet 100, Opus 5.5 100, Fable 5.1 31}, Haiku 16. Under the null that all three share P(clean) = 2/3 the observed split has probability 0.44.
- **Critics: not fatal (2/2).** Third independent simulator written from `prompt.txt` alone reproduces `key.json` on the shipped seed and on the easy/hard presets; ~35 adversarial answers found no hedging exploit (duplicate turns, alias keys, list hedges, "P1 or P2" all gain nothing). None of 15-17 alternative rule readings reproduces Fable's t40 state, so Fable's loss is state drift, category (a); zero points in any run fall to (b)/(c)/(d). Defects: the score is a 6-level step function of first-divergence turn (probe ladder 13/27/39/53/68/82); "winner" is P2 in 115/120 medium seeds and hand_size is 4 in 76-88 % of checkpoints, giving a ~13-22 point floor; grader tolerance gaps (missing zero suits -16, 4-list stockpile -20, nested `players` -80, dict-keyed checkpoints 20/100); runner and grader disagree on first-vs-largest JSON extraction; several shipped-seed rules are non-binding (capture-before-effect ordering, 2-card draw cap, WELL reshuffle). Haiku's 16 is output-cap-confounded (31,843 of 32,000). Sonnet 5 priced at Sonnet 4.6's $3/$15 (CLI list-basis costUSD $0.3101 vs recorded $0.4316).
- **Difficulty change:** ship the `hard` preset (200 turns, 10 checkpoints, 21 captures, 5 reshuffles; projected 37-50k output tokens at the observed 183-248 tok/turn, which fits; `extreme` at 300 turns projects Fable to ~63k against a 64k cap). Add a per-turn played-card log graded as longest-correct-prefix (~40 points) and/or a mid-game resync state at turn 50 so a single slip costs time-proportional points; checkpoints every 10 turns; >=5 replicates per config over 3 rotated seeds; effort sweep low/medium/high/xhigh for Fable 5.1 and Sonnet 5.

### 3.4 composition-2 — Rail Dispatch Chain
- **Separates?** No. 77.68 / 100 / 100 / 100 at the shipped `hard` preset; 0/42 frontier route errors bounds the per-route error rate at ~7 %.
- **Critics: not fatal (2/2), but the score scale is compressed.** Oracle agrees on the shipped seed and 4 fuzzed seeds; generator reproduces prompt and key byte-for-byte; S01 hand-checked end to end; no defensible alternative reading of any rule; all Haiku losses are (a) genuine. Grader design flaws verified: with `CONDITIONAL_WEIGHT = 1.0`, a zero-search chain grades 78.57 (> Haiku 77.68); `valid_walk()` grants Stage-2 credit for paths over closed segments (98.21 with S01 on a closed segment) and silently drops unknown station tokens (98.93); the Stage-3/4 degeneracy guard is beatable (invented same-minute arrivals earn 53.57 with no work); km credit is path-independent so the engineered ties are worth ~1 point each; `rests` is requested but never scored; only 3 of 14 shipments have a second-best path within 10 km; misses cluster in 3 shared corridors so the 14 items are not independent. `extreme` (20 shipments, 1 dock, 14 closures) generates and passes the oracle but 8 of 20 shipments hit the $900 cap, masking wait errors.
- **Difficulty change:** `CONDITIONAL_WEIGHT = 0.5` (rescored: Haiku 53.57, zero-search 45-47, Sonnet 100) or report absolute and diagnostic scores side by side; reweight toward Stage 1 (e.g. 35/30/20/15 or 40/20/20/20); per-item knobs — >= half of shipments with gap-to-second-best <= 5 km, >= 4 exact km ties, the README's coupled-closure mode, corridor-overlap limit, `--docks 1`, higher fee cap; score `rests` and per-shipment fees; then re-pilot n>=3 at low and medium on all four frontier models. Until then: hold.

### 3.5 deduction-3 — Crib Slide
- **Separates?** Tier only, and the evidence is compromised. Recorded 0.21 / 54 / 60 / 60; the Fable row is not a Fable measurement.
- **Critics: one rates a finding critical; neither calls the task itself fatal.** Key sound (oracle agrees, regeneration byte-identical, no leakage; hedges and duplicates handled). Findings: (1) **critical** — the Fable 5.1 record was produced by `claude-opus-5` after a `stop_reason=refusal` (`bio` classifier) triggered Claude Code's session-scoped `model_refusal_fallback`; the runner reads only top-level usage, so it recorded model=`claude-fable-5-1`, empty notes, 107,544 output tokens priced at Fable's $50/MTok ($5.73 vs Claude Code's own $3.71). (2) **high** — 2 of 2 top-tier first attempts (Fable 5.1, Opus 5.5) were cut off by the API safety classifier on a benign cipher; Opus 5.5's record carries +94 s and +9.9k tokens of retry. (3) **high** — SEALNO/EQBLYS boundary is a spec ambiguity (the shipped `oracle.py` resolves it only through a hard-coded label table), costing Sonnet 3 points; (4) **medium** — the STOP separator is a 40-occurrence known-plaintext oracle: the 5 most frequent 4-grams are all STOP encryptions, 38/38 Kasiski distances are multiples of 11, and subtracting STOP recovers the full key with no crib sliding, so the crib/window knob is decorative and longer ciphertexts get easier; (5) rotation leniency awards 30/60 to a rotated key that decrypts to 0 % agreement while a doubled key that decrypts perfectly gets 36/60; (6) `--difficulty max` failed to build within 240 s on 2 of 4 seeds; (7) parser gaps (prose "the period is 11", `11.0`, `32.0`), README bands off by ~10 points.
- **Difficulty change:** do not promote until the refusal rate is measured (n>=5 first attempts each for Fable 5.1 and Opus 5.5) after adding a synthetic-puzzle framing line; disclose the label vocabulary or rename `SEALNO`; either remove the fixed STOP separator or re-document Kasiski-on-STOP as the primary route; move the knob toward `--pmin 10 --pmax 16 --cribs 3 --window 80` with 16-20 non-crib questions; re-run Fable 5.1 (n>=2) and patch `run_claude_code` to parse `modelUsage` / fallback iterations and mark substituted records invalid.

### 3.6 adversarial-3 — Chess Open Standings With Arbiter Errata
- **Separates?** By one point (Opus 5.5 125 vs 126 / 126), i.e. the same single-point separation the current T3/T4 already give. Haiku 53.5 is a genuine failure (0/20 players match on points+BH+SB; BH inconsistent with its own points on 15/20 players).
- **Critics: not fatal (2/2).** Independent third derivation matches all 20 players and 5 answers; oracle agrees; regeneration byte-identical; no leakage; 35 adversarial answers found no hedge (constant guess 21, rating-order prior 18, naive tally 39.5). All lost points (a) genuine; 0 in (b)/(c)/(d). Structural findings: no exact (points, BH, SB) tie exists so Regulations 5.5/5.6 are dead code; the rank sub-score (20/126) is derivable from the tie-breaks; a single missed trap flips 9-20 of 20 BH cells (score is a cliff, 44-122 per missed trap); the `extreme` preset (30x11, 34.7 KB, oracle-verified) scales cell count (40 -> 60) not trap difficulty, moving expected frontier loss from ~0.3 to ~0.6 points; the `claude-code` harness runs `claude -p` with tools enabled and `key.json` one `Read` away (transcripts confirm zero tool use in the pilot, but "permission_denials empty" is not proof); first-JSON-object extraction grades a draft over a final (86/126); `{"text": ...}` wrapper scores 0; README's naive figure 42.5 is not reproducible (39.5); runner cost differs from the CLI's list-basis cost by -18 % to +28 % across the four families.
- **Difficulty change:** a trap-interaction knob (`--interactions N`: correction of a correction, announcement withdrawn and re-issued with a different scope word, a corrected lateness figure crossing the 30-minute boundary, a phone incident naming only a near-duplicate surname, a top-3 tie decided by direct encounter) with a generator assertion that each interaction changes champion or third place; generator assertion for >= 2 decided (points, BH, SB) ties and one three-way tie; reweight rank 0.5 / BH 1.5 / SB 1.5; add a propagation-aware BH/SB sub-score. Spend ~$1.50 on a low-effort frontier pilot (n=2) before changing anything.

### 3.7 (not critiqued) simulation-3 — Cold-chain depot network
- **Separates?** Yes on this single pilot: 12 / 50 / 60 / 57, all three frontier configs distinct, Sonnet's first error at the day-20 checkpoint. No critic pass exists, so key soundness, prompt ambiguity, hedge resistance and the 15/60 chance floor have not been independently attacked. The package README reports the oracle agreeing on the shipped seed and 315 further scenarios and days 1-3 hand-checked. Two of Fable's three lost points and three of Sonnet's ten come from the fill-rate precision band (6 if within 0.0005, 3 if within 0.01), which is a tolerance choice, not a capability measurement.
- **Difficulty change:** none until critiqued; the `extreme` preset (60 days / 6 depots / shorter shelf life) exists if the frontier saturates on replication.

### 3.8 (not critiqued) composition-3 — QX-16 assemble/execute/decrypt
- **Separates?** No: 25.85 / 100 / 100 / 100 at `hard` (~325 steps). Haiku needed 107k output tokens and 737 s.
- **Difficulty change:** the `extreme` preset (~500 executed instructions, two self-modified instructions) is the only untested lever; given `composition-2`'s and `simulation-2`'s experience, volume alone is unlikely to separate Opus 5.5 from Fable 5.1, and output tokens (28-37k at medium for a 325-step trace) would scale with it. Hold.

---

## 4. Recommendation: the hard tier

Adopt four packages now, a fifth conditionally, in this order. Every fix listed was demanded by a critic and verified against the shipped files by that critic; none has been applied yet.

### 4.1 Order of adoption

**1. `simulation-2` TALLY-12 (T13 candidate) — widest tier gradient measured (10 % / 56 % / 100 % / 100 %); the only finalist where Sonnet 5 and Opus 5.5 differ by more than noise.** Fixes before promotion:
- Score `out_stream` as 0.5 x longest-correct-prefix + 0.5 x pointwise matches (rescored pilot 8.25 / 59.5 / 80 / 80); keep `first_wrong_out_index` / `out_pointwise_matches` as diagnostics; update the prompt's scoring note and README.
- Per-task output budget >= 128k in `run_api` (and record the effective cap and harness in `notes`); correct the "64k" README sentence; report output tokens as thinking-dominated.
- Score only "live" cells (registers written after setup, memory cells whose value changed) and make `steps_executed` exact-only; add generator rejections for "first OUT is a constant" and "JLT taken exactly half the iterations" (static-read floor 10.5/80 today).
- Extractors (grader and runner) prefer the LAST candidate object with program keys; coerce `768.0` -> 768; `json.loads` string-valued programs; canonical-key alias resolution; fix the `_common` import path for `tasks/`.
- Replicate Opus 5.5 / Fable 5.1 at medium (n=3), then ship `hard` (390 / 1,088 steps) as canonical with `medium` kept as a calibration rung; drop the explicit OUT counts from the hard prompt.

**2. `simulation-3` Cold-chain depot network — the only task where all three frontier configs scored differently (83 % / 95 % / 100 %), in a non-programming domain, at 11-13k output tokens and ~$0.27-0.86 per run.** It skipped the critic stage, so adoption is conditional on:
- A breaker + statistician pass equivalent to the other finalists (independent re-derivation of `key.json` from `prompt.txt`, hedge/format probes, ambiguity sweep over the five-phase ordering rules, verification of the 15/60 chance floor).
- Deciding the fill-rate band: at 6 points it is 10 % of the total and cost Fable 3 of its 3 lost points for a 0.0044 deviation; either grade it exact-or-nothing at 2 points or require the model to report the numerator and denominator.
- n>=3 replicates at medium plus low for the four frontier models before any ordering is claimed; the pilot gaps are 1-5 fields.

**3. `simulation-1` Quarry Duel — a non-programming rules-adjudication task with a proven 100-turn ceiling for Sonnet 5 / Opus 5.5 and a demonstrated Fable 5.1 drift; adopt with the gradient repaired.** Fixes:
- `hard` preset (200 turns) as default; keep `extreme` off the `claude-code` harness until Fable's output cap is raised.
- Per-turn played-card log graded as longest-correct-prefix (~40 points), checkpoints every 10 turns, and a printed resync state after turn 50 so turns 51-100 are earned independently of an early slip.
- Grader: treat missing suit keys as 0; accept a 4-list stockpile, `players`/`state` nesting, dict-keyed checkpoints; positional fallback when turn labels do not match; runner and grader both prefer the balanced object containing `checkpoints` and `final`.
- Generator `acceptable()`: coverage gate that each ordering-sensitive clause changes some checkpoint; balance the winner (P2 wins 115/120 seeds); halve `hand_size` weight or fold `winner` into scores; publish the constant-guess floor (13) in `detail`.
- Harness: export `CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000` (record it), store `thinking_tokens`, flag `output_cap_bound` when output >= 95 % of the cap.
- >=5 replicates per config over 3 rotated seeds; report P(clean) and median first-divergence turn alongside mean; effort sweep for Fable 5.1 and Sonnet 5.

**4. `adversarial-3` Chess Open Standings — a non-programming long-document task with 18 working traps and a clean grader; adopt only after the knob is changed from volume to interaction, because at `hard` it reproduces the existing one-point problem.** Fixes:
- `--interactions N` knob (compounding events listed in 3.6) with assertions that each interaction changes champion or third place; assertion for >= 2 exact (points, BH, SB) ties decided by Reg 5.6 and one three-way tie by Reg 5.5.
- Reweight rank 0.5 / BH 1.5 / SB 1.5 (drop the +/-1 rank half credit); add a propagation-aware BH/SB sub-score computed from the model's own points vector so comprehension and arithmetic are reported separately.
- Runner: `--tools ""` (or a full `--disallowedTools` list) and an empty temp cwd; assert `num_turns == 1` and no `tool_use` blocks; keep `key.json` outside the model's reach.
- Extraction: last object with `standings`; unwrap `{"text": ...}` and `answer`/`result` wrappers; store naive answers in `key.json` so the README's baseline is reproducible.
- Low-effort frontier pilot (Sonnet 5, Opus 5.5, Fable 5.1 @low, n=2, ~$1.50) before promotion; Sonnet 5 at low/medium/high (n=2) plus Haiku at high to test the effort axis.

**5 (conditional). `quantitative-2` Crew Roster — top judge pick, exact key, zero format/ambiguity losses, and it separates tiers today; adopt only if regeneration with the per-item knobs moves the frontier off 60/60.** Fixes:
- Regrade legs as two independent 1-point items or weight near-transition `arr_local` 2x; cut duty/violations/home-base to ~10 points or replace them with a question needing the 840-minute sensitivity.
- Regenerate: cap fixed-offset arrivals at ~15 % of legs, force >= 2 skipped-hour departures, bias arrivals into +/-90 min of transitions, allow 2+ transitions per zone, add > 1,440-min blocks and UTC+13/+14 arrivals, chain turnarounds within duties, remove the worked example and method hint in the hard variant.
- Grader: accept integer / digit-only violation IDs and dict-shaped legs; validate day-of-month; strip trailing commas before the regex fallback and mark unparseable records invalid rather than 6/60; match duty periods by order and downgrade internally inconsistent minutes; flag near-transition on departure-side proximity too.
- Reword the DOR decree ("abolished with effect from Sunday 26 September 2027 ...") and correct the README's skipped-hour and expected-score claims.
- Pilot n>=3 at low and high on the frontier before deciding.

**Not adopted now.** `deduction-3` (refusal rate on the top tier 2 of 2 first attempts, one record silently produced by a different model, STOP-Kasiski shortcut, SEALNO ambiguity, `max` preset unreliable) — re-enter only after the refusal-rate measurement and the runner fallback detection land. `composition-2` (frontier 100/100/100; conditional credit compresses the scale to 75-100) and `composition-3` (100/100/100, no critic pass) — hold; both need per-item difficulty knobs and a re-pilot, and neither has shown a frontier gradient.

### 4.2 Benchmark-wide runner fixes surfaced by the critics (apply before publishing any hard-tier cost figure)

- `DEFAULT_PRICES["sonnet"]` is `(3.0, 3.75, 0.3, 15.0)`; four independent critic reports state Sonnet 5's list price is $2/$10 and show that `(2.0, 2.5, 0.2, 10.0)` reproduces Claude Code's own list-basis `costUSD` for the pilot runs. Every Sonnet 5 cost in `results/` and in this report is overstated by roughly 1.5x if they are right; that flips "cheapest per point" from Opus 5.5 to Sonnet 5 on `quantitative-2`, `simulation-1`, `composition-2` and `deduction-3`.
- Cache writes are priced at the 5-minute rate (1.25x) while `claude -p` writes 1-hour caches (2x): every recorded `cost_usd` under this harness differs from the CLI's `total_cost_usd` (e.g. `simulation-3`: Opus 5.5 0.3215 vs 0.3796, Fable 0.8631 vs 1.0082). Store the CLI figure alongside `cost_usd` in every record.
- `run_claude_code` must parse `modelUsage` / fallback iterations and mark any record served by a model other than the requested one `invalid`, flag `stop_reason=refusal` attempts in `notes`, append `format_deviation: fenced|prose-wrapped` when the extractor had to strip wrapping, record `num_turns > 1` continuations, `thinking_tokens`, and the effective output cap.
- Input tokens under `claude-code` are ~80 % Claude Code system prompt; report task-prompt tokens separately or measure with the API harness.

### 4.3 Estimated cost to run the hard tier across the 31-config grid at n=2

Method (all inputs are in this repository): 31 configs = haiku x3 efforts, sonnet x5, opus48 x3, opus5 x5, opus55 x5, fable x5, fable51 x5 (from `results/summary.json`); 62 runs per task. Per-family token usage is the pilot's (Haiku from Haiku@low, others from @medium); `opus5` and `opus48` reuse Opus 5.5's token counts at their own `DEFAULT_PRICES` (5/6.25/0.5/25), `fable` reuses Fable 5.1's at (10/12.5/1.0/50). Input tokens are held constant across efforts. The **flat** column prices every effort at the pilot's medium token counts (a lower bound). The **effort-scaled** column multiplies output tokens by each family's T3 output-token ratio relative to medium measured from `results/runs/` (n=2 per cell): Haiku 0.99/1.0/1.09; Sonnet 0.56/1.0/1.38/1.5/2.14; Opus 5 (and Opus 4.8) 0.76/1.0/1.77/2.39/2.69; Opus 5.5 0.19/1.0/1.25/2.51/10.34; Fable 5 0.69/1.0/1.27/2.07/3.26; Fable 5.1 0.64/1.0/1.07/2.0/3.19 for low/medium/high/xhigh/max, capped at 4x (Opus 5.5@max's 10.34x on T3 would exceed every output cap seen in the pilots). Prices are `DEFAULT_PRICES` as shipped; with Sonnet at $2/$10 the totals fall by ~1-2 %.

| Task (preset as piloted) | Flat, 62 runs ($) | Effort-scaled, cap 4x ($) | Largest family share (scaled) |
|---|---|---|---|
| simulation-2 (medium) | 104.21 | 164.24 | fable 60.17, fable51 57.34 |
| simulation-3 (hard) | 31.73 | 44.89 | fable 12.80, fable51 12.22 |
| simulation-1 (medium, 100 turns) | 44.35 | 66.52 | fable 19.74, fable51 18.84 |
| adversarial-3 (hard) | 33.60 | 46.28 | fable 12.88, fable51 12.32 |
| quantitative-2 (hard) | 23.00 | 32.34 | fable 9.36, fable51 8.92 |
| **Four-task tier (1-4)** | **213.89** | **321.93** | |
| **Five-task tier (1-5)** | **236.89** | **354.27** | 310 runs |
| (for reference) composition-2 | 27.55 | 39.69 | |
| (for reference) composition-3 | 69.51 | 106.07 | |
| (for reference) deduction-3, as recorded incl. the invalid Fable row | 152.99 | 238.43 | |

The recommended presets are harder than the piloted ones and will raise output tokens roughly in proportion to the work: `simulation-2` `hard` has ~1.19x the executed steps (1,478 vs 1,238), `simulation-1` `hard` has 2x the turns, `adversarial-3` `extreme`/interactions ~1.5x the tie-break cells. Applying those factors to the scaled column gives roughly $195 + $45 + $133 + $69 + $32 = **~$475 for the five-task tier at n=2**, dominated by the two Fable families (54-72 % of every task's spend at $50/MTok output). Wall-clock at medium effort from the pilots: 1.5-11 min per run for the frontier configs (the outlier is `simulation-2` Fable at 661 s), 4-7 min for Haiku.

---

## 5. What the tournament could not establish

1. **Any frontier ordering.** Every cell is n=1. On `simulation-2` a per-item accuracy of 0.954 is still consistent with Opus 5.5's and Fable 5.1's 64/64; on `simulation-1` {100, 100, 31} arises 44 % of the time under equal P(clean); on `adversarial-3` and `quantitative-2` the one-point gaps are single slips at ~0.4-2.5 % per-cell error rates (P(tie or reversal) ~53 % for the Sonnet gap). Only Haiku-vs-frontier gaps are robust from single samples.
2. **The effort axis.** No frontier model was run at any effort other than `medium`; the only non-medium run per task was Haiku@low, so model and effort are confounded in the one weak cell. Whether low effort drops Opus 5.5 / Fable 5.1 off 60/60, 80/80, 100/100 or 126/126, and whether high/xhigh/max buy anything, is unmeasured. The effort multipliers used for the cost estimate come from T3, not from these tasks.
3. **`claude-opus-5`.** Named in the brief as one of the four frontier models to separate; not piloted on any candidate.
4. **Fable 5.1 on `deduction-3`.** The recorded 60/60 was generated by `claude-opus-5` after a safety-classifier refusal and a silent harness fallback; Fable's true score, time and cost on that task are unknown. The runner cannot currently detect this failure mode, so any other `claude-code` record in the repository could in principle carry the same defect.
5. **Whether the harder presets separate.** `simulation-2 hard`, `simulation-1 hard`, `adversarial-3 extreme`, `composition-2 extreme`, `composition-3 extreme` and `quantitative-2` regenerated with per-item knobs were generated and oracle-checked (where noted) but never run against a model. The critics' arithmetic (per-cell error rates x cell counts) predicts that volume-only knobs will not move the frontier; that is a prediction, not a measurement.
6. **Score variance of step-function graders.** `simulation-1`'s 6-level ladder and `simulation-2`'s prefix rule (SD 13.3 vs 1.4 pointwise) mean replicates of the same config can swing 30+ points; means over n<=3 will be bimodal. No replicate was run to measure it.
7. **Cost at list price.** Two price-table disputes (Sonnet 5 $3/$15 vs $2/$10; 5-minute vs 1-hour cache-write rate) change every cost/point ranking above; the report uses `DEFAULT_PRICES` as shipped and the CLI's own figures disagree with it by -23 % to +28 % across families. Input-token figures are dominated by harness overhead (~25k tokens per run against 5-27 KB prompts; Haiku's 123k on `adversarial-3` is a continuation artefact).
8. **API-harness comparability.** All pilots used `claude-code`; `run_api` caps `max_tokens` at 64,000, below what Fable 5.1 legitimately used on `simulation-2` (70,242) and `deduction-3`. API-harness results for the hard tier would currently be truncation-confounded.
9. **Refusal rate on `deduction-3`.** 2 of 2 top-tier first attempts were classifier-stopped; whether a framing line brings this below ~10 % needs n>=5 per model.
10. **`simulation-3` and `composition-3` soundness.** Neither received a breaker or statistician pass; `simulation-3`'s status as the best discriminator rests on one pilot and the package's own self-tests.
11. **Judge calibration.** The judge scale is not recorded in the stage data; judge rank correlated poorly with measured discrimination (judges' #1 compressed to 59/60/60, #7 spread the frontier), so the judging rubric itself should be revisited before the next proposal round.
