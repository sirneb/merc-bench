#!/usr/bin/env python3
"""Grader for candidate simulation-1 (Quarry Duel). Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in key.json next to it.

Scoring (100 points at the default difficulty of 5 checkpoints):
  checkpoints: every checkpoint x 2 players x 8 points: position 1, coins 2, hand_size 1,
               hand_total 2, stockpile total 1, exact 4-suit stockpile vector 1 (exact match)
  final block: winner 2, p1_score 3, p2_score 3, total_captures 3, total_tolls_paid 3,
               discard_pile_size 3, deck_remaining 3 = 20 points, exact match
Fields are graded independently, so a run that diverges at turn 65 still keeps the points
for turns 20/40/60. detail.first_divergence_turn reports the first checkpoint with any miss.
Weights were chosen so that a lazy constant guess (zero stockpiles, hand_size 4) earns
about 10 points instead of ~30 under uniform per-suit weighting.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tasks"))
from _common import load_answer, emit, numeq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TASK_ID = "S1"
PLAYER_FIELDS = {"position": 1, "coins": 2, "hand_size": 1, "hand_total": 2}
STOCK_TOTAL_W, STOCK_VECTOR_W = 1, 1
SUITS = ["Ore", "Wood", "Grain", "Gem"]
FINAL_WEIGHTS = {"winner": 2, "p1_score": 3, "p2_score": 3, "total_captures": 3,
                 "total_tolls_paid": 3, "discard_pile_size": 3, "deck_remaining": 3}


# ---------------------------------------------------------------- tolerant parsing
def extract_json(text):
    """Return the largest parseable {...} object embedded in free text, or {}."""
    text = re.sub(r"```(?:json)?", "", text)
    best = {}
    for m in re.finditer(r"\{", text):
        start = m.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except Exception:
                        break
                    if isinstance(obj, dict) and len(json.dumps(obj)) > len(json.dumps(best)):
                        best = obj
                    break
    return best


def lower_keys(d):
    return {str(k).strip().lower(): v for k, v in d.items()} if isinstance(d, dict) else {}


def getk(d, *names):
    d = lower_keys(d)
    for n in names:
        if n.lower() in d:
            return d[n.lower()]
    return None


def player_block(cp, idx):
    """Find player idx (1 or 2) inside a checkpoint object under any common spelling."""
    return getk(cp, f"P{idx}", f"player{idx}", f"player_{idx}", f"player {idx}", f"p{idx}") or {}


def stock_count(stock, suit):
    if isinstance(stock, dict):
        return getk(stock, suit)
    return None


# ---------------------------------------------------------------- grading
def grade(ans):
    if "_text" in ans:
        ans = extract_json(ans["_text"])
    key = json.load(open(os.path.join(HERE, "key.json")))
    detail = {"misses": {}, "checkpoints_found": 0, "first_divergence_turn": None,
              "per_checkpoint": {}}
    score = 0
    total = 0

    # checkpoints: match by turn number, falling back to list position
    got_cps = getk(ans, "checkpoints") or []
    if not isinstance(got_cps, list):
        got_cps = []
    by_turn = {}
    for i, cp in enumerate(got_cps):
        if not isinstance(cp, dict):
            continue
        t = getk(cp, "turn", "after_turn")
        try:
            by_turn[int(float(t))] = cp
        except Exception:
            by_turn.setdefault(("idx", i), cp)
    for i, kcp in enumerate(key["checkpoints"]):
        turn = kcp["turn"]
        gcp = by_turn.get(turn) or by_turn.get(("idx", i)) or {}
        if gcp:
            detail["checkpoints_found"] += 1
        cp_ok = 0
        cp_total = 0
        for p in (1, 2):
            kp = kcp[f"P{p}"]
            gp = player_block(gcp, p)
            for f, w in PLAYER_FIELDS.items():
                total += w
                cp_total += w
                g = getk(gp, f, f.replace("_", ""), f.replace("_", " "))
                if numeq(g, kp[f], tol=0):
                    score += w
                    cp_ok += w
                else:
                    detail["misses"][f"t{turn}.P{p}.{f}"] = {"want": kp[f], "got": g}
            gstock = getk(gp, "stockpile", "stock", "stockpiles")
            gvec = [stock_count(gstock, s) for s in SUITS]
            kvec = [kp["stockpile"][s] for s in SUITS]
            # stockpile total (1 pt) and exact per-suit vector (1 pt)
            total += STOCK_TOTAL_W + STOCK_VECTOR_W
            cp_total += STOCK_TOTAL_W + STOCK_VECTOR_W
            try:
                gtot = sum(float(str(x).replace(",", "")) for x in gvec)
            except Exception:
                gtot = None
            if gtot is not None and numeq(gtot, sum(kvec), tol=0):
                score += STOCK_TOTAL_W
                cp_ok += STOCK_TOTAL_W
            else:
                detail["misses"][f"t{turn}.P{p}.stockpile_total"] = {"want": sum(kvec), "got": gtot}
            if all(numeq(g, k, tol=0) for g, k in zip(gvec, kvec)):
                score += STOCK_VECTOR_W
                cp_ok += STOCK_VECTOR_W
            else:
                detail["misses"][f"t{turn}.P{p}.stockpile"] = {"want": kp["stockpile"], "got": gvec}
        detail["per_checkpoint"][str(turn)] = f"{cp_ok}/{cp_total}"
        if cp_ok < cp_total and detail["first_divergence_turn"] is None:
            detail["first_divergence_turn"] = turn

    # final block
    gfin = getk(ans, "final", "final_block", "end") or {}
    for f, w in FINAL_WEIGHTS.items():
        total += w
        want = key["final"][f]
        g = getk(gfin, f, f.replace("_", ""), f.replace("_", " "))
        if f == "winner":
            hit = str(g).strip().lower().replace("player", "p").replace(" ", "") == str(want).lower()
        else:
            hit = numeq(g, want, tol=0)
        if hit:
            score += w
        else:
            detail["misses"][f"final.{f}"] = {"want": want, "got": g}
    return score, total, detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit(TASK_ID, s, t, d)
