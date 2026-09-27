# Chess open standings with arbiter errata (adversarial-3)

Replay a 132-entry arbiter log of a 20-player, 9-round Swiss under 35 verbatim regulations — with reversed results, a transposed pairing list (Novak/Nowak), scoped and retroactive rule changes, an unauthorised notice, a retracted announcement, a withdrawal and two kinds of bye — and produce exact final standings with Buchholz and Sonneborn-Berger.

## What it tests and why

Sustained exact reading where later entries change the meaning of earlier ones. The model must hold the full amended rule set while replaying ~90 games, then propagate every re-scored game through tie-breaks that depend on every other player's total. Nothing is recallable: the tie-break formulas, bye/forfeit conventions and scope words ("with effect from", "for rounds after", "retroactively from round 1") are defined in the prompt and deliberately differ from FIDE practice.

Planted trap classes (each verified to change at least one player's points, BH or SB):

| trap | what a careless reader does | cost if it is the only miss (of 126) |
|---|---|---|
| reversed result corrected a round later | keeps the first entry | 53 |
| result-slip correction in the final round | keeps the first entry | (same class) |
| move-count correction turning a draw into a short draw | keeps the entered count | 37 |
| transposed White players (Novak vs Nowak) | trusts the published list | 26.5 |
| short-draw rule "with effect from round 5" | ignores it / applies from round 6 / applies to all rounds | 62.5 / 35.5 / 82 |
| "fewer than 20 moves" boundary | treats exactly 20 as short | 54 |
| Tournament Director "suspends" the rule (no authority) | honours it | 55.5 |
| Announcement 4 retracted two entries later | honours it | 82 |
| phone rule "for rounds after round 5", incident in round 5 | applies it inclusively / ignores it | 30 / 41 |
| retroactive default-time cut to 30 min, incl. an exactly-30 arrival | ignores it / uses >= | 55.5 / 44 |
| half-point bye vs pairing-allocated bye | scores both 1 / both 0.5 | 19.5 / 47 |
| BH convention for byes/unpaired rounds (own points) | uses 0 | 8 |
| forfeit games in BH (opponent's points) | uses 0 | 14.5 |
| withdrawn player's game (forfeit win to opponent) | scores 0-0 | 24.5 |
| SB convention for byes (0) | counts them | 4 |

The naive "take every entry at face value" tally scores 42.5/126 with a different champion. Effort is expected to move the tie-break sub-score (40 of 126 points) most, because BH/SB require a second pass over the whole log after points are settled.

Difficulty knob (`generator.py --difficulty`): `small` 10 players/6 rounds, `medium` 16/7, `hard` 20/9 (shipped), `extreme` 30/11 (3 near-duplicate surname pairs, more short draws). Trap counts scale with rounds; seeds are deterministic and each seed searches sub-seeds until every trap bites and Q4 has a unique answer.

## Grading

`python grade.py <run-record.json>` prints `{task, score, total, detail}`. Ground truth is in `key.json`; it was generated and validated before any model ran. Per player (20): points 2, rank 1 (0.5 if off by one), Buchholz 1, Sonneborn-Berger 1, wins 0.5 = 110; questions: champion 4, third place 3, forfeit count 3, most-points-lost 3, withdrawn player's points 3 = 16. Total 126. Parsing is tolerant (prose-wrapped JSON, names instead of ids, "3 1/2" style numbers); format deviations are recorded, not punished. `detail.attribution` names the single-trap counterfactual (precomputed by the generator from the structured events) that best matches the submitted standings, so a report can say which trap each config fell for.

Verification: `oracle.py` re-derives the key from `prompt.txt` alone (regex-parsing the rendered log, comparison-sort ranking, no shared code) and agrees exactly; 290 fuzz seeds across all four difficulties agree; the generator asserts every trap variant and the naive baseline differ from the key.
