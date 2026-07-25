# Knowledge recall (T7)

20 unambiguous technical facts, no tools or web

## What it tests and why

Parametric knowledge floor: chemistry symbols, ports, encodings, RFCs, Roman numerals. Hypothesis: bigger models know more.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Fully saturated -- 20/20 for every config and sample. Common technical knowledge has no tier gradient in 2026.
