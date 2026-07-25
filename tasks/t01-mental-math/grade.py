#!/usr/bin/env python3
"""Grader for T1. Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in this directory."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _common import load_answer, emit, norm, numeq

HERE = os.path.dirname(os.path.abspath(__file__))

def grade(ans):
    key = json.load(open(os.path.join(HERE, "key.json")))
    got = {a.get("id"): str(a.get("value", "")) for a in ans.get("answers", [])}
    detail = {}
    ok = 0
    for i, k in enumerate(key, 1):
        g = got.get(i, "")
        hit = norm(g) == norm(k) or numeq(g, k)
        ok += bool(hit)
        if not hit:
            detail[str(i)] = {"want": k, "got": g}
    return ok, len(key), detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T1", s, t, d)
