#!/usr/bin/env python3
"""Grader for T5B. Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in this directory."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _common import load_answer, emit, norm, numeq

HERE = os.path.dirname(os.path.abspath(__file__))

ATTRS = ["nationality", "color", "drink", "pet"]


def grade(ans):
    keymap = {int(k): v for k, v in
              json.load(open(os.path.join(HERE, "key.json"))).items()}
    answers = {a.get("id"): a for a in ans.get("answers", [])}
    solved = 0
    detail = {}
    for pid, sol in keymap.items():
        a = answers.get(pid) or {}
        okc = 0
        for attr in ATTRS:
            want = [norm(v) for v in sol[attr]]
            got = ([norm(v) for v in (a.get(attr) or [])] + [""] * 5)[:5]
            okc += sum(1 for x, y in zip(want, got) if x == y)
        n = len(ATTRS) * 5
        solved += okc == n
        detail[str(pid)] = f"{okc}/{n} cells"
    return solved, len(keymap), detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T5B", s, t, d)
