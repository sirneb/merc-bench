# TALLY-12: two programs on an invented 12-bit register machine (candidate simulation-2)

Execute ~308 + ~930 steps of a made-up VM with saturating SUB, signed-only JLT and DIV-by-zero = 4095, and report the exact output stream, registers and memory, no tools.

## What it tests and why

Sustained, strictly sequential exact arithmetic under semantics that cannot be
recalled, only read. TALLY-12 has 8 twelve-bit registers, 16 memory cells and
16 opcodes; most arithmetic wraps mod 4096 but SUB saturates at 0, DIV by zero
writes 4095, JLT is the only signed comparison, ROT rotates inside 12 bits and
LD/ST index memory by register value mod 16. Both programs are built around a
12-bit LCG (`MUL` by a large odd constant, `ADDI` a large odd constant) whose
state drives data-dependent `JLT` branches, memory scrambling, and (Program B)
an inner loop whose trip count is `(state AND 7) + 1`. There is no closed form
and nothing to pattern-match: every OUT value depends on every earlier step.

The ladder: Program A (25 instructions, 308 steps, 20 OUTs) is
meant to be finishable by careful mid-tier configurations; Program B
(45 instructions, 930 steps, 40 OUTs) is meant to separate high-effort
frontier configurations from everyone else. Low effort tends to summarise loops
("the inner loop runs a few times, so r3 ends near...") which is exactly where
the LCG makes shortcuts fail; higher effort can afford to materialise the
register file after every instruction and recompute each mod-4096 product.
The traps fire often enough that a model that silently applies ordinary VM
semantics once (wrapping SUB, unsigned JLT, DIV-by-zero = 0 or error) diverges
early: in the shipped programs SUB saturates 10+36 times, JLT's signed
verdict differs from the unsigned one 12+21 times, DIV divides by zero
7+12 times, and ADD/ADDI wrap 28+139 times (A+B).

This is a programmatic-domain task, but the language has no prior existence,
so it measures execution, not recall (contrast T2, whose Python idioms are
memorised).

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`.
Total 80 points:

| component | points | rule |
|---|---|---|
| `out_stream` | 60 (20 A + 40 B) | 1 pt per value in the **longest correct prefix** (a value after the first error is only right by coincidence) |
| `final_registers` | 8 | 0.5 pt per exact register, 8 registers x 2 programs |
| `final_memory` | 8 | 0.25 pt per exact cell, 16 cells x 2 programs |
| `steps_executed` | 4 | per program: 2 pts exact, 1 pt within 2 % |
| `halted` | 0 | informational |

`detail` also reports `first_wrong_out_index` and `out_pointwise_matches` per
program as diagnostics. Parsing is tolerant: prose-wrapped or fenced JSON is
extracted, program keys are matched loosely (`program_a`, `A`, `Program A`),
and register/memory dicts (`{"r0": ...}`) are accepted; a missing component
scores 0 for that component only.

Success metric for the benchmark: frontier configurations should spread over
>= 20 points, and Program B alone should show an effort ladder within at least
one model. Expected output: ~35-50k tokens for a faithful trace, which fits the
runner's 64k output budget.

## Difficulty knob

`generator.py --seed N --difficulty easy|medium|hard|extreme` (default
`medium`, shipped with `--seed 2026`), plus `--steps-a/--steps-b` overrides.
Presets set the target executed-step count (hit within 5 %), number of OUT
values, whether Program A has an inner loop, and the AND mask bounding the
inner-loop trip count:

| preset | A steps / OUTs | B steps / OUTs |
|---|---|---|
| easy | 150 / 10 | 400 / 20 |
| **medium** | **300 / 20** | **900 / 40** |
| hard | 400 / 20 (inner loop) | 1100 / 40 (mask 7) |
| extreme | 600 / 30 | 3000 / 60 |

The seed search rejects candidates that do not halt, miss the step window,
lack any opcode statically or execute one fewer than twice, fire any trap
(saturating SUB, signed-vs-unsigned JLT disagreement, DIV by zero, ADD wrap,
MUL wrap) fewer than 3 times, have an output stream with a period <= 8, or
repeat more than 40 % of output values.

## Ground truth and verification

- `generator.py` holds the reference interpreter. The opcode table printed in
  `prompt.txt` is rendered from the same dispatch table (`OPS`: name, syntax,
  prose, function) that the interpreter executes, so the printed semantics
  and the executed semantics have one source.
- `oracle.py` is an independent second interpreter written from the prompt's
  prose (dict state, if/elif chain, signed compare via bias trick, rotation
  via bit-string slicing, saturation via `max`). It parses `prompt.txt`
  itself and must reproduce `key.json` exactly: `python oracle.py`.
  `python oracle.py --fuzz 1000` additionally compares the two interpreters
  in lock step (pc, registers, memory, output length after every step) on
  1,000 random programs rendered through the same listing format, including
  programs that hit the 5,000-step cap or jump out of the listing. Shipped
  result: 0 mismatches.
- Both shipped programs exercise all 16 opcodes (each executed >= 10 times
  apart from HLT) and every trap semantics at least 7 times.
- The first 40 steps of each program are traced below (produced by the
  reference interpreter, matched by the oracle). Steps 8-21 of A and 8-17 of
  B were additionally re-derived by hand while writing this README, e.g.
  A step 8: 261 x 4081 = 261 x (4096 - 15) = -3915 mod 4096 = 181;
  A step 10: 345 x 384 = 132480 = 32 x 4096 + 1408;
  A step 16: 256 - 384 saturates to 0;
  B step 8: 2237 x 2589 = 5,791,593 = 1413 x 4096 + 3945;
  B step 17: JLT 1357, 3890 is NOT taken because 3890 reads as -206.

### Program A, steps 1-40

    step 1  pc=0  SET r0, 20             -> r0=20
    step 2  pc=1  SET r7, 261            -> r7=261
    step 3  pc=2  SET r6, 4081           -> r6=4081
    step 4  pc=3  SET r5, 1              -> r5=1
    step 5  pc=4  SET r1, 345            -> r1=345
    step 6  pc=5  SET r2, 20             -> r2=20
    step 7  pc=6  SET r4, 592            -> r4=592
    step 8  pc=7  MUL r7, r7, r6         -> r7=181
    step 9  pc=8  ADDI r7, r7, 203       -> r7=384
    step 10  pc=9  MUL r1, r1, r7         -> r1=1408
    step 11  pc=10  LD r2, r2              -> r2=308
    step 12  pc=11  ADD r4, r4, r2         -> r4=900
    step 13  pc=12  ST r4, r7              -> mem[0]=900
    step 14  pc=13  JLT r1, r7, 17         -> (no change)
    step 15  pc=14  AND r1, r7, r2         -> r1=256
    step 16  pc=15  SUB r1, r1, r7         -> r1=0
    step 17  pc=16  JMP 18                 -> pc=18
    step 18  pc=18  XOR r4, r4, r2         -> r4=688
    step 19  pc=19  ROT r2, r7, 1          -> r2=768
    step 20  pc=20  XOR r4, r4, r1         -> (no change)
    step 21  pc=21  OUT r2                 -> OUT 768
    step 22  pc=22  ADDI r0, r0, 4095      -> r0=19
    step 23  pc=23  JNZ r0, 7              -> pc=7
    step 24  pc=7  MUL r7, r7, r6         -> r7=2432
    step 25  pc=8  ADDI r7, r7, 203       -> r7=2635
    step 26  pc=9  MUL r1, r1, r7         -> (no change)
    step 27  pc=10  LD r2, r2              -> r2=900
    step 28  pc=11  ADD r4, r4, r2         -> r4=1588
    step 29  pc=12  ST r4, r7              -> mem[11]=1588
    step 30  pc=13  JLT r1, r7, 17         -> (no change)
    step 31  pc=14  AND r1, r7, r2         -> r1=512
    step 32  pc=15  SUB r1, r1, r7         -> r1=0
    step 33  pc=16  JMP 18                 -> pc=18
    step 34  pc=18  XOR r4, r4, r2         -> r4=1456
    step 35  pc=19  ROT r2, r7, 1          -> r2=1175
    step 36  pc=20  XOR r4, r4, r1         -> (no change)
    step 37  pc=21  OUT r2                 -> OUT 1175
    step 38  pc=22  ADDI r0, r0, 4095      -> r0=18
    step 39  pc=23  JNZ r0, 7              -> pc=7
    step 40  pc=7  MUL r7, r7, r6         -> r7=1435

### Program B, steps 1-40

    step 1  pc=0  SET r2, 20             -> r2=20
    step 2  pc=1  SET r7, 2237           -> r7=2237
    step 3  pc=2  SET r0, 2589           -> r0=2589
    step 4  pc=3  SET r5, 7              -> r5=7
    step 5  pc=4  SET r4, 3019           -> r4=3019
    step 6  pc=5  SET r6, 501            -> r6=501
    step 7  pc=6  SET r3, 2055           -> r3=2055
    step 8  pc=7  MUL r7, r7, r0         -> r7=3945
    step 9  pc=8  ADDI r7, r7, 1269      -> r7=1118
    step 10  pc=9  OUT r3                 -> OUT 2055
    step 11  pc=10  LD r6, r7              -> r6=1835
    step 12  pc=11  ADD r3, r3, r6         -> r3=3890
    step 13  pc=12  ST r6, r6              -> mem[11]=1835
    step 14  pc=13  OUT r6                 -> OUT 1835
    step 15  pc=14  ROT r6, r3, 3          -> r6=2455
    step 16  pc=15  ADDI r4, r4, 2434      -> r4=1357
    step 17  pc=16  JLT r4, r3, 20         -> (no change)
    step 18  pc=17  ROT r3, r7, 4          -> r3=1508
    step 19  pc=18  XOR r6, r7, r6         -> r6=3529
    step 20  pc=19  JMP 22                 -> pc=22
    step 21  pc=22  SUB r4, r6, r4         -> r4=2172
    step 22  pc=23  AND r3, r3, r7         -> r3=1092
    step 23  pc=24  JLT r4, r7, 27         -> pc=27
    step 24  pc=27  ROT r6, r3, 3          -> r6=546
    step 25  pc=28  MUL r3, r4, r3         -> r3=240
    step 26  pc=29  XOR r3, r4, r3         -> r3=2188
    step 27  pc=30  LD r6, r4              -> r6=1407
    step 28  pc=31  SUB r3, r3, r6         -> r3=781
    step 29  pc=32  ST r6, r6              -> mem[15]=1407
    step 30  pc=33  DIV r4, r4, r7         -> r4=1
    step 31  pc=34  SUB r4, r6, r7         -> r4=289
    step 32  pc=35  DIV r3, r7, r4         -> r3=3
    step 33  pc=36  AND r1, r7, r5         -> r1=6
    step 34  pc=37  ADDI r1, r1, 1         -> r1=7
    step 35  pc=38  MUL r3, r3, r6         -> r3=125
    step 36  pc=39  ADD r6, r6, r4         -> r6=1696
    step 37  pc=40  ADDI r1, r1, 4095      -> r1=6
    step 38  pc=41  JNZ r1, 38             -> pc=38
    step 39  pc=38  MUL r3, r3, r6         -> r3=3104
    step 40  pc=39  ADD r6, r6, r4         -> r6=1985

## Files

`generator.py` (reference interpreter + program builder + prompt/key/schema
writer), `prompt.txt`, `schema.json`, `key.json` (answer plus `meta`: seed,
trap counts, opcode counts, listings, traces), `grade.py`, `oracle.py`.
