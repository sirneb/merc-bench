# Ledger audit (T3)

6 exact aggregates over 1,400 transaction rows, no tools

## What it tests and why

Precision aggregation at scale: balances, filtered counts, running-threshold detection, maxima, group sums, busiest-day counts. The strongest separator in the study.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

The wall battery — the dataset's lone hard separator, and the noisiest cell in the grid: Opus 4.8 spans 3-6/6 across replicates at every effort, Haiku 4.5 2-5/6, Haiku 5.5 3-6/6 (never clean; at max its thinking exhausts the 128k output cap in both replicates and it scores 0). Only Opus 5 (medium up), Opus 5.5 (medium up), Sonnet 5.5 (high up), Fable 5.1 (every effort), Sonnet 5@max and Fable 5@max held 6/6 in both replicates; Opus 5.5@low dropped one (4-5/6), Sonnet 5.5 dropped one at low and one or two at medium. The biggest token grinds live here.
