# Logic puzzles (5-attribute) (T5A)

3 zebra puzzles, 25 cells each, solver-verified unique, no tools

## What it tests and why

Deduction with a bigger grid. Hypothesis: scale deepens the reasoning wall.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Hypothesis rejected -- saturated for every config above Haiku 4.5, Haiku 5.5 included at every effort (richer clue sets propagate more easily; difficulty is clue minimality, not grid size). Haiku@medium dropped cells on two puzzles and Sonnet 5.5@high dropped one cell in one replicate — the only misses recorded.
