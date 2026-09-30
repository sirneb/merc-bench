#!/usr/bin/env python3
"""Run MERC tasks against a model and write run records.

Examples:
  # Anthropic API (needs ANTHROPIC_API_KEY; pip install anthropic)
  python runner/run.py --harness api --model claude-opus-5 --family opus5 \
      --effort medium --tasks all --sample mine

  # Claude Code headless (uses your local `claude` login; no API key needed)
  python runner/run.py --harness claude-code --model claude-haiku-4-5 \
      --family haiku --effort medium --tasks T1,T7 --sample mine

Any other harness (Codex, Cursor, your own script) can participate by writing
record files that conform to docs/results-format.md — the graders and report
only consume those records.
"""
import argparse
import json
import os
import re
import subprocess
import threading
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_DIR = {
    "T1": "t01-mental-math", "T2": "t02-code-trace", "T3": "t03-ledger-audit",
    "T4": "t04-constraint-gauntlet", "T5A": "t05-logic-puzzles-5attr",
    "T5B": "t05b-logic-puzzles-4attr", "T6": "t06-strict-csv",
    "T7": "t07-knowledge-recall", "T8": "t08-regex-writing",
    "T9": "t09-bug-review", "T10": "t10-state-simulation", "E": "e-subtle-bugs",
    # hard tier (added 2026-09-27 from the benchmark tournament)
    "T13": "t13-tally12-register-machine",
    "T14": "t14-cold-chain-depots",
    "T15": "t15-quarry-duel",
}
DEFAULT_PRICES = {  # $/MTok: input, cache_write (5-minute cache), cache_read, output
    "haiku": (1.0, 1.25, 0.1, 5.0),
    # Sonnet 5 lists at $2/$10 (verified 2026-09-27 against the CLI's list-basis
    # costUSD; the $3/$15 used before that date overstated every Sonnet cost ~1.5x)
    "sonnet": (2.0, 2.5, 0.2, 10.0),
    # Sonnet 5.5 (2026-09-28): same $2/$10 list price as Sonnet 5 (platform.claude.com/docs pricing page)
    "sonnet55": (2.0, 2.5, 0.2, 10.0),
    "opus48": (5.0, 6.25, 0.5, 25.0), "opus5": (5.0, 6.25, 0.5, 25.0),
    "fable": (10.0, 12.5, 1.0, 50.0),
    # Fable 5.1: same $10/$50 list price as Fable 5; cache reads are $0.25/MTok
    "fable51": (10.0, 12.5, 0.25, 50.0),
    # Opus 5.5: $4/$20 list; cache reads $0.20/MTok (derived from Claude Code list-basis costUSD)
    "opus55": (4.0, 5.0, 0.2, 20.0),
}
# `claude -p` writes 1-hour caches, billed at 2x input rather than the 5-minute
# 1.25x above. Verified for every family against the CLI's own costUSD.
CACHE_WRITE_MULT = {"api": 1.25, "claude-code": 2.0}


def load_task(tid):
    d = os.path.join(ROOT, "tasks", TASK_DIR[tid])
    return (open(os.path.join(d, "prompt.txt")).read(),
            json.load(open(os.path.join(d, "schema.json"))))


def extract_json(text):
    """Pull the first balanced JSON object out of arbitrary text."""
    text = text.strip()
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def run_api(model, effort, prompt, schema):
    import anthropic
    client = anthropic.Anthropic()
    kwargs = dict(
        model=model, max_tokens=64000,
        tools=[{"name": "submit_answer",
                "description": "Submit your final structured answer.",
                "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit_answer"},
        messages=[{"role": "user", "content": prompt}],
    )
    if effort != "none":
        kwargs["output_config"] = {"effort": effort}
    t0 = time.time()
    msg = client.messages.create(**kwargs)
    dur = time.time() - t0
    answer = None
    for block in msg.content:
        if getattr(block, "type", "") == "tool_use":
            answer = block.input
    u = msg.usage
    usage = {"input": getattr(u, "input_tokens", 0),
             "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
             "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
             "output": getattr(u, "output_tokens", 0)}
    return answer, usage, dur


def run_claude_code(model, effort, prompt, schema):
    full = (prompt + "\n\nRespond with ONLY a single JSON object matching "
            "this JSON Schema (no prose, no code fences):\n"
            + json.dumps(schema))
    # No tools: the tasks forbid them, the key files sit on disk next to the
    # runner, and an empty tool list also drops ~20k tokens of Claude Code's own
    # system prompt from every run. Records made before 2026-09-27 ran without
    # this flag (num_turns==1 and no tool use was verified on all of them).
    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--tools", ""]
    if effort != "none":
        cmd += ["--effort", effort]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, input=full, capture_output=True, text=True,
                           timeout=3600)
    except subprocess.TimeoutExpired as e:
        dur = time.time() - t0
        cli_attempts().append({"served": [], "stop_reason": "timeout",
                               "tools": "disabled", "num_turns": None,
                               "thinking_tokens": None, "total_cost_usd": None,
                               "duration_s": round(dur, 1)})
        raise RuntimeError(f"claude -p timed out after {dur:.0f}s") from e
    dur = time.time() - t0
    if r.returncode != 0:
        cli_attempts().append({"served": [], "stop_reason": "cli_error",
                               "tools": "disabled", "num_turns": None,
                               "thinking_tokens": None, "total_cost_usd": None,
                               "returncode": r.returncode, "duration_s": round(dur, 1),
                               "stderr_tail": r.stderr[-600:], "stdout_tail": r.stdout[-300:]})
        raise RuntimeError(f"claude -p exit {r.returncode} after {dur:.0f}s: "
                           f"{r.stderr.strip()[-200:] or r.stdout.strip()[-200:]}")
    out = extract_json(r.stdout) or {}
    text = out.get("result", r.stdout)
    answer = extract_json(text if isinstance(text, str) else json.dumps(text))
    usage = None
    u = out.get("usage") or {}
    if u:
        usage = {"input": u.get("input_tokens", 0),
                 "cache_write": u.get("cache_creation_input_tokens", 0) or 0,
                 "cache_read": u.get("cache_read_input_tokens", 0) or 0,
                 "output": u.get("output_tokens", 0)}
    # Provenance the CLI reports per attempt. `served` is the set of models that
    # actually produced tokens: Claude Code silently falls back to another model
    # after a safety-classifier refusal, and that answer must not be scored as
    # the requested model.
    mu = out.get("modelUsage") or {}
    cli_attempts().append({
        "served": sorted(mu.keys()),
        "stop_reason": out.get("stop_reason"),
        "tools": "disabled",
        "num_turns": out.get("num_turns"),
        "thinking_tokens": ((u.get("output_tokens_details") or {})
                            .get("thinking_tokens")),
        "total_cost_usd": out.get("total_cost_usd"),
    })
    return answer, usage, dur


_TLS = threading.local()


def cli_attempts():
    """Per-thread list of CLI attempt provenance, so concurrent runners (e.g.
    candidates/pilot.py's worker pool) never mix attempts across records."""
    if not hasattr(_TLS, "attempts"):
        _TLS.attempts = []
    return _TLS.attempts



def validate_answer(answer, schema, reason=[]):
    """Cheap structural validation + deep checks that catch truncation."""
    del reason[:]
    if not isinstance(answer, dict):
        reason.append("no JSON object could be parsed from the response")
        return False
    for key in schema.get("required", []):
        if key not in answer:
            reason.append(f"missing required key '{key}'")
            return False
    for key, spec in schema.get("properties", {}).items():
        if key in answer and spec.get("type") == "array" and \
                not isinstance(answer[key], list):
            reason.append(f"'{key}' is not an array")
            return False
    code = answer.get("fixed_code") or answer.get("code")
    if isinstance(code, str) and code.strip():
        try:
            compile(code, "<answer>", "exec")
        except SyntaxError as e:
            reason.append(f"returned code does not parse: {e}")
            return False
    return True


def attempt_with_retries(fn, model, effort, prompt, schema, tries=3):
    """Run fn, validating the answer; retry with a corrective note on failure.
    Returns (answer, usage_total, duration_total, attempts, fail_reason)."""
    usage_total = None
    dur_total = 0.0
    reason = []
    errors = []  # one entry per failed attempt, in order
    last_answer = None
    for i in range(tries):
        p = prompt if i == 0 else (
            prompt + "\n\nIMPORTANT: your previous response was rejected ("
            + "; ".join(reason) +
            "). Respond again with ONLY the complete, valid JSON object.")
        harness_err = None
        t_att = time.time()
        try:
            answer, usage, dur = fn(model, effort, p, schema)
        except Exception as e:
            harness_err = f"harness error: {e}"
            answer, usage, dur = None, None, time.time() - t_att
        dur_total += dur
        if usage:
            if usage_total is None:
                usage_total = dict(usage)
            else:
                for k in usage_total:
                    usage_total[k] += usage.get(k, 0)
        last_answer = answer if answer is not None else last_answer
        if validate_answer(answer, schema, reason):
            return answer, usage_total, dur_total, i + 1, None
        if harness_err:
            reason[:] = [harness_err]
        errors.append(reason[0] if reason else "?")
        # A retry only helps when the model produced a malformed answer. If the
        # CLI reports the response was cut off by the output cap, or ended in a
        # safety refusal, the same prompt will do the same again: stop here and
        # let the record be marked invalid instead of burning two more attempts.
        stop = (cli_attempts()[-1].get("stop_reason") if cli_attempts() else None)
        if stop in ("max_tokens", "refusal"):
            errors[-1] += f" (stop_reason={stop}; not retrying)"
            return last_answer, usage_total, dur_total, i + 1, " | ".join(
                f"attempt {k + 1}: {e}" for k, e in enumerate(errors))
    return last_answer, usage_total, dur_total, tries, " | ".join(
        f"attempt {k + 1}: {e}" for k, e in enumerate(errors))


def cost_usd(usage, family, harness="api"):
    """List-price cost of a run. cache_write is billed at the harness's cache
    TTL rate: the API runner writes 5-minute caches (the table's 1.25x), while
    `claude -p` writes 1-hour caches (2x input)."""
    if not usage or family not in DEFAULT_PRICES:
        return None
    p = DEFAULT_PRICES[family]
    cw = p[0] * CACHE_WRITE_MULT.get(harness, 1.25)
    return round((usage["input"] * p[0] + usage["cache_write"] * cw
                  + usage["cache_read"] * p[2] + usage["output"] * p[3]) / 1e6, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", choices=["api", "claude-code"], required=True)
    ap.add_argument("--model", required=True, help="exact model id passed to the harness")
    ap.add_argument("--family", required=True,
                    help="short display key used for grouping and pricing (e.g. opus5; new models: any slug)")
    ap.add_argument("--effort", default="none",
                    help="low|medium|high|xhigh|max|none (none = do not send an effort setting)")
    ap.add_argument("--tasks", default="all", help="all or comma list, e.g. T1,T3,E")
    ap.add_argument("--sample", default="s1", help="free-form sample tag")
    ap.add_argument("--price-in", type=float, help="override $/MTok input for cost calc")
    ap.add_argument("--price-out", type=float, help="override $/MTok output for cost calc")
    args = ap.parse_args()

    if args.price_in and args.price_out:
        DEFAULT_PRICES[args.family] = (args.price_in, args.price_in * 1.25,
                                       args.price_in * 0.1, args.price_out)

    tids = list(TASK_DIR) if args.tasks == "all" else \
        [t.strip().upper() for t in args.tasks.split(",")]
    outdir = os.path.join(ROOT, "results", "runs")
    os.makedirs(outdir, exist_ok=True)

    for tid in tids:
        prompt, schema = load_task(tid)
        print(f"[{tid}] running {args.model}@{args.effort} via {args.harness}...",
              flush=True)
        fn = run_api if args.harness == "api" else run_claude_code
        del cli_attempts()[:]
        CLI_ATTEMPTS = cli_attempts()
        answer, usage, dur, attempts, fail = attempt_with_retries(
            fn, args.model, args.effort, prompt, schema)
        notes = []
        if fail:
            notes.append(f"answer failed validation after {attempts} attempts: {fail}")
        elif attempts > 1:
            notes.append(f"validated after {attempts} attempts (usage includes retries)")
        rec = {
            "task": tid, "model": args.model, "family": args.family,
            "effort": args.effort, "sample": args.sample,
            "harness": args.harness, "date": time.strftime("%Y-%m-%d"),
            "answer": answer,
            "usage": usage, "duration_s": round(dur, 1),
            "cost_usd": cost_usd(usage, args.family, args.harness),
            "cost_basis": "standard list prices, USD/MTok",
            "cost_estimated": usage is None,
            "notes": "",
        }
        if fail:
            rec["invalid"] = True
        if CLI_ATTEMPTS:
            served = sorted({m for a in CLI_ATTEMPTS for m in a["served"]})
            rec["cli"] = {
                "attempts": CLI_ATTEMPTS[:],
                "served_models": served,
                "total_cost_usd": round(sum(a["total_cost_usd"] or 0
                                            for a in CLI_ATTEMPTS), 4),
            }
            refusals = [a for a in CLI_ATTEMPTS if a["stop_reason"] == "refusal"]
            if refusals:
                notes.append(f"{len(refusals)} attempt(s) ended with stop_reason=refusal")
            if any(a["num_turns"] and a["num_turns"] > 1 for a in CLI_ATTEMPTS):
                notes.append("multi-turn continuation (output cap hit)")
            wrong = [m for m in served if m != args.model]
            if wrong:
                # Claude Code's model_refusal_fallback answered with another model
                rec["invalid"] = True
                notes.append(f"served by {','.join(wrong)} instead of {args.model}"
                             " (harness fallback); not a score for this model")
        rec["notes"] = "; ".join(notes)
        fname = f"{tid.lower()}_{args.family}_{args.effort}_{args.sample}.json"
        path = os.path.join(outdir, fname)
        json.dump(rec, open(path, "w"), indent=1)
        score = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tasks", TASK_DIR[tid], "grade.py"),
             path], capture_output=True, text=True)
        print(f"[{tid}] saved {fname} · grade: {score.stdout.strip()[:120]}")


if __name__ == "__main__":
    main()
