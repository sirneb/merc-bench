#!/usr/bin/env python3
"""Grader for T8. Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in this directory."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _common import load_answer, emit, norm, numeq

HERE = os.path.dirname(os.path.abspath(__file__))
import html
import subprocess


def grade(ans):
    tasks = json.load(open(os.path.join(HERE, "key.json")))
    got = {a.get("id"): a.get("pattern", "") for a in ans.get("answers", [])}
    detail = {}
    ok = 0
    prog = ("import json,re,sys\nd=json.loads(sys.stdin.read())\n"
            "try:\n c=re.compile(d['pat'])\nexcept Exception:\n"
            " print('BAD'); sys.exit()\n"
            "okp=all(c.fullmatch(s) for s in d['pos'])\n"
            "okn=all(not c.fullmatch(s) for s in d['neg'])\n"
            "print('OK' if okp and okn else 'NO')")
    for i, t in enumerate(tasks, 1):
        pat = html.unescape(str(got.get(i, "")))
        payload = json.dumps({"pat": pat, "pos": t["pos"], "neg": t["neg"]})
        try:
            r = subprocess.run([sys.executable, "-c", prog], input=payload,
                               capture_output=True, text=True, timeout=10)
            hit = r.stdout.strip() == "OK"
        except subprocess.TimeoutExpired:
            hit = False
        ok += hit
        if not hit:
            detail[str(i)] = pat[:80]
    return ok, len(tasks), detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T8", s, t, d)
