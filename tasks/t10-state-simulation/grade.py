#!/usr/bin/env python3
"""Grader for T10. Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in this directory."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _common import load_answer, emit, norm, numeq

HERE = os.path.dirname(os.path.abspath(__file__))
import re


def parse_text(text):
    robots, floor = [], []
    pats = [
        r'id:\s*"?(R\d)"?\s*,\s*x:\s*(\d+)\s*,\s*y:\s*(\d+)\s*,\s*carrying:\s*(\d+)',
        r'"id":\s*"(R\d)"\s*,\s*"x":\s*(\d+)\s*,\s*"y":\s*(\d+)\s*,\s*"carrying":\s*(\d+)',
        r'(R\d):\s*x\s*=\s*(\d+)\s*,\s*y\s*=\s*(\d+)\s*,\s*carrying\s*=\s*(\d+)',
        r'(R\d):?\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*,?\s*carrying\s*:?=?\s*(\d+)',
    ]
    for p in pats:
        m = re.findall(p, text)
        if len({x[0] for x in m}) >= 3:
            seen = {}
            for rid, x, y, c in m:
                seen[rid] = {"id": rid, "x": int(x), "y": int(y), "carrying": int(c)}
            robots = list(seen.values())
            break
    for p in [r'x:\s*(\d+)\s*,\s*y:\s*(\d+)\s*,\s*count:\s*(\d+)',
              r'"x":\s*(\d+)\s*,\s*"y":\s*(\d+)\s*,\s*"count":\s*(\d+)',
              r'\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*[:=]\s*(\d+)']:
        m = re.findall(p, text)
        if m:
            agg = {}
            for x, y, c in m:
                agg[(int(x), int(y))] = int(c)
            floor = [{"x": x, "y": y, "count": c} for (x, y), c in agg.items()]
            break
    return {"robots": robots, "floor_boxes": floor}


def grade(ans):
    if "_text" in ans:
        ans = parse_text(ans["_text"])
    key = json.load(open(os.path.join(HERE, "key.json")))
    robots_ok = 0
    robots = ans.get("robots", [])
    if not isinstance(robots, list):
        robots = []
    for r in robots:
        if not isinstance(r, dict):
            continue
        k = key["robots"].get(str(r.get("id", "")).upper())
        if k and [r.get("x"), r.get("y"), r.get("carrying")] == k:
            robots_ok += 1
    want = {tuple(map(int, k.split(","))): v for k, v in key["floor"].items()}
    got = {}
    fb = ans.get("floor_boxes", [])
    if isinstance(fb, list):
        for f in fb:
            try:
                got[(int(f["x"]), int(f["y"]))] = int(f["count"])
            except Exception:
                pass
    inter = sum(1 for k, v in want.items() if got.get(k) == v)
    return robots_ok + inter, 3 + len(want), \
        {"robots_ok": robots_ok, "floor_cells_ok": inter,
         "floor_exact": got == want}


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T10", s, t, d)
