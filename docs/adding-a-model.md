# Adding a model (or a new effort level)

Three paths, in increasing order of independence from our tooling. All of them
end the same way: record files land in `results/runs/`, and `make report`
regrades everything and rebuilds the report with your rows in the map.

That is the **data** half. The report also carries hand-written conclusions
(findings, decision charts, claims scoreboard, limits, per-task verdicts) that
do **not** regenerate. If you are adding a model to *this* repository rather
than running it privately, work through the [complete checklist](#complete-checklist-adding-a-model-to-the-shipped-grid)
at the end of this document; the first two additions after launch (Fable 5.1
and Opus 5.5) shipped data-only and left that prose describing a six-model
grid, which is exactly the inconsistency the checklist exists to prevent.

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

Caveat: this path asks for JSON as plain text, which is fragile for small
models on long-output tasks (E's answer is a ~150-line module serialized as a
single JSON string — our haiku@medium self-test truncated mid-emission and
honestly scored 0). For E and other long-answer tasks, prefer the API runner's
forced-tool path, or rerun truncated attempts as fresh samples.

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

Every active record lives in `results/runs/` (sample tags `cc1`, `cc2` and
`selftest*`); the retired first-generation workflow-harness records are in
`archive/workflow-runs/`. Delete any subset of `results/runs/`; `make report`
rebuilds from whatever remains.

## Complete checklist: adding a model to the shipped grid

Use this when a new model (or a new effort level) becomes part of the
repository's own dataset. Do the steps in order and keep them in one branch so
the data and the prose that interprets it land together. Everything marked
**(prose)** is hand-written and will silently go stale if skipped: the
generator only warns (`make lint-prose`), it cannot write the conclusions.

### 1. Register the family

- [ ] `runner/run.py` → `DEFAULT_PRICES[family]` = `(input, cache_write, cache_read, output)` in $/MTok.
      Cache write is 1.25× input for 5-minute caches. Say in a comment where the
      prices came from (pricing page, or derived from the CLI's list-basis `costUSD`).
- [ ] `runner/sweep.py` → `GRID`: one row per effort *band*, placed next to the
      tier it belongs to (the grid runs cheap/fast bands first, `max` last).
- [ ] `runner/aggregate.py` → `FAMILY_ORDER`: insert in tier order. This fixes
      the row order of the map and every table.
- [ ] `report/config.json` → append to `models` (`family`, `name`, `model_id`,
      `color`, `price`, optional `note`/`prior_generation`) in the same tier
      position, and extend `dates` with the measurement window
      (`…; <Name>: YYYY-MM-DD → YYYY-MM-DD`).
- [ ] `report/template.html` → add the `--<family>` colour token in **both** the
      light `:root` block and the dark-mode block.

### 2. Run the grid

- [ ] Smoke-test the model id first (`claude -p --model <id> 'Reply OK'`).
- [ ] `python3 runner/sweep.py --families <family> --sample cc1`, then `--sample cc2`.
      Two replicates is the minimum for any row to be called "replicated-clean".
- [ ] Watch the log for `invalid` records. The sweep deletes and refills them for
      up to `--passes` passes; if a cell stays invalid, rerun that family later
      and note the transient failure in the commit message.
- [ ] Never edit a record by hand. A bad run is a new sample, not a fix.

### 3. Regrade and read the numbers

- [ ] `make report`. The build line prints the new family's floor
      (`floors: … <family>:<family>@<effort>`). Note it.
- [ ] From `results/summary.json`, write down for each effort of the new family:
      core-task cost and wall-clock (sum over T1–T10 excl. T5B), and every
      cell where `score_min < total` (that is a dropped point in at least one
      replicate; a config is clean only if there are none).
- [ ] Compare with the existing floors in `README.md` §"Reliability floors".
      These numbers drive every prose change below.

### 4. Update the data-facing text

- [ ] `README.md` headline table: add the row (`Tier | cheapest clean config | $ | min`).
- [ ] `README.md` prose under the table: recount "N of the grid's M
      replicated-clean configs" (M = every config with a ★ in the map).
- [ ] `README.md` §"Provenance": bump the graded-run count, add the model id
      and the measurement dates.

### 5. Update the conclusions **(prose)**

Read each fragment top to bottom asking: *does the new row change, confirm or
contradict this sentence?* Ranked by how often a new model has broken them:

- [ ] `report/template.html` §1 KPI captions. The three "big" cards summarise
      the whole grid; the floor card and the "cheap route to zero-defect" card
      name specific models and must be re-checked every time.
- [ ] `report/fragments/findings.html` **F2** (floors: must list every family and
      the replicated-clean count) and **F3** (value frontier: is the recommended
      "one config for everything hard" still the cheapest clean one?). Then F4,
      F7 (effort ladders and low→max cost multipliers per family) and F8
      (generation gaps: a same-price successor is exactly the F8 story).
- [ ] `report/fragments/decisions.html`. Each row's Use/Budget/Escalate cells
      name models. If the new model is cheaper-and-clean on the evidence the row
      cites, it replaces the recommendation; if it is not measured for that
      row, leave it out rather than guess.
- [ ] `report/fragments/scoreboard.html`. Re-grade any claim that names a model
      the new one supersedes (e.g. "Opus vs Fable" claims once a new Fable
      exists). Add a row only for a claim actually made about the new model.
- [ ] `report/fragments/limits.html`. Measurement windows, account/serving
      conditions, and anything the new run changed about the method.
- [ ] `tasks/*/README.md` → "What we found" (feeds the §5 cards). At minimum
      T3 (ledger wall) and T4 (constraint gauntlet), since they name which
      configs held clean; then any task where the new model was the only miss
      or the only pass.
- [ ] `docs/adding-a-model.md` (this file) if you changed runner flags or
      sample tags.

### 6. Verify and ship

- [ ] `make lint-prose` — fails if a family in `config.json` is missing from
      the findings, the decision chart, or the README headline table. Passing
      it is necessary, not sufficient; it cannot check that what you wrote is right.
- [ ] Commit data and prose together, then `make verify` → `VERIFY OK`
      (verify compares against the committed baseline, so run it after the commit).
- [ ] PR description: the per-effort table (cost, time, clean?), the floor,
      and any transient failures. Squash-merge.
