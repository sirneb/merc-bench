# Run record format

One JSON file per run in `results/runs/`, named
`<task>_<family>_<effort>_<sample>.json` (lowercase task id). Any harness that
writes this format participates fully — runner, graders and report make no other
assumptions.

```json
{
  "task": "T3",                      // T1..T10, T5A, T5B, E  (see tasks/)
  "model": "claude-opus-5",          // exact model id as served
  "family": "opus5",                 // short grouping key; new models: pick any slug
  "effort": "medium",                // low|medium|high|xhigh|max|none
  "sample": "canonical",             // free tag; reruns of the same config get new tags
  "harness": "api",                  // api | claude-code | codex | cursor | ...
  "date": "2026-07-24",
  "answer": { ... },                 // the model's structured answer (see tasks/<dir>/schema.json)
  "usage": {                         // token counts, or null if unavailable
    "input": 123, "cache_write": 456, "cache_read": 789, "output": 1011
  },
  "duration_s": 42.5,                // wall-clock, or null
  "cost_usd": 0.1234,                // computed at your price basis, or null
  "cost_basis": "standard list prices, USD/MTok",
  "cost_estimated": false,           // true when usage/cost is estimated or missing
  "notes": ""                        // condition deviations (e.g. "tools were available")
}
```

Rules of the road:

- **`answer` is sacred** — store exactly what the model produced (the structured
  object; if your harness only gives you text, store the raw text as a string and
  the graders will parse it tolerantly). Grading is always recomputed from it.
- **Effort `none`** is for models/harnesses without an effort control; don't fake one.
- **Never overwrite someone else's record** — pick a fresh `sample` tag. Multiple
  samples of the same config are aggregated as min–max ranges automatically.
- **Deviations go in `notes`**, not in silence: tool availability, retries,
  truncation, raised output limits.
- New model families: add a display entry to `report/config.json` (name, color,
  price) — unknown families still render with defaults.
