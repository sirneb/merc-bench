#!/usr/bin/env python3
"""Grader for candidate C3 (QX-16 assemble/execute/decrypt). Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Ground truth in key.json next to this file.

Total 100 points, all partial credit:
  Stage 1 machine_words   20   16 x fraction of words exact + 4 x fraction of "critical" words
                               (branches, address-immediates, the self-modified word)
  Stage 2 execution       35   digest 15 (3.75/word), instruction_count 5 (2 if within 5%),
                               data_block 5 (proportional), checkpoints 10 (each checkpoint:
                               pc .35, acc .35, c .15, z .15). Checkpoints and data_block are
                               scored both against the key and against the reference emulator
                               run on the MODEL'S OWN machine words; the higher total counts.
  Stage 3 plaintext       20   character accuracy vs the key plaintext, or vs the decryption
                               produced by the MODEL'S OWN digest, whichever is higher
  Stage 4 final_answer    25   25 exact; else 15 if it answers the question correctly against
                               the MODEL'S OWN reported data_block; else 0
detail reports absolute vs conditional points and the first divergent checkpoint.
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tasks"))
sys.path.insert(0, HERE)
try:
    from _common import load_answer, emit
except ImportError:  # standalone fallback
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

from generator import Machine, run_machine, keystream, eval_question, INPUT_BASE  # reference impl

TASK = "C3"


# ---------------------------------------------------------------- tolerant parsing
def coerce_answer(ans):
    """Accept dict, JSON text, python-repr text, or prose containing a JSON object."""
    if isinstance(ans, dict) and "_text" not in ans:
        return ans
    text = ans.get("_text", "") if isinstance(ans, dict) else str(ans)
    for loader in (json.loads, ast.literal_eval):
        try:
            v = loader(text)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
    text = re.sub(r"```(?:json)?", "", text)
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
    return {}


def hexval(x, width):
    """Normalise a hex-ish value (int, '0x1A', '1a', '  1A ') to an int, or None."""
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x & ((1 << (4 * width)) - 1)
    if isinstance(x, str):
        s = x.strip().lower().replace("0x", "").replace("$", "").replace("h", "")
        if re.fullmatch(r"[0-9a-f]{1,%d}" % max(width, 4), s):
            return int(s, 16)
    return None


def hexlist(x, width):
    if isinstance(x, str):
        x = re.split(r"[\s,]+", x.strip())
    if not isinstance(x, list):
        return []
    return [hexval(v, width) for v in x]


def bit(x):
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, int):
        return x if x in (0, 1) else None
    if isinstance(x, str) and x.strip() in ("0", "1"):
        return int(x.strip())
    return None


def intval(x):
    try:
        return int(str(x).strip().replace(",", ""))
    except Exception:
        return None


# ---------------------------------------------------------------- reference re-runs
def run_words(words, key):
    """Run the reference emulator on an arbitrary program image + the key's input block."""
    image = {i: w for i, w in enumerate(words) if w is not None}
    for i, h in enumerate(key["input_block"]):
        image[INPUT_BASE + i] = int(h, 16)
    m, cps, final = run_machine(image, key["config"]["interval"], max_steps=20000)
    n = len(key["input_block"])
    return {
        "halted": m.halted,
        "checkpoints": [{"step": s["step"], "pc": s["pc"], "acc": s["acc"], "c": s["c"], "z": s["z"]}
                        for s in cps + [final]],
        "data_block": m.mem[INPUT_BASE:INPUT_BASE + n],
        "instruction_count": final["step"],
    }


def key_checkpoints(key):
    return [{"step": c["step"], "pc": int(c["pc"], 16), "acc": int(c["acc"], 16), "c": c["c"], "z": c["z"]}
            for c in key["execution"]["checkpoints"]]


def score_checkpoints(got, ref):
    """got: list of parsed model checkpoints; ref: list of reference checkpoints (last = final).
    Returns (points out of 10, first divergent step or None)."""
    if not ref:
        return 0.0, None
    by_step = {}
    for g in got:
        if g["step"] is not None:
            by_step.setdefault(g["step"], g)
    last_got = max(got, key=lambda g: (g["step"] if g["step"] is not None else -1)) if got else None
    per = 10.0 / len(ref)
    pts, first_div = 0.0, None
    for i, r in enumerate(ref):
        is_final = i == len(ref) - 1
        g = by_step.get(r["step"]) if not is_final else (by_step.get(r["step"]) or last_got)
        frac = 0.0
        if g:
            frac = (0.35 * (g["pc"] == r["pc"]) + 0.35 * (g["acc"] == r["acc"]) +
                    0.15 * (g["c"] == r["c"]) + 0.15 * (g["z"] == r["z"]))
        pts += per * frac
        if frac < 1.0 and first_div is None:
            first_div = r["step"]
    return round(pts, 4), first_div


def parse_checkpoints(raw):
    out = []
    if not isinstance(raw, list):
        return out
    for c in raw:
        if not isinstance(c, dict):
            continue
        out.append({"step": intval(c.get("step")), "pc": hexval(c.get("pc"), 3),
                    "acc": hexval(c.get("acc"), 4), "c": bit(c.get("c")), "z": bit(c.get("z"))})
    return out


def char_accuracy(got, want):
    if not isinstance(got, str) or not want:
        return 0.0
    return sum(1 for a, b in zip(got, want) if a == b) / len(want)


# ---------------------------------------------------------------- grade
def grade(ans):
    ans = coerce_answer(ans)
    key = json.load(open(os.path.join(HERE, "key.json")))
    detail = {}
    total = 100

    # ---- Stage 1: machine words (20)
    kw = [int(h, 16) for h in key["machine_words"]]
    gw = hexlist(ans.get("machine_words", []), 4)
    crit = set(key["critical_word_addresses"])
    match = [i < len(gw) and gw[i] == kw[i] for i in range(len(kw))]
    s1_all = sum(match) / len(kw)
    s1_crit = sum(match[i] for i in crit) / len(crit) if crit else 1.0
    s1 = 16 * s1_all + 4 * s1_crit
    detail["stage1"] = {"points": round(s1, 3), "words_exact": sum(match), "words_total": len(kw),
                        "critical_exact": int(sum(match[i] for i in crit)), "critical_total": len(crit),
                        "first_wrong_address": next((("%03X" % i) for i, m in enumerate(match) if not m), None),
                        "length_reported": len(gw)}

    # ---- Stage 2: execution (35)
    ex = ans.get("execution", {}) if isinstance(ans.get("execution"), dict) else {}
    kd = [int(h, 16) for h in key["execution"]["digest"]]
    gd = hexlist(ex.get("digest", []), 4)
    digest_hits = sum(1 for i in range(4) if i < len(gd) and gd[i] == kd[i])
    s2_digest = 3.75 * digest_hits

    kn = key["execution"]["instruction_count"]
    gn = intval(ex.get("instruction_count"))
    s2_count = 5 if gn == kn else (2 if gn is not None and abs(gn - kn) <= 0.05 * kn else 0)

    kb = [int(h, 16) for h in key["execution"]["data_block"]]
    gb = hexlist(ex.get("data_block", []), 4)
    cps_got = parse_checkpoints(ex.get("checkpoints", []))

    def block_pts(ref):
        return 5.0 * sum(1 for i in range(len(ref)) if i < len(gb) and gb[i] == ref[i]) / len(ref)

    abs_cp, abs_div = score_checkpoints(cps_got, key_checkpoints(key))
    abs_block = block_pts(kb)
    cond_cp, cond_div, cond_block, cond_info = 0.0, None, 0.0, None
    own_words_valid = len(gw) == len(kw) and all(w is not None for w in gw)
    if own_words_valid and gw != kw:
        own = run_words(gw, key)
        cond_info = {"halted": own["halted"], "instruction_count": own["instruction_count"]}
        if own["halted"]:
            cond_cp, cond_div = score_checkpoints(cps_got, own["checkpoints"])
            cond_block = block_pts(own["data_block"])
    use_cond = (cond_cp + cond_block) > (abs_cp + abs_block)
    s2_cp = cond_cp if use_cond else abs_cp
    s2_block = cond_block if use_cond else abs_block
    s2 = s2_digest + s2_count + s2_block + s2_cp
    detail["stage2"] = {"points": round(s2, 3), "digest_words_exact": digest_hits,
                        "instruction_count": {"want": kn, "got": gn, "points": s2_count},
                        "data_block_points": round(s2_block, 3),
                        "checkpoint_points": round(s2_cp, 3),
                        "checkpoints_reported": len(cps_got),
                        "first_divergent_step_vs_key": abs_div,
                        "absolute": {"checkpoints": abs_cp, "data_block": round(abs_block, 3)},
                        "conditional_on_own_words": ({"checkpoints": cond_cp, "data_block": round(cond_block, 3),
                                                      "first_divergent_step": cond_div, **cond_info}
                                                     if cond_info else None),
                        "scored_conditionally": use_cond}

    # ---- Stage 3: plaintext (20)
    kp = key["plaintext"]
    gp = ans.get("plaintext")
    acc_abs = char_accuracy(gp, kp)
    acc_cond = 0.0
    if len(gd) == 4 and all(d is not None for d in gd) and gd != kd:
        cipher = bytes.fromhex(key["ciphertext"].replace(" ", ""))
        ks = keystream(gd, len(cipher), *key["keystream_shifts"])
        own_plain = "".join(chr(b ^ k) for b, k in zip(cipher, ks))
        acc_cond = char_accuracy(gp, own_plain)
    s3 = 20 * max(acc_abs, acc_cond)
    detail["stage3"] = {"points": round(s3, 3), "char_accuracy_vs_key": round(acc_abs, 4),
                        "char_accuracy_vs_own_digest": round(acc_cond, 4), "exact": gp == kp}

    # ---- Stage 4: final answer (25)
    ka = int(key["final_answer"], 16)
    ga = hexval(ans.get("final_answer"), 4)
    if ga is None and isinstance(ans.get("final_answer"), (int, str)):
        ga = intval(ans.get("final_answer"))  # a decimal count is tolerated
    q = key["question"]
    s4, how = 0, "wrong"
    if ga is not None and ga == ka:
        s4, how = 25, "exact"
    elif ga is not None and len(gb) == len(kb) and all(w is not None for w in gb):
        own_ans = eval_question(q["type"], q["params"], gb)
        if ga == own_ans:
            s4, how = 15, "correct against own data_block"
    detail["stage4"] = {"points": s4, "how": how, "want": key["final_answer"],
                        "got": ("%04X" % ga) if ga is not None else None, "question_type": q["type"]}

    score = round(s1 + s2 + s3 + s4, 2)
    detail["summary"] = {"stage1": round(s1, 2), "stage2": round(s2, 2), "stage3": round(s3, 2), "stage4": s4}
    return score, total, detail


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit(TASK, s, t, d)
