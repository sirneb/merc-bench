# Code trace (T2)

predict exact stdout of 8 Python snippets

## What it tests and why

Python semantics traps (mutable defaults, closure late binding, dict key collapse, try/finally returns, generator exhaustion). Ground truth produced by executing the snippets.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Walls Haiku only (6/8 at high, 7/8 at low). Everything Sonnet@low and up is perfect, with rare one-point slips at frontier low effort.
