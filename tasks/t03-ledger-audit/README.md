# Ledger audit (T3)

6 exact aggregates over 1,400 transaction rows, no tools

## What it tests and why

Precision aggregation at scale: balances, filtered counts, running-threshold detection, maxima, group sums, busiest-day counts. The strongest separator in the study.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

The wall battery: scores 3/6 to 6/6 by config; effort floors differ per tier (Sonnet crosses only at xhigh via a 256k-token grind; Opus 5 at medium; Fable at low). Verbosity events and output-ceiling failures live here.
