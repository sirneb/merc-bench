# Subtle semantic bugs (E)

5 planted conceptual bugs in a search index

## What it tests and why

Novel semantic defects (document-frequency semantics, operator precedence, case asymmetry, phrase adjacency, normalization denominator) that resist pattern-matching review.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

The generation wall: Opus 4.8 stalls at 4/5 below xhigh in both study generations; Opus 5 and Fable find 5/5 at every effort. Sonnet crosses at high; Haiku is noisy (3-5/5).
