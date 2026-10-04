#!/usr/bin/env python3
"""Pilot runner for candidate simulation-1: reproduces runner/run.py's claude-code
harness invocation (flags, retries, usage accounting, DEFAULT_PRICES) for one config."""
import json, os, subprocess, sys, time
ROOT = "/Users/neb/.claude/jobs/866a08ee/tmp/merc-bench"
CAND = os.path.join(ROOT, "candidates", "simulation-1")
PILOT = os.path.join(CAND, "pilot")
sys.path.insert(0, os.path.join(ROOT, "runner"))
import run as R  # reuse extract_json, validate_answer, cost_usd, DEFAULT_PRICES

model, family, effort = sys.argv[1], sys.argv[2], sys.argv[3]
tag = f"{family}_{effort}"
prompt = open(os.path.join(CAND, "prompt.txt")).read()
schema = json.load(open(os.path.join(CAND, "schema.json")))

attempt_no = [0]
def run_cc(model, effort, prompt, schema):
    attempt_no[0] += 1
    full = (prompt + "\n\nRespond with ONLY a single JSON object matching "
            "this JSON Schema (no prose, no code fences):\n" + json.dumps(schema))
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if effort != "none":
        cmd += ["--effort", effort]
    t0 = time.time()
    r = subprocess.run(cmd, input=full, capture_output=True, text=True, timeout=3600)
    dur = time.time() - t0
    raw = os.path.join(PILOT, f"raw_{tag}_attempt{attempt_no[0]}.json")
    open(raw, "w").write(r.stdout)
    if r.stderr:
        open(raw + ".stderr", "w").write(r.stderr)
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

print(f"[S1] running {model}@{effort} via claude-code...", flush=True)
try:
    answer, usage, dur, attempts, fail = R.attempt_with_retries(run_cc, model, effort, prompt, schema)
except subprocess.TimeoutExpired:
    answer, usage, dur, attempts, fail = None, None, 3600.0, attempt_no[0], "timeout after 3600s"
rec = {
    "task": "S1", "model": model, "family": family, "effort": effort,
    "sample": "pilot1", "harness": "claude-code", "date": time.strftime("%Y-%m-%d"),
    "answer": answer, "usage": usage, "duration_s": round(dur, 1),
    "cost_usd": R.cost_usd(usage, family),
    "cost_basis": "standard list prices, USD/MTok",
    "cost_estimated": usage is None,
    "notes": (f"answer failed validation after {attempts} attempts: {fail}" if fail else
              (f"validated after {attempts} attempts (usage includes retries)" if attempts > 1 else "")),
}
if fail:
    rec["invalid"] = True
path = os.path.join(PILOT, f"s1_{family}_{effort}_pilot1.json")
json.dump(rec, open(path, "w"), indent=1)
g = subprocess.run([sys.executable, os.path.join(CAND, "grade.py"), path], capture_output=True, text=True)
open(os.path.join(PILOT, f"grade_{tag}.json"), "w").write(g.stdout + g.stderr)
print(f"[S1] saved {path} · grade: {g.stdout.strip()[:300]}", flush=True)
