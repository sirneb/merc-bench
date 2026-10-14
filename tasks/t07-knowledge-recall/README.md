# Knowledge recall (T7)

20 unambiguous technical facts, no tools or web

## What it tests and why

Parametric knowledge floor: chemistry symbols, ports, encodings, RFCs, Roman numerals. Hypothesis: bigger models know more.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Fully saturated -- 20/20 for every config and sample, after one grading correction (2026-10-08): item 12 ("SI prefix for 10^-9?") was keyed to `nano` only, and Haiku 5.5 answered with the symbol (`n` or `n (nano)`) in eight of its ten runs — the only config ever marked wrong on it. The key now accepts the symbol and the grader strips parenthesised glosses; no other record changed. Common technical knowledge has no tier gradient in 2026.
