#!/usr/bin/env python3
"""Independent oracle for Quarry Duel (candidate simulation-1).

Reads ONLY prompt.txt: every rule parameter (track layout, deck order, suit order,
turn count, hand limit, start coins, toll amount, score multiplier, which player follows
the targeting policy and what it targets, checkpoint turns, resync turn) is parsed back
out of the rules text, then the game is re-simulated with a deliberately different
implementation (string cards, deque deck, discard pile stored top-first, sorted-hand
policies) and compared with key.json. It also checks the RESYNC STATE printed in the
prompt against its own state after that turn.

Usage: python oracle.py [--dir DIR]   -> exits 0 iff the recomputed answer == key.json
"""
import argparse
import json
import os
import re
import sys
from collections import deque, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SUITS = ["Ore", "Wood", "Grain", "Gem"]


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
    assert "never drawing more than" not in text, "a draw cap is back in the rules; teach the oracle"
    P["toll"] = int(re.search(r"TOLL: you pay (\d+) coins to your opponent", text).group(1))
    P["mult"] = int(re.search(r"final score = coins \+ (\d+) x", text).group(1))
    # policies: exactly one player line mentions candidates; the other counts suits
    pol = text.split("== POLICIES ==")[1].split("== END OF GAME")[0]
    P["policy"] = {}
    for m in re.finditer(r"^- P([12]) \((odd|even) turns\): (.*)$", pol, re.M):
        p = int(m.group(1)) - 1
        assert (m.group(2) == "odd") == (p == 0)
        line = m.group(3)
        if "candidate" in line:
            P["policy"][p] = ("target", re.search(r"onto a ([A-Z]+) space", line).group(1))
            assert "HIGHEST candidate" in line and "LOWEST card" in line
        else:
            assert "earliest of them" in line and "HIGHEST card of suit S" in line
            P["policy"][p] = ("suitcount", None)
    assert sorted(P["policy"]) == [0, 1] and {v[0] for v in P["policy"].values()} == {"target", "suitcount"}
    deck_block = text.split("== DECK ORDER (card 1 is the top) ==")[1].split("== WORKED")[0]
    cards = re.findall(r"(\d+):([A-Za-z]+-\d)", deck_block)
    nums = [int(n) for n, _ in cards]
    assert nums == list(range(1, len(nums) + 1)), "deck numbering broken"
    P["deck"] = [c for _, c in cards]
    assert len(P["deck"]) == int(re.search(r"A deck of (\d+) cards", text).group(1))
    cp = re.search(r"end \(step 6\) of turns ([\d, ]+) \(every", text).group(1)
    P["checkpoints"] = [int(x) for x in cp.split(",")]
    P["resync_turn"] = int(re.search(r"== RESYNC STATE: THE COMPLETE POSITION AFTER TURN (\d+) ==", text).group(1))
    assert P["resync_turn"] not in P["checkpoints"]
    # printed resync state, for the cross-check
    rs = text.split("== RESYNC STATE")[1].split("== WHAT TO REPORT")[0]
    R = {}
    for p in (1, 2):
        m = re.search(rf"^P{p}: space (\d+), (\d+) coins, hand (.*?) \(hand_size (\d+), hand_total (\d+)\), "
                      rf"stockpile (\{{.*?\}})$", rs, re.M)
        R[f"P{p}"] = {"position": int(m.group(1)), "coins": int(m.group(2)),
                      "hand": sorted(re.findall(r"[A-Za-z]+-\d", m.group(3))),
                      "hand_size": int(m.group(4)), "hand_total": int(m.group(5)),
                      "stockpile": json.loads(m.group(6))}
    m = re.search(r"^Deck \((\d+) cards?, top first\): (.*)$", rs, re.M)
    R["deck"] = re.findall(r"[A-Za-z]+-\d", m.group(2))
    assert len(R["deck"]) == int(m.group(1))
    m = re.search(r"^Discard pile \((\d+) cards?, top first\): (.*)$", rs, re.M)
    R["discard_top_first"] = re.findall(r"[A-Za-z]+-\d", m.group(2))
    assert len(R["discard_top_first"]) == int(m.group(1))
    m = re.search(r"Captures so far: (\d+)\. Coins paid by TOLL so far: (\d+)\. Reshuffles so far: (\d+)\.", rs)
    R["captures"], R["tolls"], R["reshuffles"] = (int(x) for x in m.groups())
    P["resync_state"] = R
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
    captures = tolls = reshuffles = 0
    out = []
    plays = []
    resync_seen = None

    def draw(me):
        nonlocal deck, discard, reshuffles
        if len(deck) == 0:
            if not discard:
                return None
            deck = deque(discard)      # top of discard (index 0) becomes top of deck
            discard = []
            reshuffles += 1
        c = deck.popleft()
        me.hand.append(c)
        return c

    def policy_suitcount(me):
        cnt = Counter(suit(c) for c in me.hand)
        top = max(cnt.values())
        s = sorted((s for s in cnt if cnt[s] == top), key=lambda s: rank[s])[0]
        return sorted((c for c in me.hand if suit(c) == s), key=order)[-1]

    def policy_target(me, target):
        cands = [c for c in me.hand if P["track"][(me.pos + val(c)) % T] == target]
        if cands:
            return sorted(cands, key=order)[-1]
        return sorted(me.hand, key=order)[0]

    def snap(p):
        return {"position": p.pos, "coins": p.coins, "hand_size": len(p.hand),
                "hand_total": sum(val(c) for c in p.hand),
                "stockpile": {s: p.stock[s] for s in SUITS}}

    for turn in range(1, P["turns"] + 1):
        idx = 0 if turn % 2 == 1 else 1
        me, you = pl[idx], pl[1 - idx]
        # 1 draw
        while len(me.hand) < P["hand_limit"] and draw(me) is not None:
            pass
        if not me.hand:
            plays.append(None)
        else:
            # 2 play
            kind, target = P["policy"][idx]
            card = policy_suitcount(me) if kind == "suitcount" else policy_target(me, target)
            me.hand.remove(card)
            plays.append(card)
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
            out.append({"turn": turn, "P1": snap(pl[0]), "P2": snap(pl[1])})
        if turn == P["resync_turn"]:
            resync_seen = {"P1": {**snap(pl[0]), "hand": sorted(pl[0].hand)},
                           "P2": {**snap(pl[1]), "hand": sorted(pl[1].hand)},
                           "deck": list(deck), "discard_top_first": list(discard),
                           "captures": captures, "tolls": tolls, "reshuffles": reshuffles}
    s1 = pl[0].coins + P["mult"] * sum(pl[0].stock.values())
    s2 = pl[1].coins + P["mult"] * sum(pl[1].stock.values())
    final = {"winner": "P1" if s1 > s2 else ("P2" if s2 > s1 else "draw"),
             "p1_score": s1, "p2_score": s2, "total_captures": captures,
             "total_tolls_paid": tolls, "discard_pile_size": len(discard),
             "deck_remaining": len(deck)}
    return {"plays": plays, "checkpoints": out, "final": final,
            "resync_turn": P["resync_turn"]}, resync_seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=HERE)
    a = ap.parse_args()
    P = parse_prompt(open(os.path.join(a.dir, "prompt.txt")).read())
    got, resync_seen = simulate(P)
    key = json.load(open(os.path.join(a.dir, "key.json")))
    ok = got == key
    rs_ok = resync_seen == P["resync_state"]
    if ok and rs_ok:
        print(f"ORACLE AGREES with key.json ({len(got['plays'])} plays, {len(got['checkpoints'])} checkpoints, "
              f"resync after turn {got['resync_turn']} matches the printed state, final={got['final']})")
        return 0
    print("ORACLE DISAGREES" + ("" if ok else " on the answer") + ("" if rs_ok else " on the resync state"))
    print(json.dumps({"oracle": got, "key": key, "oracle_resync": resync_seen,
                      "printed_resync": P["resync_state"]}, indent=1)[:6000])
    return 1


if __name__ == "__main__":
    sys.exit(main())
