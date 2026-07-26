#!/usr/bin/env python3
"""One-time migration: move workflow-harness records out of the active dataset.

The original study's records were produced through Claude Code workflow
subagents — a harness nobody can reproduce from this repository. They are
preserved here for provenance and comparison, but the active dataset
(results/runs/) contains only records produced through reproducible harnesses
(the shipped runner or the documented record contract).

Usage: python archive/retire_workflow_runs.py
"""
import glob
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "archive", "workflow-runs")
os.makedirs(DEST, exist_ok=True)

moved = 0
for p in glob.glob(os.path.join(ROOT, "results", "runs", "*.json")):
    if json.load(open(p)).get("harness") == "claude-code-workflow":
        shutil.move(p, os.path.join(DEST, os.path.basename(p)))
        moved += 1
print(f"retired {moved} workflow-harness records to archive/workflow-runs/")
