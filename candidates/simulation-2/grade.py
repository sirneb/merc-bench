#!/usr/bin/env python3
"""Grader for candidate simulation-2 (TALLY-12). Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in key.json.

Scoring (total 80):
  out_stream        1 pt per value in the longest correct prefix: 20 (A) + 40 (B) = 60
  final_registers   0.5 pt per exact register x 8 x 2 programs              =  8
  final_memory      0.25 pt per exact cell x 16 x 2 programs                =  8
  steps_executed    2 pts exact, 1 pt within 2 %, per program               =  4
  halted            informational only                                       =  0
Tolerant parsing: if the answer is prose or malformed JSON, the first JSON
object found in the text is used; program keys are matched loosely
("program_a", "A", "Program A"); register/memory dicts are accepted.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tasks"))
from _common import load_answer, emit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TASK_ID = "SIM2"


def _extract_json(text):
    # largest balanced {...} that parses
    starts = [m.start() for m in re.finditer(r"\{", text)]
    for s in starts:
        depth = 0
        for i in range(s, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[s:i + 1])
                        if isinstance(obj, dict) and any(
                                _prog_tag(k) for k in obj):
                            return obj
                    except Exception:
                        pass
                    break
    return {}


def _prog_tag(key):
    k = re.sub(r"[^a-z]", "", str(key).lower())
    if k in ("a", "programa", "proga", "pa"):
        return "a"
    if k in ("b", "programb", "progb", "pb"):
        return "b"
    return None


def _ints(x, n=None):
    """Coerce a list (or {'r0':..} / {'0':..} dict) into a list of ints."""
    if isinstance(x, dict):
        items = []
        for k, v in x.items():
            m = re.search(r"(\d+)", str(k))
            if m:
                items.append((int(m.group(1)), v))
        x = [v for _, v in sorted(items)]
    if isinstance(x, str):
        x = re.findall(r"-?\d+", x)
    if not isinstance(x, list):
        return []
    out = []
    for v in x:
        try:
            out.append(int(str(v).strip()))
        except Exception:
            out.append(None)
    return out


def _prefix_len(got, want):
    n = 0
    for g, w in zip(got, want):
        if g != w:
            break
        n += 1
    return n


def grade_program(ans, want):
    d = {}
    pts = 0.0
    got_out = _ints(ans.get("out_stream", []))
    p = _prefix_len(got_out, want["out_stream"])
    pts += p
    d["out_prefix_correct"] = p
    d["out_total"] = len(want["out_stream"])
    d["first_wrong_out_index"] = None if p == len(want["out_stream"]) else p
    d["out_reported"] = len(got_out)
    d["out_pointwise_matches"] = sum(1 for g, w in zip(got_out, want["out_stream"]) if g == w)

    regs = _ints(ans.get("final_registers", []))
    rok = sum(1 for i, w in enumerate(want["final_registers"]) if i < len(regs) and regs[i] == w)
    pts += 0.5 * rok
    d["registers_ok"] = rok

    mem = _ints(ans.get("final_memory", []))
    mok = sum(1 for i, w in enumerate(want["final_memory"]) if i < len(mem) and mem[i] == w)
    pts += 0.25 * mok
    d["memory_ok"] = mok

    try:
        steps = int(str(ans.get("steps_executed", "")).strip())
    except Exception:
        steps = None
    ws = want["steps_executed"]
    if steps == ws:
        sp = 2
    elif steps is not None and abs(steps - ws) <= 0.02 * ws:
        sp = 1
    else:
        sp = 0
    pts += sp
    d["steps"] = {"want": ws, "got": steps, "points": sp}
    d["halted"] = {"want": want["halted"], "got": ans.get("halted")}
    return pts, d


def grade(ans):
    key = json.load(open(os.path.join(HERE, "key.json")))["answer"]
    if "_text" in ans:
        ans = _extract_json(ans["_text"])
    progs = {}
    for k, v in ans.items():
        t = _prog_tag(k)
        if t and isinstance(v, dict):
            progs[t] = v
    total = 0
    score = 0.0
    detail = {}
    for tag in ("a", "b"):
        want = key["program_" + tag]
        total += len(want["out_stream"]) + 4 + 4 + 2
        pts, d = grade_program(progs.get(tag, {}), want)
        score += pts
        detail["program_" + tag] = d
    score = round(score, 2)
    if score == int(score):
        score = int(score)
    return score, total, detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit(TASK_ID, s, t, d)
