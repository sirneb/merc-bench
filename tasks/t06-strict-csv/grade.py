#!/usr/bin/env python3
"""Grader for T6. Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in this directory."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _common import load_answer, emit, norm, numeq

HERE = os.path.dirname(os.path.abspath(__file__))
import html


def grade(ans):
    want = open(os.path.join(HERE, "key.txt")).read().strip().splitlines()
    got = html.unescape(ans.get("csv", "") or "").strip().splitlines()
    ok = sum(1 for i, wline in enumerate(want)
             if i < len(got) and got[i].strip() == wline)
    detail = {"lines_expected": len(want), "lines_got": len(got)}
    return ok, len(want), detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T6", s, t, d)
