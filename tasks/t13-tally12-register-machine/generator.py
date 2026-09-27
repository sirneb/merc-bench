#!/usr/bin/env python3
"""TALLY-12 generator (candidate simulation-2).

Usage:
    python generator.py [--seed N] [--difficulty easy|medium|hard|extreme]
                        [--steps-a N] [--steps-b N] [--out-dir DIR]

Deterministic for a given (seed, difficulty, overrides). Writes prompt.txt,
key.json and schema.json into the task directory.

Design: the opcode table printed in prompt.txt and the semantics executed by
the reference interpreter are rendered from ONE dispatch table (OPS below), so
the prose and the behaviour cannot drift apart. Programs are template-built
(12-bit LCG feeding data-dependent JLT branches, an inner loop of
data-dependent length, and LD/ST memory scrambling) with random filler
arithmetic, then a seed search keeps only programs that halt, hit the target
step count within 5 %, exercise every opcode, fire every trap semantics
(saturating SUB, signed JLT, DIV-by-zero, wrap-around ADD) at least 3 times,
emit an output stream with no period <= 8, do not emit a statically
readable constant as the first OUT, and have no JLT that is taken exactly
half the times it executes (or never / always).

The shipped default is the `hard` preset (Program A ~400 steps with an
inner loop, Program B ~1,100 steps with mask 7); `medium` is kept as a
calibration rung.  key.json carries, per program, the set of "live" cells
(registers written after the setup block, memory cells whose value changed),
which is all the grader scores for registers/memory.
"""
import argparse
import json
import os
import random
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

WIDTH = 12
MASK = (1 << WIDTH) - 1          # 4095
HALF = 1 << (WIDTH - 1)          # 2048
MEMSZ = 16
NREG = 8
STEP_CAP = 5000


def signed(v):
    return v - (MASK + 1) if v >= HALF else v


def rotl(v, k):
    k %= WIDTH
    return ((v << k) | (v >> (WIDTH - k))) & MASK


# --------------------------------------------------------------------------
# Reference machine
# --------------------------------------------------------------------------
class Machine:
    def __init__(self, program, memory, step_cap=STEP_CAP, setup_len=None):
        self.prog = program
        self.mem = list(memory)
        self.reg = [0] * NREG
        self.pc = 0
        self.out = []
        self.steps = 0
        self.halted = False
        self.running = True
        self.step_cap = step_cap
        self.traps = Counter()
        self.opcount = Counter()
        self.trace = []          # (step, pc, text, effect) for the first N steps
        self.trace_limit = 0
        # "setup" = the leading run of SET instructions; registers first written
        # after it are the live registers the grader scores.
        self.setup_len = setup_len if setup_len is not None else leading_sets(program)
        self.cur_pc = 0
        self.written_after_setup = set()
        self.jlt_exec = Counter()    # static pc -> times executed
        self.jlt_taken = Counter()   # static pc -> times taken
        self.out_src = []            # (register, written_after_setup?) per OUT

    # helpers used by the dispatch table
    def w(self, rd, val):
        self.reg[rd] = val & MASK
        if self.cur_pc >= self.setup_len:
            self.written_after_setup.add(rd)

    def live_registers(self):
        return sorted(self.written_after_setup)

    def live_memory(self, initial):
        return [i for i in range(MEMSZ) if self.mem[i] != initial[i]]

    def trap(self, name):
        self.traps[name] += 1

    def run(self, trace_limit=0, on_step=None):
        self.trace_limit = trace_limit
        while self.running:
            if on_step is not None:
                on_step(self)
            if self.steps >= self.step_cap:
                self.running = False
                break
            if not (0 <= self.pc < len(self.prog)):
                self.running = False
                break
            ins = self.prog[self.pc]
            name, ops = ins[0], ins[1:]
            before = (list(self.reg), list(self.mem), len(self.out))
            cur_pc = self.pc
            self.cur_pc = cur_pc
            self.steps += 1
            self.opcount[name] += 1
            nxt = OPFN[name](self, ops)
            self.pc = cur_pc + 1 if nxt is None else nxt
            if self.steps <= self.trace_limit:
                self.trace.append((self.steps, cur_pc, render_ins(ins),
                                   self._effect(before, nxt)))
        return self

    def _effect(self, before, nxt):
        regs, mem, nout = before
        eff = []
        for i in range(NREG):
            if self.reg[i] != regs[i]:
                eff.append("r%d=%d" % (i, self.reg[i]))
        for i in range(MEMSZ):
            if self.mem[i] != mem[i]:
                eff.append("mem[%d]=%d" % (i, self.mem[i]))
        if len(self.out) > nout:
            eff.append("OUT %d" % self.out[-1])
        if nxt is not None:
            eff.append("pc=%d" % nxt)
        if self.halted:
            eff.append("HALT")
        return ", ".join(eff) if eff else "(no change)"


def leading_sets(program):
    n = 0
    for ins in program:
        if ins[0] != "SET":
            break
        n += 1
    return n


def _hlt(m, o):
    m.halted = True
    m.running = False
    return None


def _set(m, o):
    m.w(o[0], o[1])


def _add(m, o):
    s = m.reg[o[1]] + m.reg[o[2]]
    if s > MASK:
        m.trap("add_wrap")
    m.w(o[0], s)


def _addi(m, o):
    s = m.reg[o[1]] + o[2]
    if s > MASK:
        m.trap("add_wrap")
    m.w(o[0], s)


def _sub(m, o):
    a, b = m.reg[o[1]], m.reg[o[2]]
    if a < b:
        m.trap("sub_saturate")
    m.w(o[0], a - b if a >= b else 0)


def _mul(m, o):
    p = m.reg[o[1]] * m.reg[o[2]]
    if p > MASK:
        m.trap("mul_wrap")
    m.w(o[0], p)


def _div(m, o):
    a, b = m.reg[o[1]], m.reg[o[2]]
    if b == 0:
        m.trap("div_zero")
        m.w(o[0], MASK)
    else:
        m.w(o[0], a // b)


def _and(m, o):
    m.w(o[0], m.reg[o[1]] & m.reg[o[2]])


def _xor(m, o):
    m.w(o[0], m.reg[o[1]] ^ m.reg[o[2]])


def _rot(m, o):
    m.w(o[0], rotl(m.reg[o[1]], o[2]))


def _ld(m, o):
    m.w(o[0], m.mem[m.reg[o[1]] % MEMSZ])


def _st(m, o):
    m.mem[m.reg[o[1]] % MEMSZ] = m.reg[o[0]]


def _out(m, o):
    m.out.append(m.reg[o[0]])
    m.out_src.append((o[0], o[0] in m.written_after_setup))


def _jmp(m, o):
    return o[0]


def _jlt(m, o):
    a, b = m.reg[o[0]], m.reg[o[1]]
    s = signed(a) < signed(b)
    if s != (a < b):
        m.trap("jlt_signed_differs")
    m.jlt_exec[m.cur_pc] += 1
    if s:
        m.jlt_taken[m.cur_pc] += 1
    return o[2] if s else None


def _jnz(m, o):
    return o[1] if m.reg[o[0]] != 0 else None


# name, syntax, prose (what the model reads), function (what the machine does)
OPS = [
    ("HLT", "HLT",
     "Stop the machine. halted = true. HLT itself counts as one executed step.",
     _hlt),
    ("SET", "SET rd, imm",
     "rd = imm  (imm is a constant 0..4095).",
     _set),
    ("ADD", "ADD rd, ra, rb",
     "rd = (ra + rb) mod 4096  (wraps around).",
     _add),
    ("ADDI", "ADDI rd, ra, imm",
     "rd = (ra + imm) mod 4096  (wraps around; e.g. ADDI r1, r1, 4095 decrements r1 by one, and 0 + 4095 = 4095).",
     _addi),
    ("SUB", "SUB rd, ra, rb",
     "rd = ra - rb if ra >= rb, otherwise rd = 0.  SATURATES at 0; it never wraps.",
     _sub),
    ("MUL", "MUL rd, ra, rb",
     "rd = (ra * rb) mod 4096  (only the low 12 bits of the product are kept).",
     _mul),
    ("DIV", "DIV rd, ra, rb",
     "rd = floor(ra / rb) if rb != 0.  If rb == 0, rd = 4095.",
     _div),
    ("AND", "AND rd, ra, rb",
     "rd = ra AND rb  (bitwise).",
     _and),
    ("XOR", "XOR rd, ra, rb",
     "rd = ra XOR rb  (bitwise).",
     _xor),
    ("ROT", "ROT rd, ra, k",
     "rd = ra rotated LEFT by k bit positions inside a 12-bit word (0 <= k <= 11): "
     "bits pushed out past bit 11 re-enter at bit 0.  "
     "Formally rd = ((ra << k) | (ra >> (12 - k))) AND 4095.",
     _rot),
    ("LD", "LD rd, ra",
     "rd = mem[ra mod 16]  (the cell index is the value of ra reduced mod 16).",
     _ld),
    ("ST", "ST rs, ra",
     "mem[ra mod 16] = rs  (the value of the FIRST operand is stored into the cell selected by the SECOND operand mod 16).",
     _st),
    ("OUT", "OUT ra",
     "Append the current value of ra to the output stream.  Registers and memory are unchanged.",
     _out),
    ("JMP", "JMP L",
     "pc = L.",
     _jmp),
    ("JLT", "JLT ra, rb, L",
     "SIGNED compare.  Interpret ra and rb as 12-bit two's complement: a value v in 2048..4095 stands for v - 4096 "
     "(so 4095 means -1, 2048 means -2048; 0..2047 are themselves).  If signed(ra) < signed(rb) then pc = L, "
     "otherwise pc = pc + 1.  This is the ONLY instruction that treats values as signed.",
     _jlt),
    ("JNZ", "JNZ ra, L",
     "If ra != 0 then pc = L, otherwise pc = pc + 1.",
     _jnz),
]
OPFN = {name: fn for name, _, _, fn in OPS}
OPSYNTAX = {name: syn for name, syn, _, _ in OPS}


def op_kinds(name):
    """Operand kinds from the syntax string: 'r' register, 'i' immediate, 'L' label."""
    parts = OPSYNTAX[name].split(None, 1)
    if len(parts) == 1:
        return []
    kinds = []
    for tok in parts[1].split(","):
        tok = tok.strip()
        if tok in ("rd", "ra", "rb", "rs"):
            kinds.append("r")
        elif tok in ("imm", "k"):
            kinds.append("i")
        elif tok == "L":
            kinds.append("L")
        else:
            raise ValueError(tok)
    return kinds


def render_ins(ins):
    name, ops = ins[0], ins[1:]
    kinds = op_kinds(name)
    parts = []
    for k, v in zip(kinds, ops):
        parts.append("r%d" % v if k == "r" else str(v))
    return name + (" " + ", ".join(parts) if parts else "")


def render_listing(program):
    w = len(str(len(program) - 1))
    return "\n".join("%*d: %s" % (w, i, render_ins(ins)) for i, ins in enumerate(program))


def render_opcode_table():
    lines = []
    for name, syn, prose, _ in OPS:
        lines.append("  %-18s %s" % (syn, prose))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Program builder
# --------------------------------------------------------------------------
class Asm:
    def __init__(self):
        self.code = []
        self.labels = {}
        self.n = 0

    def emit(self, *ins):
        self.code.append(list(ins))

    def label(self, name=None):
        if name is None:
            self.n += 1
            name = "L%d" % self.n
        self.labels[name] = len(self.code)
        return name

    def new_label(self):
        self.n += 1
        return "L%d" % self.n

    def resolve(self):
        out = []
        for ins in self.code:
            name = ins[0]
            kinds = op_kinds(name)
            ops = []
            for k, v in zip(kinds, ins[1:]):
                ops.append(self.labels[v] if k == "L" else v)
            out.append(tuple([name] + ops))
        return out


def build_program(rng, cfg):
    """Template: setup; LOOP: LCG step; shuffled body segments (fillers, JLT
    if/else blocks, memory scramble, inner loop of data-dependent length,
    OUTs); counter decrement via wrapping ADDI; JNZ back; HLT."""
    regs = list(range(NREG))
    rng.shuffle(regs)
    STATE, MULT, OUTER, INNER, MSK, S1, S2, S3 = regs
    scratch = [S1, S2, S3]
    srcs = scratch + [STATE]
    a = Asm()

    per_iter = cfg["outs_per_iter"]
    n_iter = cfg["outs"] // per_iter
    use_inner = cfg["inner"]
    mask_val = rng.choice(cfg["mask_pool"])

    def pick_two(pool):
        x = rng.choice(pool)
        y = rng.choice([r for r in pool if r != x])
        return x, y

    def filler(accumulate=False):
        """One or two data-dependent instructions on the scratch registers.
        Two-source ops never use the same register twice (no x-x, x^x, x&x
        degeneracies).  accumulate=True forces d = d op x so that repeating
        the instruction (inside the inner loop) keeps changing state."""
        d = rng.choice(scratch)
        if accumulate:
            x = d
            y = rng.choice([r for r in srcs if r != d])
        elif rng.random() < 0.6:
            x = d
            y = rng.choice([r for r in srcs if r != d])
            if rng.random() < 0.5:
                x, y = y, x
        else:
            x, y = pick_two(srcs)
        if accumulate:
            # d = d op x must keep moving when repeated: no ROT (period <= 12),
            # XOR (period 2) or AND (idempotent) in the inner loop body
            kinds = ["ADD", "SUB", "MUL", "MUL", "DIV", "ADDI"]
        else:
            kinds = ["ADD", "SUB", "SUB", "MUL", "DIV", "AND", "XOR", "ROT", "ADDI",
                     "SUBDIV", "ANDDIV"]
        kind = rng.choice(kinds)
        if kind == "ROT":
            return [("ROT", d, x, rng.randrange(1, WIDTH))]
        if kind == "ADDI":
            return [("ADDI", d, x, rng.randrange(1, MASK + 1))]
        if kind == "SUBDIV":
            d2 = rng.choice([s for s in scratch if s != d])
            return [("SUB", d, x, y), ("DIV", d2, rng.choice([r for r in srcs if r != d]), d)]
        if kind == "ANDDIV":
            d2 = rng.choice([s for s in scratch if s != d])
            return [("AND", d, x, MSK), ("DIV", d2, rng.choice([r for r in srcs if r != d]), d)]
        return [(kind, d, x, y)]

    def fillers(n, accumulate=False):
        out = []
        for _ in range(n):
            out.extend(filler(accumulate))
        return out

    # ---- setup
    a.emit("SET", OUTER, n_iter)
    a.emit("SET", STATE, rng.randrange(1, MASK + 1))
    a.emit("SET", MULT, rng.randrange(101, MASK + 1) | 1)   # odd, >= 101: MUL needs real work
    a.emit("SET", MSK, mask_val)
    for s in scratch:
        a.emit("SET", s, rng.randrange(0, MASK + 1))
    a.label("LOOP")
    a.emit("MUL", STATE, STATE, MULT)
    a.emit("ADDI", STATE, STATE, rng.randrange(101, MASK + 1) | 1)

    segments = []
    # plain fillers, chunked
    n_fill = rng.randint(*cfg["fillers"])
    while n_fill > 0:
        c = min(n_fill, rng.randint(1, 3))
        segments.append(("fill", fillers(c)))
        n_fill -= c
    # JLT if/else blocks
    for _ in range(cfg["jlt_blocks"]):
        x = rng.choice(srcs)
        y = rng.choice([s for s in srcs if s != x])
        segments.append(("jlt", x, y, fillers(rng.randint(1, 2)),
                         fillers(rng.randint(1, 2))))
    # memory scramble segments
    for _ in range(cfg["mem_segments"]):
        d = rng.choice(scratch)
        mix = rng.choice([s for s in scratch if s != d])
        segments.append(("mem", d, rng.choice(srcs), mix,
                         rng.choice(["XOR", "ADD", "SUB"]),
                         rng.choice(scratch), rng.choice(srcs)))
    # inner loop
    if use_inner:
        segments.append(("inner", fillers(rng.randint(1, 2), accumulate=True)))
    # OUTs
    for _ in range(per_iter):
        segments.append(("out", rng.choice(scratch)))
    rng.shuffle(segments)

    for seg in segments:
        kind = seg[0]
        if kind == "fill":
            for ins in seg[1]:
                a.emit(*ins)
        elif kind == "jlt":
            _, x, y, then_ops, else_ops = seg
            l_else, l_end = a.new_label(), a.new_label()
            a.emit("JLT", x, y, l_else)
            for ins in then_ops:
                a.emit(*ins)
            a.emit("JMP", l_end)
            a.label(l_else)
            for ins in else_ops:
                a.emit(*ins)
            a.label(l_end)
        elif kind == "mem":
            _, d, idx, mix, mixop, sreg, sidx = seg
            a.emit("LD", d, idx)
            a.emit(mixop, mix, mix, d)
            a.emit("ST", sreg, sidx)
        elif kind == "inner":
            l_in = a.new_label()
            a.emit("AND", INNER, STATE, MSK)
            a.emit("ADDI", INNER, INNER, 1)
            a.label(l_in)
            for ins in seg[1]:
                a.emit(*ins)
            a.emit("ADDI", INNER, INNER, MASK)
            a.emit("JNZ", INNER, l_in)
        elif kind == "out":
            a.emit("OUT", seg[1])

    a.emit("ADDI", OUTER, OUTER, MASK)
    a.emit("JNZ", OUTER, "LOOP")
    a.emit("HLT")
    program = a.resolve()
    memory = [rng.randrange(0, MASK + 1) for _ in range(MEMSZ)]
    return program, memory


def has_short_period(seq, maxp=8):
    for p in range(1, maxp + 1):
        if len(seq) > p and all(seq[i] == seq[i - p] for i in range(p, len(seq))):
            return True
    return False


def static_constants(program, memory):
    """Values a zero-execution reader can lift straight off the listing: the
    setup immediates, the initial memory cells and 0 (an unset register)."""
    consts = {0}
    for ins in program[:leading_sets(program)]:
        consts.add(ins[2])
    consts.update(memory)
    return consts


def acceptable(m, program, cfg, memory=None):
    tgt = cfg["steps"]
    if not m.halted:
        return "nohalt"
    if abs(m.steps - tgt) > 0.05 * tgt:
        return "steps"
    if len(m.out) != cfg["outs"]:
        return "outs"
    static = Counter(ins[0] for ins in program)
    for name, _, _, _ in OPS:
        if static[name] < 1:
            return "static:" + name
        need = 1 if name == "HLT" else 2
        if m.opcount[name] < need:
            return "dyn:" + name
    for t in ("sub_saturate", "jlt_signed_differs", "div_zero", "add_wrap", "mul_wrap"):
        if m.traps[t] < 3:
            return "trap:" + t
    if has_short_period(m.out):
        return "periodic"
    if len(set(m.out)) < 0.6 * len(m.out):
        return "repetitive"
    # first OUT must not be a constant a static read could copy: the emitting
    # register has to have been written since setup AND the value must not
    # equal a setup immediate / initial memory cell / 0
    if m.out_src and not m.out_src[0][1]:
        return "first_out_constant"
    if memory is not None and m.out[0] in static_constants(program, memory):
        return "first_out_constant"
    # every JLT must be genuinely data-dependent: not never/always taken, and
    # not taken exactly half of the times it executes
    for pc, n in m.jlt_exec.items():
        t = m.jlt_taken[pc]
        if n >= 2 and (t == 0 or t == n):
            return "jlt_dead"
        if n >= 2 and 2 * t == n:
            return "jlt_half"
    if cfg.get("max_insts") and len(program) > cfg["max_insts"]:
        return "long"
    return None


def search(seed, tag, cfg, max_cand=200000):
    reasons = Counter()
    for cand in range(max_cand):
        rng = random.Random("%s|%s|%d" % (seed, tag, cand))
        program, memory = build_program(rng, cfg)
        m = Machine(program, memory).run()
        why = acceptable(m, program, cfg, memory)
        if why is None:
            return program, memory, cand, reasons
        reasons[why] += 1
    raise SystemExit("no acceptable program for %s after %d candidates: %s"
                     % (tag, max_cand, dict(reasons)))


# --------------------------------------------------------------------------
# Difficulty presets
# --------------------------------------------------------------------------
def preset(name):
    """Difficulty knob. steps = target executed-step count (+-5 %), outs =
    number of OUT values, inner = data-dependent inner loop, mask_pool = the
    AND mask bounding the inner-loop trip count (mask+1 max trips).  show_out_counts controls
    whether the prompt states how many values each program emits (easy and
    medium do; hard and extreme make the model find out by running the
    program)."""
    base_a = dict(outs=20, outs_per_iter=1, fillers=(2, 4), jlt_blocks=1,
                  mem_segments=1, inner=False, mask_pool=[1], max_insts=32,
                  show_out_counts=True)
    base_b = dict(outs=40, outs_per_iter=2, fillers=(6, 9), jlt_blocks=2,
                  mem_segments=2, inner=True, mask_pool=[3, 7], max_insts=56,
                  show_out_counts=True)
    P = {
        "easy":    (dict(base_a, steps=150, outs=10),
                    dict(base_b, steps=400, outs=20)),
        "medium":  (dict(base_a, steps=300),
                    dict(base_b, steps=900)),
        "hard":    (dict(base_a, steps=400, inner=True, show_out_counts=False),
                    dict(base_b, steps=1100, mask_pool=[7], show_out_counts=False)),
        "extreme": (dict(base_a, steps=600, outs=30, inner=True, mask_pool=[3],
                         show_out_counts=False),
                    dict(base_b, steps=3000, outs=60, mask_pool=[7, 15],
                         fillers=(8, 12), max_insts=64, show_out_counts=False)),
    }
    return P[name]


DEFAULT_DIFFICULTY = "hard"


# --------------------------------------------------------------------------
# Prompt / schema / key
# --------------------------------------------------------------------------
PROMPT_HEAD = """IMPORTANT: Solve without any tools - no Bash, no Python, no code execution, no files, no web. Work it out yourself, step by step.

You are given the complete specification of TALLY-12, a small register machine that does not exist anywhere else, and two programs written for it. Execute both programs EXACTLY as the machine would and report the results as one JSON object.

=== THE MACHINE ===

- 8 registers r0..r7. Every register holds a 12-bit UNSIGNED integer, 0..4095. All registers start at 0.
- 16 memory cells mem[0]..mem[15], each also a 12-bit unsigned integer. The initial contents are given with each program.
- A program counter pc, starting at 0. Instructions are numbered from 0 in the listing; jump targets are instruction numbers.
- An output stream, initially empty.
- Arithmetic is modulo 4096 (results are reduced to their low 12 bits) EXCEPT where the opcode table says otherwise: SUB saturates at 0 and DIV by zero yields 4095. JLT is the only instruction that reads values as signed.
- Execution: fetch the instruction at pc, execute it, then pc = pc + 1 unless the instruction set pc itself (a taken jump). Every executed instruction counts as one step, including jumps that are not taken and the final HLT.
- The machine stops when it executes HLT (halted = true). If it has executed 5000 steps without HLT, or pc ever leaves the listing, it stops with halted = false. (Both given programs are known to halt well before 5000 steps.)

=== OPCODES (all 16) ===

In the syntax column rd is the destination register, ra/rb/rs are source registers, imm and k are constants, L is an instruction number.

"""

PROMPT_TAIL = """
=== WHAT TO REPORT ===

For each program, report the state at the moment the machine stopped:
- out_stream: every value passed to OUT, in order%(out_counts)s.
- final_registers: [r0, r1, r2, r3, r4, r5, r6, r7] - exactly 8 integers in that order.
- final_memory: [mem[0], ..., mem[15]] - exactly 16 integers in that order.
- steps_executed: the total number of instructions executed, including the HLT.
- halted: true if the machine stopped on HLT.

Scoring note: out_stream is scored half by its longest correct PREFIX and half by how many positions match, so a stream that drifts early loses most of its points while an isolated slip costs little. Registers and memory are scored per element, and only cells the program actually changes count (report all of them anyway). steps_executed earns credit only when exact. Do not skip loop iterations or estimate - every value depends on every earlier step.

=== OUTPUT FORMAT ===

Respond with ONLY this JSON object and nothing else - no prose, no markdown fences, no working:

{"program_a": {"out_stream": [<ints>], "final_registers": [<8 ints>], "final_memory": [<16 ints>], "steps_executed": <int>, "halted": <true|false>},
 "program_b": {"out_stream": [<ints>], "final_registers": [<8 ints>], "final_memory": [<16 ints>], "steps_executed": <int>, "halted": <true|false>}}
"""


def render_prompt(progs):
    parts = [PROMPT_HEAD, render_opcode_table(), "\n\n=== THE PROGRAMS ===\n"]
    for tag, (program, memory) in progs.items():
        parts.append("\nProgram %s  (%d instructions)\n" % (tag, len(program)))
        parts.append("Initial memory mem[0..15] = %s\n" % json.dumps(memory))
        parts.append("Listing:\n")
        parts.append(render_listing(program))
        parts.append("\n")
    return "".join(parts)


SCHEMA = {
    "type": "object",
    "properties": {
        k: {
            "type": "object",
            "properties": {
                "out_stream": {"type": "array", "items": {"type": "integer"}},
                "final_registers": {"type": "array", "items": {"type": "integer"},
                                    "minItems": 8, "maxItems": 8},
                "final_memory": {"type": "array", "items": {"type": "integer"},
                                 "minItems": 16, "maxItems": 16},
                "steps_executed": {"type": "integer"},
                "halted": {"type": "boolean"},
            },
            "required": ["out_stream", "final_registers", "final_memory",
                         "steps_executed", "halted"],
        } for k in ("program_a", "program_b")
    },
    "required": ["program_a", "program_b"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--difficulty", default=DEFAULT_DIFFICULTY,
                    choices=["easy", "medium", "hard", "extreme"])
    ap.add_argument("--steps-a", type=int, help="override Program A target step count")
    ap.add_argument("--steps-b", type=int, help="override Program B target step count")
    ap.add_argument("--out-dir", default=HERE)
    args = ap.parse_args()

    cfg_a, cfg_b = preset(args.difficulty)
    if args.steps_a:
        cfg_a["steps"] = args.steps_a
    if args.steps_b:
        cfg_b["steps"] = args.steps_b

    key = {"answer": {}, "meta": {"seed": args.seed, "difficulty": args.difficulty,
                                  "targets": {"A": cfg_a["steps"], "B": cfg_b["steps"]},
                                  "out_counts_in_prompt": bool(cfg_a["show_out_counts"] and cfg_b["show_out_counts"]),
                                  "programs": {}}}
    progs = {}
    for tag, cfg in (("A", cfg_a), ("B", cfg_b)):
        program, memory, cand, reasons = search(args.seed, tag, cfg)
        m = Machine(program, memory).run(trace_limit=40)
        progs[tag] = (program, memory)
        key["answer"]["program_%s" % tag.lower()] = {
            "out_stream": m.out,
            "final_registers": m.reg,
            "final_memory": m.mem,
            "steps_executed": m.steps,
            "halted": m.halted,
        }
        key["meta"]["programs"][tag] = {
            "instructions": len(program),
            "candidate_index": cand,
            "rejections": dict(reasons),
            "trap_counts": dict(m.traps),
            "opcode_exec_counts": dict(m.opcount),
            "setup_len": m.setup_len,
            # the grader scores ONLY these registers / memory cells
            "live": {"registers": m.live_registers(),
                     "memory": m.live_memory(memory)},
            "jlt": {str(pc): {"executed": n, "taken": m.jlt_taken[pc]}
                    for pc, n in sorted(m.jlt_exec.items())},
            "first_out": {"register": m.out_src[0][0], "value": m.out[0]},
            "initial_memory": memory,
            "listing": render_listing(program).split("\n"),
            "trace_first_40": ["step %d  pc=%d  %-22s -> %s" % t for t in m.trace],
        }
        print("Program %s: %d instructions, %d steps, %d outs, candidate #%d, traps=%s, "
              "live regs=%s, live mem=%d/16"
              % (tag, len(program), m.steps, len(m.out), cand, dict(m.traps),
                 m.live_registers(), len(m.live_memory(memory))),
              file=sys.stderr)

    prompt = render_prompt(progs)
    if cfg_a["show_out_counts"] and cfg_b["show_out_counts"]:
        out_counts = " (Program A emits %d values, Program B emits %d)" % (cfg_a["outs"], cfg_b["outs"])
    else:
        out_counts = ""
    prompt += PROMPT_TAIL % {"out_counts": out_counts}
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "prompt.txt"), "w") as f:
        f.write(prompt)
    with open(os.path.join(args.out_dir, "key.json"), "w") as f:
        json.dump(key, f, indent=1)
    with open(os.path.join(args.out_dir, "schema.json"), "w") as f:
        json.dump(SCHEMA, f, indent=1)
    print("wrote prompt.txt (%d bytes), key.json, schema.json" % len(prompt.encode()),
          file=sys.stderr)


if __name__ == "__main__":
    main()
