#!/usr/bin/env python3
"""Grader for candidate simulation-2 (TALLY-12). Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in key.json.

Scoring (total 80 with the shipped `hard` preset: 20 + 40 OUT values):
  out_stream        per program, N = number of OUT values:
                    0.5 x (longest correct prefix) + 0.5 x (pointwise matches)  = N
                    -> 20 (A) + 40 (B)                                          = 60
  final_registers   4 pts per program, split evenly over the LIVE registers
                    (registers written after the setup block; key.json meta)   =  8
  final_memory      4 pts per program, split evenly over the LIVE memory cells
                    (cells whose value changed during the run)                 =  8
  steps_executed    2 pts per program, exact only                              =  4
  halted            informational only                                         =  0
Dead registers (setup constants never rewritten) and untouched memory cells
earn nothing, so a zero-execution "static read" of the listing scores ~0 on
those components.  first_wrong_out_index / out_pointwise_matches /
out_prefix_correct are reported in detail as diagnostics.

Tolerant parsing: if the answer is prose or malformed JSON, the LAST balanced
JSON object that carries program keys is used (a corrected final answer beats
an earlier draft); `answer`/`result`/`response` wrappers are unwrapped;
program and field names resolve through a fixed alias priority (canonical
name first, so "program_a" beats a stray "A"); string-valued programs are
json.loads'ed; 768.0 / "768" coerce to 768; register/memory dicts
({"r0": ...}) are accepted.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_common():
    """_common.py lives in tasks/.  This grader is run from candidates/<id>/
    (tasks is ../../tasks) and, once promoted, from tasks/<id>/ (tasks is ..)."""
    for rel in ("..", os.path.join("..", "..", "tasks"), os.path.join("..", "tasks")):
        d = os.path.normpath(os.path.join(HERE, rel))
        if os.path.exists(os.path.join(d, "_common.py")):
            return d
    return None


_COMMON = _find_common()
if _COMMON:
    sys.path.insert(0, _COMMON)
try:
    from _common import load_answer, emit  # noqa: E402
except ImportError:  # pragma: no cover - standalone fallback, same behaviour
    def load_answer(path):
        rec = json.load(open(path))
        ans = rec.get("answer")
        if isinstance(ans, str):
            try:
                ans = json.loads(ans)
            except Exception:
                ans = {"_text": ans}
        return rec, (ans if isinstance(ans, dict) else {})

    def emit(task, score, total, detail):
        print(json.dumps({"task": task, "score": score, "total": total,
                          "detail": detail}))

TASK_ID = "T13"

REG_POINTS = 4.0      # per program, spread over live registers
MEM_POINTS = 4.0      # per program, spread over live memory cells
STEP_POINTS = 2       # per program, exact only

# alias priority: canonical first.  Keys are normalised with _norm().
PROG_ALIASES = {
    "a": ["programa", "proga", "progra", "pa", "a"],
    "b": ["programb", "progb", "progrb", "pb", "b"],
}
FIELD_ALIASES = {
    "out_stream": ["outstream", "outputstream", "outputs", "output", "outs", "out", "stream"],
    "final_registers": ["finalregisters", "registers", "finalregs", "regs", "reg", "r"],
    "final_memory": ["finalmemory", "memory", "finalmem", "mem", "m"],
    "steps_executed": ["stepsexecuted", "steps", "stepcount", "executedsteps", "step", "nsteps"],
    "halted": ["halted", "halt"],
}
WRAPPERS = ["answer", "result", "response", "output", "final", "finalanswer", "json"]


def _norm(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _has_prog_keys(obj):
    if not isinstance(obj, dict):
        return False
    ks = {_norm(k) for k in obj}
    return any(a in ks for a in PROG_ALIASES["a"]) or any(b in ks for b in PROG_ALIASES["b"])


def _balanced_objects(text):
    """Yield (start, obj) for every balanced {...} substring that parses as JSON."""
    n = len(text)
    i = 0
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        end = None
        for j in range(i, n):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end is None:
            i += 1
            continue
        try:
            obj = json.loads(text[i:end + 1])
        except Exception:
            obj = None
        if isinstance(obj, dict):
            yield i, obj
        i += 1


def _extract_json(text):
    """The LAST balanced JSON object that carries program keys (a corrected
    final answer beats an earlier draft).  Falls back to the last object that
    wraps such an object one level down."""
    last = None
    last_wrapped = None
    for _, obj in _balanced_objects(text):
        if _has_prog_keys(obj):
            last = obj
        else:
            inner = _unwrap(obj)
            if inner is not obj and _has_prog_keys(inner):
                last_wrapped = inner
    return last if last is not None else (last_wrapped or {})


def _unwrap(obj):
    """{"answer": {...program_a...}} -> the inner dict (one or two levels)."""
    cur = obj
    for _ in range(2):
        if _has_prog_keys(cur) or not isinstance(cur, dict):
            return cur
        nxt = None
        by = {_norm(k): v for k, v in cur.items()}
        for w in WRAPPERS:
            v = by.get(w)
            if isinstance(v, str):
                v = _loads_maybe(v)
            if isinstance(v, dict):
                nxt = v
                break
        if nxt is None:
            # single-key wrapper of any name
            if len(cur) == 1:
                v = next(iter(cur.values()))
                if isinstance(v, str):
                    v = _loads_maybe(v)
                if isinstance(v, dict):
                    nxt = v
        if nxt is None:
            return cur
        cur = nxt
    return cur


def _loads_maybe(s):
    try:
        return json.loads(s)
    except Exception:
        objs = list(_balanced_objects(s))
        return objs[-1][1] if objs else s


def _pick(obj, aliases):
    """First alias (in priority order) present among the normalised keys of obj."""
    if not isinstance(obj, dict):
        return None
    by = {}
    for k, v in obj.items():
        by.setdefault(_norm(k), v)   # first occurrence of a normalised key wins
    for a in aliases:
        if a in by:
            return by[a]
    return None


def _int(v):
    """768 -> 768; 768.0 -> 768; "768" / " 768.0 " -> 768; anything else -> None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    if isinstance(v, str):
        t = v.strip().rstrip(",;")
        try:
            return int(t)
        except Exception:
            pass
        try:
            f = float(t)
            return int(f) if f.is_integer() else None
        except Exception:
            return None
    return None


def _ints(x):
    """Coerce a list (or {'r0':..} / {'0':..} / {'mem[3]':..} dict, or a
    string of numbers) into a list of ints (None for unparseable slots)."""
    if isinstance(x, str):
        parsed = _loads_maybe(x)
        x = parsed if isinstance(parsed, (list, dict)) else re.findall(r"-?\d+(?:\.\d+)?", x)
    if isinstance(x, dict):
        items = []
        for k, v in x.items():
            m = re.search(r"(\d+)", str(k))
            if m:
                items.append((int(m.group(1)), v))
        x = [v for _, v in sorted(items)]
    if not isinstance(x, list):
        return []
    return [_int(v) for v in x]


def _prefix_len(got, want):
    n = 0
    for g, w in zip(got, want):
        if g != w:
            break
        n += 1
    return n


def _program(ans, tag):
    v = _pick(ans, PROG_ALIASES[tag])
    if isinstance(v, str):
        v = _loads_maybe(v)
    return v if isinstance(v, dict) else {}


def grade_program(prog, want, live):
    d = {}
    pts = 0.0
    n_out = len(want["out_stream"])

    got_out = _ints(_pick(prog, FIELD_ALIASES["out_stream"]) or [])
    p = _prefix_len(got_out, want["out_stream"])
    pw = sum(1 for g, w in zip(got_out, want["out_stream"]) if g == w)
    out_pts = 0.5 * p + 0.5 * pw
    pts += out_pts
    d["out_points"] = round(out_pts, 2)
    d["out_total"] = n_out
    d["out_prefix_correct"] = p
    d["out_pointwise_matches"] = pw
    d["first_wrong_out_index"] = None if p == n_out else p
    d["out_reported"] = len(got_out)

    regs = _ints(_pick(prog, FIELD_ALIASES["final_registers"]) or [])
    live_r = live["registers"]
    rok = [i for i in live_r if i < len(regs) and regs[i] == want["final_registers"][i]]
    reg_pts = REG_POINTS * len(rok) / len(live_r) if live_r else 0.0
    pts += reg_pts
    d["registers"] = {"live": live_r, "ok": rok, "points": round(reg_pts, 3),
                      "all_8_ok": sum(1 for i, w in enumerate(want["final_registers"])
                                      if i < len(regs) and regs[i] == w)}

    mem = _ints(_pick(prog, FIELD_ALIASES["final_memory"]) or [])
    live_m = live["memory"]
    mok = [i for i in live_m if i < len(mem) and mem[i] == want["final_memory"][i]]
    mem_pts = MEM_POINTS * len(mok) / len(live_m) if live_m else 0.0
    pts += mem_pts
    d["memory"] = {"live": live_m, "ok": mok, "points": round(mem_pts, 3),
                   "all_16_ok": sum(1 for i, w in enumerate(want["final_memory"])
                                    if i < len(mem) and mem[i] == w)}

    steps = _int(_pick(prog, FIELD_ALIASES["steps_executed"]))
    ws = want["steps_executed"]
    sp = STEP_POINTS if steps == ws else 0
    pts += sp
    d["steps"] = {"want": ws, "got": steps, "points": sp}
    d["halted"] = {"want": want["halted"], "got": _pick(prog, FIELD_ALIASES["halted"])}
    return pts, d


def load_key():
    key = json.load(open(os.path.join(HERE, "key.json")))
    live = {}
    for tag in ("a", "b"):
        meta = key["meta"]["programs"][tag.upper()]
        live[tag] = meta["live"]
    return key["answer"], live


def grade(ans):
    answer, live = load_key()
    if not isinstance(ans, dict):
        ans = {}
    if "_text" in ans and not _has_prog_keys(ans):
        ans = _extract_json(str(ans["_text"]))
    ans = _unwrap(ans)
    total = 0
    score = 0.0
    detail = {}
    for tag in ("a", "b"):
        want = answer["program_" + tag]
        total += len(want["out_stream"]) + int(REG_POINTS) + int(MEM_POINTS) + STEP_POINTS
        pts, d = grade_program(_program(ans, tag), want, live[tag])
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
