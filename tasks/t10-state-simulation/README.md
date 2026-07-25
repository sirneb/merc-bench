# State simulation (T10)

30 sequential warehouse-robot commands, exact final state

## What it tests and why

Sustained state tracking with conflict rules (walls, collisions, capacity, no-ops). Simulator-generated ground truth.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is embedded in `grade.py`; it was generated/validated before any model ran (see docs/methodology.md).

## What we found

Saturated for every config on exact state (two mid-effort samples dropped robot cells). Short-horizon state tracking is solved.
