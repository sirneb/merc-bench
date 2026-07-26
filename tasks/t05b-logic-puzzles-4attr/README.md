# Logic puzzles (4-attribute, minimal clues) (T5B)

6 zebra puzzles with minimized clue sets, no tools

## What it tests and why

Pure deduction with irreducible clue sets. Used for reliability replicates: same set, repeated attempts per config.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Separates by effort direction, not tier: Haiku solves all 6 at low and medium but collapses at high (replicated in both study generations); every other config is perfect except one Fable@low sample (5/6).
