# Mental math (T1)

16 exact computations, no tools

## What it tests and why

Tests exact arithmetic under load: 4-digit products, signed sums, modular exponentiation, compound percentages. Hypothesis: tier gaps and effort gains on raw computation.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Near-saturated: only Haiku@high missed one item (a mod-pow). Effort spent up to 4.3x tokens for identical scores. 2026 frontier and mid-tier models simply do arithmetic.
