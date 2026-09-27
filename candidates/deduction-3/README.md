# Crib Slide (D3, candidate deduction-3)

Recover an 11-letter Vigenere key (period known only as "10-14") from four short cribs with coarse position windows, decrypt 1,328 letters of an invented shipping manifest, and answer 10 extraction questions - no tools.

## What it tests and why

Hypothesis elimination driven by exact modular arithmetic, followed by a long
exact grind whose errors are visible and therefore correctable by the diligent.

The ciphertext is a periodic Vigenere encryption of a synthetic A-Z manifest
(invented proper nouns, numbers written in words, random-letter codes, fields in
a shuffled order separated by `STOP`). The model is told the period lies in
[10, 14] and is given four field labels (`PALLETS`, `CONSIGNEE`, `SHIPPER`,
`VESSEL`) that each occur exactly once, with a 40-letter window for where each
starts. Every crib is shorter than the smallest admissible period, so **no crib
can reveal the period or the whole key on its own** and nothing sits at a known
offset (this answers the judges' "MANIFEST at offset 0" leak): the solver must
slide each crib through its window, derive the implied key fragment at each
offset (`C - P mod 26`), and keep only the period + offset combination on which
all four fragments agree modulo the period. Alternatives such as Kasiski on the
repeated `STOP` groups or per-column frequency analysis are legitimate but no
cheaper. Only then can the ~1,300-letter decryption and the reading begin.

Why it should separate frontier tiers and effort levels:

- ~1,200 subtractions of crib-sliding plus ~1,300 of decryption, organised by a
  search: low effort tends to misalign a crib by one, pick a period that fits
  three cribs but not four, or slip on a single letter.
- A single wrong key letter corrupts every p-th plaintext letter. Number and
  name answers are then *recoverable* by careful reading (`THIRTYTWO` with one
  letter wrong is still readable) and a careful solver notices the garbling and
  fixes the key; the two random-letter codes (container, seal) are **not**
  recoverable, so they reward only a fully correct key. The self-test shows the
  resulting bands: 60 (perfect), ~46 (one key letter wrong but answers
  error-corrected), ~28 (one key letter wrong, answers read off the garbled text),
  0 (no key).
- Vocabulary is invented, so recall cannot substitute for derivation; the
  answer space (5 periods x 26^p keys) cannot be guessed.

Ground truth: `generator.py --seed 20260926 --difficulty hard` builds the
manifest, key and cribs and brute-forces every (period, crib-offset) combination
in the stated range and windows; the shipped instance has **exactly one**
consistent combination, and it stays unique even with no windows at all.
`oracle.py` re-derives period, key, plaintext and all ten answers from
`prompt.txt` alone with a different algorithm (key-mask unification instead of
offset DFS) and agrees with `key.json` exactly.

Difficulty knob (`--difficulty easy|medium|hard|max`, or the individual flags
`--length --pmin --pmax --cribs --window`): ciphertext length 700-2,000, period
range width, number of cribs (3-5), crib window width (10 letters to "anywhere"),
and whether cribs may be longer than the period (easy/medium) or must be shorter
(hard/max). `hard` is the default and the shipped instance.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`.
Total 60, partial credit throughout:

- **Period, 6 pts** - exact.
- **Key, 24 pts** - if the submitted key has the true length, 24 x (fraction of
  key letters that match). The canonical alignment is K[0] at position 1, but
  the best cyclic rotation of the submitted key is taken, because a rotated key
  is the same cyclic object (documented leniency; `detail` reports the rotation
  used). If the length is wrong, the ciphertext is decrypted with the submitted
  key anyway and up to 6 of the 24 points are given for the fraction of
  plaintext letters that agree.
- **Answers, 30 pts** - 10 questions x 3. Numbers are compared as integers and
  accepted as digits or words; codes and names are compared letters-only,
  ignoring case and spaces.

Prose answers are parsed tolerantly (period, key and `Qn:` lines are extracted
from text) in line with the repository's policy of recording rather than
punishing format deviations. Ground truth lives in `key.json` next to the grader.
