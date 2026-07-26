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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="cc1")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--harness", default="claude-code")
    args = ap.parse_args()
    jobs = [(f, m, e) for f, m, efforts in GRID for e in efforts]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_config, f, m, e, args.sample, args.harness)
                for f, m, e in jobs]
        for fut in futs:
            fut.result()
    print("SWEEP COMPLETE", flush=True)


if __name__ == "__main__":
    main()
