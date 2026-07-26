# Regex writing without testing (T8)

8 fullmatch patterns against trap sets, graded by execution

## What it tests and why

Write-only correctness: the model cannot test its patterns; the grader executes them against must-match / must-not-match sets.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Saturated on score (8/8 everywhere, one Haiku@low 7/8) with a large efficiency tell: cost and wall-clock vary by an order of magnitude for the same result.
