# Strict CSV normalization (T6)

messy records to exact canonical CSV under 9 interacting rules

## What it tests and why

Attention-to-detail transform: date normalization, dedupe-by-latest, conditional quoting, multi-key sort, invalid-row filtering. Exact line-by-line grading.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Saturated at every tier and effort (rare frontier-low one-line slips). Rules-following transforms are safe on the cheapest configs.
