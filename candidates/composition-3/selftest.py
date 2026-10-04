#!/usr/bin/env python3
"""Self-test for candidate C3: grader sanity + oracle/generator agreement + emulator fuzz.
Usage: python selftest.py [--seeds 40] [--fuzz 300]
"""
import argparse
import copy
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generator
import oracle
from grade import grade, run_words

KEY = json.load(open(os.path.join(HERE, "key.json")))


def key_answer():
    return {"machine_words": list(KEY["machine_words"]),
            "execution": copy.deepcopy(KEY["execution"]),
            "plaintext": KEY["plaintext"], "final_answer": KEY["final_answer"]}


def record(answer):
    path = tempfile.mktemp(suffix=".json")
    json.dump({"task": "C3", "model": "selftest", "family": "x", "effort": "none", "sample": "s",
               "harness": "selftest", "date": "2026-09-26", "answer": answer, "usage": None,
               "duration_s": None, "cost_usd": None, "cost_basis": "", "cost_estimated": True,
               "notes": ""}, open(path, "w"))
    return path


def cli_score(answer):
    out = subprocess.run([sys.executable, os.path.join(HERE, "grade.py"), record(answer)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--fuzz", type=int, default=300)
    args = ap.parse_args()
    ok = True

    # ---------- 1. key -> full marks (through the CLI, i.e. the same path the runner uses)
    full = cli_score(key_answer())
    print("[key answer]           score=%s/%s" % (full["score"], full["total"]))
    ok &= full["score"] == 100 and full["total"] == 100

    # ---------- 2. corruptions -> strictly fewer marks, and in the right stage
    cases = {}
    a = key_answer(); a["machine_words"][3] = "0000"; cases["one wrong word"] = a
    a = key_answer(); a["execution"]["digest"][2] = "0000"; cases["one wrong digest word"] = a
    a = key_answer(); a["final_answer"] = "FFFF"; cases["wrong final answer"] = a
    a = key_answer(); a["plaintext"] = "x" * len(KEY["plaintext"]); cases["garbage plaintext"] = a
    a = key_answer(); a["execution"]["instruction_count"] += 3; cases["count off by 3 (within 5%)"] = a
    a = key_answer(); a["execution"]["checkpoints"] = a["execution"]["checkpoints"][:2]; cases["only 2 checkpoints"] = a
    cases["empty answer"] = {}
    cases["prose answer (should be full)"] = {"_text": "Here is my answer:\n```json\n" + json.dumps(key_answer()) + "\n```\nDone."}
    cases["python-repr answer (should be full)"] = {"_text": repr(key_answer())}
    lower = key_answer(); lower["machine_words"] = ["0x" + w.lower() for w in lower["machine_words"]]
    lower["final_answer"] = "0x" + lower["final_answer"].lower(); cases["lowercase/0x hex (should be full)"] = lower
    # conditional path: mis-assemble the self-modified LDA word (patch operand off by one) and
    # faithfully emulate the resulting program; Stage 2/3/4 conditional credit should kick in.
    a = key_answer()
    sm_addr = next(ad for ad in KEY["critical_word_addresses"]
                   if int(KEY["machine_words"][ad], 16) >> 12 == 1 and (int(KEY["machine_words"][ad], 16) >> 9) & 7 == 1)
    words = [int(w, 16) for w in a["machine_words"]]
    words[sm_addr] += 1
    a["machine_words"] = ["%04X" % w for w in words]
    own = run_words(words, KEY)
    a["execution"]["checkpoints"] = [{"step": c["step"], "pc": "%03X" % c["pc"], "acc": "%04X" % c["acc"],
                                      "c": c["c"], "z": c["z"]} for c in own["checkpoints"]]
    a["execution"]["instruction_count"] = own["instruction_count"]
    a["execution"]["data_block"] = ["%04X" % w for w in own["data_block"]]
    # digest from own run: read the digest labels' addresses from the key
    labels = KEY["labels"]
    img = {i: w for i, w in enumerate(words)}
    for i, h in enumerate(KEY["input_block"]):
        img[generator.INPUT_BASE + i] = int(h, 16)
    m, _, _ = generator.run_machine(img, KEY["config"]["interval"])
    digest_labels = [ln.split(":")[0] for ln in KEY["listing"].splitlines() if ".word 0x" in ln and ":" in ln][:4]
    own_digest = [m.mem[labels[l]] for l in digest_labels]
    a["execution"]["digest"] = ["%04X" % d for d in own_digest]
    cipher = bytes.fromhex(KEY["ciphertext"].replace(" ", ""))
    ks = generator.keystream(own_digest, len(cipher), *KEY["keystream_shifts"])
    a["plaintext"] = "".join(chr(b ^ k) for b, k in zip(cipher, ks))
    a["final_answer"] = "%04X" % generator.eval_question(KEY["question"]["type"], KEY["question"]["params"],
                                                         own["data_block"])
    cases["mis-assembled self-modified word, faithful own emulation (conditional credit)"] = a

    for name, ans in cases.items():
        r = cli_score(ans)
        s = r["detail"].get("summary", {})
        print("[%-75s] score=%6.2f  stages=%s" % (name, r["score"], s))
        if "should be full" in name:
            ok &= r["score"] == 100
        else:
            ok &= r["score"] < 100
    ok &= cli_score(cases["empty answer"])["score"] == 0

    # ---------- 3. oracle vs generator over many seeds and all difficulties
    tmp = tempfile.mkdtemp()
    fails = 0
    tried = 0
    for diff in sorted(generator.DIFFICULTY):
        for seed in range(1, args.seeds + 1):
            prompt, key, _ = generator.build(seed, diff)
            mine = oracle.derive(prompt)
            tried += 1
            if any(mine[k] != key[k] for k in mine):
                fails += 1
                print("  ORACLE MISMATCH seed=%d difficulty=%s" % (seed, diff))
    # also the self-modifying knob 0 and 2 on the default difficulty
    for sm in (0, 2):
        for seed in range(1, args.seeds + 1):
            prompt, key, _ = generator.build(seed, "hard", sm=sm)
            mine = oracle.derive(prompt)
            tried += 1
            if any(mine[k] != key[k] for k in mine):
                fails += 1
                print("  ORACLE MISMATCH seed=%d sm=%d" % (seed, sm))
    shutil.rmtree(tmp, ignore_errors=True)
    print("[oracle vs generator]  %d instances, %d mismatches" % (tried, fails))
    ok &= fails == 0

    # ---------- 4. dual-emulator fuzz on random instruction images
    rng = random.Random(7)
    mism = 0
    for _ in range(args.fuzz):
        n = rng.randrange(8, 64)
        img = {}
        for i in range(n):
            op = rng.randrange(0, 16) if rng.random() < 0.1 else rng.randrange(1, 14)
            mode = rng.randrange(0, 8) if rng.random() < 0.15 else rng.randrange(0, 3)
            opnd = rng.randrange(0, 512) if rng.random() < 0.3 else rng.randrange(0, n + 8)
            if op in (10, 11, 12, 13) and mode == 0:
                opnd = 256 + rng.randrange(-n, n)
            img[i] = (op << 12) | (mode << 9) | (opnd & 0x1FF)
        for i in range(n, n + 8):
            img[i] = rng.randrange(0, 0x10000)
        m, cps, final = generator.run_machine(img, 25, max_steps=3000)
        st, snaps = oracle.emulate(img, 25, budget=3000)
        ref = [{"step": s["step"], "pc": "%03X" % s["pc"], "acc": "%04X" % s["acc"], "c": s["c"], "z": s["z"]}
               for s in cps + [final]]
        same = ref == snaps and m.mem == st["mem"] and m.halted == (not st["run"])
        if not same:
            mism += 1
    print("[dual emulator fuzz]   %d random programs, %d mismatches" % (args.fuzz, mism))
    ok &= mism == 0

    print("SELFTEST", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
