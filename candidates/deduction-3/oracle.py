#!/usr/bin/env python3
"""Independent oracle for candidate D3 (Crib Slide).

Reads ONLY prompt.txt (never key.json until the final comparison), re-derives
the period and key from the ciphertext, cribs and windows with a different
method from generator.py, decrypts, parses the manifest and extracts the ten
answers, then compares everything against key.json.  Exit code 0 = agreement.

Method (deliberately different from the generator's DFS over crib offsets):
  for each admissible period p, each (crib, offset) hypothesis is turned into a
  p-character "mask" string ('.' = unknown).  The candidate mask SETS of the
  cribs are intersected pairwise (mask unification), deduplicating along the
  way, so the search is over key masks rather than offset tuples.  Whatever
  survives all cribs is a consistent key; there must be exactly one over all p,
  and it must be fully specified.  Independent verification: decrypting with it
  must make every crib appear exactly once and split cleanly on STOP.

Usage: python oracle.py [--dir DIR]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# label lookup for the ten questions (from the question wording, not from key.json)
Q_LABELS = {1: "CONTAINER", 2: "SEALNO", 3: "PALLETS", 4: "CARTONS", 5: "GROSSMASSKG",
            6: "DECLAREDVALUE", 7: "CONSIGNEE", 8: "PORTOFDISCHARGE", 9: "VESSEL",
            10: "SHIPPER"}


def parse_prompt(text):
    m = re.search(r"period p is unknown, but it is between (\d+) and (\d+) inclusive", text)
    pmin, pmax = int(m.group(1)), int(m.group(2))
    lines = re.findall(r"^(\d{4})  ((?:[A-Z]{1,5} ?)+)$", text, re.M)
    ct = ""
    for pos, groups in lines:
        assert int(pos) == len(ct) + 1, "ciphertext line numbering broken"
        ct += groups.replace(" ", "")
    cribs = []
    for lb, lo, hi in re.findall(r"^  - ([A-Z]+)  \(its first letter is at some position between (\d+) and (\d+) inclusive\)", text, re.M):
        cribs.append((lb, int(lo) - 1, int(hi) - 1))
    for lb in re.findall(r"^  - ([A-Z]+)  \(position unknown", text, re.M):
        cribs.append((lb, 0, len(ct) - len(lb)))
    assert cribs, "no cribs parsed"
    return pmin, pmax, ct, cribs


def mask_for(ct, crib, off, p):
    """Key mask implied by placing crib at 0-based offset off, or None if self-contradictory."""
    mask = ["."] * p
    for j, ch in enumerate(crib):
        k = chr((ord(ct[off + j]) - ord(ch)) % 26 + 65)
        r = (off + j) % p
        if mask[r] == ".":
            mask[r] = k
        elif mask[r] != k:
            return None
    return "".join(mask)


def unify(a, b):
    out = []
    for x, y in zip(a, b):
        if x == ".":
            out.append(y)
        elif y == "." or x == y:
            out.append(x)
        else:
            return None
    return "".join(out)


def solve(pmin, pmax, ct, cribs):
    found = []
    for p in range(pmin, pmax + 1):
        sets = []
        for lb, lo, hi in cribs:
            s = set()
            for off in range(lo, hi + 1):
                mk = mask_for(ct, lb, off, p)
                if mk:
                    s.add(mk)
            sets.append(s)
        sets.sort(key=len)
        cur = sets[0]
        for nxt in sets[1:]:
            cur = {u for a in cur for b in nxt for u in [unify(a, b)] if u}
            if not cur:
                break
        for mk in cur:
            found.append((p, mk))
    return found


def vdecrypt(ct, key):
    # written independently: table lookup instead of modular arithmetic on ords
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    idx = {c: i for i, c in enumerate(alpha)}
    out = []
    for i, c in enumerate(ct):
        out.append(alpha[(idx[c] - idx[key[i % len(key)]]) % 26])
    return "".join(out)


def parse_manifest(pt, labels):
    fields = pt.split("STOP")
    got = {}
    for f in fields[1:]:  # first chunk is the carrier header
        for lb in sorted(labels, key=len, reverse=True):
            if f.startswith(lb):
                got[lb] = f[len(lb):]
                break
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    args = ap.parse_args()
    text = open(os.path.join(args.dir, "prompt.txt")).read()
    pmin, pmax, ct, cribs = parse_prompt(text)
    print(f"parsed: {len(ct)} letters, period in [{pmin},{pmax}], cribs={[(c[0], c[1]+1, c[2]+1) for c in cribs]}")

    found = solve(pmin, pmax, ct, cribs)
    print(f"consistent (period, key-mask) candidates: {found}")
    full = [(p, k) for p, k in found if "." not in k]
    if len(found) != 1 or len(full) != 1:
        print("ORACLE FAIL: solution is not unique / not fully determined")
        sys.exit(2)
    p, key = full[0]
    pt = vdecrypt(ct, key)
    # independent sanity: every crib exactly once, STOP splits into label-led fields
    for lb, lo, hi in cribs:
        assert pt.count(lb) == 1 and lo <= pt.index(lb) <= hi, f"crib {lb} check failed"
    got = parse_manifest(pt, list(Q_LABELS.values()))
    answers = {qid: got.get(lb) for qid, lb in Q_LABELS.items()}
    print(f"period={p} key={key}")
    print("answers:", answers)

    ref = json.load(open(os.path.join(args.dir, "key.json")))
    ok = True
    if ref["period"] != p:
        print(f"MISMATCH period: key.json {ref['period']} vs oracle {p}"); ok = False
    if ref["key"] != key:
        print(f"MISMATCH key: key.json {ref['key']} vs oracle {key}"); ok = False
    if ref["plaintext"] != pt:
        print("MISMATCH plaintext"); ok = False
    for a in ref["answers"]:
        want = re.sub(r"[^A-Z]", "", a["value"].upper())
        if answers.get(a["id"]) != want:
            print(f"MISMATCH Q{a['id']}: key.json {want} vs oracle {answers.get(a['id'])}"); ok = False
    print("ORACLE AGREES WITH key.json" if ok else "ORACLE DISAGREES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
