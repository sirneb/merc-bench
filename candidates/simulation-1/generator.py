#!/usr/bin/env python3
"""Generator for candidate task simulation-1: "Quarry Duel".

Deterministic given --seed and --difficulty. Writes into this directory:
  prompt.txt   rules text rendered FROM THE SAME CONSTANTS the simulator uses,
               plus track layout, deck order and output format
  key.json     reference answer (checkpoints + final block) from the simulator
  schema.json  JSON schema of the answer
  trace.json   full per-turn state trace (auditing / README hand-verification)
  meta.json    difficulty parameters, chosen game seed, event statistics

Usage: python generator.py [--seed 1] [--difficulty easy|medium|hard|extreme]
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Constants shared by simulator and rules renderer
# --------------------------------------------------------------------------
SUITS = ["Ore", "Wood", "Grain", "Gem"]
TRACK_LEN = 12
HAND_LIMIT = 5
START_COINS = 5
OPENING_HAND = 4
DRAW_MAX = 2
TOLL_AMOUNT = 2
STOCK_MULT = 3          # final score = coins + STOCK_MULT * stockpile cards
CHECKPOINT_EVERY = 20

EFFECT_TEXT = {
    "PLAIN": "nothing happens.",
    "MINE": "you gain coins equal to the value of the played card.",
    "TOLL": (f"you pay {TOLL_AMOUNT} coins to your opponent. If you hold fewer than "
             f"{TOLL_AMOUNT} coins you pay everything you have (possibly 0). Every coin "
             "paid this way counts towards total_tolls_paid."),
    "FORGE": ("if your stockpile holds at least one card: take the suit of which your "
              "stockpile holds the MOST cards (ties: the earliest such suit in the suit "
              "order); remove one card of that suit from your stockpile and add one card "
              "of the NEXT suit in the suit order (the suit after the last one wraps "
              "around to the first). If your stockpile is empty, nothing happens."),
    "SWAP": ("you and your opponent exchange positions. Nothing else is triggered by "
             "this (no capture, no effect of the space either player now stands on)."),
    "QUARRY": ("the played card is placed into your stockpile (add 1 to your count of "
               "its suit). It does NOT go to the discard pile."),
    "WELL": (f"you draw one card from the deck (reshuffle rule applies), even if you "
             f"already hold {HAND_LIMIT} or more cards."),
    "TRADE": ("if both you and your opponent hold at least one card: your HIGHEST card "
              "and your opponent's LOWEST card change hands (you receive their card, "
              "they receive yours). Otherwise nothing happens."),
    "BANK": "you gain coins equal to the total number of cards in your stockpile.",
}

# layout = how many track spaces (of 1..11; space 0 is always PLAIN) carry each effect
DIFFICULTY = {
    "easy":    dict(turns=60,  deck=40, layout={"MINE": 3, "TOLL": 2, "SWAP": 1, "QUARRY": 2}),
    "medium":  dict(turns=100, deck=48, layout={"MINE": 2, "TOLL": 2, "FORGE": 1, "SWAP": 1,
                                                "QUARRY": 2, "WELL": 1}),
    "hard":    dict(turns=200, deck=60, layout={"MINE": 2, "TOLL": 2, "FORGE": 1, "SWAP": 1,
                                                "QUARRY": 2, "WELL": 1}),
    "extreme": dict(turns=300, deck=88, layout={"MINE": 2, "TOLL": 1, "FORGE": 1, "SWAP": 1,
                                                "QUARRY": 2, "WELL": 1, "TRADE": 1, "BANK": 1}),
}
MIN_FIRES = 3   # every enabled effect (and capture / reshuffle) must fire at least this often


# --------------------------------------------------------------------------
# Reference simulator
# --------------------------------------------------------------------------
class Sim:
    def __init__(self, game, turns):
        self.track = game["track"]
        self.deck = list(game["deck"])          # index 0 = top
        self.suit_rank = {s: i for i, s in enumerate(game["suit_order"])}
        self.suit_order = game["suit_order"]
        self.p2_target = game["p2_target"]
        self.turns = turns
        self.discard = []                         # last element = top
        self.pos = [0, 0]
        self.coins = [START_COINS, START_COINS]
        self.hand = [[], []]
        self.stock = [{s: 0 for s in SUITS}, {s: 0 for s in SUITS}]
        self.stats = {k: 0 for k in ["captures", "tolls_paid", "toll_events", "reshuffles",
                                     "hand_limit_discards", "empty_hand_turns", "swap_same_space"]}
        for e in EFFECT_TEXT:
            self.stats["fire_" + e] = 0
        self.trace = []
        self.total_cards = len(self.deck)
        for _ in range(OPENING_HAND):
            self.hand[0].append(self.deck.pop(0))
        for _ in range(OPENING_HAND):
            self.hand[1].append(self.deck.pop(0))

    # card ordering: value first, then suit order
    def key(self, c):
        return (c[1], self.suit_rank[c[0]])

    def lowest(self, cards):
        return min(cards, key=self.key)

    def highest(self, cards):
        return max(cards, key=self.key)

    def draw_one(self, p):
        if not self.deck:
            if not self.discard:
                return False
            self.deck = list(reversed(self.discard))
            self.discard = []
            self.stats["reshuffles"] += 1
            self.reshuffle_turns.append(self.turn)
        self.hand[p].append(self.deck.pop(0))
        return True

    def choose(self, p):
        hand = self.hand[p]
        if p == 0:
            counts = {s: sum(1 for c in hand if c[0] == s) for s in SUITS}
            best = max(counts.values())
            suit = min((s for s in SUITS if counts[s] == best), key=lambda s: self.suit_rank[s])
            return self.highest([c for c in hand if c[0] == suit])
        cands = [c for c in hand if self.track[(self.pos[p] + c[1]) % TRACK_LEN] == self.p2_target]
        return self.highest(cands) if cands else self.lowest(hand)

    def check_invariants(self):
        n = (len(self.deck) + len(self.discard) + len(self.hand[0]) + len(self.hand[1])
             + sum(self.stock[0].values()) + sum(self.stock[1].values()))
        assert n == self.total_cards, (self.turn, n)
        assert all(c >= 0 for c in self.coins)
        assert all(0 <= x < TRACK_LEN for x in self.pos)

    def snapshot(self, p):
        return {"position": self.pos[p], "coins": self.coins[p],
                "hand_size": len(self.hand[p]),
                "hand_total": sum(c[1] for c in self.hand[p]),
                "stockpile": dict(self.stock[p])}

    def run(self):
        self.reshuffle_turns = []
        checkpoints = []
        for self.turn in range(1, self.turns + 1):
            p = (self.turn - 1) % 2
            o = 1 - p
            ev = {"turn": self.turn, "player": f"P{p+1}", "drew": [], "events": []}
            # 1 draw phase
            drawn = 0
            while len(self.hand[p]) < HAND_LIMIT and drawn < DRAW_MAX:
                if not self.draw_one(p):
                    break
                ev["drew"].append(self.hand[p][-1])
                drawn += 1
            if not self.hand[p]:
                self.stats["empty_hand_turns"] += 1
                ev["events"].append("empty hand: no play")
            else:
                # 2 play
                card = self.choose(p)
                self.hand[p].remove(card)
                ev["played"] = card
                self.pos[p] = (self.pos[p] + card[1]) % TRACK_LEN
                ev["moved_to"] = self.pos[p]
                # 3 capture
                if self.pos[p] == self.pos[o] and self.hand[o]:
                    stolen = self.lowest(self.hand[o])
                    self.hand[o].remove(stolen)
                    self.hand[p].append(stolen)
                    self.stats["captures"] += 1
                    ev["events"].append(f"capture {stolen[0]}-{stolen[1]}")
                # 4 effect
                eff = self.track[self.pos[p]]
                ev["space"] = eff
                quarried = False
                if eff == "MINE":
                    self.coins[p] += card[1]
                    self.stats["fire_MINE"] += 1
                elif eff == "TOLL":
                    amt = min(TOLL_AMOUNT, self.coins[p])
                    self.coins[p] -= amt
                    self.coins[o] += amt
                    self.stats["tolls_paid"] += amt
                    self.stats["toll_events"] += 1
                    if amt > 0:
                        self.stats["fire_TOLL"] += 1
                    ev["events"].append(f"toll {amt}")
                elif eff == "FORGE":
                    if sum(self.stock[p].values()) > 0:
                        best = max(self.stock[p].values())
                        suit = min((s for s in SUITS if self.stock[p][s] == best),
                                   key=lambda s: self.suit_rank[s])
                        nxt = self.suit_order[(self.suit_rank[suit] + 1) % 4]
                        self.stock[p][suit] -= 1
                        self.stock[p][nxt] += 1
                        self.stats["fire_FORGE"] += 1
                        ev["events"].append(f"forge {suit}->{nxt}")
                elif eff == "SWAP":
                    if self.pos[p] == self.pos[o]:
                        self.stats["swap_same_space"] += 1
                    self.pos[p], self.pos[o] = self.pos[o], self.pos[p]
                    self.stats["fire_SWAP"] += 1
                    ev["events"].append(f"swap -> P{p+1}@{self.pos[p]} P{o+1}@{self.pos[o]}")
                elif eff == "QUARRY":
                    self.stock[p][card[0]] += 1
                    quarried = True
                    self.stats["fire_QUARRY"] += 1
                    ev["events"].append("quarried")
                elif eff == "WELL":
                    if self.draw_one(p):
                        self.stats["fire_WELL"] += 1
                        ev["events"].append(f"well drew {self.hand[p][-1][0]}-{self.hand[p][-1][1]}")
                elif eff == "TRADE":
                    if self.hand[p] and self.hand[o]:
                        mine = self.highest(self.hand[p])
                        theirs = self.lowest(self.hand[o])
                        self.hand[p].remove(mine)
                        self.hand[o].remove(theirs)
                        self.hand[p].append(theirs)
                        self.hand[o].append(mine)
                        self.stats["fire_TRADE"] += 1
                        ev["events"].append(f"trade gave {mine} got {theirs}")
                elif eff == "BANK":
                    self.coins[p] += sum(self.stock[p].values())
                    self.stats["fire_BANK"] += 1
                # 5 discard
                if not quarried:
                    self.discard.append(card)
                # 6 hand limit
                while len(self.hand[p]) > HAND_LIMIT:
                    low = self.lowest(self.hand[p])
                    self.hand[p].remove(low)
                    self.discard.append(low)
                    self.stats["hand_limit_discards"] += 1
                    ev["events"].append(f"hand limit discard {low[0]}-{low[1]}")
            self.check_invariants()
            ev["state"] = {"P1": self.snapshot(0), "P2": self.snapshot(1),
                           "hand_P1": sorted(self.hand[0], key=self.key),
                           "hand_P2": sorted(self.hand[1], key=self.key),
                           "deck_remaining": len(self.deck), "discard_size": len(self.discard),
                           "discard_top": self.discard[-1] if self.discard else None}
            self.trace.append(ev)
            if self.turn % CHECKPOINT_EVERY == 0:
                checkpoints.append({"turn": self.turn, "P1": self.snapshot(0),
                                    "P2": self.snapshot(1)})
        s1 = self.coins[0] + STOCK_MULT * sum(self.stock[0].values())
        s2 = self.coins[1] + STOCK_MULT * sum(self.stock[1].values())
        final = {"winner": "P1" if s1 > s2 else "P2" if s2 > s1 else "draw",
                 "p1_score": s1, "p2_score": s2,
                 "total_captures": self.stats["captures"],
                 "total_tolls_paid": self.stats["tolls_paid"],
                 "discard_pile_size": len(self.discard),
                 "deck_remaining": len(self.deck)}
        return checkpoints, final


# --------------------------------------------------------------------------
# Game instance construction + seed selection
# --------------------------------------------------------------------------
def build_game(rng, cfg):
    per_suit = cfg["deck"] // 4
    deck = []
    for s in SUITS:
        vals = list(range(1, 10)) + [rng.randint(1, 9) for _ in range(per_suit - 9)]
        deck += [(s, v) for v in vals]
    rng.shuffle(deck)
    effects = []
    for e, n in cfg["layout"].items():
        effects += [e] * n
    effects += ["PLAIN"] * (TRACK_LEN - 1 - len(effects))
    rng.shuffle(effects)
    track = ["PLAIN"] + effects
    suit_order = SUITS[:]
    rng.shuffle(suit_order)
    targets = [e for e in ("MINE", "QUARRY") if e in cfg["layout"]]
    p2_target = rng.choice(targets)
    return {"deck": deck, "track": track, "suit_order": suit_order, "p2_target": p2_target}


def acceptable(sim, final, cfg):
    st = sim.stats
    for e in cfg["layout"]:
        if st["fire_" + e] < MIN_FIRES:
            return False
    if st["captures"] < MIN_FIRES or st["reshuffles"] < 2:
        return False
    if st["empty_hand_turns"] > 0:
        return False
    if ("WELL" in cfg["layout"] or "TRADE" in cfg["layout"]) and st["hand_limit_discards"] < 1:
        return False
    if final["winner"] == "draw" or abs(final["p1_score"] - final["p2_score"]) < 2:
        return False
    if st["swap_same_space"] > 0:
        return False
    # both players must land on TOLL with fewer than TOLL_AMOUNT coins at least once? not required
    return True


def select_game(seed, difficulty):
    cfg = DIFFICULTY[difficulty]
    rng = random.Random(f"quarry-duel-{difficulty}-{seed}")
    for attempt in range(1, 5000):
        game = build_game(rng, cfg)
        sim = Sim(game, cfg["turns"])
        cps, final = sim.run()
        if acceptable(sim, final, cfg):
            return game, sim, cps, final, attempt
    raise SystemExit("no acceptable game found")


# --------------------------------------------------------------------------
# Rules renderer (from the constants above)
# --------------------------------------------------------------------------
def card_name(c):
    return f"{c[0]}-{c[1]}"


def render_prompt(game, cfg, cps_turns, opening):
    so = game["suit_order"]
    track_lines = "\n".join(f"  space {i:2d}: {e}" + ("   (start)" if i == 0 else "")
                            for i, e in enumerate(game["track"]))
    deck_lines = "\n".join(
        "  " + "  ".join(f"{i+1:2d}:{card_name(c):<8}" for i, c in enumerate(game["deck"][j:j+8], start=j)).rstrip()
        for j in range(0, len(game["deck"]), 8))
    enabled = ["PLAIN"] + list(cfg["layout"].keys())
    effect_lines = "\n".join(f"  - {e}: {EFFECT_TEXT[e]}" for e in enabled)
    n = len(game["deck"])
    cp_list = ", ".join(str(t) for t in cps_turns)
    p1_cards = ", ".join(card_name(c) for c in game["deck"][:OPENING_HAND])
    p2_cards = ", ".join(card_name(c) for c in game["deck"][OPENING_HAND:2*OPENING_HAND])

    cp_obj = ('{"turn": T, "P1": {"position": 0, "coins": 0, "hand_size": 0, "hand_total": 0, '
              '"stockpile": {"Ore": 0, "Wood": 0, "Grain": 0, "Gem": 0}}, "P2": {...same fields...}}')

    t1 = opening  # worked example text for turn 1
    return f"""IMPORTANT: Solve without any tools — no Bash, no Python, no code execution, no files, no web. Work it out yourself. Do not skip, batch or estimate turns: every turn depends on the exact state left by all previous turns.

QUARRY DUEL is a two-player card-and-track game with NO decisions and NO randomness: both players follow fixed policies, so the whole game is determined by the rules below. Play the game for exactly {cfg['turns']} turns and report the requested state.

== COMPONENTS ==
- A circular track of {TRACK_LEN} spaces numbered 0-{TRACK_LEN-1}. Moving forward from space {TRACK_LEN-1} continues at space 0. Each space has an effect:
{track_lines}
- A deck of {n} cards. Each card has a suit (one of {", ".join(SUITS)}) and a value from 1 to 9; several cards can be identical. The deck is listed below from top (card 1) to bottom (card {n}). It is never shuffled randomly.
- Two players, P1 and P2. Each has a position on the track, a number of coins, a hand of cards, and a stockpile (a count of banked cards per suit).
- One shared discard pile (ordered: the most recently discarded card is on top).

== SUIT ORDER ==
For every tie-break in this game the suit order is: {" < ".join(so)}  ({so[0]} is the earliest/lowest suit, {so[3]} the latest/highest).
Comparing two cards: the card with the higher value is the higher card; if the values are equal, the card whose suit comes later in the suit order is higher. "Lowest card" and "highest card" always use this comparison. Two cards with the same suit and value are interchangeable.

== SETUP ==
- Both players start on space 0 with {START_COINS} coins each and an empty stockpile.
- P1 takes the top {OPENING_HAND} cards of the deck (cards 1-{OPENING_HAND}: {p1_cards}) into hand; P2 takes the next {OPENING_HAND} (cards {OPENING_HAND+1}-{2*OPENING_HAND}: {p2_cards}). Card {2*OPENING_HAND+1} is now the top of the deck. The discard pile is empty.

== TURN SEQUENCE ==
Turns are numbered 1 to {cfg['turns']}. P1 takes every odd-numbered turn and P2 every even-numbered turn. The player taking the turn is "you"; the other player is "your opponent". Each turn consists of these steps, strictly in this order:

1. DRAW PHASE. Draw the top card of the deck into your hand, repeating until you hold {HAND_LIMIT} cards, but never drawing more than {DRAW_MAX} cards in this phase. If you already hold {HAND_LIMIT} or more cards you draw nothing.
   RESHUFFLE RULE (applies to every draw in the game): if you must draw a card and the deck is empty, the whole discard pile becomes the new deck in REVERSED order — the most recently discarded card becomes the top of the new deck and the oldest discarded card becomes its bottom. The discard pile is then empty. If the discard pile is also empty, the draw simply does not happen.
2. PLAY PHASE. If your hand is empty, skip steps 2-6. Otherwise select ONE card from your hand as dictated by your policy (see POLICIES) and remove it from your hand; it is the "played card". Move forward along the track by the played card's value: new position = (old position + value) mod {TRACK_LEN}.
3. CAPTURE. If your new position is the same space your opponent occupies AND your opponent holds at least one card, take your opponent's LOWEST card into your hand. This counts as one capture. (Captures are checked before the space effect; a SWAP in step 4 never causes a capture.)
4. SPACE EFFECT. Apply the effect of the space you now occupy:
{effect_lines}
5. DISCARD. Unless the played card went to your stockpile (QUARRY), place it on top of the discard pile.
6. HAND LIMIT. If you now hold more than {HAND_LIMIT} cards, discard your LOWEST card onto the top of the discard pile; repeat until you hold exactly {HAND_LIMIT}. (Only the player whose turn it is checks the hand limit.)

== POLICIES ==
- P1 (odd turns): count the cards of each suit in your hand. Let S be the suit you hold the most cards of; if several suits tie for the most, S is the earliest of them in the suit order. Play the HIGHEST card of suit S.
- P2 (even turns): a card in your hand is a "candidate" if playing it would move you (from your current position, after the draw phase) onto a {game['p2_target']} space. If you have at least one candidate, play the HIGHEST candidate. Otherwise play the LOWEST card in your hand.

== END OF GAME AND SCORING ==
The game ends after turn {cfg['turns']}. Each player's final score = coins + {STOCK_MULT} x (total number of cards in their stockpile). The player with the higher score wins ("P1" or "P2"; report "draw" if equal).

== DECK ORDER (card 1 is the top) ==
{deck_lines}

== WORKED EXAMPLE: TURN 1 ==
{t1}

== WHAT TO REPORT ==
Checkpoints: the state of BOTH players immediately after the end (step 6) of turns {cp_list}. For each player report: position, coins, hand_size (number of cards in hand), hand_total (sum of the values of the cards in hand), and stockpile counts for every suit (Ore, Wood, Grain, Gem — always all four keys, 0 if none).
Final block (after turn {cfg['turns']}): winner ("P1", "P2" or "draw"), p1_score, p2_score, total_captures (number of captures in the whole game), total_tolls_paid (total coins transferred by TOLL effects in the whole game), discard_pile_size (cards in the discard pile at the end), deck_remaining (cards left in the deck at the end).

== OUTPUT FORMAT ==
Return ONLY a single JSON object, no prose before or after, no markdown fences, exactly this shape (all numbers are integers):
{{
  "checkpoints": [
    {cp_obj},
    ... one object per checkpoint turn, in order: {cp_list}
  ],
  "final": {{"winner": "P1", "p1_score": 0, "p2_score": 0, "total_captures": 0, "total_tolls_paid": 0, "discard_pile_size": 0, "deck_remaining": 0}}
}}
"""


def render_opening(trace, game):
    ev = trace[0]
    st = ev["state"]
    tr = game["track"]
    lines = []
    lines.append(f"P1 holds {', '.join(card_name(c) for c in game['deck'][:OPENING_HAND])} ({OPENING_HAND} cards), "
                 f"so the draw phase draws {', '.join(card_name(c) for c in ev['drew'])} "
                 f"(now {OPENING_HAND+len(ev['drew'])} cards).")
    lines.append(f"P1's policy selects {card_name(ev['played'])}; P1 moves from space 0 to space "
                 f"{ev['moved_to']} ({tr[ev['moved_to']]}). P2 is on space 0, so there is no capture.")
    if ev["space"] == "QUARRY":
        lines.append(f"QUARRY: {card_name(ev['played'])} goes into P1's stockpile ({ev['played'][0]}: 1); "
                     "the discard pile stays empty.")
    else:
        if ev["space"] == "PLAIN":
            lines.append("PLAIN: the space effect does nothing.")
        elif ev["events"]:
            lines.append(f"{ev['space']}: " + "; ".join(ev["events"]) + ".")
        lines.append(f"{card_name(ev['played'])} is placed on the discard pile.")
    p1 = st["P1"]
    lines.append(f"State after turn 1: P1 on space {p1['position']} with {p1['coins']} coins, hand "
                 f"{', '.join(card_name(c) for c in st['hand_P1'])} (hand_size {p1['hand_size']}, hand_total "
                 f"{p1['hand_total']}), stockpile {json.dumps(p1['stockpile'])}; P2 unchanged; deck has "
                 f"{st['deck_remaining']} cards; discard pile has {st['discard_size']} card(s).")
    return "\n".join(lines)


SCHEMA = {
    "type": "object",
    "properties": {
        "checkpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "turn": {"type": "integer"},
                    "P1": {"$ref": "#/$defs/player"},
                    "P2": {"$ref": "#/$defs/player"},
                },
                "required": ["turn", "P1", "P2"],
            },
        },
        "final": {
            "type": "object",
            "properties": {
                "winner": {"type": "string", "enum": ["P1", "P2", "draw"]},
                "p1_score": {"type": "integer"},
                "p2_score": {"type": "integer"},
                "total_captures": {"type": "integer"},
                "total_tolls_paid": {"type": "integer"},
                "discard_pile_size": {"type": "integer"},
                "deck_remaining": {"type": "integer"},
            },
            "required": ["winner", "p1_score", "p2_score", "total_captures",
                         "total_tolls_paid", "discard_pile_size", "deck_remaining"],
        },
    },
    "required": ["checkpoints", "final"],
    "$defs": {
        "player": {
            "type": "object",
            "properties": {
                "position": {"type": "integer"},
                "coins": {"type": "integer"},
                "hand_size": {"type": "integer"},
                "hand_total": {"type": "integer"},
                "stockpile": {
                    "type": "object",
                    "properties": {s: {"type": "integer"} for s in SUITS},
                    "required": SUITS,
                },
            },
            "required": ["position", "coins", "hand_size", "hand_total", "stockpile"],
        }
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--difficulty", choices=list(DIFFICULTY), default="medium")
    ap.add_argument("--out", default=HERE)
    a = ap.parse_args()
    cfg = DIFFICULTY[a.difficulty]
    game, sim, cps, final, attempt = select_game(a.seed, a.difficulty)
    cps_turns = [c["turn"] for c in cps]
    opening = render_opening(sim.trace, game)
    prompt = render_prompt(game, cfg, cps_turns, opening)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "prompt.txt"), "w") as f:
        f.write(prompt)
    with open(os.path.join(a.out, "key.json"), "w") as f:
        json.dump({"checkpoints": cps, "final": final}, f, indent=1)
    with open(os.path.join(a.out, "schema.json"), "w") as f:
        json.dump(SCHEMA, f, indent=1)
    with open(os.path.join(a.out, "trace.json"), "w") as f:
        json.dump(sim.trace, f)
    meta = {"seed": a.seed, "difficulty": a.difficulty, "attempt": attempt,
            "params": {"turns": cfg["turns"], "deck": cfg["deck"], "layout": cfg["layout"],
                       "hand_limit": HAND_LIMIT, "checkpoint_every": CHECKPOINT_EVERY},
            "game": {"track": game["track"], "suit_order": game["suit_order"],
                     "p2_target": game["p2_target"], "deck": [card_name(c) for c in game["deck"]]},
            "stats": sim.stats, "reshuffle_turns": sim.reshuffle_turns,
            "prompt_bytes": len(prompt.encode())}
    with open(os.path.join(a.out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(json.dumps({"attempt": attempt, "stats": sim.stats, "reshuffles": sim.reshuffle_turns,
                      "final": final, "prompt_bytes": meta["prompt_bytes"]}, indent=1))


if __name__ == "__main__":
    main()
