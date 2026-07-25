# Constraint gauntlet (T4)

one essay satisfying 10 mechanical constraints

## What it tests and why

Instruction-following under load: exact word counts, an e-free paragraph, exact substring counts, ordered first words, length caps -- all machine-checkable.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

The cleanest effort ladder: Sonnet 3/10 at low to 10/10 at high. Haiku walls (2-8/10). Frontier low effort slips here in some samples; max regressed once (the e-free rule).
