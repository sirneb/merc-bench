#!/usr/bin/env python3
"""Independent oracle for Quarry Duel (candidate simulation-1).

Reads ONLY prompt.txt: every rule parameter (track layout, deck order, suit order,
turn count, hand limit, draw cap, start coins, toll amount, score multiplier, P2's
target space, checkpoint turns) is parsed back out of the rules text, then the game
is re-simulated with a deliberately different implementation (string cards, deque
deck, discard pile stored top-first, sorted-hand policies) and compared with key.json.

Usage: python oracle.py [--dir DIR]   -> exits 0 iff the recomputed answer == key.json
"""
import argparse
import json
import os
import re
import sys
from collections import deque, Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_prompt(text):
    P = {}
    P["turns"] = int(re.search(r"Play the game for exactly (\d+) turns", text).group(1))
    P["track_len"] = int(re.search(r"circular track of (\d+) spaces", text).group(1))
    P["track"] = {int(m.group(1)): m.group(2)
                  for m in re.finditer(r"^\s*space\s+(\d+):\s+([A-Z]+)", text, re.M)}
    assert len(P["track"]) == P["track_len"]
    P["suit_order"] = re.search(r"the suit order is:\s*([A-Za-z]+) < ([A-Za-z]+) < ([A-Za-z]+) < ([A-Za-z]+)",
                                text).groups()
    P["start_coins"] = int(re.search(r"start on space 0 with (\d+) coins", text).group(1))
    P["opening"] = int(re.search(r"P1 takes the top (\d+) cards", text).group(1))
    P["hand_limit"] = int(re.search(r"repeating until you hold (\d+) cards", text).group(1))
    P["draw_max"] = int(re.search(r"never drawing more than (\d+) cards in this phase", text).group(1))
    P["toll"] = int(re.search(r"TOLL: you pay (\d+) coins to your opponent", text).group(1))
    P["mult"] = int(re.search(r"final score = coins \+ (\d+) x", text).group(1))
    P["p2_target"] = re.search(r"onto a ([A-Z]+) space\. If you have at least one candidate", text).group(1)
    deck_block = text.split("== DECK ORDER (card 1 is the top) ==")[1].split("== WORKED")[0]
    cards = re.findall(r"(\d+):([A-Za-z]+-\d)", deck_block)
    nums = [int(n) for n, _ in cards]
    assert nums == list(range(1, len(nums) + 1)), "deck numbering broken"
    P["deck"] = [c for _, c in cards]
    assert len(P["deck"]) == int(re.search(r"A deck of (\d+) cards", text).group(1))
    cp = re.search(r"end \(step 6\) of turns ([\d, ]+)\.", text).group(1)
    P["checkpoints"] = [int(x) for x in cp.split(",")]
    P["effects_present"] = set(re.findall(r"^\s*- ([A-Z]+): ", text.split("4. SPACE EFFECT")[1]
                                          .split("5. DISCARD")[0], re.M))
    return P


def val(card):
    return int(card.split("-")[1])


def suit(card):
    return card.split("-")[0]


class Player:
    def __init__(self, start_coins):
        self.pos = 0
        self.coins = start_coins
        self.hand = []
        self.stock = Counter()


def simulate(P):
    rank = {s: i for i, s in enumerate(P["suit_order"])}
    order = lambda c: (val(c), rank[suit(c)])   # ascending = lowest first
    T = P["track_len"]
    deck = deque(P["deck"])
    discard = []                                   # discard[0] is the TOP of the pile
    pl = [Player(P["start_coins"]), Player(P["start_coins"])]
    for _ in range(P["opening"]):
        pl[0].hand.append(deck.popleft())
    for _ in range(P["opening"]):
        pl[1].hand.append(deck.popleft())
    captures = tolls = 0
    out = []

    def draw(me):
        nonlocal deck, discard
        if len(deck) == 0:
            if not discard:
                return None
            deck = deque(discard)      # top of discard (index 0) becomes top of deck
            discard = []
        c = deck.popleft()
        me.hand.append(c)
        return c

    def policy_p1(me):
        cnt = Counter(suit(c) for c in me.hand)
        top = max(cnt.values())
        s = sorted((s for s in cnt if cnt[s] == top), key=lambda s: rank[s])[0]
        return sorted((c for c in me.hand if suit(c) == s), key=order)[-1]

    def policy_p2(me):
        cands = [c for c in me.hand if P["track"][(me.pos + val(c)) % T] == P["p2_target"]]
        if cands:
            return sorted(cands, key=order)[-1]
        return sorted(me.hand, key=order)[0]

    for turn in range(1, P["turns"] + 1):
        me, you = (pl[0], pl[1]) if turn % 2 == 1 else (pl[1], pl[0])
        # 1 draw
        n = 0
        while len(me.hand) < P["hand_limit"] and n < P["draw_max"] and draw(me) is not None:
            n += 1
        if me.hand:
            # 2 play
            card = policy_p1(me) if turn % 2 == 1 else policy_p2(me)
            me.hand.remove(card)
            me.pos = (me.pos + val(card)) % T
            # 3 capture
            if me.pos == you.pos and you.hand:
                low = sorted(you.hand, key=order)[0]
                you.hand.remove(low)
                me.hand.append(low)
                captures += 1
            # 4 effect
            eff = P["track"][me.pos]
            keep = False
            if eff == "MINE":
                me.coins += val(card)
            elif eff == "TOLL":
                pay = P["toll"] if me.coins >= P["toll"] else me.coins
                me.coins -= pay
                you.coins += pay
                tolls += pay
            elif eff == "FORGE":
                if sum(me.stock.values()) > 0:
                    top = max(me.stock.values())
                    s = sorted((s for s in me.stock if me.stock[s] == top), key=lambda s: rank[s])[0]
                    nxt = P["suit_order"][(rank[s] + 1) % len(P["suit_order"])]
                    me.stock[s] -= 1
                    me.stock[nxt] += 1
            elif eff == "SWAP":
                me.pos, you.pos = you.pos, me.pos
            elif eff == "QUARRY":
                me.stock[suit(card)] += 1
                keep = True
            elif eff == "WELL":
                draw(me)
            elif eff == "TRADE":
                if me.hand and you.hand:
                    hi = sorted(me.hand, key=order)[-1]
                    lo = sorted(you.hand, key=order)[0]
                    me.hand.remove(hi); you.hand.remove(lo)
                    me.hand.append(lo); you.hand.append(hi)
            elif eff == "BANK":
                me.coins += sum(me.stock.values())
            elif eff == "PLAIN":
                pass
            else:
                raise ValueError("unknown effect " + eff)
            # 5 discard
            if not keep:
                discard.insert(0, card)
            # 6 hand limit
            while len(me.hand) > P["hand_limit"]:
                low = sorted(me.hand, key=order)[0]
                me.hand.remove(low)
                discard.insert(0, low)
        if turn in P["checkpoints"]:
            def snap(p):
                return {"position": p.pos, "coins": p.coins, "hand_size": len(p.hand),
                        "hand_total": sum(val(c) for c in p.hand),
                        "stockpile": {s: p.stock[s] for s in ["Ore", "Wood", "Grain", "Gem"]}}
            out.append({"turn": turn, "P1": snap(pl[0]), "P2": snap(pl[1])})
    s1 = pl[0].coins + P["mult"] * sum(pl[0].stock.values())
    s2 = pl[1].coins + P["mult"] * sum(pl[1].stock.values())
    final = {"winner": "P1" if s1 > s2 else ("P2" if s2 > s1 else "draw"),
             "p1_score": s1, "p2_score": s2, "total_captures": captures,
             "total_tolls_paid": tolls, "discard_pile_size": len(discard),
             "deck_remaining": len(deck)}
    return {"checkpoints": out, "final": final}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    a = ap.parse_args()
    P = parse_prompt(open(os.path.join(a.dir, "prompt.txt")).read())
    got = simulate(P)
    key = json.load(open(os.path.join(a.dir, "key.json")))
    if got == key:
        print(f"ORACLE AGREES with key.json ({len(got['checkpoints'])} checkpoints, "
              f"final={got['final']})")
        return 0
    print("ORACLE DISAGREES")
    print(json.dumps({"oracle": got, "key": key}, indent=1))
    return 1


if __name__ == "__main__":
    sys.exit(main())
