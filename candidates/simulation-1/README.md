# Quarry Duel (candidate S1 / simulation-1)

200 turns (`hard` preset, the default) of a fully deterministic two-player card-and-track game,
played from a rulebook rendered out of the simulator's own constants; report the card played on
every turn, 19 checkpoints and a final block, no tools. The prompt prints the complete game state
after turn 50, so turns 51-200 are earned independently of any slip in turns 1-50.

## What it tests and why

Sustained multi-entity state tracking where nothing can be chunked. Every turn depends on the exact
hand, deck pointer, discard order, positions, coins and stockpiles left by all previous turns:
draw (with a deterministic reversed-discard reshuffle at turns 53, 98, 139 and 174 on the shipped
seed, the third one triggered mid-turn by a WELL draw), pick a card by a fixed policy that reads
the whole hand (one player: highest card of the most-held suit with a suit-order tie-break; the
other: highest card that lands on a MINE else lowest card), move on a 12-space circular track,
capture (steal the opponent's lowest card), then one of six space effects (MINE, TOLL, FORGE,
SWAP, QUARRY, WELL), discard, and hand-limit enforcement. That is 200 turns x 6-8 dependent rule
checks (~1,400 state updates), not decomposable into independent partial sums.

The task is not recallable: the game, the track layout, the 60-card printed deck order, the suit
tie-break order and which player follows which policy are generated per seed. Weaker
configurations lose the thread somewhere in turns 20-60 (mis-tracking a hand after a capture or
a WELL draw, forgetting that the reshuffle reverses the discard pile, discarding the played card
before a WELL draw reshuffles); stronger ones reach the later checkpoints. Higher effort buys the
budget to write out an explicit per-turn table and re-check the hand after every draw, play,
capture and discard; at low effort a model that "summarises" several turns drifts. The first
pilot (medium preset, 100 turns) showed Sonnet 5 and Opus 5.5 clean at 100 turns and Fable 5.1
drifting at turn 37; the 200-turn preset with per-turn scoring is the gradient repair the
tournament asked for.

Prompt: 10.4 KB (+1.3 KB schema appended by the runner). Estimated model output: 40-55K tokens of
working at the 183-248 tokens/turn observed in the pilot, plus a ~7 KB (~2.5K-token) JSON answer.
That fits a 64K output cap; the `extreme` preset (300 turns) does not reliably.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Total 1000 points:

- **Plays, 400 points (2 per turn).** The 200-entry played-card log is scored as the longest
  correct prefix of two segments graded independently: turns 1-50 (100 points) and turns 51-200
  (300 points). The boundary is the resync turn whose full state the prompt prints, so a slip at
  turn 37 costs turns 37-50 of segment 1 and nothing else, provided the model restarts turn 51
  from the printed state. `detail.plays` reports each segment's prefix, first wrong turn, the
  number of entries reported and the pointwise match count (diagnostic only).
- **Checkpoints, 456 points.** After turns 10, 20, 30, 40, 60, 70, ..., 200 (every 10th turn except
  the printed turn 50): for each of the two players, position 2, coins 3, hand_size 1,
  hand_total 3, stockpile total 1, exact four-suit stockpile vector 2 = 12 points per player,
  24 per checkpoint. Every field is graded independently by exact match.
- **Final block, 144 points.** p1_score, p2_score, total_captures, total_tolls_paid,
  discard_pile_size, deck_remaining: 24 each, exact match. `winner` is implied by the two scores
  and is **not scored** (it was a free 2 points in the pilot grader; across seeds it is now a coin
  flip by construction, see below). It is reported under `detail.winner`.

Floors, published in `detail.floors` for every graded record: the naive constant guess (all
zeros, hand_size 4, empty plays) scores **36/1000** on the shipped seed; the best possible
constant per field (the modal value of every checkpoint field plus the best repeated opening
card, final block 0) scores **93/1000**. The pilot's "repeat the correct turn-20 state at every
checkpoint" hedge, which out-scored Fable's honest 100-turn attempt (33 vs 31), now scores 106.
`detail.first_divergence_turn` is the first checkpoint with any miss; `detail.per_checkpoint`
the points per checkpoint; `detail.checkpoint_matching` says whether turn labels or positions
were used.

Parsing follows `tasks/_common.py` conventions and is tolerant of the shapes the tournament
critics found the pilot grader rejecting: JSON in prose or fences (the balanced object that
contains both `checkpoints` and `final` is preferred over the first or largest object);
`answer`/`result` wrappers; missing suit keys count as 0; a stockpile given as a 4-list in
Ore, Wood, Grain, Gem order or as `[{suit, count}]`; players nested under `players`/`state`
(dict or 2-list) or wrapped in a per-player `state`; `checkpoints` as a dict keyed by turn
(`"20"`, `turn_20`); positional fallback when turn labels are absent or mostly wrong (e.g.
numbered 1-19), with positional fill for a single mislabelled entry; an unrequested turn-50
checkpoint is ignored; plays as strings (`"Grain-4"`, `"grain 4"`), `[suit, value]` pairs,
`{suit, value}` or `{turn, card}` objects, or a dict keyed by turn; alternate key spellings
(`player1`, `Player 2`, `hand size`, `tolls paid`, lowercase suits, numbers as strings).
Garbage and truncated JSON score 0; a record whose answer is `key.json` scores 1000/1000
(self-test: `python grade.py` on `{"answer": <key minus resync_turn>}`, also as a JSON string and
fenced inside prose). The runner's schema validation requires the `plays`, `checkpoints` and
`final` keys, so an answer that omits the log is retried with a corrective note.

## Ground truth and verification

- `generator.py` (default `--seed 1 --difficulty hard`) builds the game, simulates it with the
  reference simulator and renders `prompt.txt` from the same constant tables the simulator uses
  (`EFFECT_TEXT`, `HAND_LIMIT`, `TOLL_AMOUNT`, the per-player policy text, ...), so prompt and
  oracle cannot drift. It also writes `key.json` (`plays`, `checkpoints`, `final`, `resync_turn`),
  `schema.json`, `trace.json` (every turn's full state) and `meta.json` (parameters, event counts,
  reshuffle turns, the printed resync state, the coverage report and the rejection tally).
- `oracle.py` is an independent second implementation that reads ONLY `prompt.txt`, parses every
  parameter back out of the rules text (including which player follows which policy and the
  checkpoint/resync turns), re-simulates with different data structures (string cards, deque
  deck, discard pile stored top-first, sorted-hand policies) and compares with `key.json`; it also
  checks the printed resync state against its own state after that turn. It agrees exactly on the
  shipped seed and on hard seeds 2-8, medium 1-2, easy 1-2 and extreme 1-2.
- Invariants asserted after every turn of the reference simulation: hand + deck + discard +
  stockpiles = 60 cards, coins >= 0, positions in 0..11.
- **Seed selection.** Cheap gates: every enabled effect fires >= 3 times, >= 3 captures, >= 2
  reshuffles, >= 1 hand-limit discard, no empty-hand turn, no SWAP with both players on the same
  space, no draw and a winning margin >= 2, and the card pool (deck + discard) never drops below
  16 cards (a MINE-targeting game keeps 17-31 cards circulating; a QUARRY-targeting game at 200
  turns quarries ~54 of the 60 cards and collapses into a reshuffle-every-turn loop, so it can no
  longer be selected at `hard`).
- **Coverage gate.** Each accepted seed is re-simulated under 12 single-clause misreadings
  (reshuffle not reversed; played card discarded before the space effect; a WELL draw from an
  empty deck not reshuffling; WELL respecting the hand limit; hand limit discarding the highest
  card; TOLL all-or-nothing when short of coins; FORGE ties to the latest suit; capture taking the
  highest card; the targeting player playing its lowest candidate; the suit-count player breaking
  suit ties to the latest suit; equal-value cards compared in reversed suit order; SWAP also
  applying the destination space's effect). A seed is accepted only if every one of them changes
  at least one checkpoint, i.e. every clause is binding. `meta.json.coverage` records the result;
  shipped seed: all 12 binding (accepted on attempt 181; 104 rejections for pool depletion, 34
  for no hand-limit discard, 42 for a non-binding clause, mostly the short-TOLL and WELL-reshuffle
  cases). Two clauses cannot be made binding by any seed and are handled otherwise: the pilot's
  "never draw more than 2 cards" cap (a player always holds 4-5 cards after its own turn and
  loses at most one to a capture before its next draw) was removed from the rules; the
  capture-before-effect order is inert unless an effect touches the opponent's hand (TRADE,
  `extreme` only) because a capture on the SWAP space is exactly the same-space swap the
  generator rejects, so it is gated only when TRADE is enabled and stays in the prompt as a
  clarification.
- **Winner balance.** The targeting policy beats the suit-count policy in ~98 % of raw games, so
  which player follows it alternates with the seed: P2 on odd seeds, P1 on even. Winners on the
  seeds checked: hard 1-8 = P2, P1, P2, P1, P2, P1, P2, P1. A constant "P2" therefore earns
  nothing in expectation even if it were scored.
- Shipped seed statistics: MINE 61, TOLL 23 events (45 coins, one short payment of 1 coin at turn
  25), FORGE 11 (5 with a suit tie), SWAP 14, QUARRY 24, WELL 19, captures 18 (18 P2 turns with
  more than one MINE candidate, 20 P1 suit ties), hand-limit discard 1 (turn 168), reshuffles at
  53, 98, 139 (WELL-triggered) and 174; minimum circulation 28 cards. Final 126 : 377 to P2.

### Hand-verified opening (turns 1-12), both first reshuffles, and the binding edge cases

Suit order Wood < Gem < Ore < Grain. Track: 0 PLAIN, 1 PLAIN, 2 SWAP, 3 MINE, 4 WELL, 5 FORGE,
6 QUARRY, 7 TOLL, 8 PLAIN, 9 MINE, 10 TOLL, 11 QUARRY. P1 follows the suit-count policy, P2
targets MINE. Opening hands: P1 Ore-5, Gem-4, Gem-4, Wood-4; P2 Wood-5, Ore-8, Ore-9, Ore-1;
card 9 (Ore-3) on top of the deck.

| Turn | Player | Draw | Hand before play (policy reasoning) | Play, move | Effect / events | Coins P1/P2 |
|---|---|---|---|---|---|---|
| 1 | P1 | Ore-3 | Ore-5 Gem-4 Gem-4 Wood-4 Ore-3 (Gem=Ore=2, Gem earlier) | Gem-4 -> 4 | WELL: draws Wood-8 (hand 5) | 5/5 |
| 2 | P2 | Ore-6 | Wood-5 Ore-8 Ore-9 Ore-1 Ore-6 (only Ore-9 reaches a MINE, 9) | Ore-9 -> 9 | MINE +9 | 5/14 |
| 3 | P1 | none (holds 5) | Ore-5 Gem-4 Wood-4 Ore-3 Wood-8 (Ore=Wood=2, Wood earlier) | Wood-8 -> 0 | PLAIN | 5/14 |
| 4 | P2 | Grain-8 | Wood-5 Ore-8 Ore-1 Ore-6 Grain-8 (Ore-6 -> 3 MINE) | Ore-6 -> 3 | MINE +6 | 5/20 |
| 5 | P1 | Grain-6 | Ore-5 Gem-4 Wood-4 Ore-3 Grain-6 (Ore x2) | Ore-5 -> 5 | FORGE: empty stockpile, nothing | 5/20 |
| 6 | P2 | Gem-8 | Wood-5 Ore-8 Ore-1 Grain-8 Gem-8 (no MINE; lowest Ore-1) | Ore-1 -> 4 | WELL: draws Gem-7 (hand 5) | 5/20 |
| 7 | P1 | Grain-2 | Gem-4 Wood-4 Ore-3 Grain-6 Grain-2 (Grain x2) | Grain-6 -> 11 | QUARRY: Grain banked | 5/20 |
| 8 | P2 | none (holds 5) | Wood-5 Ore-8 Grain-8 Gem-8 Gem-7 (Wood-5 -> 9 MINE) | Wood-5 -> 9 | MINE +5 | 5/25 |
| 9 | P1 | Grain-3 | Gem-4 Wood-4 Ore-3 Grain-2 Grain-3 (Grain x2) | Grain-3 -> 2 | SWAP: P1 to 9, P2 to 2 | 5/25 |
| 10 | P2 | Ore-6 | Ore-8 Grain-8 Gem-8 Gem-7 Ore-6 (Gem-7 -> 9 MINE) | Gem-7 -> 9 | capture P1's lowest, Grain-2; MINE +7 | 5/32 |
| 11 | P1 | Ore-3, Ore-7 (held 3) | Gem-4 Wood-4 Ore-3 Ore-3 Ore-7 (Ore x3) | Ore-7 -> 4 | WELL: draws Wood-1 (hand 5) | 5/32 |
| 12 | P2 | none (holds 5) | Ore-8 Grain-8 Gem-8 Ore-6 Grain-2 (Ore-6 -> 3 MINE) | Ore-6 -> 3 | MINE +6 | 5/38 |

Turn 25: P1 plays Wood-8 onto TOLL 10 holding 1 coin and pays 1 (the short-payment clause; coins
0/50). Resync (after turn 50, printed in the prompt): deck 1 card (Ore-7), discard 43 cards, no
reshuffle yet. Turn 51: P1 draws that last card. Turn 52: P2 (holding 5) plays Gem-3 onto TOLL 7;
the discard pile is 45 cards with Gem-3 on top and the deck is empty. Turn 53: P1 must draw, so
the 45-card discard pile is turned over (Gem-3 becomes the top card) and P1 draws it (deck 44);
P1 then plays Gem-4 onto FORGE 5 and converts a Wood stockpile card to Gem. The second reshuffle
is at turn 98 (P2 draws Gem-4, the card P1 discarded at turn 97). Turn 139 is the WELL-triggered
reshuffle: P1 holds 5, draws nothing, plays onto WELL 4 with the deck empty; the WELL draw turns
the 35-card discard pile over and draws Gem-4 (the card discarded at turn 138) before the played
card reaches the discard pile, which is why "discard before effect" and "WELL does not reshuffle"
both change later checkpoints. Turn 168: P2 plays Ore-1 onto WELL 4 where P1 stands, captures
Gem-3, the WELL draw makes 6 cards, and the hand limit discards the lowest card, that same Gem-3.
All of this matches `trace.json` line by line.

## Difficulty knob

`--difficulty easy|medium|hard|extreme` (turns 60/100/200/300, deck 40/48/60/88, resync after turn
30/50/50/100, effect types 4/6/6/8 with TRADE and BANK added at extreme). Checkpoints stay every
10 turns minus the resync turn, so total = 2 x turns + 24 x checkpoints + 144 (easy 384, medium
560, hard 1000, extreme 1440). `hard` is the shipped default; `medium` (the piloted length) is kept
as a calibration rung; `extreme` projects Fable 5.1 to ~63K output tokens against a 64K cap and
should stay off the `claude-code` harness until that cap is raised. Constants `HAND_LIMIT`,
`TOLL_AMOUNT` and the per-preset track layout are single-point edits in `generator.py`; the
rules text re-renders from them and the oracle re-parses whatever the prompt says, so it keeps
validating after any such change. Generation cost: hard seeds take 16-191 attempts (< 1 s),
extreme 2-3K (~20 s).

## Changes since the first pilot (TOURNAMENT.md §4.1 item 3)

Applied: `hard` (200 turns) as default; per-turn played-card log scored as longest correct
prefix (400/1000, two segments); checkpoints every 10 turns; printed resync state after turn 50;
all listed grader tolerances plus prefer-the-object-with-checkpoints-and-final extraction;
coverage gate over 12 clause misreadings; winner balanced across seeds by alternating which
player follows the targeting policy; `winner` folded into the scores (unscored) and hand_size cut
from 1/8 to 1/12 of a player-checkpoint; constant-guess and best-constant floors published in
`detail.floors`; the never-binding 2-card draw cap removed from the rules. Not applied here:
the runner-side extraction change and the harness items (`CLAUDE_CODE_MAX_OUTPUT_TOKENS`,
`thinking_tokens`, `output_cap_bound`) live outside this directory; replicates and the effort
sweep are the replication step's job. The pilot records in `pilot/` were produced by the
100-turn medium prompt and the 100-point grader and are not comparable with this version.

## Files

`generator.py` (reference simulator + variant simulator + renderer), `oracle.py` (independent
checker), `grade.py`, `prompt.txt`, `schema.json`, `key.json`, `trace.json`, `meta.json`,
`pilot/` (first pilot, medium preset, untouched).
