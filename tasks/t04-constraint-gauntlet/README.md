# Constraint gauntlet (T4)

one essay satisfying 10 mechanical constraints

## What it tests and why

Instruction-following under load: exact word counts, an e-free paragraph, exact substring counts, ordered first words, length caps -- all machine-checkable.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Near-saturated (a published correction: the original "Sonnet 3/10 to 10/10 effort ladder" was a grading artifact from scoring JSON-wrapped text). Every tier above Haiku scores 9-10/10; Fable 5 persistently dropped the same single constraint at every effort below max, in both replicates; Fable 5.1 does the same below xhigh; Opus 5.5 dropped it in one replicate at medium and high (clean at low, xhigh and max); Sonnet 5.5 dropped it in both replicates at low and once at high; Sonnet 5 never dropped it; Haiku 4.5 drops 1-2; Haiku 5.5 dropped one point once at medium and once at high, clean at low, xhigh and max.
