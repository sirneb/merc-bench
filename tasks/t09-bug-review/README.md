# Bug review without tools (T9)

7 planted classic bugs in a rate limiter, pure code review

## What it tests and why

Review with no execution: boundary conditions, off-by-ones, mutable default sharing, clamp ordering, fractional truncation. Behavioral grading of the returned fixed module.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Saturated -- every config found all 7. Classic-pattern bugs are within every tier's reach; only novel semantic bugs (see e-subtle-bugs) separate.
