#!/usr/bin/env python3
"""Grader for adversarial-3 (Chess Open Standings With Arbiter Errata).
Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in key.json in this directory.

Scoring (per player: points 2, rank 1 [0.5 if off by one], Buchholz 1, Sonneborn-Berger 1, wins 0.5;
questions: champion 4, third place 3, forfeit count 3, most-points-lost 3, withdrawn player's points 3).
For 20 players: 110 + 16 = 126.  The detail block also reports which single-trap counterfactual
(precomputed by the generator from the structured events) best matches the model's standings.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(HERE, "..", "..", "tasks"), os.path.join(HERE, "..")):
    if os.path.exists(os.path.join(cand, "_common.py")):
        sys.path.insert(0, cand)
        break
try:
    from _common import load_answer, emit, norm, numeq
except ImportError:  # fall back to local copies so the grader also runs standalone
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
        print(json.dumps({"task": task, "score": score, "total": total, "detail": detail}))

    def norm(s):
        return re.sub(r"[\s,]+", " ", str(s).strip().lower()).strip()

    def numeq(a, b, tol=0.005):
        try:
            return abs(float(str(a).replace(",", "")) - float(b)) <= tol
        except Exception:
            return False

TASK_ID = "A3"
W_POINTS, W_RANK, W_BH, W_SB, W_WINS = 2.0, 1.0, 1.0, 1.0, 0.5
W_Q = {"champion": 4, "third_place": 3, "total_forfeits": 3, "most_points_lost": 3,
       "withdrawn_player_points": 3}


def extract_json(text):
    """First balanced JSON object in arbitrary text (tolerant of prose / fences)."""
    text = text.strip()
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def to_num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", ".")
        m = re.fullmatch(r"(-?\d+)\s*(?:1/2|½)", s)
        if m:
            return float(m.group(1)) + 0.5
        if s in ("1/2", "½"):
            return 0.5
        try:
            return float(s)
        except Exception:
            return None
    return None


def make_resolver(names):
    """names: id -> 'Surname, Given'. Accepts P07 / p7 / 7 / full name / unique surname."""
    by_full = {}
    by_sur = {}
    for pid, full in names.items():
        sur, _, giv = full.partition(",")
        sur, giv = sur.strip(), giv.strip()
        by_full[norm(full)] = pid
        by_full[norm(f"{giv} {sur}")] = pid
        by_full[norm(f"{sur} {giv}")] = pid
        by_sur.setdefault(norm(sur), []).append(pid)

    def resolve(x):
        if x is None:
            return None
        s = str(x).strip()
        m = re.fullmatch(r"[Pp]?\s*0*(\d{1,2})", s)
        if m:
            pid = f"P{int(m.group(1)):02d}"
            return pid if pid in names else None
        n = norm(s)
        if n in by_full:
            return by_full[n]
        # "P07 Surname, Given" style
        m = re.match(r"[Pp](\d{2})\b", s)
        if m and f"P{m.group(1)}" in names:
            return f"P{m.group(1)}"
        if n in by_sur and len(by_sur[n]) == 1:
            return by_sur[n][0]
        return None
    return resolve


def grade(ans):
    key = json.load(open(os.path.join(HERE, "key.json")))
    if "_text" in ans:
        ans = extract_json(ans["_text"]) or {}
    names = key["player_names"]
    resolve = make_resolver(names)
    kstand = {s["player_id"]: s for s in key["standings"]}

    # ---- parse the model's standings into id -> row
    rows = ans.get("standings", [])
    if isinstance(rows, dict):
        rows = [dict(v, player_id=v.get("player_id", k)) if isinstance(v, dict) else {}
                for k, v in rows.items()]
    got = {}
    if isinstance(rows, list):
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            pid = resolve(r.get("player_id", r.get("player", r.get("id", r.get("name")))))
            if pid is None or pid in got:
                continue
            rank = to_num(r.get("rank"))
            if rank is None:
                rank = float(i + 1)
            got[pid] = dict(rank=rank, points=to_num(r.get("points", r.get("score"))),
                            buchholz=to_num(r.get("buchholz", r.get("bh"))),
                            sonneborn_berger=to_num(r.get("sonneborn_berger", r.get("sb"))),
                            wins=to_num(r.get("wins")))

    score = 0.0
    sub = dict(points=0.0, rank=0.0, buchholz=0.0, sonneborn_berger=0.0, wins=0.0, questions=0.0)
    misses = {}
    for pid, k in kstand.items():
        g = got.get(pid)
        m = {}
        if g is None:
            misses[pid] = "missing"
            continue
        if g["points"] is not None and abs(g["points"] - k["points"]) < 0.01:
            sub["points"] += W_POINTS
        else:
            m["points"] = [k["points"], g["points"]]
        if g["rank"] is not None and int(round(g["rank"])) == k["rank"]:
            sub["rank"] += W_RANK
        elif g["rank"] is not None and abs(g["rank"] - k["rank"]) <= 1:
            sub["rank"] += W_RANK / 2
            m["rank"] = [k["rank"], g["rank"]]
        else:
            m["rank"] = [k["rank"], g["rank"]]
        if g["buchholz"] is not None and abs(g["buchholz"] - k["buchholz"]) < 0.01:
            sub["buchholz"] += W_BH
        else:
            m["buchholz"] = [k["buchholz"], g["buchholz"]]
        if g["sonneborn_berger"] is not None and abs(g["sonneborn_berger"] - k["sonneborn_berger"]) < 0.01:
            sub["sonneborn_berger"] += W_SB
        else:
            m["sonneborn_berger"] = [k["sonneborn_berger"], g["sonneborn_berger"]]
        if g["wins"] is not None and int(round(g["wins"])) == k["wins"]:
            sub["wins"] += W_WINS
        else:
            m["wins"] = [k["wins"], g["wins"]]
        if m:
            misses[pid] = m

    # ---- questions
    qa = ans.get("answers", {})
    if not isinstance(qa, dict):
        qa = {}
    kq = key["answers"]
    qdetail = {}
    for q, w in W_Q.items():
        want, gv = kq[q], qa.get(q)
        if q in ("champion", "third_place", "most_points_lost"):
            hit = resolve(gv) == want
        elif q == "total_forfeits":
            hit = to_num(gv) is not None and int(round(to_num(gv))) == want
        else:
            hit = to_num(gv) is not None and abs(to_num(gv) - want) < 0.01
        if hit:
            sub["questions"] += w
        else:
            qdetail[q] = {"want": want, "got": gv}
    score = sum(sub.values())
    total = len(kstand) * (W_POINTS + W_RANK + W_BH + W_SB + W_WINS) + sum(W_Q.values())

    # ---- counterfactual attribution: which single-trap-missed standings best match the answer?
    def match_count(stats):
        n = 0
        for pid, v in stats.items():
            g = got.get(pid)
            if not g or g["points"] is None or g["buchholz"] is None or g["sonneborn_berger"] is None:
                continue
            if (abs(g["points"] - v[0]) < 0.01 and abs(g["buchholz"] - v[1]) < 0.01
                    and abs(g["sonneborn_berger"] - v[2]) < 0.01):
                n += 1
        return n

    key_match = match_count({p: [s["points"], s["buchholz"], s["sonneborn_berger"]]
                             for p, s in kstand.items()})
    cands = {name: match_count(v["stats"]) for name, v in key.get("variants", {}).items()}
    cands["naive_first_entry"] = match_count(key["naive"]["stats"])
    best = max(cands.values()) if cands else 0
    attribution = {
        "players_matching_key_points_bh_sb": key_match,
        "best_single_trap_counterfactual": sorted(n for n, c in cands.items() if c == best and c > key_match),
        "best_counterfactual_matches": best,
    }
    detail = {"sub_scores": {k: round(v, 2) for k, v in sub.items()},
              "players_parsed": len(got), "player_misses": misses, "question_misses": qdetail,
              "attribution": attribution}
    return round(score, 2), round(total, 2), detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit(TASK_ID, s, t, d)
