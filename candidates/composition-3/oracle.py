#!/usr/bin/env python3
"""Independent oracle for candidate C3.

Recomputes the whole key from prompt.txt alone (listing, ciphertext, keystream
constants and reporting parameters are all parsed out of the prompt text) with an
implementation that shares no code with generator.py:
  * assembler: regex tokenizer + encoder table, symbol table built by a pre-scan
  * emulator: table-driven decode (dict of opcode -> handler closures) over a state dict
  * keystream: Python generator
  * question: parsed from the DECRYPTED plaintext with regexes and evaluated on the
    oracle's own final memory
Usage: python oracle.py [--dir DIR] [--quiet]   (exit 0 iff it agrees with key.json)
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MNEMONICS = "HLT LDA STA ADD ADC SUB AND XOR ROL ROR JMP JZ JNZ JC".split()
CODE = dict(zip(MNEMONICS, range(16)))
BRANCHES = ("JMP", "JZ", "JNZ", "JC")


# ------------------------------------------------------------------ prompt parsing
def slice_prompt(text):
    m = re.search(r"PART C[^\n]*\n=+\n\n(.*?)\n\nStage 1 ", text, re.S)
    listing = m.group(1)
    cipher = re.search(r"Ciphertext \(\d+ bytes, hex, in order\):\n([0-9A-F ]+)\n", text).group(1)
    a = int(re.search(r"t  = s0 \^ \(\(s0 << (\d+)\)", text).group(1))
    b, c = map(int, re.search(r"u  = s3 \^ \(s3 >> (\d+)\) \^ t \^ \(t >> (\d+)\)", text).groups())
    labs = re.search(r"the four words labelled (\w+), (\w+), (\w+), (\w+),", text).groups()
    interval = int(re.search(r"after every (\d+)th executed instruction", text).group(1))
    lo, hi = re.search(r"input block at 0x([0-9A-F]{3})\.\.0x([0-9A-F]{3}),", text).groups()
    return dict(listing=listing, cipher=bytes.fromhex(cipher.replace(" ", "")),
                shifts=(a, b, c), digest_labels=labs, interval=interval,
                block=(int(lo, 16), int(hi, 16)))


# ------------------------------------------------------------------ assembler
TOKEN = re.compile(r"^(?:(?P<label>\w+):)?\s*(?:(?P<mn>\.?\w+)(?:\s+(?P<arg>[^;]*?))?)?\s*(?:;.*)?$")


def value_of(tok, syms):
    tok = tok.strip()
    return int(tok, 0) if re.fullmatch(r"(0x[0-9A-Fa-f]+|\d+)", tok) else syms[tok]


def statements(src):
    for raw in src.splitlines():
        m = TOKEN.match(raw.strip())
        if not m:
            raise SyntaxError(raw)
        yield m.group("label"), (m.group("mn") or "").upper(), (m.group("arg") or "").strip()


def size_of(mn, arg):
    if mn == ".ORG":
        return 0
    if mn == ".WORD":
        return len([x for x in arg.split(",") if x.strip()])
    return 1 if mn else 0


def symbols(src):
    syms, here = {}, 0
    for label, mn, arg in statements(src):
        if label:
            syms[label] = here
        here = value_of(arg, {}) if mn == ".ORG" else here + size_of(mn, arg)
    return syms


def encode_data(mn, arg, syms, here):
    if arg.startswith("#"):
        mode, v = 0, value_of(arg[1:], syms)
    elif arg.startswith("["):
        mode, v = 2, value_of(arg.strip("[]"), syms)
    else:
        mode, v = 1, value_of(arg, syms)
    return CODE[mn] << 12 | mode << 9 | v


def encode_branch(mn, arg, syms, here):
    if arg.startswith("["):
        mode, v = 2, value_of(arg.strip("[]"), syms)
    elif arg.startswith("="):
        mode, v = 1, value_of(arg[1:], syms)
    else:
        mode, v = 0, value_of(arg, syms) - here - 1 + 256
    assert 0 <= v < 512, "operand out of range"
    return CODE[mn] << 12 | mode << 9 | v


def assemble(src):
    syms = symbols(src)
    mem, here = {}, 0
    for _, mn, arg in statements(src):
        if mn == ".ORG":
            here = value_of(arg, {})
        elif mn == ".WORD":
            for x in arg.split(","):
                if x.strip():
                    mem[here] = value_of(x, syms) & 0xFFFF
                    here += 1
        elif mn == "HLT":
            mem[here] = 0
            here += 1
        elif mn in BRANCHES:
            mem[here] = encode_branch(mn, arg, syms, here)
            here += 1
        elif mn:
            mem[here] = encode_data(mn, arg, syms, here)
            here += 1
    return mem, syms


# ------------------------------------------------------------------ emulator
def make_cpu(mem_init):
    st = {"mem": [mem_init.get(i, 0) for i in range(512)], "acc": 0, "pc": 0, "c": 0, "z": 0,
          "n": 0, "run": True}

    def setz():
        st["z"] = int(st["acc"] == 0)

    def arith(fn):
        def h(v, ea):
            r = fn(st["acc"], v, st["c"])
            st["c"], st["acc"] = (r >> 16) & 1, r & 0xFFFF
            setz()
        return h

    def logic(fn):
        def h(v, ea):
            st["acc"] = fn(st["acc"], v) & 0xFFFF
            setz()
        return h

    def sub(v, ea):
        st["c"] = int(st["acc"] < v)
        st["acc"] = (st["acc"] - v) % 65536
        setz()

    def rol(v, ea):
        for _ in range(v % 16):
            x = st["c"] << 16 | st["acc"]            # 17-bit value C:ACC
            x = ((x << 1) | (x >> 16)) & 0x1FFFF     # rotate it left by one
            st["acc"], st["c"] = x & 0xFFFF, x >> 16
        setz()

    def ror(v, ea):
        for _ in range(v % 16):
            x = st["c"] << 16 | st["acc"]
            x = (x >> 1) | ((x & 1) << 16)           # rotate 17-bit value right by one
            st["acc"], st["c"] = x & 0xFFFF, x >> 16
        setz()

    def sta(v, ea):
        st["mem"][ea] = st["acc"]

    def halt(v, ea):
        st["run"] = False

    def lda(v, ea):
        st["acc"] = v
        setz()

    data_ops = {0: halt, 1: lda, 2: sta,
                3: arith(lambda a, v, c: a + v), 4: arith(lambda a, v, c: a + v + c),
                5: sub, 6: logic(lambda a, v: a & v), 7: logic(lambda a, v: a ^ v),
                8: rol, 9: ror, 14: halt, 15: halt}
    cond = {10: lambda: True, 11: lambda: st["z"] == 1, 12: lambda: st["z"] == 0,
            13: lambda: st["c"] == 1}

    def tick():
        here = st["pc"]
        w = st["mem"][here]
        st["pc"] = (here + 1) % 512
        st["n"] += 1
        op, mode, k = w >> 12, (w >> 9) & 7, w & 511
        if op in cond:
            tgt = {0: (here + 1 + k - 256) % 512, 1: k}.get(mode, st["mem"][k] & 511)
            if cond[op]():
                st["pc"] = tgt
            return
        ea = k if mode == 0 else (k if mode == 1 else st["mem"][k] & 511)
        v = k if mode == 0 else st["mem"][ea]
        data_ops[op](v, ea)

    return st, tick


def emulate(mem_init, interval, budget=20000):
    st, tick = make_cpu(mem_init)
    snaps = []
    snap = lambda: {"step": st["n"], "pc": "%03X" % st["pc"], "acc": "%04X" % st["acc"],
                    "c": st["c"], "z": st["z"]}
    while st["run"] and st["n"] < budget:
        tick()
        if st["run"] and st["n"] % interval == 0:
            snaps.append(snap())
    snaps.append(snap())
    return st, snaps


# ------------------------------------------------------------------ keystream / question
def stream(seed_words, a, b, c):
    s0, s1, s2, s3 = seed_words
    while True:
        t = s0 ^ ((s0 << a) & 0xFFFF)
        u = s3 ^ (s3 >> b) ^ t ^ (t >> c)
        s0, s1, s2, s3 = s1, s2, s3, u
        yield (s3 ^ (s3 >> 8)) & 0xFF


def decrypt(cipher, digest, shifts):
    g = stream(digest, *shifts)
    return "".join(chr(cb ^ next(g)) for cb in cipher)


def answer_question(q, mem, lo, hi):
    words = mem[lo:hi + 1]
    if m := re.match(r"XOR of the final words at 0x([0-9A-F]+) and 0x([0-9A-F]+)", q):
        return mem[int(m[1], 16)] ^ mem[int(m[2], 16)]
    if m := re.match(r"Sum mod 65536 of the final words at 0x([0-9A-F]+), 0x([0-9A-F]+), 0x([0-9A-F]+)", q):
        return sum(mem[int(x, 16)] for x in m.groups()) % 65536
    if m := re.match(r"How many of the \d+ final input words have bit (\d+) set", q):
        return sum((w >> int(m[1])) & 1 for w in words)
    if re.match(r"Address of the largest final input word", q):
        return lo + words.index(max(words))
    raise ValueError("unrecognised question: " + q)


# ------------------------------------------------------------------ main
def derive(prompt_text):
    P = slice_prompt(prompt_text)
    mem, syms = assemble(P["listing"])
    lo, hi = P["block"]
    prog = [mem[i] for i in range(lo) if i in mem]
    assert len(prog) == max(i for i in mem if i < lo) + 1, "gap in program image"
    st, snaps = emulate(mem, P["interval"])
    assert not st["run"], "did not halt"
    digest = [st["mem"][syms[l]] for l in P["digest_labels"]]
    plain = decrypt(P["cipher"], digest, P["shifts"])
    ans = answer_question(plain, st["mem"], lo, hi)
    return {
        "machine_words": ["%04X" % w for w in prog],
        "execution": {"checkpoints": snaps, "digest": ["%04X" % d for d in digest],
                      "instruction_count": st["n"],
                      "data_block": ["%04X" % w for w in st["mem"][lo:hi + 1]]},
        "plaintext": plain,
        "final_answer": "%04X" % ans,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    mine = derive(open(os.path.join(args.dir, "prompt.txt")).read())
    key = json.load(open(os.path.join(args.dir, "key.json")))
    theirs = {k: key[k] for k in mine}
    ok = mine == theirs
    if not args.quiet:
        print(json.dumps(mine, indent=1))
    if ok:
        print("ORACLE AGREES with key.json (%d words, %d steps, answer %s)" % (
            len(mine["machine_words"]), mine["execution"]["instruction_count"], mine["final_answer"]))
    else:
        for k in mine:
            if mine[k] != theirs[k]:
                print("MISMATCH in", k, "\n oracle:", mine[k], "\n key:   ", theirs[k])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
