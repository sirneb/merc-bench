#!/usr/bin/env python3
"""Pilot runner for composition-3: mirrors runner/run.py's claude-code harness exactly."""
import json, os, subprocess, sys, time
ROOT = "/Users/neb/.claude/jobs/866a08ee/tmp/merc-bench"
sys.path.insert(0, os.path.join(ROOT, "runner"))
import run as R   # extract_json, validate_answer, cost_usd, DEFAULT_PRICES

CAND = os.path.join(ROOT, "candidates", "composition-3")
PILOT = os.path.join(CAND, "pilot")
prompt = open(os.path.join(CAND, "prompt.txt")).read()
schema = json.load(open(os.path.join(CAND, "schema.json")))

CONFIGS = [("claude-haiku-4-5", "low", "haiku"),
           ("claude-sonnet-5", "medium", "sonnet"),
           ("claude-opus-5-5", "medium", "opus55"),
           ("claude-fable-5-1", "medium", "fable51")]

def run_claude_code(model, effort, prompt, schema, tag):
    full = (prompt + "\n\nRespond with ONLY a single JSON object matching "
            "this JSON Schema (no prose, no code fences):\n" + json.dumps(schema))
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if effort != "none":
        cmd += ["--effort", effort]
    t0 = time.time()
    r = subprocess.run(cmd, input=full, capture_output=True, text=True, timeout=3600)
    dur = time.time() - t0
    open(os.path.join(PILOT, f"raw_{tag}.json"), "w").write(r.stdout)
    if r.stderr:
        open(os.path.join(PILOT, f"raw_{tag}.stderr.txt"), "w").write(r.stderr)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed: {r.stderr[:300]}")
    out = R.extract_json(r.stdout) or {}
    text = out.get("result", r.stdout)
    answer = R.extract_json(text if isinstance(text, str) else json.dumps(text))
    usage = None
    u = out.get("usage") or {}
    if u:
        usage = {"input": u.get("input_tokens", 0),
                 "cache_write": u.get("cache_creation_input_tokens", 0) or 0,
                 "cache_read": u.get("cache_read_input_tokens", 0) or 0,
                 "output": u.get("output_tokens", 0)}
    return answer, usage, dur

def attempt_with_retries(model, effort, family, tries=3):
    usage_total, dur_total, reason, last_answer = None, 0.0, [], None
    for i in range(tries):
        p = prompt if i == 0 else (prompt + "\n\nIMPORTANT: your previous response was rejected ("
             + "; ".join(reason) + "). Respond again with ONLY the complete, valid JSON object.")
        tag = f"{family}_{effort}_a{i+1}"
        try:
            answer, usage, dur = run_claude_code(model, effort, p, schema, tag)
        except Exception as e:
            reason = [f"harness error: {e}"]; answer, usage, dur = None, None, 0.0
        dur_total += dur
        if usage:
            if usage_total is None: usage_total = dict(usage)
            else:
                for k in usage_total: usage_total[k] += usage.get(k, 0)
        last_answer = answer if answer is not None else last_answer
        if R.validate_answer(answer, schema, reason):
            return answer, usage_total, dur_total, i + 1, None
    return last_answer, usage_total, dur_total, tries, "; ".join(reason)

for model, effort, family in CONFIGS:
    print(f"[C3] running {model}@{effort}...", flush=True)
    answer, usage, dur, attempts, fail = attempt_with_retries(model, effort, family)
    rec = {"task": "C3", "model": model, "family": family, "effort": effort,
           "sample": "pilot", "harness": "claude-code", "date": time.strftime("%Y-%m-%d"),
           "answer": answer, "usage": usage, "duration_s": round(dur, 1),
           "cost_usd": R.cost_usd(usage, family),
           "cost_basis": "standard list prices, USD/MTok", "cost_estimated": usage is None,
           "notes": (f"answer failed validation after {attempts} attempts: {fail}" if fail else
                     (f"validated after {attempts} attempts (usage includes retries)" if attempts > 1 else ""))}
    if fail: rec["invalid"] = True
    path = os.path.join(PILOT, f"c3_{family}_{effort}_pilot.json")
    json.dump(rec, open(path, "w"), indent=1)
    g = subprocess.run([sys.executable, os.path.join(CAND, "grade.py"), path], capture_output=True, text=True)
    open(os.path.join(PILOT, f"grade_{family}_{effort}.json"), "w").write(g.stdout + g.stderr)
    print(f"[C3] {family}@{effort} dur={dur:.0f}s usage={usage} cost={rec['cost_usd']} grade={g.stdout.strip()[:200]}", flush=True)
print("DONE", flush=True)
