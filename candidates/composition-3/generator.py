#!/usr/bin/env python3
"""Generator for candidate C3: QX-16 Assemble -> Execute -> Decrypt -> Answer.

Deterministic given --seed and --difficulty. Writes prompt.txt, key.json, schema.json
into this directory (or --out).

Pipeline (all reference implementations live here; oracle.py re-derives the key
independently from prompt.txt with different code):
  1. compose a randomized QX-16 assembly listing (mixing loop, self-modifying load,
     indirect table lookup, indirect write-back, forward/backward relative branches)
  2. reference assembler  -> machine words (Stage 1 key)
  3. reference emulator   -> checkpoints, digest, final input block, step count (Stage 2 key)
  4. question generator   -> English question about the final input block (Stage 4 key)
  5. keystream (4-lane 16-bit xorshift) seeded by the digest encrypts the question (Stage 3 key)
"""
import argparse
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))

OPS = ["HLT", "LDA", "STA", "ADD", "ADC", "SUB", "AND", "XOR",
       "ROL", "ROR", "JMP", "JZ", "JNZ", "JC"]
OPCODE = {m: i for i, m in enumerate(OPS)}
JUMPS = {"JMP", "JZ", "JNZ", "JC"}
MEM_WORDS = 512
INPUT_BASE = 0x100

DIFFICULTY = {
    # name: (input words N, self-modifying instructions, ciphertext length, checkpoint interval)
    "easy":    (5, 1, 48, 50),
    "medium":  (7, 1, 56, 50),
    "hard":    (9, 1, 64, 50),
    "extreme": (14, 2, 80, 50),
}


# ----------------------------------------------------------------------------
# Reference assembler (two-pass, explicit parsing)
# ----------------------------------------------------------------------------
def parse_number(tok, labels):
    tok = tok.strip()
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", tok):
        return int(tok, 16)
    if re.fullmatch(r"\d+", tok):
        return int(tok)
    if tok in labels:
        return labels[tok]
    raise ValueError("unknown symbol %r" % tok)


def split_line(line):
    line = line.split(";", 1)[0].rstrip()
    label = None
    m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
    if m:
        label, line = m.group(1), m.group(2)
    return label, line.strip()


def assemble(listing):
    """Return (image dict addr->word, labels dict, meta list of (addr, word, mnemonic, kind))."""
    lines = listing.splitlines()
    # pass 1: addresses
    labels, pc = {}, 0
    for ln in lines:
        label, body = split_line(ln)
        if label:
            if label in labels:
                raise ValueError("duplicate label " + label)
            labels[label] = pc
        if not body:
            continue
        parts = body.split(None, 1)
        mnem = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""
        if mnem == ".ORG":
            pc = parse_number(arg, {})
        elif mnem == ".WORD":
            pc += len([a for a in arg.split(",") if a.strip()])
        else:
            pc += 1
    # pass 2: encode
    image, meta, pc = {}, [], 0
    for ln in lines:
        _, body = split_line(ln)
        if not body:
            continue
        parts = body.split(None, 1)
        mnem = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if mnem == ".ORG":
            pc = parse_number(arg, {})
            continue
        if mnem == ".WORD":
            for a in arg.split(","):
                if a.strip():
                    v = parse_number(a, labels) & 0xFFFF
                    image[pc] = v
                    meta.append((pc, v, ".word", "data"))
                    pc += 1
            continue
        op = OPCODE[mnem]
        if mnem == "HLT":
            word, kind = 0, "hlt"
        elif mnem in JUMPS:
            if arg.startswith("[") and arg.endswith("]"):
                mode, val, kind = 2, parse_number(arg[1:-1], labels), "jump"
            elif arg.startswith("="):
                mode, val, kind = 1, parse_number(arg[1:], labels), "jump"
            else:
                target = parse_number(arg, labels)
                val = target - (pc + 1) + 256
                if not 0 <= val <= 511:
                    raise ValueError("relative branch out of range at %d" % pc)
                mode, kind = 0, "jump"
            word = (op << 12) | (mode << 9) | (val & 0x1FF)
        else:
            if arg.startswith("#"):
                mode, val = 0, parse_number(arg[1:], labels)
                kind = "imm-label" if re.fullmatch(r"[A-Za-z_]\w*", arg[1:]) else "imm"
            elif arg.startswith("[") and arg.endswith("]"):
                mode, val, kind = 2, parse_number(arg[1:-1], labels), "indirect"
            else:
                mode, val, kind = 1, parse_number(arg, labels), "direct"
            if not 0 <= val <= 511:
                raise ValueError("operand does not fit 9 bits at %d: %s" % (pc, body))
            word = (op << 12) | (mode << 9) | val
        image[pc] = word
        meta.append((pc, word, body, kind))
        pc += 1
    return image, labels, meta


# ----------------------------------------------------------------------------
# Reference emulator (explicit if/elif per opcode)
# ----------------------------------------------------------------------------
class Machine:
    def __init__(self, image):
        self.mem = [0] * MEM_WORDS
        for a, w in image.items():
            self.mem[a] = w & 0xFFFF
        self.acc, self.pc, self.c, self.z = 0, 0, 0, 0
        self.steps = 0
        self.halted = False

    def state(self):
        return {"step": self.steps, "pc": self.pc, "acc": self.acc, "c": self.c, "z": self.z}

    def step(self):
        addr = self.pc
        w = self.mem[addr]
        self.pc = (self.pc + 1) & 0x1FF
        op, mode, opnd = (w >> 12) & 0xF, (w >> 9) & 7, w & 0x1FF
        self.steps += 1
        if op == 0 or op >= 14:
            self.halted = True
            return
        # operand resolution
        if op in (10, 11, 12, 13):
            if mode == 0:
                target = (addr + 1 + opnd - 256) & 0x1FF
            elif mode == 1:
                target = opnd
            else:
                target = self.mem[opnd] & 0x1FF
            taken = (op == 10) or (op == 11 and self.z == 1) or \
                    (op == 12 and self.z == 0) or (op == 13 and self.c == 1)
            if taken:
                self.pc = target
            return
        if mode == 0:
            ea, v = opnd, opnd
        elif mode == 1:
            ea = opnd
            v = self.mem[ea]
        else:
            ea = self.mem[opnd] & 0x1FF
            v = self.mem[ea]
        a = self.acc
        if op == 1:      # LDA
            self.acc = v
        elif op == 2:    # STA
            self.mem[ea] = a
            return
        elif op == 3:    # ADD
            r = a + v
            self.c = (r >> 16) & 1
            self.acc = r & 0xFFFF
        elif op == 4:    # ADC
            r = a + v + self.c
            self.c = (r >> 16) & 1
            self.acc = r & 0xFFFF
        elif op == 5:    # SUB
            self.c = 1 if a < v else 0
            self.acc = (a - v) & 0xFFFF
        elif op == 6:    # AND
            self.acc = a & v
        elif op == 7:    # XOR
            self.acc = a ^ v
        elif op == 8:    # ROL
            n = v & 15
            for _ in range(n):
                nc = (self.acc >> 15) & 1
                self.acc = ((self.acc << 1) | self.c) & 0xFFFF
                self.c = nc
        elif op == 9:    # ROR
            n = v & 15
            for _ in range(n):
                nc = self.acc & 1
                self.acc = (self.acc >> 1) | (self.c << 15)
                self.c = nc
        self.z = 1 if self.acc == 0 else 0


def run_machine(image, interval=50, max_steps=20000):
    m = Machine(image)
    cps = []
    while not m.halted and m.steps < max_steps:
        m.step()
        if m.steps % interval == 0 and not m.halted:
            cps.append(m.state())
    final = m.state()
    return m, cps, final


# ----------------------------------------------------------------------------
# Keystream + question
# ----------------------------------------------------------------------------
def keystream(digest, n, a, b, c):
    s = list(digest)
    out = []
    for _ in range(n):
        t = s[0] ^ ((s[0] << a) & 0xFFFF)
        s[0], s[1], s[2] = s[1], s[2], s[3]
        s[3] = s[3] ^ (s[3] >> b) ^ t ^ (t >> c)
        out.append((s[3] ^ (s[3] >> 8)) & 0xFF)
    return out


QUESTION_TYPES = ["xor2", "sum3", "bitcount", "argmax"]


def make_question(rng, n_words):
    qt = rng.choice(QUESTION_TYPES)
    if qt == "xor2":
        i, j = sorted(rng.sample(range(n_words), 2))
        text = "XOR of the final words at 0x%03X and 0x%03X, as 4 hex digits?" % (INPUT_BASE + i, INPUT_BASE + j)
        params = [i, j]
    elif qt == "sum3":
        i, j, k = sorted(rng.sample(range(n_words), 3))
        text = "Sum mod 65536 of the final words at 0x%03X, 0x%03X, 0x%03X, as 4 hex digits?" % (
            INPUT_BASE + i, INPUT_BASE + j, INPUT_BASE + k)
        params = [i, j, k]
    elif qt == "bitcount":
        b = rng.randrange(0, 16)
        text = "How many of the %d final input words have bit %d set, as 4 hex digits?" % (n_words, b)
        params = [b]
    else:
        text = "Address of the largest final input word (lowest if tied), as 4 hex digits?"
        params = []
    return qt, params, text


def eval_question(qt, params, block):
    if qt == "xor2":
        return block[params[0]] ^ block[params[1]]
    if qt == "sum3":
        return (block[params[0]] + block[params[1]] + block[params[2]]) & 0xFFFF
    if qt == "bitcount":
        return sum(1 for w in block if (w >> params[0]) & 1)
    if qt == "argmax":
        best = max(block)
        return INPUT_BASE + block.index(best)
    raise ValueError(qt)


# ----------------------------------------------------------------------------
# Program composition
# ----------------------------------------------------------------------------
LABEL_POOLS = {
    "loop": ["round", "mix", "loop", "again", "turn", "cycle"],
    "skip": ["skip", "over", "pass", "keep", "hop"],
    "ld": ["fetch", "grab", "load", "pull"],
    "st": ["put", "emit", "drop", "stash"],
    "tmp": ["tmp", "scratch", "x", "cur"],
    "cnt": ["cnt", "left", "remain", "n"],
    "wp": ["wp", "outp", "dst", "wcur"],
    "tp": ["tp", "tab", "sel", "ix"],
    "rp": ["rp", "src", "inp", "rcur"],
    "k": ["salt", "key1", "kc", "mask1"],
    "tbl": ["sbox", "table", "tbl", "lut"],
    "in": ["input", "block", "data", "inbuf"],
}


def compose(rng, n_words, sm_count):
    L = {k: rng.choice(v) for k, v in LABEL_POOLS.items()}
    h = rng.choice([("h0", "h1", "h2", "h3"), ("s0", "s1", "s2", "s3"),
                    ("d0", "d1", "d2", "d3"), ("acc0", "acc1", "acc2", "acc3")])
    r1, r2 = rng.randrange(1, 8), rng.randrange(1, 8)
    K1 = rng.randrange(0x1000, 0xFFFF)
    k3 = rng.randrange(0x20, 0x1FF)
    init = [rng.randrange(0x1000, 0xFFFF) for _ in range(4)]
    table = [rng.randrange(0, 0x10000) for _ in range(8)]
    inp = [rng.randrange(0, 256) for _ in range(n_words)]
    lines = []
    A = lines.append
    A("        .org 0x000")
    if sm_count >= 2:
        A("start:  LDA #%d" % n_words)
        A("        STA %s" % L["cnt"])
    else:
        A("start:  LDA #%s" % L["in"])
        A("        STA %s" % L["wp"])
        A("        LDA #%d" % n_words)
        A("        STA %s" % L["cnt"])
    if sm_count == 0:
        A("        LDA #%s" % L["in"])
        A("        STA %s" % L["rp"])
    A("%s:" % L["loop"])
    if sm_count >= 1:
        A("%s: LDA %s          ; operand is patched at runtime" % (L["ld"], L["in"]))
    else:
        A("        LDA [%s]" % L["rp"])
    A("        STA %s" % L["tmp"])
    A("        XOR %s" % h[0])
    A("        ROL #%d" % r1)
    A("        ADC %s" % h[1])
    A("        STA %s" % h[0])
    A("        LDA %s" % L["tmp"])
    A("        AND #7")
    A("        ADD #%s" % L["tbl"])
    A("        STA %s" % L["tp"])
    A("        LDA [%s]" % L["tp"])
    A("        XOR %s" % h[1])
    A("        ROR #%d" % r2)
    A("        STA %s" % h[1])
    A("        LDA %s" % h[2])
    A("        ADC %s" % L["tmp"])
    A("        XOR %s" % L["k"])
    A("        STA %s" % h[2])
    A("        LDA %s" % h[3])
    A("        SUB %s" % h[0])
    A("        JC %s" % L["skip"])
    A("        XOR #0x%03X" % k3)
    A("%s: ADD %s" % (L["skip"], h[2]))
    A("        STA %s" % h[3])
    A("        XOR %s" % h[1])
    if sm_count >= 2:
        A("%s: STA %s          ; operand is patched at runtime" % (L["st"], L["in"]))
        A("        LDA %s" % L["st"])
        A("        ADD #1")
        A("        STA %s" % L["st"])
    else:
        A("        STA [%s]" % L["wp"])
        A("        LDA %s" % L["wp"])
        A("        ADD #1")
        A("        STA %s" % L["wp"])
    if sm_count >= 1:
        A("        LDA %s" % L["ld"])
        A("        ADD #1")
        A("        STA %s" % L["ld"])
    else:
        A("        LDA %s" % L["rp"])
        A("        ADD #1")
        A("        STA %s" % L["rp"])
    A("        LDA %s" % L["cnt"])
    A("        SUB #1")
    A("        STA %s" % L["cnt"])
    A("        JNZ %s" % L["loop"])
    A("        HLT")
    for i in range(4):
        A("%s:     .word 0x%04X" % (h[i], init[i]))
    A("%s:    .word 0" % L["tmp"])
    A("%s:    .word 0" % L["cnt"])
    if sm_count < 2:
        A("%s:    .word 0" % L["wp"])
    if sm_count == 0:
        A("%s:    .word 0" % L["rp"])
    A("%s:    .word 0" % L["tp"])
    A("%s:    .word 0x%04X" % (L["k"], K1))
    A("%s:    .word %s" % (L["tbl"], ", ".join("0x%04X" % t for t in table)))
    A("        .org 0x%03X" % INPUT_BASE)
    A("%s:  .word %s" % (L["in"], ", ".join("0x%02X" % b for b in inp)))
    # normalise label column widths: re-render lines with 'label:' padded to 8 cols
    out = []
    for ln in lines:
        m = re.match(r"^([A-Za-z_]\w*):\s*(.*)$", ln)
        if m:
            out.append(("%s:" % m.group(1)).ljust(8) + m.group(2))
        else:
            out.append(ln)
    listing = "\n".join(out) + "\n"
    info = {"labels": L, "digest_labels": list(h), "r1": r1, "r2": r2, "K1": K1, "k3": k3,
            "init": init, "table": table, "input": inp}
    return listing, info


# ----------------------------------------------------------------------------
# Worked example (assembled and traced by the reference implementation)
# ----------------------------------------------------------------------------
EXAMPLE = """        .org 0x000
        LDA #0x1F3
        SUB #0x1FF
        ROL #3
        ADC val
        JC over
        XOR #1
over:   STA ptr
        LDA [ptr]
        ADD #0x0A5
        JZ over
        HLT
val:    .word 0xC0DE
ptr:    .word val
"""


def render_example():
    image, labels, meta = assemble(EXAMPLE)
    rows = ["address  word    source"]
    for addr, word, body, kind in meta:
        rows.append("0x%03X    0x%04X  %s" % (addr, word, body))
    m = Machine(image)
    trace = ["step  PC(before)  word    ACC(after)  C  Z  PC(after)  note"]
    notes = {
        0: "immediate 0x1F3 zero-extended; Z=0",
        1: "0x01F3 - 0x1FF borrows: C=1, ACC wraps to 0xFFF4",
        2: "3 rotates through carry: C in at bit 0 each time, bit 15 out into C",
        3: "ADC adds mem[val] plus carry-in 1; carry out of bit 16 sets C",
        4: "JC taken (C=1): target = 0x004 + 1 + (0x101 - 256) = 0x006",
        5: "STA ptr (this word is at 0x006 = over): writes ACC into ptr; flags unchanged",
        6: "indirect: address = mem[ptr] & 0x1FF, loads that word; Z from result",
        7: "ADD #0x0A5: no carry out, so C becomes 0; Z=0",
        8: "JZ not taken (Z=0): falls through to 0x00A (operand 0x0FC = 252 would have meant 0x009 + 1 + 252 - 256 = 0x006)",
        9: "HLT: counted as an executed instruction; PC(after) = 0x00B",
    }
    i = 0
    while not m.halted:
        pcb = m.pc
        w = m.mem[pcb]
        m.step()
        trace.append("%-5d 0x%03X       0x%04X  0x%04X      %d  %d  0x%03X      %s" %
                     (m.steps, pcb, w, m.acc, m.c, m.z, m.pc, notes.get(i, "")))
        i += 1
    return "\n".join(rows), "\n".join(trace), m


# ----------------------------------------------------------------------------
# Prompt text
# ----------------------------------------------------------------------------
def spec_text(cfg, ex_words, ex_trace, ex_final, listing, info, cipher_hex, n_cp, ks):
    a, b, c = ks
    L = info["labels"]
    n_words = len(info["input"])
    return f"""IMPORTANT: Solve without any tools — no Bash, no Python, no code execution, no files, no web, no calculator. Work it out yourself, by hand, with exact arithmetic. Your ENTIRE reply must be a single JSON object matching the OUTPUT FORMAT at the end (no prose, no markdown fences, nothing before or after the JSON).

You are given the specification of an invented 16-bit machine (the "QX-16"), an assembly listing, a ciphertext and a keystream definition. Four stages, each a deterministic function of the previous one:

  Stage 1  assemble the listing into exact 16-bit machine words;
  Stage 2  emulate the program from address 0x000 until HLT and report checkpoints, the digest, the final input block and the executed-instruction count;
  Stage 3  use the digest to run the keystream generator and decrypt the ciphertext into an English question;
  Stage 4  answer that question from your Stage 2 final memory.

The QX-16 is not any real machine. Nothing about it can be recalled; everything needed is defined below.

============================================================
PART A — THE QX-16 MACHINE
============================================================

Memory: 512 words of 16 bits, addresses 0x000..0x1FF. Everything not set by the listing is 0x0000.
Registers: ACC (16-bit accumulator), PC (9-bit program counter), flags C (carry, 1 bit) and Z (zero, 1 bit).
Reset state: ACC = 0x0000, PC = 0x000, C = 0, Z = 0 (Z starts at 0 even though ACC is zero).

Instruction word layout (bit 15 = most significant):
  bits 15..12  opcode      (4 bits)
  bits 11..9   mode        (3 bits)
  bits 8..0    operand     (9 bits, an unsigned value 0..511)
  word = (opcode << 12) | (mode << 9) | operand.

Execution cycle, repeated until HLT:
  1. w = mem[PC];  addr = PC;  PC = (PC + 1) & 0x1FF.
  2. decode w and execute it (a taken jump then overwrites PC with its target).
  3. the executed-instruction count increases by 1 (HLT itself counts).
Instructions are fetched from memory each cycle, so a store that changes a word which is executed later changes what executes. The program below deliberately does this.

Modes for data instructions (LDA STA ADD ADC SUB AND XOR ROL ROR):
  mode 0  immediate   value v = operand (zero-extended to 16 bits). For STA, the effective address is the operand itself.
  mode 1  direct      effective address ea = operand;  v = mem[ea].
  mode 2  indirect    ea = mem[operand] & 0x1FF;  v = mem[ea]  (the pointer word's upper 7 bits are ignored).
  modes 3..7 behave exactly like mode 2. (The assembler never emits them.)
Modes for jumps (JMP JZ JNZ JC):
  mode 0  PC-relative  target = (addr + 1 + operand - 256) & 0x1FF, where addr is the address of the jump instruction itself. The bias is 256: operand 256 means "the next word", 255 means "jump to itself", 257 skips one word.
  mode 1  absolute     target = operand.
  mode 2  indirect     target = mem[operand] & 0x1FF.   (modes 3..7 behave like mode 2.)

Opcodes (hex), semantics, and flag effects. "v" is the resolved value, "a" the ACC value before the instruction. All arithmetic is on 16-bit unsigned values.
  0  HLT   stop. Nothing changes except that the instruction is counted and PC has already advanced by 1.
  1  LDA   ACC = v.                                   Z = (ACC == 0).                          C unchanged.
  2  STA   mem[ea] = ACC.                              flags unchanged.
  3  ADD   r = a + v;  ACC = r & 0xFFFF;               C = bit 16 of r (1 if a + v >= 65536).   Z = (ACC == 0).
  4  ADC   r = a + v + C;  ACC = r & 0xFFFF;           C = bit 16 of r.                          Z = (ACC == 0).
  5  SUB   ACC = (a - v) & 0xFFFF;                     C = 1 if a < v (a borrow occurred) else 0. Z = (ACC == 0).
  6  AND   ACC = a & v.                                Z = (ACC == 0).                          C unchanged.
  7  XOR   ACC = a ^ v.                                Z = (ACC == 0).                          C unchanged.
  8  ROL   n = v & 15. Repeat n times: newC = bit 15 of ACC; ACC = ((ACC << 1) | C) & 0xFFFF; C = newC.  Then Z = (ACC == 0).
           (rotate left through carry: the carry flag is a 17th bit; n = 0 changes nothing except Z.)
  9  ROR   n = v & 15. Repeat n times: newC = bit 0 of ACC; ACC = (ACC >> 1) | (C << 15); C = newC.       Then Z = (ACC == 0).
  A  JMP   PC = target.                                flags unchanged.
  B  JZ    if Z == 1: PC = target.                     flags unchanged.
  C  JNZ   if Z == 0: PC = target.                     flags unchanged.
  D  JC    if C == 1: PC = target.                     flags unchanged.
  E, F     not used by the assembler; if ever executed they behave exactly like HLT.
There is no undefined behaviour: every word is executable under the rules above.

============================================================
PART B — ASSEMBLER SYNTAX
============================================================

One statement per line. A line is:  [label:]  [instruction | directive]  [; comment]
Labels are case-sensitive identifiers; a label's value is the address of the word that follows it (the next emitted word).
Numbers are decimal (e.g. 7) or hexadecimal with 0x (e.g. 0x1F3). A bare identifier used as a number is a label.
Directives:
  .org N          continue emitting at address N.
  .word V, V...   emit one 16-bit word per value (a label as a value emits its address).
Operand forms for data instructions:
  #X    mode 0 (immediate; X must be 0..511; X may be a label, giving that label's address as the value)
  X     mode 1 (direct)
  [X]   mode 2 (indirect)
Operand forms for jumps:
  X     mode 0 (PC-relative to the label X: operand = X - (addr + 1) + 256, which must fall in 0..511)
  =X    mode 1 (absolute)
  [X]   mode 2 (indirect)
HLT takes no operand and assembles to 0x0000.
Assembly is two-pass: forward references to labels are fine. Words are emitted in listing order.

============================================================
WORKED EXAMPLE (assembled and executed exactly by these rules)
============================================================

Listing:
{EXAMPLE}
Machine words:
{ex_words}

Execution trace (PC(after) is the PC once the instruction has completed):
{ex_trace}

Final state: ACC = 0x{ex_final.acc:04X}, C = {ex_final.c}, Z = {ex_final.z}, PC = 0x{ex_final.pc:03X}, executed instructions = {ex_final.steps}.
Study this example until every column is reproducible; the same rules apply to the real program.

============================================================
PART C — THE PROGRAM (Stage 1 and Stage 2)
============================================================

{listing}
Stage 1 — "machine_words": list the words at addresses 0x000 up to and including the last word emitted before the ".org 0x{INPUT_BASE:03X}" line, in address order, each as exactly 4 hex digits. Every address in that range is emitted by the listing; there are no gaps. Do NOT include the input block.

Stage 2 — "execution": emulate from reset until HLT and report
  "checkpoints": after every {cfg['interval']}th executed instruction (step {cfg['interval']}, {2*cfg['interval']}, {3*cfg['interval']}, ...) record {{"step", "pc", "acc", "c", "z"}} where pc is the PC value after that instruction completed (i.e. the address of the next instruction to execute) as 3 hex digits, acc as 4 hex digits, and c/z as 0 or 1. Then append one last entry for the final state after HLT, with "step" = the total executed-instruction count. If the machine halts exactly on a multiple of {cfg['interval']}, report that state once, as the final entry.
  "digest": the final contents of the four words labelled {info['digest_labels'][0]}, {info['digest_labels'][1]}, {info['digest_labels'][2]}, {info['digest_labels'][3]}, in that order, 4 hex digits each.
  "instruction_count": the total number of executed instructions including HLT.
  "data_block": the final contents of the {n_words} words of the input block at 0x{INPUT_BASE:03X}..0x{INPUT_BASE + n_words - 1:03X}, in address order, 4 hex digits each (the program overwrites them).

============================================================
PART D — KEYSTREAM AND CIPHERTEXT (Stage 3)
============================================================

Let s0, s1, s2, s3 be the four digest words from Stage 2 ({info['digest_labels'][0]}, {info['digest_labels'][1]}, {info['digest_labels'][2]}, {info['digest_labels'][3]} in that order). All values are 16-bit; "<<" discards bits shifted above bit 15, ">>" is a logical (zero-fill) shift. Generate one keystream byte per ciphertext byte, in order:

  for each byte index i = 0, 1, 2, ...:
      t  = s0 ^ ((s0 << {a}) & 0xFFFF)
      u  = s3 ^ (s3 >> {b}) ^ t ^ (t >> {c})          (computed from the CURRENT s3, before the shift below)
      s0 = s1;  s1 = s2;  s2 = s3;  s3 = u
      k[i] = (s3 ^ (s3 >> 8)) & 0xFF
      plaintext[i] = ciphertext[i] ^ k[i]

Ciphertext ({len(cipher_hex.split())} bytes, hex, in order):
{cipher_hex}

The plaintext is printable ASCII: one English sentence ending in "?". Report it verbatim as "plaintext" (if a few characters come out wrong, still report exactly what you computed; do not "repair" it).

============================================================
PART E — FINAL ANSWER (Stage 4)
============================================================

The plaintext is a question about the FINAL contents of the input block (the words at 0x{INPUT_BASE:03X}..0x{INPUT_BASE + n_words - 1:03X} after HLT, i.e. your "data_block"). "Address" means a memory address (0x{INPUT_BASE:03X} is the first word of the block). Answer it with exactly 4 hex digits in "final_answer": a 16-bit value as 4 hex digits, a count as 4 hex digits (e.g. 5 -> "0005"), an address as 4 hex digits (e.g. 0x104 -> "0104").

============================================================
OUTPUT FORMAT
============================================================

Return ONLY this JSON object (uppercase hex, no 0x prefixes, fixed widths as stated):
{{
  "machine_words": ["....", "....", ...],
  "execution": {{
    "checkpoints": [{{"step": {cfg['interval']}, "pc": "...", "acc": "....", "c": 0, "z": 0}}, ...],
    "digest": ["....", "....", "....", "...."],
    "instruction_count": 0,
    "data_block": ["....", ...]
  }},
  "plaintext": "...",
  "final_answer": "...."
}}
Every stage is graded separately with partial credit, and the later stages are also graded against your own earlier-stage values, so always fill in every field with your best exact computation rather than leaving anything out.
"""


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def build(seed, difficulty, n_words=None, sm=None, cipher_len=None, interval=None):
    N, SM, CL, IV = DIFFICULTY[difficulty]
    if n_words is not None:
        N = n_words
    if sm is not None:
        SM = sm
    if cipher_len is not None:
        CL = cipher_len
    if interval is not None:
        IV = interval
    cfg = {"seed": seed, "difficulty": difficulty, "n_words": N, "self_modifying": SM,
           "cipher_len": CL, "interval": IV}
    rng = random.Random(seed * 1000003 + N * 101 + SM)
    for attempt in range(200):
        listing, info = compose(rng, N, SM)
        image, labels, meta = assemble(listing)
        m, cps, final = run_machine(image, IV)
        if not m.halted:
            continue
        digest = [m.mem[labels[x]] for x in info["digest_labels"]]
        block = m.mem[INPUT_BASE:INPUT_BASE + N]
        qt, params, qtext = make_question(rng, N)
        ks_shift = (rng.randrange(3, 7), rng.randrange(3, 8), rng.randrange(1, 4))
        plaintext = qtext
        cfg["cipher_len"] = len(plaintext)
        ks = keystream(digest, len(plaintext), *ks_shift)
        cipher = [ord(ch) ^ k for ch, k in zip(plaintext, ks)]
        answer = eval_question(qt, params, block)
        # sanity: the answer must be deterministic and the block must actually change
        if block == info["input"]:
            continue
        break
    else:
        raise RuntimeError("could not compose a halting instance")

    prog_end = max(a for a in image if a < INPUT_BASE) + 1
    words = [image[a] for a in range(prog_end)]
    critical = sorted({a for a, w, body, kind in meta
                       if kind in ("jump", "imm-label") or
                       (kind != "data" and a in (labels.get(info["labels"]["ld"]),
                                                 labels.get(info["labels"]["st"])))})
    ex_words, ex_trace, ex_final = render_example()
    cipher_hex = " ".join("%02X" % b for b in cipher)
    n_cp = len(cps) + 1
    prompt = spec_text(cfg, ex_words, ex_trace, ex_final, listing, info, cipher_hex, n_cp, ks_shift)
    key = {
        "task": "C3",
        "config": cfg,
        "machine_words": ["%04X" % w for w in words],
        "critical_word_addresses": critical,
        "labels": labels,
        "listing": listing,
        "input_block": ["%04X" % b for b in info["input"]],
        "execution": {
            "checkpoints": [{"step": s["step"], "pc": "%03X" % s["pc"], "acc": "%04X" % s["acc"],
                             "c": s["c"], "z": s["z"]} for s in cps + [final]],
            "digest": ["%04X" % d for d in digest],
            "instruction_count": final["step"],
            "data_block": ["%04X" % w for w in block],
        },
        "keystream_shifts": list(ks_shift),
        "ciphertext": cipher_hex,
        "plaintext": plaintext,
        "question": {"type": qt, "params": params},
        "final_answer": "%04X" % answer,
    }
    schema = {
        "type": "object",
        "properties": {
            "machine_words": {"type": "array", "items": {"type": "string"}},
            "execution": {
                "type": "object",
                "properties": {
                    "checkpoints": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"step": {"type": "integer"}, "pc": {"type": "string"},
                                       "acc": {"type": "string"}, "c": {"type": "integer"},
                                       "z": {"type": "integer"}},
                        "required": ["step", "pc", "acc", "c", "z"]}},
                    "digest": {"type": "array", "items": {"type": "string"}},
                    "instruction_count": {"type": "integer"},
                    "data_block": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["checkpoints", "digest", "instruction_count", "data_block"],
            },
            "plaintext": {"type": "string"},
            "final_answer": {"type": "string"},
        },
        "required": ["machine_words", "execution", "plaintext", "final_answer"],
    }
    return prompt, key, schema


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--difficulty", choices=sorted(DIFFICULTY), default="hard")
    ap.add_argument("--n-words", type=int, default=None, help="override input block length")
    ap.add_argument("--self-modifying", type=int, choices=[0, 1, 2], default=None)
    ap.add_argument("--cipher-len", type=int, default=None)
    ap.add_argument("--interval", type=int, default=None, help="checkpoint interval")
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    prompt, key, schema = build(args.seed, args.difficulty, args.n_words, args.self_modifying,
                                args.cipher_len, args.interval)
    os.makedirs(args.out, exist_ok=True)
    open(os.path.join(args.out, "prompt.txt"), "w").write(prompt)
    json.dump(key, open(os.path.join(args.out, "key.json"), "w"), indent=1)
    json.dump(schema, open(os.path.join(args.out, "schema.json"), "w"), indent=1)
    print("seed=%d difficulty=%s words=%d steps=%d checkpoints=%d prompt=%d bytes" % (
        args.seed, args.difficulty, len(key["machine_words"]),
        key["execution"]["instruction_count"], len(key["execution"]["checkpoints"]), len(prompt)))


if __name__ == "__main__":
    main()
