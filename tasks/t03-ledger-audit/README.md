# Ledger audit (T3)

6 exact aggregates over 1,400 transaction rows, no tools

## What it tests and why

Precision aggregation at scale: balances, filtered counts, running-threshold detection, maxima, group sums, busiest-day counts. The strongest separator in the study.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

The wall battery — the dataset's lone hard separator. Perfect-sweep floors: Opus 5@medium, Opus 4.8@low, Sonnet@xhigh, Fable@xhigh; Haiku never crosses and its score falls as effort rises. The biggest token grinds live here.
