#!/usr/bin/env python3
"""Independent oracle for TALLY-12 (candidate simulation-2).

Written from the prompt text only: it parses prompt.txt (the opcode prose is
implemented by hand below, NOT imported from generator.py), executes both
programs, and compares against key.json.  Exit code 0 iff every field agrees.

    python oracle.py                 # verify the shipped prompt/key
    python oracle.py --fuzz 1000     # lock-step comparison against the
                                     # reference interpreter on 1000 random
                                     # programs rendered through the same
                                     # listing format as the prompt

Implementation choices deliberately differ from the reference: dict-based
state, an if/elif chain, signed compare via XOR-bias, rotation via bit-string
slicing, saturation via max(), and a per-step state hash for the fuzz check.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIMIT = 5000


def parse_operands(text):
    ops = []
    if text is None or not text.strip():
        return ops
    for tok in text.split(","):
        tok = tok.strip()
        if re.fullmatch(r"r[0-7]", tok):
            ops.append(("r", int(tok[1])))
        elif re.fullmatch(r"\d+", tok):
            ops.append(("n", int(tok)))
        else:
            raise ValueError("bad operand %r" % tok)
    return ops


def parse_listing(text):
    """'  3: SET r7, 1' lines -> [(op, [operands])]; numbering must be 0..n-1."""
    prog = []
    for line in text.strip().splitlines():
        m = re.match(r"\s*(\d+):\s+([A-Z]+)(?:\s+(.*))?$", line)
        if not m:
            raise ValueError("bad listing line %r" % line)
        idx = int(m.group(1))
        if idx != len(prog):
            raise ValueError("listing numbering gap at %r" % line)
        prog.append((m.group(2), parse_operands(m.group(3))))
    return prog


def parse_prompt(prompt):
    programs = {}
    blocks = re.split(r"\nProgram ([AB])\s+\(\d+ instructions\)\n", prompt)
    # blocks: [head, 'A', bodyA, 'B', bodyB]
    for tag, body in zip(blocks[1::2], blocks[2::2]):
        mm = re.search(r"Initial memory mem\[0\.\.15\] = (\[[^\]]*\])", body)
        memory = json.loads(mm.group(1))
        listing = body.split("Listing:\n", 1)[1]
        listing = listing.split("\n\n", 1)[0]
        programs[tag] = (parse_listing(listing), memory)
    return programs


def to_signed(v):
    # 12-bit two's complement via bias trick (different from the v>=2048 test)
    return ((v + 2048) % 4096) - 2048


def rot_left(v, k):
    bits = format(v, "012b")
    k = k % 12
    return int(bits[k:] + bits[:k], 2)


def execute(prog, memory, on_state=None):
    st = {"r": [0] * 8, "m": list(memory), "pc": 0, "out": [], "n": 0, "halted": False}
    R, M = st["r"], st["m"]

    def val(o):          # operand value: register content or literal
        return R[o[1]] if o[0] == "r" else o[1]

    while True:
        if on_state is not None:
            on_state(st)
        if st["n"] >= LIMIT:
            break
        pc = st["pc"]
        if pc < 0 or pc >= len(prog):
            break
        op, o = prog[pc]
        st["n"] += 1
        nxt = pc + 1
        if op == "HLT":
            st["halted"] = True
            st["pc"] = pc + 1
            break
        elif op == "SET":
            R[o[0][1]] = val(o[1]) % 4096
        elif op == "ADD":
            R[o[0][1]] = (val(o[1]) + val(o[2])) % 4096
        elif op == "ADDI":
            R[o[0][1]] = (val(o[1]) + val(o[2])) % 4096
        elif op == "SUB":
            R[o[0][1]] = max(0, val(o[1]) - val(o[2]))
        elif op == "MUL":
            R[o[0][1]] = (val(o[1]) * val(o[2])) % 4096
        elif op == "DIV":
            b = val(o[2])
            R[o[0][1]] = 4095 if b == 0 else val(o[1]) // b
        elif op == "AND":
            R[o[0][1]] = val(o[1]) & val(o[2])
        elif op == "XOR":
            R[o[0][1]] = val(o[1]) ^ val(o[2])
        elif op == "ROT":
            R[o[0][1]] = rot_left(val(o[1]), val(o[2]))
        elif op == "LD":
            R[o[0][1]] = M[val(o[1]) % 16]
        elif op == "ST":
            M[val(o[1]) % 16] = val(o[0])
        elif op == "OUT":
            st["out"].append(val(o[0]))
        elif op == "JMP":
            nxt = val(o[0])
        elif op == "JLT":
            if to_signed(val(o[0])) < to_signed(val(o[1])):
                nxt = val(o[2])
        elif op == "JNZ":
            if val(o[0]) != 0:
                nxt = val(o[1])
        else:
            raise ValueError("unknown opcode %s" % op)
        st["pc"] = nxt
    return {"out_stream": st["out"], "final_registers": R, "final_memory": M,
            "steps_executed": st["n"], "halted": st["halted"]}


def verify_shipped(quiet=False):
    prompt = open(os.path.join(HERE, "prompt.txt")).read()
    key = json.load(open(os.path.join(HERE, "key.json")))["answer"]
    programs = parse_prompt(prompt)
    ok = True
    for tag in ("A", "B"):
        got = execute(*programs[tag])
        want = key["program_" + tag.lower()]
        for field in ("out_stream", "final_registers", "final_memory",
                      "steps_executed", "halted"):
            if got[field] != want[field]:
                ok = False
                print("MISMATCH Program %s %s:\n  oracle %r\n  key    %r"
                      % (tag, field, got[field], want[field]))
        if not quiet:
            print("Program %s: %d steps, %d outs, halted=%s -> %s"
                  % (tag, got["steps_executed"], len(got["out_stream"]),
                     got["halted"], "agrees with key" if ok else "DISAGREES"))
    return ok


def fuzz(n, seed=7):
    """Lock-step comparison against the reference interpreter on random
    programs (including ones that do not halt and hit the 5000-step cap)."""
    import random
    sys.path.insert(0, HERE)
    import generator as G

    mism = 0
    capped = 0
    for i in range(n):
        rng = random.Random("fuzz|%d|%d" % (seed, i))
        # vary structure widely, not just the shipped presets
        cfg = dict(outs=rng.choice([4, 10, 20, 40]), outs_per_iter=rng.choice([1, 2]),
                   fillers=(1, 9), jlt_blocks=rng.randint(0, 3),
                   mem_segments=rng.randint(0, 2), inner=rng.random() < 0.7,
                   mask_pool=[1, 3, 7, 15, 63, 4095])
        cfg["outs"] -= cfg["outs"] % cfg["outs_per_iter"]
        program, memory = G.build_program(rng, cfg)
        # occasionally corrupt a jump target / operand to exercise the
        # out-of-range and cap rules
        if rng.random() < 0.15:
            j = rng.randrange(len(program))
            ins = list(program[j])
            if ins[0] in ("JMP", "JNZ", "JLT"):
                ins[-1] = rng.randrange(len(program) + 3)
            elif ins[0] == "SET":
                ins[2] = rng.randrange(4096)
            program[j] = tuple(ins)
        text = G.render_listing(program)
        parsed = parse_listing(text)

        ref_states = []
        ref = G.Machine(program, memory).run(
            on_step=lambda m: ref_states.append((m.pc, tuple(m.reg), tuple(m.mem), len(m.out))))
        orc_states = []
        got = execute(parsed, memory,
                      on_state=lambda s: orc_states.append((s["pc"], tuple(s["r"]), tuple(s["m"]), len(s["out"]))))
        want = {"out_stream": ref.out, "final_registers": ref.reg, "final_memory": ref.mem,
                "steps_executed": ref.steps, "halted": ref.halted}
        if not ref.halted:
            capped += 1
        if got != want or ref_states != orc_states:
            mism += 1
            k = next((k for k, (a, b) in enumerate(zip(ref_states, orc_states)) if a != b), None)
            print("FUZZ MISMATCH #%d (first divergent step %s)\n%s" % (i, k, text))
            if mism >= 5:
                break
    print("fuzz: %d programs, %d mismatches, %d hit the step cap / left the listing"
          % (n, mism, capped))
    return mism == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuzz", type=int, default=0)
    args = ap.parse_args()
    good = verify_shipped()
    if args.fuzz:
        good = fuzz(args.fuzz) and good
    sys.exit(0 if good else 1)
