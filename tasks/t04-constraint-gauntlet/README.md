# Constraint gauntlet (T4)

one essay satisfying 10 mechanical constraints

## What it tests and why

Instruction-following under load: exact word counts, an e-free paragraph, exact substring counts, ordered first words, length caps -- all machine-checkable.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Near-saturated (a published correction: the original "Sonnet 3/10 to 10/10 effort ladder" was a grading artifact from scoring JSON-wrapped text). Every tier above Haiku scores 9-10/10; Fable persistently dropped the same single constraint below xhigh; Haiku drops 1-2.
