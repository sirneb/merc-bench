# MERC — Model · Effort · Reliability · Cost

A reproducible benchmark of how **model choice × effort level** trades off against
**reliability and cost** on 12 machine-graded tasks — with every raw model answer,
every grader, every prompt, and every dollar figure shipped in this repository.

The headline result: **most tasks saturate** (every tier solves them — buy the
cheapest config), and the tasks that don't define each tier's **perfection floor**:

| Tier | Cheapest replicated-clean config (10 core tasks, n=2) | Cost | Wall-clock |
|---|---|---|---|
| Haiku 4.5 | never | $0.86–1.14/sweep | 25–29 min |
| Sonnet 5 | `@max` | $4.79 | 33 min |
| Opus 4.8 | never | $2.64–4.30/sweep | 13–22 min |
| **Opus 5** | **`@medium`** | **$2.25** | **9 min** |
| Fable 5 | `@max` | $10.66 | 27 min |

"Clean" means zero points dropped in **every** replicate. The floors follow
neither the price list nor the generation order; four of the grid's seven
replicated-clean configs belong to Opus 5. Replication killed three of our own
single-sample headlines (Opus 4.8@low's sweep, Sonnet@xhigh's crossing, "max
never wins") — the full story is in the report. Full findings: open
[`site/report.html`](site/report.html) (or regenerate it, below).

## What's in the box

```
tasks/       12 task packages: prompt.txt · schema.json · grade.py (self-contained,
             ground truth embedded) · README.md (what it tests, why, what we found)
results/     runs/*.json — every raw run record (answer + usage + cost + duration)
             scores.csv + summary.json — regenerated aggregates
runner/      run.py (portable runner: Anthropic API or Claude Code headless)
             aggregate.py (regrades everything from raw answers)
report/      generate.py + template + editorial fragments -> site/report.html
docs/        methodology, adding a model, record format
archive/     earlier tool-enabled experiment rounds (different conditions; kept for
             transparency, not part of the core dataset)
```

## Quickstart

```bash
make report          # regrade all shipped runs from raw answers, rebuild site/report.html
make verify          # same, plus fail loudly if any grade disagrees with results/scores.csv
open site/report.html
```

No dependencies beyond Python 3.10+ for grading and reporting.
(`pip install anthropic` only if you use the API runner.)

## Add a model or effort level

```bash
# Anthropic API (set ANTHROPIC_API_KEY):
python runner/run.py --harness api --model claude-opus-5 --family opus5 \
    --effort medium --tasks all --sample yours

# Claude Code subscription (no API key; uses your `claude` login):
python runner/run.py --harness claude-code --model claude-haiku-4-5 \
    --family haiku --effort medium --tasks all --sample yours

make report          # your rows appear in the map automatically
```

Non-Anthropic models, or harnesses like Codex/Cursor/your own scripts: anything
that can write a record file conforming to
[`docs/results-format.md`](docs/results-format.md) participates on equal terms —
the graders and the report consume only those records. Full walkthrough:
[`docs/adding-a-model.md`](docs/adding-a-model.md).

## Verify our numbers

Grading is recomputed from raw answers on every build; nothing published here is
hand-entered. `make verify` regrades all shipped answers and diffs against the
committed `results/scores.csv`. Ground truth was generated and validated before
any model ran (independent oracles, fuzzing, solver-verified puzzles, executed
snippets) — see [`docs/methodology.md`](docs/methodology.md), including the
corrections section (we found and fixed one of our own grading artifacts this
way; the correction is documented, not hidden).

## Provenance

Active dataset: 517 graded runs (two replicates per config) measured 2026-07-25 → 2026-07-26 across
`claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-4-8`, `claude-opus-5` and
`claude-fable-5` at effort levels low → max — every record produced through the
shipped runner (`runner/sweep.py` reruns the whole grid). The study's
first-generation dataset (284 runs, ~$131, produced through a session-bound
orchestration harness nobody can reproduce from this repo) is preserved in
`archive/workflow-runs/` for provenance and comparison. MIT licensed — data,
tasks, and code alike.
