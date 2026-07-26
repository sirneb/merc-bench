#!/usr/bin/env python3
"""Run the full MERC grid through one harness, idempotently.

Usage: python runner/sweep.py [--sample cc1] [--workers 3] [--harness claude-code]

For every config in GRID, finds tasks with no record for the given sample tag
and runs only those. Safe to interrupt and rerun — completed records are
skipped. Progress goes to stdout; run it under nohup/tmux for long sweeps.
"""
import argparse
import glob
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = ["T1", "T2", "T3", "T4", "T5A", "T5B", "T6", "T7", "T8", "T9", "T10", "E"]

# (family, model id, efforts) — cheap/fast configs first, grinds last
GRID = [
    ("haiku", "claude-haiku-4-5", ["low", "medium", "high"]),
    ("sonnet", "claude-sonnet-5", ["low", "medium", "high"]),
    ("opus48", "claude-opus-4-8", ["low", "high"]),
    ("opus5", "claude-opus-5", ["low", "medium", "high"]),
    ("fable", "claude-fable-5", ["low", "medium", "high"]),
    ("sonnet", "claude-sonnet-5", ["xhigh"]),
    ("opus48", "claude-opus-4-8", ["xhigh"]),
    ("opus5", "claude-opus-5", ["xhigh"]),
    ("fable", "claude-fable-5", ["xhigh"]),
    ("sonnet", "claude-sonnet-5", ["max"]),
    ("opus5", "claude-opus-5", ["max"]),
    ("fable", "claude-fable-5", ["max"]),
]


def missing_tasks(family, effort, sample):
    have = set()
    for f in glob.glob(os.path.join(ROOT, "results", "runs",
                                    f"*_{family}_{effort}_{sample}.json")):
        have.add(os.path.basename(f).split("_")[0].upper())
    return [t for t in TASKS if t not in have]


def run_config(family, model, effort, sample, harness):
    todo = missing_tasks(family, effort, sample)
    if not todo:
        print(f"== {family}@{effort}: complete, skipping", flush=True)
        return
    print(f"== {family}@{effort}: running {len(todo)} tasks", flush=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "runner", "run.py"),
                    "--harness", harness, "--model", model, "--family", family,
                    "--effort", effort, "--tasks", ",".join(todo),
                    "--sample", sample])
    left = missing_tasks(family, effort, sample)
    print(f"== {family}@{effort}: done ({len(left)} unrecorded)", flush=True)


def next_auto_sample():
    """Next ccN replicate tag: one past the highest ccN present anywhere."""
    import re
    top = 0
    for f in glob.glob(os.path.join(ROOT, "results", "runs", "*_cc*.json")):
        m = re.search(r"_cc(\d+)\.json$", f)
        if m:
            top = max(top, int(m.group(1)))
    return f"cc{top + 1}"


def clean_invalid(sample):
    """Delete invalid records for this sample so a rerun can refill them."""
    import json
    removed = 0
    for f in glob.glob(os.path.join(ROOT, "results", "runs",
                                    f"*_{sample}.json")):
        try:
            if json.load(open(f)).get("invalid"):
                os.remove(f)
                removed += 1
        except Exception:
            pass
    return removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="cc1",
                    help="record tag; 'auto' picks the next ccN replicate")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--harness", default="claude-code")
    ap.add_argument("--passes", type=int, default=3,
                    help="max sweep passes; between passes, invalid records "
                         "(transient transport/limit failures) are deleted and refilled")
    args = ap.parse_args()
    sample = next_auto_sample() if args.sample == "auto" else args.sample
    print(f"sample tag: {sample}", flush=True)
    jobs = [(f, m, e) for f, m, efforts in GRID for e in efforts]
    for p in range(args.passes):
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(run_config, f, m, e, sample, args.harness)
                    for f, m, e in jobs]
            for fut in futs:
                fut.result()
        bad = clean_invalid(sample)
        if not bad:
            break
        print(f"pass {p + 1}: removed {bad} invalid records, refilling...",
              flush=True)
    print("SWEEP COMPLETE", flush=True)


if __name__ == "__main__":
    main()
