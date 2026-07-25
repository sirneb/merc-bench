# Subtle semantic bugs (E)

5 planted conceptual bugs in a search index

## What it tests and why

Novel semantic defects (document-frequency semantics, operator precedence, case asymmetry, phrase adjacency, normalization denominator) that resist pattern-matching review.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

The knowledge wall: 4.x-generation models stall at 4/5 at high effort (xhigh fixes them); 5th-generation frontier finds 5/5 even at low effort for a tenth of the escalation cost.
