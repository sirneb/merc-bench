# Adding a model (or a new effort level)

Three paths, in increasing order of independence from our tooling. All of them
end the same way: record files land in `results/runs/`, and `make report`
regrades everything and rebuilds the report with your rows in the map.

## Path 1 — Anthropic API runner

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
python runner/run.py --harness api \
    --model claude-sonnet-5 --family sonnet --effort medium \
    --tasks all --sample $(whoami)-1
make report
```

- `--tasks all` runs the 10 core tasks + E + T5B; or pass a comma list (`T1,T3,E`).
- `--effort none` for models without the effort parameter.
- For non-Claude pricing, pass `--price-in`/`--price-out` ($/MTok) so `cost_usd`
  is computed on your basis (and say so in the record's `cost_basis`).
- The API runner forces a `submit_answer` tool call with the task's JSON schema,
  which is how the original dataset enforced structured answers.

## Path 2 — Claude Code headless (subscription, no API key)

```bash
python runner/run.py --harness claude-code \
    --model claude-opus-5 --family opus5 --effort low \
    --tasks all --sample $(whoami)-1
```

Uses your local `claude` login via `claude -p`. Structured answers are requested
as JSON-only output and parsed tolerantly; usage/cost fields are captured when
the CLI reports them (otherwise the record is marked `cost_estimated`).

## Path 3 — any other harness (Codex, Cursor, OpenAI, local models, humans…)

You don't need our runner at all:

1. For each task directory in `tasks/`, feed the model `prompt.txt` and obtain an
   answer conforming to `schema.json` (ask for JSON-only output; the graders
   parse tolerantly and, where the answer is prose, extract what they can).
2. Write one record per run following [`results-format.md`](results-format.md)
   into `results/runs/` (unique `sample` tag; exact `model` id; honest `notes`).
3. `make report`.

Conditions that keep runs comparable to the shipped dataset:

- **No tools** during the task (no code execution, no web) — this is the single
  most important condition; tool access saturates several tasks completely.
- One shot per record: no retries folded into a single record (a retry is a new
  sample).
- Don't paraphrase prompts; don't truncate them (T3's prompt is ~67KB by design).
- Allow long responses: precision tasks at high effort can produce 40k–250k+
  output tokens on some models. If your harness caps response length, either
  raise the cap or record the failure honestly (`answer: null` + `notes`) — both
  outcomes are data.

## Grading a single run by hand

```bash
python tasks/t03-ledger-audit/grade.py results/runs/t3_opus5_medium_yours.json
# -> {"task": "T3", "score": 6, "total": 6, "detail": {}}
```

## Removing our data

Every original record lives in `results/runs/` with sample tags from the study
(`r3`, `s1`, `s2`, `canonical`, `esc`, `probe`, `grid`, `r2`). Delete any subset;
`make report` rebuilds from whatever remains.
