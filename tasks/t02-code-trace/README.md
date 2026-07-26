# Code trace (T2)

predict exact stdout of 8 Python snippets

## What it tests and why

Python semantics traps (mutable defaults, closure late binding, dict key collapse, try/finally returns, generator exhaustion). Ground truth produced by executing the snippets.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

A one-point noise band: scattered single misses across Haiku (all efforts), Sonnet low/medium and Opus 4.8@xhigh; perfect elsewhere. No config missed two.
