# MERC — Model · Effort · Reliability · Cost

A reproducible benchmark of how **model choice × effort level** trades off against
**reliability and cost** on 15 machine-graded tasks (13 core, two supplementary) — with every raw model answer,
every grader, every prompt, and every dollar figure shipped in this repository.

The headline result: **most tasks saturate** (every tier solves them — buy the
cheapest config), and the tasks that don't define each tier's **perfection floor**:

| Tier | Cheapest replicated-clean config (13 core tasks, n=2) | Cost | Wall-clock |
|---|---|---|---|
| Haiku 4.5 | never | $1.84–2.43/sweep | 43–60 min |
| Haiku 5.5 | never | $0.18–1.12/sweep | 18–111 min |
| Sonnet 5 | never | $1.57–13.81/sweep | 11–162 min |
| Sonnet 5.5 | never | $1.69–11.24/sweep | 12–150 min |
| Opus 4.8 | never | $11.63–25.46/sweep | 61–203 min |
| Opus 5 | never | $5.24–16.93/sweep | 23–84 min |
| **Opus 5.5** | **`@xhigh`** | **$7.22** | **32 min** |
| Fable 5 | never | $11.19–50.69/sweep | 35–142 min |
| Fable 5.1 | `@xhigh` | $19.61 | 48 min |

"Clean" means zero points dropped in **every** replicate of all thirteen core
tasks. Only two families ever get there: Opus 5.5 from `@xhigh`, and Fable 5.1
from `@xhigh` at 2.7× the price. What stops everyone else is almost always one
task — cold-chain (T14), a 30-day perishable-inventory simulation that Opus 5
holds in one run out of two at every effort, Fable 5 never holds twice, and
Sonnet 5.5 holds from medium while dropping Quarry Duel. Haiku 5.5, added in
October 2026 at a tenth of Haiku 4.5's list price, is never clean either — a
ledger point at every effort, and from `@high` its thinking exhausts the 128k
output cap on TALLY-12 and Quarry Duel — but it holds cold-chain twice at
`@xhigh` and `@max` and clears the saturated ten (bar the ledger) for $0.04–0.37.
Ten of the thirteen tasks are saturated (every tier above the Haiku pair scores
98–100 % on them); on those
ten alone the cheapest clean configs are Sonnet 5.5 `@xhigh` ($1.29), Opus 5
`@medium` ($2.76), Opus 5.5 `@xhigh` and Fable 5.1 `@xhigh` — which is why
T13–T15 were added in September 2026, from a propose → judge → build → pilot →
critique tournament (`candidates/TOURNAMENT.md` on the `hard-tier-candidates`
branch). Effort has a ceiling: above xhigh, max buys Opus 5.5 and Fable 5.1
nothing, and on the Sonnet tier it overruns the 128k output cap or the one-hour
wall clock and scores zero (recorded as null answers). Replication killed three
of our own single-sample headlines (Opus 4.8@low's sweep, Sonnet@xhigh's
crossing, "max never wins") — the full story is in the report. Full findings:
open [`site/report.html`](site/report.html) (or regenerate it, below).

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
[`docs/adding-a-model.md`](docs/adding-a-model.md) — including the
[checklist](docs/adding-a-model.md#complete-checklist-adding-a-model-to-the-shipped-grid)
for adding a model to the shipped grid, since the report's conclusions are
hand-written and do not regenerate with the data.

## Verify our numbers

Grading is recomputed from raw answers on every build; nothing published here is
hand-entered. `make verify` regrades all shipped answers and diffs against the
committed `results/scores.csv`. Ground truth was generated and validated before
any model ran (independent oracles, fuzzing, solver-verified puzzles, executed
snippets) — see [`docs/methodology.md`](docs/methodology.md), including the
corrections section (we found and fixed one of our own grading artifacts this
way; the correction is documented, not hidden).

## Provenance

Active dataset: 1,269 graded runs (two replicates per config; a few cells carry three) measured
2026-07-25 → 2026-07-26 (core grid), 2026-09-01 → 09-02 (Fable 5.1), 2026-09-26 (Opus 5.5),
2026-09-27 → 10-03 (Sonnet 5.5 on all tasks; T13–T15 on every config) and 2026-10-08 (Haiku 5.5) across
`claude-haiku-4-5`, `claude-haiku-5-5`, `claude-sonnet-5`, `claude-sonnet-5-5`, `claude-opus-4-8`, `claude-opus-5`,
`claude-opus-5-5`, `claude-fable-5` and `claude-fable-5-1` at effort levels low → max — every record
produced through the shipped runner (`runner/sweep.py` reruns the whole grid). Runs from 2026-09-27
on use `claude -p --tools ""`; earlier runs carry ~20k extra harness system-prompt tokens per call
(see Limits in the report). A harness budget overrun — the 128k output-token cap or the runner's
one-hour wall clock — is recorded once as a null answer (score 0), not retried and not quarantined; so is a
complete response that never contains the requested JSON (a model declining the task in prose). Capped runs
are billed from the CLI's own list-basis cost where that basis is verified for the family (all but Sonnet 5.5,
which the CLI could not price in its window — its `@max` sweep is therefore flagged ≈ and understated). The study's
first-generation dataset (284 runs, ~$131, produced through a session-bound
orchestration harness nobody can reproduce from this repo) is preserved in
`archive/workflow-runs/` for provenance and comparison. MIT licensed — data,
tasks, and code alike.
