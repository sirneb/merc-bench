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

## Known limits

Synthetic, single-shot tasks ≤60 minutes without repository context; long-horizon
autonomy and agentic orchestration are out of scope. Most cells are n=1
(frontier configs n≤3). Original runs came from one account over three days
(2026-07-23 → 25) through Claude Code subagents; Opus 5 was measured from its
release day and serving stacks change. Rerun before trusting fine margins —
that's what this repository is for.
