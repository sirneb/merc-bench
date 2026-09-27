#!/usr/bin/env python3
"""Pilot adversarial-3 with the runner's exact claude-code invocation (sequential, like runner/run.py)."""
import json, os, subprocess, sys, time
ROOT = "/Users/neb/.claude/jobs/866a08ee/tmp/merc-bench"
TASK = os.path.join(ROOT, "candidates", "adversarial-3")
PILOT = os.path.join(TASK, "pilot")
sys.path.insert(0, os.path.join(ROOT, "runner"))
import run as R  # reuse run_claude_code / attempt_with_retries / cost_usd / DEFAULT_PRICES verbatim

CONFIGS = [("claude-haiku-4-5", "low", "haiku"),
           ("claude-sonnet-5", "medium", "sonnet"),
           ("claude-opus-5-5", "medium", "opus55"),
           ("claude-fable-5-1", "medium", "fable51")]

prompt = open(os.path.join(TASK, "prompt.txt")).read()
schema = json.load(open(os.path.join(TASK, "schema.json")))

_raw_log = {"tag": None, "n": 0}
_orig = R.subprocess.run
def _capturing_run(*a, **kw):
    r = _orig(*a, **kw)
    _raw_log["n"] += 1
    p = os.path.join(PILOT, f"raw_{_raw_log['tag']}_attempt{_raw_log['n']}.json")
    with open(p, "w") as f:
        f.write(r.stdout)
    if r.stderr:
        with open(p.replace(".json", ".stderr.txt"), "w") as f:
            f.write(r.stderr)
    return r
R.subprocess.run = _capturing_run

for model, effort, family in CONFIGS:
    tag = f"{family}_{effort}"
    _raw_log.update(tag=tag, n=0)
    print(f"[A3] running {model}@{effort} via claude-code...", flush=True)
    try:
        answer, usage, dur, attempts, fail = R.attempt_with_retries(
            R.run_claude_code, model, effort, prompt, schema)
    except subprocess.TimeoutExpired as e:
        answer, usage, dur, attempts, fail = None, None, 3600.0, 1, f"timeout: {e}"
    rec = {
        "task": "A3", "model": model, "family": family, "effort": effort,
        "sample": "pilot", "harness": "claude-code", "date": time.strftime("%Y-%m-%d"),
        "answer": answer, "usage": usage, "duration_s": round(dur, 1),
        "cost_usd": R.cost_usd(usage, family),
        "cost_basis": "standard list prices, USD/MTok",
        "cost_estimated": usage is None,
        "notes": (f"answer failed validation after {attempts} attempts: {fail}" if fail else
                  (f"validated after {attempts} attempts (usage includes retries)" if attempts > 1 else "")),
    }
    if fail:
        rec["invalid"] = True
    path = os.path.join(PILOT, f"a3_{family}_{effort}_pilot.json")
    json.dump(rec, open(path, "w"), indent=1)
    g = subprocess.run([sys.executable, os.path.join(TASK, "grade.py"), path],
                       capture_output=True, text=True)
    open(os.path.join(PILOT, f"grade_{family}_{effort}.json"), "w").write(g.stdout + g.stderr)
    print(f"[A3] {tag}: dur={dur:.0f}s usage={usage} cost={rec['cost_usd']} fail={fail}", flush=True)
    print(f"[A3] grade: {g.stdout.strip()[:200]}", flush=True)
print("PILOT DONE", flush=True)
