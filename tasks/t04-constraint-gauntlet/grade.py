#!/usr/bin/env python3
"""Grader for T4. Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in this directory."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _common import load_answer, emit, norm, numeq

HERE = os.path.dirname(os.path.abspath(__file__))
import html
import re


def grade(ans):
    text = html.unescape(ans.get("text", "") or "").strip()
    if text.startswith('{"text"'):
        try:
            text = json.loads(text)["text"]
        except Exception:
            pass
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    c = {}
    c["C1_4paras"] = len(paras) == 4
    p = paras + [""] * (4 - len(paras))
    w = [x.split() for x in p[:4]]
    c["C2_p1_40w"] = len(w[0]) == 40
    c["C3_p2_55w"] = len(w[1]) == 55
    c["C4_p3_noE_30w"] = len(w[2]) >= 30 and "e" not in p[2].lower()
    c["C5_p4_20w_done"] = len(w[3]) == 20 and (w[3][-1] if w[3] else "") == "done."
    c["C6_3semicolons"] = text.count(";") == 3
    firsts = [ws[0].strip(".,;:!?") if ws else "" for ws in w]
    c["C7_first_words"] = firsts == ["Meanwhile", "However", "Along", "Finally"]
    c["C8_cache_x5"] = text.lower().count("cache") == 5
    c["C9_word_len"] = all(len(t.strip('.,;:!?"\'')) <= 14 for t in text.split())
    c["C10_max180w"] = len(text.split()) <= 180
    return sum(c.values()), 10, c


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T4", s, t, d)
