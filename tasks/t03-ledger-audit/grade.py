#!/usr/bin/env python3
"""Grader for T3. Usage: python grade.py <run-record.json>
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
        g = norm(got.get(i, "")).lstrip("#")
        kn = norm(k).lstrip("#")
        hit = g == kn or numeq(got.get(i, ""), k) if not k.startswith("#") \
            else g == kn
        if k.startswith("#"):
            hit = g == kn
        elif not hit:
            hit = numeq(got.get(i, ""), k)
        ok += bool(hit)
        if not hit:
            detail[str(i)] = {"want": k, "got": got.get(i, "")}
    return ok, len(key), detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T3", s, t, d)
