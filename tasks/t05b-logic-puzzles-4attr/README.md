# Logic puzzles (4-attribute, minimal clues) (T5B)

6 zebra puzzles with minimized clue sets, no tools

## What it tests and why

Pure deduction with irreducible clue sets. Used for reliability replicates: same set, repeated attempts per config.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Separates hard: Haiku 2/6; Sonnet@low perfect on all attempts; mid-effort Fable failed the same puzzle by the same 2 cells in 2 of 4 attempts (a last-mile verification skip); Opus 5 clean on 8 attempts.
