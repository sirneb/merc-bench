# Logic puzzles (4-attribute, minimal clues) (T5B)

6 zebra puzzles with minimized clue sets, no tools

## What it tests and why

Pure deduction with irreducible clue sets. Used for reliability replicates: same set, repeated attempts per config.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Separates Haiku from everyone: every non-Haiku config solved all 6 in both replicates (one Fable@low sample: 5/6). Haiku@high spans 3-6/6 across samples — a wide variance band where the first generation of this study saw a crisp collapse.
