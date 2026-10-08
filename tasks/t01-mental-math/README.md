# Mental math (T1)

16 exact computations, no tools

## What it tests and why

Tests exact arithmetic under load: 4-digit products, signed sums, modular exponentiation, compound percentages. Hypothesis: tier gaps and effort gains on raw computation.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Near-saturated: only Haiku 4.5 drops an item (n=1 cells); Haiku 5.5 is clean at every effort. Effort spends multiples of tokens for identical scores. 2026 models simply do arithmetic.
