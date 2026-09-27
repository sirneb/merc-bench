# TALLY-12: two programs on an invented 12-bit register machine (T13)

Execute 390 + 1072 steps of a made-up VM with saturating SUB, signed-only JLT and DIV-by-zero = 4095, and report the exact output stream, registers and memory, no tools. Shipped at the `hard` preset (the tournament's recommended canonical rung).

## What it tests and why

Sustained, strictly sequential exact arithmetic under semantics that cannot be
recalled, only read. TALLY-12 has 8 twelve-bit registers, 16 memory cells and
16 opcodes; most arithmetic wraps mod 4096 but SUB saturates at 0, DIV by zero
writes 4095, JLT is the only signed comparison, ROT rotates inside 12 bits and
LD/ST index memory by register value mod 16. Both programs are built around a
12-bit LCG (`MUL` by a large odd constant, `ADDI` a large odd constant) whose
state drives data-dependent `JLT` branches, memory scrambling, and an inner
loop whose trip count is `(state AND mask) + 1` (mask 1 in Program A, mask 7
in Program B). There is no closed form and nothing to pattern-match: every OUT
value depends on every earlier step.

The ladder: Program A (27 instructions, 390 steps, 20 OUTs, inner loop of
1-2 trips) is meant to be finishable by careful mid-tier configurations;
Program B (48 instructions, 1072 steps, 40 OUTs, inner loop of 1-8 trips) is meant
to separate high-effort frontier configurations from everyone else. The hard
prompt does NOT say how many values each program emits: the model has to find
out by running the loop to completion. Low effort tends to summarise loops
("the inner loop runs a few times, so r1 ends near...") which is exactly where
the LCG makes shortcuts fail; higher effort can afford to materialise the
register file after every instruction and recompute each mod-4096 product.
The traps fire often enough that a model that silently applies ordinary VM
semantics once (wrapping SUB, unsigned JLT, DIV-by-zero = 0 or error) diverges
early: in the shipped programs SUB saturates 11+21 times, JLT's signed
verdict differs from the unsigned one 12+21 times, DIV divides by zero
23+18 times, ADD/ADDI wrap 79+182 times and MUL wraps 20+143 times (A+B).

This is a programmatic-domain task, but the language has no prior existence,
so it measures execution, not recall (contrast T2, whose Python idioms are
memorised).

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`.
Total 80 points:

| component | points | rule |
|---|---|---|
| `out_stream` | 60 (20 A + 40 B) | per program, **0.5 x longest correct prefix + 0.5 x pointwise matches** (each OUT position is worth 1 point at most). A stream that drifts at position k keeps ~k/2 + coincidences; an isolated non-propagating slip at position k costs (N - k)/2 + 0.5 |
| `final_registers` | 8 | 4 pts per program, split evenly over the **live** registers: those written by an instruction after the leading SET block (A: r0, r1, r2, r5, r6, r7; B: r0, r1, r2, r4, r5, r6). The dead registers (A: r3, r4; B: r3, r7: the multiplier and the AND mask) earn nothing, right or wrong |
| `final_memory` | 8 | 4 pts per program, split evenly over the **live** cells, i.e. those whose value changed during the run (A: cells 0, 2, 9, 10, 11, 12, 14, 15; B: cells 3, 4, 5, 7, 9, 10, 14, 15). Untouched cells earn nothing |
| `steps_executed` | 4 | 2 pts per program, **exact only** |
| `halted` | 0 | informational |

The live sets are stored in `key.json` under `meta.programs.<A|B>.live` (the
generator computes them; `oracle.py` re-derives them independently and checks
they agree). `detail` reports, per program, `out_points`,
`out_prefix_correct`, `out_pointwise_matches`, `first_wrong_out_index`,
`out_reported`, the live indices hit for registers/memory (plus `all_8_ok` /
`all_16_ok` for reference) and the steps verdict.

Why the blend: the first pilot's Sonnet 5 run got 36/40 of Program B's OUT
values right with four isolated, non-propagating slips, and a pure
longest-prefix rule turned that into a 34-point loss (44.5/80); the critics
showed that values after a slip are genuine execution, not coincidence, and
that a prefix-only score has a Monte-Carlo SD of 13 points at a 5 % slip rate
versus 1.4 for pointwise. Prefix still carries half the weight because a
pointwise-only rule would let a model that drops out of sync early (and later
happens to realign) score like a careful one.

Why live cells only: with all 8 registers and 16 cells scored, a zero-execution
"static read" of the listing (setup constants for registers, the printed
initial memory for cells) scored 10.5/80 in the piloted medium package. With
the shipped programs and this grader the same static read scores 2.67/80
(only the four loop counters -- the outer r1/r6 and the inner r5 in each
program -- which any reader can see end at 0); a static read that also
guesses zeros for the whole output stream scores 4.67/80 (Program B has four
zero OUT values, Program A none; measured by grading such an answer).

Parsing is tolerant: prose-wrapped or fenced JSON is extracted, taking the
**last** balanced object that carries program keys (so a corrected final
answer beats an earlier draft); `answer`/`result`/`response` wrappers are
unwrapped; program keys resolve through a fixed alias priority (`program_a`
first, then `Program A`, `A`, ...), as do field names (`final_registers`,
`registers`, `regs`, ...); string-valued programs are `json.loads`'ed;
`768.0` and `"768"` coerce to 768; register/memory dicts (`{"r0": ...}`) are
accepted. A missing component scores 0 for that component only. `grade.py`
finds `tasks/_common.py` whether it runs from `candidates/<id>/` or from
`tasks/<id>/` (and falls back to an inline copy of `load_answer`/`emit`).

Success metric for the benchmark: frontier configurations should spread over
>= 20 points, and Program B alone should show an effort ladder within at least
one model.

## Expected output volume

In the medium-preset pilot (1,238 executed steps) a faithful trace cost
34-35k output tokens for Sonnet 5 and Opus 5.5 and 70k for Fable 5.1 at
medium effort; 98-99 % of every run's output tokens were thinking (Fable:
69,756 of 70,242). The shipped `hard` programs execute 1462 steps, 1.18x
the pilot, so expect roughly **40-42k output tokens for Sonnet 5 / Opus 5.5
and ~83k for Fable 5.1 at medium**, thinking-dominated. That is above the
64,000-token `max_tokens` hard-coded in `runner/run.py::run_api` as shipped:
the API harness needs a per-task output budget of >= 128k for this task (and
should record the effective cap and harness in `notes`), otherwise the
strongest configurations are truncated and recorded invalid. Do not ship
`extreme` (3,600 steps): it projects to 100-200k output tokens and converts
capability differences into truncation failures. The prompt is 6226 bytes.

## Difficulty knob

`generator.py --seed N --difficulty easy|medium|hard|extreme` (default
**`hard`**, shipped with `--seed 2026`), plus `--steps-a/--steps-b` overrides.
`medium` is kept as a calibration rung (its pilot is in `pilot/`). Presets set
the target executed-step count (hit within 5 %), number of OUT values, whether
Program A has an inner loop, the AND mask bounding the inner-loop trip count,
and whether the prompt states the OUT counts:

| preset | A steps / OUTs | B steps / OUTs | OUT counts in prompt |
|---|---|---|---|
| easy | 150 / 10 | 400 / 20 | yes |
| medium | 300 / 20 | 900 / 40 | yes |
| **hard** (default) | **400 / 20 (inner loop, mask 1)** | **1100 / 40 (mask 7)** | **no** |
| extreme | 600 / 30 | 3000 / 60 | no |

Shipped result at `hard`, seed 2026: A 390 steps (candidate #129), B 1072 steps
(candidate #656).

The seed search rejects candidates that do not halt, miss the step window,
lack any opcode statically or execute one fewer than twice, fire any trap
(saturating SUB, signed-vs-unsigned JLT disagreement, DIV by zero, ADD wrap,
MUL wrap) fewer than 3 times, have an output stream with a period <= 8, or
repeat more than 40 % of output values. Two rejections were added after the
tournament critique:

- `first_out_constant`: the first OUT must come from a register that has been
  written since the setup block, and its value must not equal any setup
  immediate, any initial memory cell or 0 (the piloted Program B opened with
  `OUT r3` = the SET constant 2055, a free point for a static read).
- `jlt_half` / `jlt_dead`: for every JLT instruction, the number of times it
  is taken must not be exactly half of the times it executes, and it must not
  be never- or always-taken (a coin-flip or a constant guess would otherwise
  reproduce the branch pattern). Shipped take-rates: A pc19 8/20;
  B pc19 8/20, pc38 13/20.

Rejection tallies for the shipped seed are in `key.json` `meta.programs.<X>.rejections`
(B needed 656 candidates, 5 of them rejected for `first_out_constant`).

## Ground truth and verification

- `generator.py` holds the reference interpreter. The opcode table printed in
  `prompt.txt` is rendered from the same dispatch table (`OPS`: name, syntax,
  prose, function) that the interpreter executes, so the printed semantics
  and the executed semantics have one source.
- `oracle.py` is an independent second interpreter written from the prompt's
  prose (dict state, if/elif chain, signed compare via bias trick, rotation
  via bit-string slicing, saturation via `max`). It parses `prompt.txt`
  itself and must reproduce `key.json` exactly, including the live
  register/memory sets: `python oracle.py`. It also asserts that the hard
  prompt states no OUT counts. `python oracle.py --fuzz 500` additionally
  compares the two interpreters in lock step (pc, registers, memory, output
  length after every step, and the live sets at the end) on 500 random
  programs rendered through the same listing format, including programs that
  hit the 5,000-step cap or jump out of the listing. Shipped result: agrees
  with key on every field; 0 mismatches in 500 fuzz programs (76 of them hit
  the cap or left the listing).
- Both shipped programs exercise all 16 opcodes (each executed >= 7 times
  apart from HLT) and every trap semantics at least 11 times.
- The first 40 steps of each program are traced below (produced by the
  reference interpreter, matched by the oracle). The first loop iteration of
  each program was additionally re-derived by hand while writing this README:
  A step 8: 417 x 193 = 80,481 = 19 x 4096 + 2657;
  A step 9: 2657 + 2913 = 5570 - 4096 = 1474;
  A step 12: `LD r0, r6` reads mem[3937 mod 16] = mem[1] = 971;
  A step 13: 3937 + 971 = 4908 - 4096 = 812; step 14 stores it at mem[971 mod 16] = mem[11];
  A step 20: `JLT r7, r6` compares 3555 (reads as -541) with 812: taken, where an unsigned compare would fall through;
  A step 21: ROT 812 left by 8: (812 << 8) AND 4095 = 3072, 812 >> 4 = 50, OR = 3122 (the first OUT);
  B step 8: 758 x 4067 = 3,082,786 = 752 x 4096 + 2594; step 9: 2594 + 1289 = 3883;
  B step 10: 3883 AND 7 = 3, so the inner loop runs 4 times;
  B step 12: 2122 x 1309 = 2,777,698 = 678 x 4096 + 610;
  B step 32: `JLT r1, r4` compares 2850 (-1246) with 3883 (-213): taken;
  B step 36: 734 - 3712 saturates to 0; step 39: DIV by r1 = 0 gives 4095.

### Program A, steps 1-40

    step 1  pc=0  SET r1, 20             -> r1=20
    step 2  pc=1  SET r2, 417            -> r2=417
    step 3  pc=2  SET r3, 193            -> r3=193
    step 4  pc=3  SET r4, 1              -> r4=1
    step 5  pc=4  SET r0, 2782           -> r0=2782
    step 6  pc=5  SET r7, 3555           -> r7=3555
    step 7  pc=6  SET r6, 3937           -> r6=3937
    step 8  pc=7  MUL r2, r2, r3         -> r2=2657
    step 9  pc=8  ADDI r2, r2, 2913      -> r2=1474
    step 10  pc=9  AND r0, r0, r6         -> r0=2624
    step 11  pc=10  XOR r0, r0, r2         -> r0=3970
    step 12  pc=11  LD r0, r6              -> r0=971
    step 13  pc=12  ADD r6, r6, r0         -> r6=812
    step 14  pc=13  ST r6, r0              -> mem[11]=812
    step 15  pc=14  AND r5, r2, r4         -> (no change)
    step 16  pc=15  ADDI r5, r5, 1         -> r5=1
    step 17  pc=16  DIV r0, r0, r7         -> r0=0
    step 18  pc=17  ADDI r5, r5, 4095      -> r5=0
    step 19  pc=18  JNZ r5, 16             -> (no change)
    step 20  pc=19  JLT r7, r6, 22         -> pc=22
    step 21  pc=22  ROT r6, r6, 8          -> r6=3122
    step 22  pc=23  OUT r6                 -> OUT 3122
    step 23  pc=24  ADDI r1, r1, 4095      -> r1=19
    step 24  pc=25  JNZ r1, 7              -> pc=7
    step 25  pc=7  MUL r2, r2, r3         -> r2=1858
    step 26  pc=8  ADDI r2, r2, 2913      -> r2=675
    step 27  pc=9  AND r0, r0, r6         -> (no change)
    step 28  pc=10  XOR r0, r0, r2         -> r0=675
    step 29  pc=11  LD r0, r6              -> r0=3836
    step 30  pc=12  ADD r6, r6, r0         -> r6=2862
    step 31  pc=13  ST r6, r0              -> mem[12]=2862
    step 32  pc=14  AND r5, r2, r4         -> r5=1
    step 33  pc=15  ADDI r5, r5, 1         -> r5=2
    step 34  pc=16  DIV r0, r0, r7         -> r0=1
    step 35  pc=17  ADDI r5, r5, 4095      -> r5=1
    step 36  pc=18  JNZ r5, 16             -> pc=16
    step 37  pc=16  DIV r0, r0, r7         -> r0=0
    step 38  pc=17  ADDI r5, r5, 4095      -> r5=0
    step 39  pc=18  JNZ r5, 16             -> (no change)
    step 40  pc=19  JLT r7, r6, 22         -> (no change)

### Program B, steps 1-40

    step 1  pc=0  SET r6, 20             -> r6=20
    step 2  pc=1  SET r4, 758            -> r4=758
    step 3  pc=2  SET r7, 4067           -> r7=4067
    step 4  pc=3  SET r3, 7              -> r3=7
    step 5  pc=4  SET r0, 1804           -> r0=1804
    step 6  pc=5  SET r2, 1309           -> r2=1309
    step 7  pc=6  SET r1, 2122           -> r1=2122
    step 8  pc=7  MUL r4, r4, r7         -> r4=2594
    step 9  pc=8  ADDI r4, r4, 1289      -> r4=3883
    step 10  pc=9  AND r5, r4, r3         -> r5=3
    step 11  pc=10  ADDI r5, r5, 1         -> r5=4
    step 12  pc=11  MUL r1, r1, r2         -> r1=610
    step 13  pc=12  ADDI r1, r1, 778       -> r1=1388
    step 14  pc=13  ADDI r5, r5, 4095      -> r5=3
    step 15  pc=14  JNZ r5, 11             -> pc=11
    step 16  pc=11  MUL r1, r1, r2         -> r1=2364
    step 17  pc=12  ADDI r1, r1, 778       -> r1=3142
    step 18  pc=13  ADDI r5, r5, 4095      -> r5=2
    step 19  pc=14  JNZ r5, 11             -> pc=11
    step 20  pc=11  MUL r1, r1, r2         -> r1=494
    step 21  pc=12  ADDI r1, r1, 778       -> r1=1272
    step 22  pc=13  ADDI r5, r5, 4095      -> r5=1
    step 23  pc=14  JNZ r5, 11             -> pc=11
    step 24  pc=11  MUL r1, r1, r2         -> r1=2072
    step 25  pc=12  ADDI r1, r1, 778       -> r1=2850
    step 26  pc=13  ADDI r5, r5, 4095      -> r5=0
    step 27  pc=14  JNZ r5, 11             -> (no change)
    step 28  pc=15  ROT r2, r4, 1          -> r2=3671
    step 29  pc=16  ADDI r2, r4, 3925      -> r2=3712
    step 30  pc=17  MUL r0, r0, r2         -> r0=3584
    step 31  pc=18  OUT r2                 -> OUT 3712
    step 32  pc=19  JLT r1, r4, 23         -> pc=23
    step 33  pc=23  SUB r0, r0, r1         -> r0=734
    step 34  pc=24  AND r1, r0, r1         -> r1=514
    step 35  pc=25  OUT r1                 -> OUT 514
    step 36  pc=26  SUB r0, r0, r2         -> r0=0
    step 37  pc=27  ADD r2, r0, r2         -> (no change)
    step 38  pc=28  AND r1, r0, r3         -> r1=0
    step 39  pc=29  DIV r0, r0, r1         -> r0=4095
    step 40  pc=30  AND r2, r2, r3         -> r2=0

## Pilot history

`pilot/` holds the first pilot, run on the **medium** preset (seed 2026,
A 308 / B 930 steps, prefix-only out_stream scoring, all cells scored):
Haiku 4.5 @low 8.25, Sonnet 5 @medium 44.5, Opus 5.5 @medium 80, Fable 5.1
@medium 80 (of 80). Rescored with the blended out_stream rule those become
8.25 / 59.5 / 80 / 80 (tournament report, section 2.2). Those records are
answers to the medium programs and do not grade against the shipped hard
key; they are kept untouched as provenance. Note that `--difficulty medium`
regenerated with today's generator no longer reproduces the piloted programs
(the new `first_out_constant` rule rejects the piloted Program B, whose first
OUT was the SET constant 2055): it now yields A 308 / B 877 steps. The tournament's next step is to
replicate Opus 5.5 and Fable 5.1 at medium (n=3) and then pilot this hard
package.

## Changes applied after the tournament (TOURNAMENT.md section 4.1, item 1)

- `out_stream` scored 0.5 x longest-correct-prefix + 0.5 x pointwise matches; `first_wrong_out_index` / `out_pointwise_matches` kept as diagnostics; prompt scoring note and this README updated.
- Registers and memory scored only on live cells (registers written after setup, cells whose value changed), 4 + 4 points per program spread evenly; `steps_executed` exact-only.
- Generator rejections `first_out_constant` and `jlt_half` (plus `jlt_dead`); live sets, per-JLT take counts and the first OUT's provenance recorded in `key.json` meta; the oracle re-derives and checks the live sets.
- Grader extractor prefers the LAST candidate object with program keys, unwraps `answer`/`result` wrappers, coerces `768.0` / `"768"` to 768, `json.loads` string-valued programs, resolves program and field names through a fixed canonical-first alias order; the `_common` import works from both `candidates/<id>/` and `tasks/<id>/`.
- `hard` preset (A ~400 steps with inner loop / 20 OUTs, B ~1,100 steps / 40 OUTs, mask 7) is the shipped default; prompt, key and schema regenerated with it; the hard prompt no longer states the OUT counts.
- The false "fits the 64k output budget" claim is replaced by the measured token figures and the >= 128k budget requirement above. The `run_api` cap itself lives in `runner/run.py`, outside this package, and is not changed here.

## Files

`generator.py` (reference interpreter + program builder + prompt/key/schema
writer), `prompt.txt`, `schema.json`, `key.json` (answer plus `meta`: seed,
preset, live sets, trap counts, opcode counts, JLT take counts, listings,
traces), `grade.py`, `oracle.py`, `pilot/` (first pilot on the medium preset).
