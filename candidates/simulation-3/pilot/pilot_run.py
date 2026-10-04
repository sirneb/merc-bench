#!/usr/bin/env python3
"""Pilot runner for candidate simulation-3: reproduces runner/run.py's claude-code
harness invocation (same flags, prompt suffix, validation, retry policy, cost basis)
and additionally saves the raw CLI JSON output per attempt."""
import json, os, subprocess, sys, time, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = "/Users/neb/.claude/jobs/866a08ee/tmp/merc-bench"
CAND = os.path.join(ROOT, "candidates", "simulation-3")
PILOT = os.path.join(CAND, "pilot")
sys.path.insert(0, os.path.join(ROOT, "runner"))
import run as R  # reuse extract_json, validate_answer, cost_usd, DEFAULT_PRICES

prompt = open(os.path.join(CAND, "prompt.txt")).read()
schema = json.load(open(os.path.join(CAND, "schema.json")))

CONFIGS = [
    ("claude-haiku-4-5", "low", "haiku"),
    ("claude-sonnet-5", "medium", "sonnet"),
    ("claude-opus-5-5", "medium", "opus55"),
    ("claude-fable-5-1", "medium", "fable51"),
]
lock = threading.Lock()

def run_claude_code(model, effort, prompt, schema, tag):
    full = (prompt + "\n\nRespond with ONLY a single JSON object matching "
            "this JSON Schema (no prose, no code fences):\n" + json.dumps(schema))
    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    if effort != "none":
        cmd += ["--effort", effort]
    t0 = time.time()
    r = subprocess.run(cmd, input=full, capture_output=True, text=True, timeout=3600)
    dur = time.time() - t0
    with open(os.path.join(PILOT, f"raw_{tag}.stdout.json"), "w") as f:
        f.write(r.stdout)
    if r.stderr:
        with open(os.path.join(PILOT, f"raw_{tag}.stderr.txt"), "w") as f:
            f.write(r.stderr)
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
    return answer, usage, dur, out

def attempt_with_retries(model, effort, family, tries=3):
    usage_total, dur_total, reason, last_answer, raws = None, 0.0, [], None, []
    for i in range(tries):
        p = prompt if i == 0 else (
            prompt + "\n\nIMPORTANT: your previous response was rejected ("
            + "; ".join(reason) + "). Respond again with ONLY the complete, valid JSON object.")
        tag = f"{family}_{effort}_attempt{i+1}"
        try:
            answer, usage, dur, out = run_claude_code(model, effort, p, schema, tag)
            raws.append({"attempt": i + 1, "cli_cost_usd": out.get("total_cost_usd"),
                         "cli_duration_ms": out.get("duration_ms"),
                         "cli_duration_api_ms": out.get("duration_api_ms"),
                         "is_error": out.get("is_error"), "num_turns": out.get("num_turns")})
        except Exception as e:
            reason = [f"harness error: {e}"]
            answer, usage, dur = None, None, 0.0
            raws.append({"attempt": i + 1, "error": str(e)[:300]})
        dur_total += dur
        if usage:
            if usage_total is None:
                usage_total = dict(usage)
            else:
                for k in usage_total:
                    usage_total[k] += usage.get(k, 0)
        last_answer = answer if answer is not None else last_answer
        if R.validate_answer(answer, schema, reason):
            return answer, usage_total, dur_total, i + 1, None, raws
    return last_answer, usage_total, dur_total, tries, "; ".join(reason), raws

def do(cfg):
    model, effort, family = cfg
    with lock:
        print(f"[S3] running {model}@{effort} via claude-code...", flush=True)
    answer, usage, dur, attempts, fail, raws = attempt_with_retries(model, effort, family)
    rec = {
        "task": "S3", "model": model, "family": family, "effort": effort,
        "sample": "pilot1", "harness": "claude-code", "date": time.strftime("%Y-%m-%d"),
        "answer": answer, "usage": usage, "duration_s": round(dur, 1),
        "cost_usd": R.cost_usd(usage, family),
        "cost_basis": "standard list prices, USD/MTok", "cost_estimated": usage is None,
        "notes": (f"answer failed validation after {attempts} attempts: {fail}" if fail else
                  (f"validated after {attempts} attempts (usage includes retries)" if attempts > 1 else "")),
        "pilot_cli_meta": raws,
    }
    if fail:
        rec["invalid"] = True
    path = os.path.join(PILOT, f"s3_{family}_{effort}_pilot1.json")
    json.dump(rec, open(path, "w"), indent=1)
    g = subprocess.run([sys.executable, os.path.join(CAND, "grade.py"), path],
                       capture_output=True, text=True)
    with lock:
        print(f"[S3] {family}@{effort}: dur={rec['duration_s']}s usage={usage} cost={rec['cost_usd']} "
              f"attempts={attempts} fail={fail}\n   grade: {g.stdout.strip()[:400]} {g.stderr[-200:]}", flush=True)

with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(do, CONFIGS))
print("DONE")
