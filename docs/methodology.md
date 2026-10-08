# Methodology

## Design

- **One variable at a time.** Identical prompts per task; only the model or its
  effort setting changes between runs. Prompts ship verbatim in `tasks/*/prompt.txt`.
- **Ground truth before models.** Every grader's ground truth was generated and
  validated before any model ran: the recurrence/ledger/simulation answers come
  from generators; puzzle solutions are solver-verified unique; code-trace
  answers come from executing the snippets; the two bug-hunt tasks were validated
  by scoring the planted-bug baseline 0 and a reference fix perfect. During
  construction, an independent oracle plus 400 fuzzed cases caught two bugs in
  our own harness — before any model was measured.
- **No tools on core tasks.** Earlier tool-enabled rounds (kept in `archive/`)
  showed that execution access lets every tier self-verify to perfection,
  masking model differences entirely. The core dataset forbids tools; deviations
  are flagged per record in `notes`.
- **Replication.** Frontier configurations carry up to three full-sweep samples;
  the six-puzzle set has repeated attempts per configuration. Aggregates show
  min–max ranges; sample provenance is preserved per record.

- **Thirteen core tasks.** The original ten core tasks (T1–T10; E and T5B are
  supplementary) had saturated by September 2026: every frontier tier scored
  98–100 on them. Three long exact simulations (T13 TALLY-12, T14 cold-chain
  depots, T15 Quarry Duel) were added from a propose → judge → build → pilot →
  critique tournament (`candidates/TOURNAMENT.md` on the `hard-tier-candidates`
  branch) and are scored exactly like the others: they enter the reliability
  floors, the map totals and the scatter. Their graders give partial credit but a
  single slip cascades, so min–max across replicates matters more there; the
  scatter's reliability encoding is the mean share of points dropped per task so
  a 1000-point task weighs the same as a 6-point one. Each package ships a seeded
  generator with a difficulty knob, an independent oracle that must agree with
  the key, and a grader self-test.

## Measurement

- **Scores** are recomputed from raw answers by `runner/aggregate.py` on every
  build. `results/scores.csv` is a build artifact, not an input.
- **Cost** = input + cache-write + cache-read + output tokens priced at standard
  list rates (USD/MTok), from per-request logs. Two replicate batches lost usage
  records to a logging fault; those records carry `cost_usd: null` and are
  excluded from totals (map totals containing estimated cells are marked ≈).
- **Duration** is wall-clock from request timestamps.

## Corrections (found by our own verification loop)

1. **T4 under-grading.** Several runs returned JSON-wrapped text
   (`{"text": "..."}"` inside the text field). The first-pass grader scored the
   wrapper as content, producing an apparent effort ladder on the constraint
   gauntlet (Sonnet 3/10 at low → 10/10 at high) that we published and later
   retracted: grading the unwrapped essays — the same tolerant-parsing policy
   applied everywhere else — shows T4 near-saturated for every tier above Haiku.
   The shipped graders implement the corrected policy.
2. **Tolerant answer parsing.** A minority of runs answered in prose instead of
   schema JSON (notably the state-simulation task). Graders parse content out of
   prose rather than scoring format compliance; format deviations are recorded,
   not punished. Both corrections are reproducible from the shipped raw answers.
3. **T7 item 12 (2026-10-08).** "SI prefix for 10^-9?" was keyed to `nano`
   only; Haiku 5.5 answered with the symbol (`n`, or `n (nano)`) in eight of its
   ten runs and was the only config marked wrong. The key now accepts the
   symbol and the grader strips parenthesised glosses before matching. No other
   record changed score.

- **Budget overruns are data.** A run that exceeds the harness output-token
  maximum (128k under Claude Code) or the runner's one-hour wall clock is
  recorded once as a valid record with a null answer (score 0) and is not
  retried: a model that cannot finish inside the budget is a measured outcome of
  that configuration. Transport failures (CLI crash, usage-limit refusal, a
  fallback model answering) remain `invalid` and are refilled; the quarantined
  originals are kept under `results/invalid/` with their provenance. The same
  rule covers a model that returns complete responses without the requested
  JSON on every attempt (Haiku 5.5 at low effort declined the 200-turn Quarry
  Duel simulation in prose): that is the model's answer, scored 0, not a
  transport fault.
- **Capped runs are still billed.** A run cut off at the output cap carries no
  token usage in records made before 2026-10-08 (the runner now keeps it); for
  those, the aggregator uses the CLI's own list-basis cost for the attempt,
  but only for families whose CLI figure reproduces our pricing on complete
  records (every family except Sonnet 5.5, which the CLI could not price in its
  window). Cells it cannot price stay `null` and mark their sweep total ≈.

## Known limits

Synthetic, single-shot tasks ≤60 minutes without repository context; long-horizon
autonomy and agentic orchestration are out of scope. Most cells are n=1
(frontier configs n≤3). Original runs came from one account over three days
(2026-07-23 → 25) through Claude Code subagents; Opus 5 was measured from its
release day and serving stacks change. Rerun before trusting fine margins —
that's what this repository is for.
