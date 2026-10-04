#!/usr/bin/env python3
"""Grader for candidate D3 (Crib Slide). Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in key.json
in this directory (written by generator.py).

Scoring (total 60, partial credit throughout):
  period   6   exact match of the integer period
  key     24   if len(key) == true period: 24 x (fraction of key letters that match,
               taking the best cyclic rotation of the submitted key - the canonical
               alignment is K[0] at position 1, but a key reported from a different
               phase is the same cyclic object and is accepted);
               if the length is wrong: the ciphertext is decrypted with the submitted
               key anyway and up to 6 points are given for plaintext letter agreement
  answers 30   10 questions x 3, numbers compared as integers (digits or words),
               codes/names compared letters-only, case- and space-insensitive
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tasks"))
try:
    from _common import load_answer, emit  # noqa: E402
except Exception:  # pragma: no cover - fallback if run outside the repo
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

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = "D3"
PTS_PERIOD, PTS_KEY, PTS_KEY_WRONGLEN, PTS_Q = 6, 24, 6, 3

# ---------------------------------------------------------------- number words
_NW = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
       "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
       "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
       "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
       "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
       "ninety": 90, "hundred": 100, "thousand": 1000, "million": 1000000, "and": None}
_NW_KEYS = sorted(_NW, key=len, reverse=True)


def words_to_int(s):
    """'SEVENTHOUSANDFOURHUNDREDTHIRTYNINE' / 'seven thousand four hundred thirty-nine' -> 7439."""
    s = re.sub(r"[^a-z]", "", str(s).lower())
    if not s:
        return None
    toks, i = [], 0
    while i < len(s):
        for w in _NW_KEYS:
            if s.startswith(w, i):
                toks.append(w)
                i += len(w)
                break
        else:
            return None
    total = cur = 0
    seen_digit_style = all(_NW[t] is not None and _NW[t] < 10 for t in toks)
    if seen_digit_style and len(toks) > 1 and any(t == "zero" for t in toks):
        return int("".join(str(_NW[t]) for t in toks))  # digit-by-digit reading
    for t in toks:
        v = _NW[t]
        if v is None:
            continue
        if v == 100:
            cur = (cur or 1) * 100
        elif v >= 1000:
            total += (cur or 1) * v
            cur = 0
        else:
            cur += v
    return total + cur


def as_int(s):
    s = str(s)
    if re.search(r"\d", s):
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else None
    return words_to_int(s)


def letters(s):
    return re.sub(r"[^A-Z]", "", str(s).upper())


def decrypt(ct, key):
    p = len(key)
    return "".join(chr((ord(c) - ord(key[i % p])) % 26 + 65) for i, c in enumerate(ct))


# ---------------------------------------------------------------- tolerant parsing
def parse_text(text):
    out = {}
    m = re.search(r'"?period"?\s*[:=]\s*"?(\d+)', text, re.I)
    if m:
        out["period"] = int(m.group(1))
    m = re.search(r'"?key"?\s*[:=]\s*"([A-Za-z ]+)"', text) or \
        re.search(r'\bkey\b[^A-Za-z\n]{0,12}([A-Z]{5,30})\b', text)
    if m:
        out["key"] = m.group(1)
    pairs = re.findall(r'"id"\s*:\s*"?(\d+)"?\s*,\s*"value"\s*:\s*"([^"]*)"', text)
    if not pairs:
        pairs = re.findall(r'\bQ?(\d{1,2})\s*[.:)\-]\s*([A-Za-z0-9 ,]+)', text)
    out["answers"] = [{"id": int(i), "value": v} for i, v in pairs]
    return out


def answers_map(ans):
    a = ans.get("answers")
    got = {}
    if isinstance(a, dict):
        for k, v in a.items():
            m = re.search(r"\d+", str(k))
            if m:
                got[int(m.group())] = v
    elif isinstance(a, list):
        for i, item in enumerate(a, 1):
            if isinstance(item, dict):
                try:
                    got[int(str(item.get("id")).strip().lstrip("Qq"))] = item.get("value", "")
                except Exception:
                    pass
            else:
                got[i] = item
    return got


# ---------------------------------------------------------------- grading
def grade(ans):
    key = json.load(open(os.path.join(HERE, "key.json")))
    true_p, true_key, ct, true_pt = key["period"], key["key"], key["ciphertext"], key["plaintext"]
    if "_text" in ans and not ans.get("key"):
        ans = {**parse_text(ans["_text"]), **{k: v for k, v in ans.items() if k != "_text"}}
    detail = {}
    score = 0.0

    # period
    try:
        got_p = int(str(ans.get("period", "")).strip())
    except Exception:
        got_p = None
    if got_p == true_p:
        score += PTS_PERIOD
    else:
        detail["period"] = {"want": true_p, "got": ans.get("period")}

    # key
    sub = letters(ans.get("key", ""))
    key_pts = 0.0
    if sub:
        pt_sub = decrypt(ct, sub)
        agree = sum(a == b for a, b in zip(pt_sub, true_pt)) / len(true_pt)
        detail["plaintext_agreement"] = round(agree, 4)
        if len(sub) == true_p:
            rot_scores = [sum(a == b for a, b in zip(sub[r:] + sub[:r], true_key)) for r in range(true_p)]
            best = max(rot_scores)
            rot = rot_scores.index(best)
            key_pts = PTS_KEY * best / true_p
            detail["key_letters_correct"] = f"{best}/{true_p}"
            if rot:
                detail["key_rotation_applied"] = rot
            if best < true_p:
                detail["key"] = {"want": true_key, "got": sub}
        else:
            key_pts = PTS_KEY_WRONGLEN * agree
            detail["key"] = {"want": true_key, "got": sub, "note": "wrong length; plaintext-agreement credit only"}
    else:
        detail["key"] = {"want": true_key, "got": ans.get("key", "")}
    score += key_pts

    # questions
    got = answers_map(ans)
    q_ok = 0
    for q in key["answers"]:
        g = got.get(q["id"], "")
        want = q["value"]
        if q["type"] == "num":
            hit = as_int(g) is not None and as_int(g) == words_to_int(want)
        else:
            hit = letters(g) == letters(want) and letters(g) != ""
        if hit:
            q_ok += 1
        else:
            detail[f"Q{q['id']}"] = {"want": want, "got": g}
    score += PTS_Q * q_ok
    detail["questions_correct"] = f"{q_ok}/{len(key['answers'])}"
    total = PTS_PERIOD + PTS_KEY + PTS_Q * len(key["answers"])
    return round(score, 2), total, detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit(TASK, s, t, d)
