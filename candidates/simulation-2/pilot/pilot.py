#!/usr/bin/env python3
"""Pilot runner for candidate simulation-2: reproduces runner/run.py's claude-code harness."""
import json, os, sys, time, subprocess
ROOT = "/Users/neb/.claude/jobs/866a08ee/tmp/merc-bench"
CAND = os.path.join(ROOT, "candidates", "simulation-2")
PILOT = os.path.join(CAND, "pilot")
sys.path.insert(0, os.path.join(ROOT, "runner"))
import run as R  # noqa

prompt = open(os.path.join(CAND, "prompt.txt")).read()
schema = json.load(open(os.path.join(CAND, "schema.json")))

CONFIGS = [
    ("claude-haiku-4-5", "low", "haiku"),
    ("claude-sonnet-5", "medium", "sonnet"),
    ("claude-opus-5-5", "medium", "opus55"),
    ("claude-fable-5-1", "medium", "fable51"),
]
raw_log = []

def run_cc(model, effort, p, sch):
    full = (p + "\n\nRespond with ONLY a single JSON object matching "
            "this JSON Schema (no prose, no code fences):\n" + json.dumps(sch))
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if effort != "none":
        cmd += ["--effort", effort]
    t0 = time.time()
    r = subprocess.run(cmd, input=full, capture_output=True, text=True, timeout=3600)
    dur = time.time() - t0
    raw_log.append({"cmd": cmd, "returncode": r.returncode, "stdout": r.stdout,
                    "stderr": r.stderr[-2000:], "duration_s": dur})
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

only = sys.argv[1:] 
for model, effort, family in CONFIGS:
    if only and family not in only:
        continue
    raw_log.clear()
    print(f"[SIM2] running {model}@{effort} ...", flush=True)
    answer, usage, dur, attempts, fail = R.attempt_with_retries(run_cc, model, effort, prompt, schema)
    rec = {
        "task": "SIM2", "model": model, "family": family, "effort": effort,
        "sample": "pilot1", "harness": "claude-code", "date": time.strftime("%Y-%m-%d"),
        "answer": answer, "usage": usage, "duration_s": round(dur, 1),
        "cost_usd": R.cost_usd(usage, family),
        "cost_basis": "standard list prices, USD/MTok", "cost_estimated": usage is None,
        "notes": (f"answer failed validation after {attempts} attempts: {fail}" if fail else
                  (f"validated after {attempts} attempts (usage includes retries)" if attempts > 1 else "")),
    }
    if fail:
        rec["invalid"] = True
    fname = f"sim2_{family}_{effort}_pilot1.json"
    path = os.path.join(PILOT, fname)
    json.dump(rec, open(path, "w"), indent=1)
    json.dump(raw_log, open(os.path.join(PILOT, f"raw_{family}_{effort}_pilot1.json"), "w"), indent=1)
    g = subprocess.run([sys.executable, os.path.join(CAND, "grade.py"), path], capture_output=True, text=True)
    open(os.path.join(PILOT, f"grade_{family}_{effort}_pilot1.json"), "w").write(g.stdout)
    print(f"[SIM2] saved {fname} dur={dur:.0f}s usage={usage} grade: {g.stdout.strip()[:300]}", flush=True)
