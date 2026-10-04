#!/usr/bin/env python3
"""Grade every run record and build the aggregate tables.

Usage: python runner/aggregate.py
Reads  results/runs/*.json
Writes results/scores.csv       (one graded row per run)
       results/summary.json     (per family@effort per task: scores, cost, time)

Grading is recomputed from raw answers every time — nothing is trusted from
the stored records except the answers themselves. Cost is likewise recomputed
from the stored token usage at the current price table (runner/run.py
DEFAULT_PRICES, harness-aware cache-write rate), so a price correction
re-prices the whole dataset on the next build. This is the verification
path: if you doubt our numbers, delete scores.csv and run this.
"""
import csv
import glob
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runner"))
from run import cost_usd  # noqa: E402  (price table lives with the runner)
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
EFFORT_ORDER = ["none", "low", "medium", "high", "xhigh", "max"]
FAMILY_ORDER = ["haiku", "sonnet", "sonnet55", "opus48", "opus5", "opus55", "fable", "fable51"]

_graders = {}


def grader(task):
    if task not in _graders:
        path = os.path.join(ROOT, "tasks", TASK_DIR[task], "grade.py")
        spec = importlib.util.spec_from_file_location(f"grade_{task}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, os.path.join(ROOT, "tasks"))
        spec.loader.exec_module(mod)
        _graders[task] = mod
    return _graders[task]


def main():
    rows = []
    skipped = []
    for f in sorted(glob.glob(os.path.join(ROOT, "results", "runs", "*.json"))):
        rec = json.load(open(f))
        if rec.get("invalid"):
            skipped.append(os.path.basename(f))
            continue
        ans = rec.get("answer")
        if isinstance(ans, str):
            try:
                ans = json.loads(ans)
            except Exception:
                ans = {"_text": ans}
        if not isinstance(ans, dict):
            ans = {}
        try:
            score, total, detail = grader(rec["task"]).grade(ans)
        except Exception as e:
            score, total, detail = 0, 0, {"grade_error": str(e)[:120]}
        rows.append({
            "file": os.path.basename(f), "task": rec["task"],
            "family": rec["family"], "effort": rec["effort"],
            "sample": rec["sample"], "score": score, "total": total,
            "cost_usd": (cost_usd(rec.get("usage"), rec["family"],
                                  rec.get("harness", "api"))
                         if rec.get("usage") else rec.get("cost_usd")),
            "cost_estimated": rec.get("cost_estimated"),
            "duration_s": rec.get("duration_s"),
            "output_tokens": (rec.get("usage") or {}).get("output"),
            "date": rec.get("date"), "harness": rec.get("harness"),
        })

    out_csv = os.path.join(ROOT, "results", "scores.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    summary = {}
    for r in rows:
        cfg = f"{r['family']}@{r['effort']}"
        cell = summary.setdefault(cfg, {}).setdefault(r["task"], {
            "scores": [], "total": r["total"], "cost_usd": [], "duration_s": []})
        cell["scores"].append(r["score"])
        if r["cost_usd"] is not None:
            cell["cost_usd"].append(r["cost_usd"])
        if r["duration_s"] is not None:
            cell["duration_s"].append(r["duration_s"])
    for cfg, tasks in summary.items():
        for t, c in tasks.items():
            c["n"] = len(c["scores"])
            c["score_min"] = min(c["scores"])
            c["score_max"] = max(c["scores"])
            c["cost_usd"] = round(sorted(c["cost_usd"])[len(c["cost_usd"]) // 2], 4) \
                if c["cost_usd"] else None
            c["duration_s"] = round(sorted(c["duration_s"])[len(c["duration_s"]) // 2], 1) \
                if c["duration_s"] else None
            del c["scores"]
    ordered = dict(sorted(summary.items(), key=lambda kv: (
        FAMILY_ORDER.index(kv[0].split("@")[0]) if kv[0].split("@")[0] in FAMILY_ORDER else 99,
        EFFORT_ORDER.index(kv[0].split("@")[1]) if kv[0].split("@")[1] in EFFORT_ORDER else 99)))
    json.dump(ordered, open(os.path.join(ROOT, "results", "summary.json"), "w"),
              indent=1)
    print(f"graded {len(rows)} runs -> results/scores.csv, results/summary.json"
          + (f" (skipped {len(skipped)} invalid: {', '.join(skipped)})" if skipped else ""))


if __name__ == "__main__":
    main()
