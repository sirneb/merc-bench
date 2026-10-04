# MERC — Model · Effort · Reliability · Cost

A reproducible benchmark of how **model choice × effort level** trades off against
**reliability and cost** on 12 machine-graded tasks — with every raw model answer,
every grader, every prompt, and every dollar figure shipped in this repository.

The headline result: **most tasks saturate** (every tier solves them — buy the
cheapest config), and the tasks that don't define each tier's **perfection floor**:

| Tier | Cheapest replicated-clean config (10 core tasks, n=2) | Cost | Wall-clock |
|---|---|---|---|
| Haiku 4.5 | never | $0.93–1.21/sweep | 25–29 min |
| Sonnet 5 | `@max` | $3.55 | 33 min |
| **Sonnet 5.5** | **`@xhigh`** | **$1.29** | **9 min** |
| Opus 4.8 | never | $3.11–4.77/sweep | 13–22 min |
| Opus 5 | `@medium` | $2.76 | 9 min |
| Opus 5.5 | `@xhigh` | $3.08 | 10 min |
| Fable 5 | `@max` | $11.53 | 27 min |
| Fable 5.1 | `@xhigh` | $8.03 | 16 min |

"Clean" means zero points dropped in **every** replicate. The floors follow
neither the price list nor the generation order. Sonnet 5.5 (added
2026-09-28) takes the cheapest-clean crown from Opus 5 — clean twice at `@xhigh`
for $1.29, less than half Opus 5@medium's $2.76 and a third of Sonnet 5@max —
though note it ran on the tools-disabled harness, which trims ~$0.36 of
system-prompt tokens from a Sonnet sweep (≈$1.65 like-for-like, still the
cheapest). Four of the grid's twelve replicated-clean configs still belong to
Opus 5; Opus 5.5 is clean from `@xhigh`, its lower list price paid back in two
extra effort steps; Fable 5.1 moved the Fable tier's floor down one step to
`@xhigh`. Replication killed three of our own
single-sample headlines (Opus 4.8@low's sweep, Sonnet@xhigh's crossing, "max
never wins") — the full story is in the report. Full findings: open
[`site/report.html`](site/report.html) (or regenerate it, below).

## The hard tier (T13–T15)

By September 2026 the ten core tasks had saturated: every frontier tier scored
98–100 and the floors above were being decided by single flaky points. Three
harder tasks were added from a propose → judge → build → pilot → critique
tournament (`candidates/TOURNAMENT.md` on the `hard-tier-candidates` branch) and
run across the whole grid at n=2 (2026-09-27 → 10-03, tools disabled):

| | TALLY-12 (T13) | Cold-chain depots (T14) | Quarry Duel (T15) |
|---|---|---|---|
| What it is | execute two programs on an invented 12-bit CPU | 30-day, 4-depot perishable-inventory simulation | play both sides of a 200-turn card game |
| Points | 80 | 60 | 1000 |
| Replicated-clean configs | 13 of 36 | **7 of 36** | 13 of 36 |

Hard-tier results are reported on mean % of points, min–max and P(clean), not
the binary floor, because one slip cascades (§3b of the report). The headline:
**Opus 5.5 is the only model clean on all three tasks in both replicates — at
high, xhigh and max — for $2.37 and 13 minutes at high.** Fable 5.1 matches it
only from xhigh ($11.33, 31 min). Cold-chain is the separator: Opus 5 and 4.8
collapse on it in one of every two runs at every effort, Fable 5 never holds it
twice, Sonnet 5.5 holds it at medium for $0.20 but drops a third of Quarry Duel.
Sonnet 5 peaks at medium and *degrades* above it: at max it overruns the
128k-token output cap on Quarry Duel and the one-hour wall clock on TALLY-12
(recorded as null answers, scored 0). Haiku scores 3–17 % everywhere.

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

Active dataset: 1,119 graded runs (two replicates per config; a few cells carry three) measured
2026-07-25 → 2026-07-26 (core grid), 2026-09-01 → 09-02 (Fable 5.1), 2026-09-26 (Opus 5.5), and
2026-09-27 → 10-03 (Sonnet 5.5 on all tasks; the T13–T15 hard tier on every config) across
`claude-haiku-4-5`, `claude-sonnet-5`, `claude-sonnet-5-5`, `claude-opus-4-8`, `claude-opus-5`,
`claude-opus-5-5`, `claude-fable-5` and `claude-fable-5-1` at effort levels low → max — every record
produced through the shipped runner (`runner/sweep.py` reruns the whole grid). Runs from 2026-09-27
on use `claude -p --tools ""`; earlier runs carry ~20k extra harness system-prompt tokens per call
(see Limits in the report). A harness budget overrun — the 128k output-token cap or the runner's
one-hour wall clock — is recorded once as a null answer (score 0), not retried and not quarantined. The study's
first-generation dataset (284 runs, ~$131, produced through a session-bound
orchestration harness nobody can reproduce from this repo) is preserved in
`archive/workflow-runs/` for provenance and comparison. MIT licensed — data,
tasks, and code alike.
