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
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_DIR = {
    "T1": "t01-mental-math", "T2": "t02-code-trace", "T3": "t03-ledger-audit",
    "T4": "t04-constraint-gauntlet", "T5A": "t05-logic-puzzles-5attr",
    "T5B": "t05b-logic-puzzles-4attr", "T6": "t06-strict-csv",
    "T7": "t07-knowledge-recall", "T8": "t08-regex-writing",
    "T9": "t09-bug-review", "T10": "t10-state-simulation", "E": "e-subtle-bugs",
}
DEFAULT_PRICES = {  # $/MTok: input, cache_write, cache_read, output
    "haiku": (1.0, 1.25, 0.1, 5.0), "sonnet": (3.0, 3.75, 0.3, 15.0),
    "opus48": (5.0, 6.25, 0.5, 25.0), "opus5": (5.0, 6.25, 0.5, 25.0),
    "fable": (10.0, 12.5, 1.0, 50.0),
}


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
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if effort != "none":
        cmd += ["--effort", effort]
    t0 = time.time()
    r = subprocess.run(cmd, input=full, capture_output=True, text=True,
                       timeout=3600)
    dur = time.time() - t0
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed: {r.stderr[:300]}")
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
    return answer, usage, dur



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
    last_answer = None
    for i in range(tries):
        p = prompt if i == 0 else (
            prompt + "\n\nIMPORTANT: your previous response was rejected ("
            + "; ".join(reason) +
            "). Respond again with ONLY the complete, valid JSON object.")
        try:
            answer, usage, dur = fn(model, effort, p, schema)
        except Exception as e:
            reason = [f"harness error: {e}"]
            answer, usage, dur = None, None, 0.0
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
    return last_answer, usage_total, dur_total, tries, "; ".join(reason)


def cost_usd(usage, family):
    if not usage or family not in DEFAULT_PRICES:
        return None
    p = DEFAULT_PRICES[family]
    return round((usage["input"] * p[0] + usage["cache_write"] * p[1]
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
        answer, usage, dur, attempts, fail = attempt_with_retries(
            fn, args.model, args.effort, prompt, schema)
        rec = {
            "task": tid, "model": args.model, "family": args.family,
            "effort": args.effort, "sample": args.sample,
            "harness": args.harness, "date": time.strftime("%Y-%m-%d"),
            "answer": answer,
            "usage": usage, "duration_s": round(dur, 1),
            "cost_usd": cost_usd(usage, args.family),
            "cost_basis": "standard list prices, USD/MTok",
            "cost_estimated": usage is None,
            "notes": (f"answer failed validation after {attempts} attempts: {fail}"
                      if fail else
                      (f"validated after {attempts} attempts (usage includes retries)"
                       if attempts > 1 else "")),
        }
        if fail:
            rec["invalid"] = True
        fname = f"{tid.lower()}_{args.family}_{args.effort}_{args.sample}.json"
        path = os.path.join(outdir, fname)
        json.dump(rec, open(path, "w"), indent=1)
        score = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tasks", TASK_DIR[tid], "grade.py"),
             path], capture_output=True, text=True)
        print(f"[{tid}] saved {fname} · grade: {score.stdout.strip()[:120]}")


if __name__ == "__main__":
    main()
