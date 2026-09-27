# Quarry Duel (candidate S1 / simulation-1)

100 turns of a fully deterministic two-player card-and-track game, played from a rulebook rendered out of the simulator's own constants; report 5 checkpoints and a final block, no tools.

## What it tests and why

Sustained multi-entity state tracking where nothing can be chunked. Every turn depends on the exact
hand, deck pointer, discard order, positions, coins and stockpiles left by all previous turns:
draw (with a deterministic reversed-discard reshuffle around turns 38 and 73), pick a card by a
fixed policy that reads the whole hand (P1: highest card of the most-held suit, P2: highest card
that lands on a MINE else lowest card), move on a 12-space circular track, capture (steal the
opponent's lowest card), then one of six space effects (MINE, TOLL, FORGE, SWAP, QUARRY, WELL),
discard, and hand-limit enforcement. That is roughly 100 turns x 6-8 dependent rule checks
(~700 state updates), an order of magnitude beyond the saturated T10 (30 commands, 3 rules) and,
unlike T3, not decomposable into independent partial sums.

The task is not recallable: the game, the track layout, the 48-card printed deck order, the
suit tie-break order and P2's target space are generated per seed. Weaker configurations are
expected to lose the thread somewhere in turns 20-60 (mis-tracking a hand after a capture or
a WELL draw, forgetting that the reshuffle reverses the discard pile, mis-ordering capture
before the space effect); stronger ones reach the later checkpoints. Higher effort buys the
budget to write out an explicit per-turn table and re-check the hand after every draw, play,
capture and discard; at low effort a model that "summarises" several turns drifts.

Prompt: 8.0 KB. Estimated model output: 20-40K tokens of working plus a ~1 KB JSON answer.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Total 100 points:

- Checkpoints after turns 20, 40, 60, 80, 100: for each of the two players, position 1,
  coins 2, hand_size 1, hand_total 2, stockpile total 1, exact four-suit stockpile vector 1
  = 8 points per player, 16 per checkpoint, 80 in all. Every field is graded independently by
  exact match, so a run that diverges after turn 60 keeps its first three checkpoints (about
  48-55 points) and one that diverges after turn 80 keeps about 70.
- Final block, 20 points: winner 2, p1_score 3, p2_score 3, total_captures 3,
  total_tolls_paid 3, discard_pile_size 3, deck_remaining 3.

Weights deliberately de-emphasise the guessable fields: a constant guess (all zeros, hand_size 4,
winner "P2") scores 13/100; garbage scores 0. `detail.first_divergence_turn` reports the first
checkpoint with any miss (the secondary "turn of first divergence" diagnostic), and
`detail.per_checkpoint` the points per checkpoint. Parsing follows `tasks/_common.py`
conventions: JSON strings and prose-wrapped/fenced JSON are extracted, alternate key spellings
(`player1`, lowercase suits) are accepted, missing fields score 0.

## Ground truth and verification

- `generator.py --seed 1 --difficulty medium` (the shipped setting) builds the game, simulates it
  with the reference simulator and renders `prompt.txt` from the same constant tables the
  simulator uses (`EFFECT_TEXT`, `HAND_LIMIT`, `TOLL_AMOUNT`, ...), so prompt and oracle cannot
  drift. It also writes `key.json`, `schema.json`, `trace.json` (every turn's full state) and
  `meta.json` (parameters, event counts, reshuffle turns).
- `oracle.py` is an independent second implementation that reads ONLY `prompt.txt`, parses every
  parameter back out of the rules text, and re-simulates with different data structures (string
  cards, deque deck, discard pile stored top-first, sorted-hand policies). It agrees with
  `key.json` exactly on the shipped seed and on 100/100 further medium seeds plus 5 seeds at each
  of the other three difficulty presets.
- Invariants asserted after every turn of the reference simulation: hand + deck + discard +
  stockpiles = 48 cards, coins >= 0, positions in 0..11.
- Seed selection rejects games where any enabled effect fires fewer than 3 times, fewer than 3
  captures, fewer than 2 reshuffles, no hand-limit discard, any empty-hand turn, a SWAP with both
  players on the same space, a draw or a winning margin under 2. Shipped seed (attempt 1):
  MINE 29, TOLL 11 (21 coins), FORGE 8, SWAP 6, QUARRY 9, WELL 9, captures 9, hand-limit
  discards 2, reshuffles at turns 38 and 73.

### Hand-verified opening (turns 1-12) and both reshuffles

Suit order Wood < Grain < Ore < Gem. Track: 0 PLAIN, 1 TOLL, 2 PLAIN, 3 TOLL, 4 QUARRY, 5 MINE,
6 WELL, 7 MINE, 8 FORGE, 9 QUARRY, 10 SWAP, 11 PLAIN. P2 targets MINE.

| Turn | Player | Draw | Hand before play | Play, move | Effect / events | Coins P1/P2 |
|---|---|---|---|---|---|---|
| 1 | P1 | Grain-4 | Wood-6 Ore-9 Ore-2 Grain-1 Grain-4 (Ore=Grain=2, Grain earlier) | Grain-4 -> 4 | QUARRY: Grain banked | 5/5 |
| 2 | P2 | Grain-6 | Gem-1 Wood-7 Ore-1 Gem-2 Grain-6 (only Wood-7 reaches a MINE) | Wood-7 -> 7 | MINE +7 | 5/12 |
| 3 | P1 | Ore-1 | Grain-1 Ore-2 Wood-6 Ore-9 Ore-1 (Ore x3) | Ore-9 -> 1 | TOLL -2 | 3/14 |
| 4 | P2 | Gem-9 | Ore-1 Gem-1 Gem-2 Grain-6 Gem-9 (no MINE; Ore-1 < Gem-1 by suit) | Ore-1 -> 8 | FORGE: empty stockpile, nothing | 3/14 |
| 5 | P1 | Ore-5 | Grain-1 Ore-1 Ore-2 Wood-6 Ore-5 (Ore x3) | Ore-5 -> 6 | WELL: draws Grain-8 (hand 5) | 3/14 |
| 6 | P2 | Grain-2 | Gem-1 Gem-2 Grain-6 Gem-9 Grain-2 (Gem-9 -> 5 MINE) | Gem-9 -> 5 | MINE +9 | 3/23 |
| 7 | P1 | none (holds 5) | Grain-1 Ore-1 Ore-2 Wood-6 Grain-8 (Grain=Ore=2, Grain earlier) | Grain-8 -> 2 | PLAIN | 3/23 |
| 8 | P2 | Wood-5 | Gem-1 Grain-2 Gem-2 Grain-6 Wood-5 (Grain-2 and Gem-2 reach 7; Gem later = higher) | Gem-2 -> 7 | MINE +2 | 3/25 |
| 9 | P1 | Gem-5 | Grain-1 Ore-1 Ore-2 Wood-6 Gem-5 (Ore x2) | Ore-2 -> 4 | QUARRY: Ore banked | 3/25 |
| 10 | P2 | Grain-5 | Gem-1 Grain-2 Wood-5 Grain-6 Grain-5 (no MINE) | Gem-1 -> 8 | FORGE: empty, nothing | 3/25 |
| 11 | P1 | Ore-6 | Grain-1 Ore-1 Gem-5 Wood-6 Ore-6 (Ore x2) | Ore-6 -> 10 | SWAP: P1 to 8, P2 to 10 | 3/25 |
| 12 | P2 | Ore-7 | Grain-2 Wood-5 Grain-5 Grain-6 Ore-7 (Ore-7 -> 5 MINE) | Ore-7 -> 5 | MINE +7 | 3/32 |

After turn 12: deck 28 cards (card 21 Wood-4 on top), discard 10 (Ore-7 on top), P1 stockpile
Ore 1 Grain 1, P2 stockpile empty.

Turn 37 (P1, holds 5, no draw) plays Wood-8 to space 6 where P2 stands: captures P2's lowest card
(Gem-6), WELL draws Grain-7 (deck now 1 card), hand is 6 so the lowest, Gem-2, is discarded
(discard pile 34, Gem-2 on top). Turn 38 (P2, holds 3): draws Gem-8 (deck empty), then the
reshuffle turns the 34-card discard pile over so Gem-2 is the new top card and P2 draws it
(deck 33, discard 0); no card reaches a MINE from space 6, so the lowest card Gem-2 is played to
space 8 FORGE, converting P2's single Grain stockpile card to Ore (the suit after Grain).
The second reshuffle happens in the draw phase of turn 73 (P1 draws Wood-9, the card discarded
at turn 72). All of this matches `trace.json` line by line.

## Difficulty knob

`--difficulty easy|medium|hard|extreme` (turns 60/100/200/300, deck 40/48/60/88, effect types
4/6/6/8 with TRADE and BANK added at extreme); checkpoint interval stays 20 so the gradient is
preserved (total = 16 x checkpoints + 20). Constants `HAND_LIMIT`, `DRAW_MAX`, `TOLL_AMOUNT`
and the per-preset track layout are single-point edits in `generator.py`; the rules text
re-renders from them. The oracle re-parses whatever the prompt says, so it keeps validating
after any such change.

## Files

`generator.py` (reference simulator + renderer), `oracle.py` (independent checker),
`grade.py`, `prompt.txt`, `schema.json`, `key.json`, `trace.json`, `meta.json`.
