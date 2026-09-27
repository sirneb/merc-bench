#!/usr/bin/env python3
"""Generator for adversarial-3: "Chess Open Standings With Arbiter Errata".

Deterministic given --seed and --difficulty. Writes prompt.txt, key.json, schema.json.

    python generator.py --seed 20260926 --difficulty hard --out .

Pipeline
  1. Simulate a Swiss tournament (players with hidden strengths, simple Dutch-ish pairing that
     avoids rematches, colour balancing, pairing-allocated byes).
  2. Plant a fixed schedule of "traps": mis-entered results later corrected, a transposed
     pairing list involving near-duplicate surnames, a move-count correction, five
     announcements with different scopes / authorities (one retracted), late arrivals,
     phone incidents, a withdrawal, two kinds of bye.
  3. Keep the AUTHORITATIVE structured event list; the reference scorer applies the
     regulations (as amended) to it -> standings (key).
  4. Compute counterfactual standings for every single-trap-missed variant (for the grader's
     attribution) and for the naive "first-entry" tally; assert that every trap bites.
  5. Render the regulations + the chronological arbiter log as prompt.txt.
"""
import argparse
import json
import os
import random
import sys

# --------------------------------------------------------------------------------------
# Difficulty presets
# --------------------------------------------------------------------------------------
PRESETS = {
    # players, rounds, near-duplicate surname pairs, extra random short draws
    "small":   dict(players=10, rounds=6,  dup_pairs=1, extra_short=0),
    "medium":  dict(players=16, rounds=7,  dup_pairs=1, extra_short=1),
    "hard":    dict(players=20, rounds=9,  dup_pairs=2, extra_short=2),
    "extreme": dict(players=30, rounds=11, dup_pairs=3, extra_short=4),
}

# Near-duplicate surname pairs come first (each pair = two different players).
DUP_PAIRS = [
    (("Novak", "Aleksander"), ("Nowak", "Andrzej")),
    (("Lindqvist", "Olof"), ("Lindkvist", "Oskar")),
    (("Ferreira", "Rui"), ("Ferrera", "Raul")),
]
OTHER_NAMES = [
    ("Kowalczyk", "Marek"), ("Berg", "Sofia"), ("Kim", "Daniel"), ("Duarte", "Ines"),
    ("Haidar", "Leila"), ("Okafor", "Chidi"), ("Petrov", "Ilya"), ("Tanaka", "Yui"),
    ("Moreau", "Camille"), ("Schulz", "Jonas"), ("Rossi", "Giulia"), ("Nair", "Arjun"),
    ("Byrne", "Aoife"), ("Castillo", "Mateo"), ("Horvath", "Eszter"), ("Aliyev", "Timur"),
    ("Mbeki", "Thabo"), ("Sorensen", "Freja"), ("Quintero", "Lucia"), ("Ibrahim", "Yusuf"),
    ("Varga", "Bence"), ("Delacroix", "Elise"), ("Papadopoulos", "Nikos"), ("Zhang", "Wei"),
    ("Almeida", "Tiago"), ("Fischer", "Lena"), ("Osei", "Kwame"), ("Ivanova", "Daria"),
    ("Brennan", "Ciaran"), ("Halvorsen", "Sigrid"), ("Rahman", "Farah"), ("Costa", "Bruno"),
]

DRAW = "1/2-1/2"

# --------------------------------------------------------------------------------------
# Reference scorer (applies regulations to the structured events)
# --------------------------------------------------------------------------------------
DEFAULT_OPTS = dict(
    corrections=True,        # apply result corrections
    swap=True,               # apply transposed-pairing correction
    moves_corr=True,         # apply move-count correction
    ignore_ann=set(),        # announcement ids to ignore entirely
    honor_td=False,          # honour announcements by the Tournament Director
    honor_retracted=False,   # honour retracted announcements
    from_exclusive=False,    # misread "with effect from round r" as r+1..
    after_inclusive=False,   # misread "for rounds after round r" as r..
    sd_le=False,             # short draw threshold "<" misread as "<="
    late_ge=False,           # late threshold ">" misread as ">="
    full_bye=1.0,
    half_bye=0.5,
    bh_bye="own",            # BH contribution of bye/unpaired round: own points | zero
    forfeit_bh="opp",        # BH contribution of a forfeit game: opponent's points | zero
    withdraw_game="forfeit", # withdrawn player's game: forfeit | zero (both 0, not a game)
    sb_bye_zero=True,        # SB: byes contribute 0 (key); False -> bye pts * own pts
)


def ann_applies(ann, rnd, o):
    if ann["id"] in o["ignore_ann"]:
        return False
    if ann["by"] != "CA" and not o["honor_td"]:
        return False
    if ann.get("retracted") and not o["honor_retracted"]:
        return False
    sc = ann["scope"]
    if sc["type"] == "from":
        return rnd > sc["r"] if o["from_exclusive"] else rnd >= sc["r"]
    if sc["type"] == "after":
        return rnd >= sc["r"] if o["after_inclusive"] else rnd > sc["r"]
    if sc["type"] == "retro":
        return True
    if sc["type"] == "rounds":
        return rnd in sc["rounds"]
    raise ValueError(sc)


def score_tournament(T, opts=None):
    """T: dict with players (list of ids in start order), rounds (r -> {boards:{b:[w,bl]}, byes:{pid:kind}}),
    events (log-ordered). Returns dict with per-player stats, ordered ranking, forfeits count."""
    o = dict(DEFAULT_OPTS)
    if opts:
        o.update(opts)
    R = T["rounds_n"]
    players = T["players"]
    # 1. build game table from pairing lists
    games = {}
    for r in range(1, R + 1):
        for b, (w, bl) in T["rounds"][str(r)]["boards"].items():
            games[(r, int(b))] = dict(r=r, b=int(b), w=w, bl=bl, res=None, moves=None,
                                      forfeit=False, late={}, phone=set(), withdrawn=False)
    anns = {}
    # 2. replay the log
    for ev in T["events"]:
        t = ev["type"]
        if t == "result":
            g = games[(ev["r"], ev["b"])]
            g["res"], g["moves"], g["forfeit"] = ev["res"], ev.get("moves"), ev.get("forfeit", False)
            g["withdrawn"] = ev.get("reason") == "withdrawn"
        elif t == "corr_result":
            if o["corrections"]:
                g = games[(ev["r"], ev["b"])]
                g["res"] = ev["res"]
                if "moves" in ev:
                    g["moves"] = ev["moves"]
        elif t == "corr_swap":
            if o["swap"]:
                g1, g2 = games[(ev["r"], ev["b1"])], games[(ev["r"], ev["b2"])]
                g1["w"], g2["w"] = g2["w"], g1["w"]
        elif t == "corr_moves":
            if o["moves_corr"]:
                games[(ev["r"], ev["b"])]["moves"] = ev["moves"]
        elif t == "late":
            games[(ev["r"], ev["b"])]["late"][ev["color"]] = ev["minutes"]
        elif t == "phone":
            games[(ev["r"], ev["b"])]["phone"].add(ev["color"])
        elif t == "announce":
            anns[ev["id"]] = dict(ev)
        elif t == "retract":
            anns[ev["ann"]]["retracted"] = True
        elif t in ("withdraw", "note", "pairings"):
            pass
        else:
            raise ValueError(t)
    # 3. apply rules per game
    pts = {p: 0.0 for p in players}
    gres = {}  # (r,b) -> (pw, pb, is_forfeit, is_game)
    forfeits = 0
    for key, g in sorted(games.items()):
        r = g["r"]
        res = g["res"]
        assert res is not None, key
        base = {"1-0": (1, 0), "0-1": (0, 1), DRAW: (0.5, 0.5), "+/-": (1, 0), "-/+": (0, 1)}[res]
        pw, pb = base
        is_forfeit = g["forfeit"]
        is_game = True
        if g["withdrawn"] and o["withdraw_game"] == "zero":
            pw, pb, is_forfeit, is_game = 0, 0, False, False
        elif not is_forfeit:
            # late-arrival retro forfeit rule
            done = False
            for a in anns.values():
                if a["kind"] == "late_forfeit" and ann_applies(a, r, o):
                    thr = a["threshold"]
                    for color, m in g["late"].items():
                        hit = m >= thr if o["late_ge"] else m > thr
                        if hit:
                            pw, pb = ((0, 1) if color == "w" else (1, 0))
                            is_forfeit = True
                            done = True
                    if done:
                        break
            if not done:
                for a in anns.values():
                    if a["kind"] == "phone_loss" and ann_applies(a, r, o) and g["phone"]:
                        color = next(iter(g["phone"]))
                        pw, pb = ((0, 1) if color == "w" else (1, 0))
                        done = True
                        break
            if not done and res == DRAW:
                suspended = any(a["kind"] == "suspend_short_draw" and ann_applies(a, r, o)
                                for a in anns.values())
                if not suspended:
                    for a in anns.values():
                        if a["kind"] == "short_draw" and ann_applies(a, r, o):
                            thr = a["threshold"]
                            hit = g["moves"] <= thr if o["sd_le"] else g["moves"] < thr
                            if hit:
                                pw, pb = 0, 0
                                break
        if is_forfeit:
            forfeits += 1
        gres[key] = (pw, pb, is_forfeit, is_game)
        pts[g["w"]] += pw
        pts[g["bl"]] += pb
    # byes
    byes = {}
    for r in range(1, R + 1):
        for pid, kind in T["rounds"][str(r)]["byes"].items():
            v = o["full_bye"] if kind == "full" else o["half_bye"]
            pts[pid] += v
            byes[(pid, r)] = v
    # 4. tiebreaks
    sched = {p: {} for p in players}  # p -> r -> (opp, my_pts, is_forfeit, is_game)
    for (r, b), g in games.items():
        pw, pb, ff, ig = gres[(r, b)]
        sched[g["w"]][r] = (g["bl"], pw, ff, ig)
        sched[g["bl"]][r] = (g["w"], pb, ff, ig)
    stats = {}
    for p in players:
        bh = sb = 0.0
        wins = 0
        for r in range(1, R + 1):
            if r in sched[p] and sched[p][r][3]:
                opp, my, ff, _ = sched[p][r]
                bh += 0.0 if (ff and o["forfeit_bh"] == "zero") else pts[opp]
                sb += pts[opp] * my
                if my == 1:
                    wins += 1
            else:
                bh += pts[p] if o["bh_bye"] == "own" else 0.0
                if not o["sb_bye_zero"] and (p, r) in byes:
                    sb += byes[(p, r)] * pts[p]
        stats[p] = dict(points=pts[p], buchholz=bh, sonneborn_berger=sb, wins=wins)
    # 5. ranking
    start = {p: i for i, p in enumerate(players)}
    groups = {}
    for p in players:
        s = stats[p]
        groups.setdefault((s["points"], s["buchholz"], s["sonneborn_berger"]), []).append(p)
    order = []
    for k in sorted(groups, reverse=True):
        grp = groups[k]
        if len(grp) == 2:
            a, c = grp
            de = None
            for r, (opp, my, ff, ig) in sched[a].items():
                if opp == c and ig:
                    de = my
            if de == 1:
                order += [a, c]
                continue
            if de == 0:
                order += [c, a]
                continue
        order += sorted(grp, key=lambda p: (-stats[p]["wins"], start[p]))
    for i, p in enumerate(order, 1):
        stats[p]["rank"] = i
    return dict(stats=stats, order=order, forfeits=forfeits, gres={f"{r}-{b}": v for (r, b), v in gres.items()})


NAIVE_OPTS = dict(corrections=False, swap=False, moves_corr=False, ignore_ann={1, 2, 3, 4, 5})

# Single-trap-missed variants (name -> opts override).  "honor_retracted" == apply the
# short-draw rule to every round; "td" == honour the Director's suspension.
VARIANTS = {
    "miss_result_correction": dict(corrections=False),
    "miss_pairing_transposition": dict(swap=False),
    "miss_movecount_correction": dict(moves_corr=False),
    "ignore_short_draw_rule": dict(ignore_ann={1}),
    "short_draw_scope_exclusive": dict(from_exclusive=True),
    "short_draw_boundary_le": dict(sd_le=True),
    "honor_retracted_retro_extension": dict(honor_retracted=True),
    "honor_director_suspension": dict(honor_td=True),
    "ignore_phone_rule": dict(ignore_ann={2}),
    "phone_scope_inclusive": dict(after_inclusive=True),
    "ignore_late_retro_rule": dict(ignore_ann={5}),
    "late_boundary_ge": dict(late_ge=True),
    "half_bye_as_full": dict(half_bye=1.0),
    "full_bye_as_half": dict(full_bye=0.5),
    "bh_bye_as_zero": dict(bh_bye="zero"),
    "forfeit_bh_as_zero": dict(forfeit_bh="zero"),
    "withdrawn_game_as_zero": dict(withdraw_game="zero"),
    "sb_bye_counted": dict(sb_bye_zero=False),
}


# --------------------------------------------------------------------------------------
# Swiss simulation
# --------------------------------------------------------------------------------------
def make_pairing(order, played, pts):
    """order: players sorted best-first. Return list of (a, b) pairs avoiding rematches.
    Greedy top-half/bottom-half within the score bracket (floaters drop to the next bracket),
    with backtracking so that a complete rematch-free pairing is always found."""
    n = len(order)
    assert n % 2 == 0

    def rec(rem):
        if not rem:
            return []
        a = rem[0]
        rest = rem[1:]
        # candidates: same-score players first, folded (top half vs bottom half of the bracket),
        # then lower brackets in order (downfloat)
        grp = [i for i, x in enumerate(rest) if pts[x] == pts[a]]
        half = (len(grp) + 1) // 2
        # bracket of size g+1 including a: a's partner is the first of the bottom half
        pref = grp[half - 1:] + grp[: half - 1] if grp else []
        others = [i for i in range(len(rest)) if i not in grp]
        cands = pref + others
        for i in cands:
            c = rest[i]
            if c in played[a]:
                continue
            sub = rec(rest[:i] + rest[i + 1:])
            if sub is not None:
                return [(a, c)] + sub
        return None

    res = rec(order)
    assert res is not None, "no pairing found"
    return res


def assign_colors(a, b, colors, last_color, rank):
    wa = colors[a].count("w") - colors[a].count("b")
    wb = colors[b].count("w") - colors[b].count("b")
    if wa < wb:
        return a, b
    if wb < wa:
        return b, a
    # equal balance: alternate for the higher-ranked player
    hi, lo = (a, b) if rank[a] < rank[b] else (b, a)
    if last_color.get(hi) == "w":
        return lo, hi
    return hi, lo


def simulate(seed, preset):
    rng = random.Random(seed)
    N, R = preset["players"], preset["rounds"]
    # ---- players
    names = []
    for i in range(preset["dup_pairs"]):
        names += list(DUP_PAIRS[i])
    others = OTHER_NAMES[:]
    rng.shuffle(others)
    names += others[: N - len(names)]
    rng.shuffle(names)
    ids = [f"P{i:02d}" for i in range(1, N + 1)]
    players = []
    for pid, (sur, giv) in zip(ids, names):
        players.append(dict(id=pid, surname=sur, given=giv, name=f"{sur}, {giv}"))
    strength = {p["id"]: 2350 - 22 * i + rng.uniform(-40, 40) for i, p in enumerate(players)}
    late_entrant = ids[-1]        # admitted after round-1 pairings
    withdrawer = None

    # ---- trap schedule (round numbers)
    a1 = (R + 1) // 2             # short-draw rule with effect from a1; phone rule after a1
    wr = R - 2                    # withdrawal after pairings of round wr
    plan = {
        "short_draw_pre": [1, 2, 3] if R >= 7 else [1],     # short draws before the rule (unaffected)
        "short_draw_hit": [a1, R - 1, R],                    # short draws that become 0-0
        "short_draw_boundary": [a1 + 1, R],                  # draws in exactly `threshold` moves
        "movecount_corr": a1 + 2,                            # draw entered as 20+ moves, corrected to <20
        "reversed": 3 if R >= 5 else 2,                      # reversed result, corrected during next round
        "second_corr": R - 1,                                # 1-0 entered, corrected to draw, during round R
        "swap": a1 + 1,                                      # transposed white players (Novak/Nowak)
        "phone_warn": [a1 - 1, a1],                          # phone incidents: warnings (a1 is the scope trap)
        "phone_loss": a1 + 2,                                # phone incident that costs the game
        "late": [(2, 34), (a1, 22), (a1 + 1, 30), (R - 2, 47)],  # (round, minutes late), game played
        "late_default": 3,                                   # > 60 min -> forfeit at the time
        "no_show": 4 if R >= 7 else 2,
        "td_rounds": [R - 1, R],
        "a4_before": a1 + 2,                                 # retro-extension announced then retracted
    }
    if R < 7:
        plan["late"] = [(2, 34), (a1 + 1, 30)]
        plan["phone_warn"] = [a1]
    threshold = 20

    # ---- state
    rounds = {}
    events = []            # structured, log-ordered
    log = []               # rendered log entries (strings, possibly multi-line)
    played = {p: set() for p in ids}
    colors = {p: [] for p in ids}
    last_color = {}
    had_bye = set()
    pairing_entry = {}
    late_players = set()
    by_id = {p["id"]: p for p in players}
    sur2id = {p["surname"]: p["id"] for p in players}
    swap_pair = [sur2id[DUP_PAIRS[0][0][0]], sur2id[DUP_PAIRS[0][1][0]]]
    name_pair = ([sur2id[DUP_PAIRS[1][0][0]], sur2id[DUP_PAIRS[1][1][0]]]
                 if preset["dup_pairs"] >= 2 else swap_pair)
    dupset = {p["id"] for p in players
              if any(p["surname"] in (a[0], b[0]) for a, b in DUP_PAIRS[: preset["dup_pairs"]])}

    def entry(text):
        log.append(text)
        return len(log)

    def pname(pid):
        return f"{pid} {by_id[pid]['name']}"

    def current_view():
        Tv = dict(players=ids, rounds=rounds, events=events, rounds_n=len(rounds))
        return score_tournament(Tv)["stats"]

    # registration entries
    entry("REGISTRATION CLOSED. Players registered, with start numbers assigned by rating (start numbers "
          "are also the final tie-break, Reg. 5.2(e)):\n" +
          "\n".join(f"      {pname(p['id'])}" for p in players[:-1]))
    entry(f"Late admission (Reg. 4.2): {pname(late_entrant)} was admitted to the tournament after the "
          f"round-1 pairings had been published and receives the start number {late_entrant}. "
          "The player will be paired from round 2. — Chief Arbiter")
    entry("Officials for the event: Chief Arbiter, Deputy Arbiter, Tournament Director, Appeals Committee "
          "(three members). Routine result entries and corrections in this log are recorded by the "
          "Deputy Arbiter unless stated otherwise. — Chief Arbiter")

    def game_result(w, bl):
        pw = 1 / (1 + 10 ** ((strength[bl] - strength[w] - 35) / 400))
        x = rng.random()
        pd = 0.30
        if x < pd:
            return DRAW
        return "1-0" if (x - pd) / (1 - pd) < pw else "0-1"

    active = set(ids) - {late_entrant}
    withdrawn_round = None
    for r in range(1, R + 1):
        if r == 2:
            active.add(late_entrant)
        view = current_view() if r > 1 else {p: dict(points=0.0) for p in ids}
        rank = {p: i for i, p in enumerate(ids)}
        order = sorted(active, key=lambda p: (-view[p]["points"], rank[p]))
        byes = {}
        if r == 1:
            byes[late_entrant] = "half"
        if len(order) % 2 == 1:
            for p in reversed(order):
                if p not in had_bye:
                    byes[p] = "full"
                    had_bye.add(p)
                    order.remove(p)
                    break
        pairs = make_pairing(order, played, {p: view[p]["points"] for p in ids})
        # board order: by best of the pair
        pairs.sort(key=lambda ab: min(rank[ab[0]], rank[ab[1]]))
        boards = {}
        for b, (a, c) in enumerate(pairs, 1):
            w, bl = assign_colors(a, c, colors, last_color, rank)
            boards[str(b)] = [w, bl]
            colors[w].append("w")
            colors[bl].append("b")
            last_color[w], last_color[bl] = "w", "b"
            played[w].add(bl)
            played[bl].add(w)
        rounds[str(r)] = dict(boards=boards, byes=byes)
        nb = len(boards)

        # ---- announcements before the round
        if r == a1:
            eid = entry(f"ANNOUNCEMENT 1 — With effect from round {a1}, any game drawn in fewer than "
                        f"{threshold} moves shall be scored 0-0, that is zero points for both players "
                        "(Reg. 8.2 applies). — Chief Arbiter")
            events.append(dict(type="announce", id=1, by="CA", kind="short_draw", threshold=threshold,
                               scope=dict(type="from", r=a1), entry=eid))
            eid = entry(f"ANNOUNCEMENT 2 — For rounds after round {a1}, a mobile phone or other electronic "
                        "device producing a sound in the playing hall during play shall be penalised by "
                        "loss of the game (Reg. 10.2 applies). — Chief Arbiter")
            events.append(dict(type="announce", id=2, by="CA", kind="phone_loss",
                               scope=dict(type="after", r=a1), entry=eid))
        if r == plan["a4_before"]:
            eid = entry("ANNOUNCEMENT 4 — Following consultation with the players' representative, "
                        "Announcement 1 (short-draw scoring) shall apply retroactively from round 1; "
                        f"drawn games of fewer than {threshold} moves in rounds 1 to {a1 - 1} are to be "
                        "re-scored 0-0 accordingly. — Chief Arbiter")
            events.append(dict(type="announce", id=4, by="CA", kind="short_draw", threshold=threshold,
                               scope=dict(type="retro"), entry=eid))
            entry("Playing hall: the ventilation fault reported yesterday has been repaired. "
                  "Refreshments are available in the foyer from 09:30. — Tournament Director")
            eid = entry("ANNOUNCEMENT 4 is withdrawn with immediate effect: the Appeals Committee has upheld "
                        "an appeal against it (Reg. 1.4). Announcement 1 continues to apply as originally "
                        "scoped. — Chief Arbiter")
            events.append(dict(type="retract", ann=4, entry=eid))
        if r == plan["td_rounds"][0]:
            eid = entry("TOURNAMENT DIRECTOR'S NOTICE — In view of complaints from spectators and sponsors, "
                        "the short-draw scoring introduced by Announcement 1 is suspended for rounds "
                        f"{plan['td_rounds'][0]} and {plan['td_rounds'][1]}; drawn games in those rounds "
                        "are scored 1/2-1/2 regardless of the number of moves. — Tournament Director")
            events.append(dict(type="announce", id=3, by="TD", kind="suspend_short_draw",
                               scope=dict(type="rounds", rounds=plan["td_rounds"]), entry=eid))

        # ---- pairings entry
        lines = [f"PAIRINGS — ROUND {r}"]
        pub_boards = dict(boards)
        swap_here = (r == plan["swap"])
        if swap_here:
            # find the dup pair players (ids of DUP_PAIRS[0]); transpose their white/black? We
            # transpose the WHITE players of the two boards where they play.  Ensure both are white.
            d1, d2 = swap_pair
            b1 = next((b for b, (w, bl) in boards.items() if d1 in (w, bl)), None)
            b2 = next((b for b, (w, bl) in boards.items() if d2 in (w, bl)), None)
            if b1 is None or b2 is None or b1 == b2:
                swap_here = False
            else:
                # force both to be white on their boards (colour bookkeeping is cosmetic)
                for b, d in ((b1, d1), (b2, d2)):
                    w, bl = boards[b]
                    if w != d:
                        boards[b] = [bl, w]
                pub_boards = dict(boards)
                pub_boards[b1] = [boards[b2][0], boards[b1][1]]
                pub_boards[b2] = [boards[b1][0], boards[b2][1]]
                swap_boards = (int(b1), int(b2))
        for b in sorted(pub_boards, key=int):
            w, bl = pub_boards[b]
            lines.append(f"      B{int(b):02d}: {pname(w)} (White) — {pname(bl)} (Black)")
        for pid, kind in byes.items():
            if kind == "full":
                lines.append(f"      Pairing-allocated bye (Reg. 4.1): {pname(pid)}")
            else:
                lines.append(f"      Half-point bye (Reg. 4.2, late admission): {pname(pid)}")
        # the structured rounds hold the list AS PUBLISHED; the scorer replays the correction
        rounds[str(r)]["boards"] = pub_boards
        eid = entry("\n".join(lines))
        pairing_entry[r] = eid
        events.append(dict(type="pairings", r=r, entry=eid))
        entry(f"Round {r} started at the scheduled time.")

        # ---- withdrawal (after pairings of round wr)
        if r == wr:
            # choose a mid-table player who is not a dup-name player, not late entrant
            if preset["dup_pairs"] >= 2:
                # the withdrawal is announced by surname only: use the second near-duplicate pair
                withdrawer = max(name_pair, key=lambda p: (order.index(p) if p in order else -1))
            else:
                cands = [p for p in order if p not in dupset and p != late_entrant]
                withdrawer = cands[len(cands) // 2]
            withdrawn_round = r
            wb = next(b for b, (w, bl) in boards.items() if withdrawer in (w, bl))
            eid = entry(f"{by_id[withdrawer]['surname']} notified the Chief Arbiter in writing that "
                        f"{'he' if rng.random() < 0.5 else 'she'} withdraws from the tournament with "
                        "immediate effect for medical reasons (Reg. 11). Results already scored stand. "
                        "— Chief Arbiter")
            events.append(dict(type="withdraw", player=withdrawer, r=r, entry=eid))

        # ---- generate results with plants
        results = {}
        plants = {}   # board -> tag
        free = [b for b in boards if not (r == wr and withdrawer in boards[b])]
        rng.shuffle(free)

        def take(tag):
            if not free:
                return None
            b = free.pop()
            plants[b] = tag
            return b

        for b, (w, bl) in boards.items():
            res = game_result(w, bl)
            if res == DRAW:
                moves = rng.randint(threshold + 3, 68)
            else:
                moves = rng.randint(24, 78)
            results[b] = dict(res=res, moves=moves, forfeit=False)
        if r == wr:
            wbd = next(b for b, (w, bl) in boards.items() if withdrawer in boards[b])
            w, bl = boards[wbd]
            results[wbd] = dict(res="-/+" if w == withdrawer else "+/-", moves=None, forfeit=True,
                                reason="withdrawn")
        if r == plan["phone_loss"]:
            # the offender should not already have lost, so that the penalty changes the score
            pref = [p for p in name_pair if p != withdrawer]
            bb = next((b for b in free if any(p in boards[b] for p in pref)), None)
            if bb is not None:
                free.remove(bb)
                plants[bb] = "phone_loss"
                b = bb
                offender = next(p for p in pref if p in boards[b])
                color = "w" if boards[b][0] == offender else "b"
            else:
                b = take("phone_loss")
                color = rng.choice("wb")
            if b:
                win = "1-0" if color == "w" else "0-1"
                results[b] = dict(res=rng.choice([win, DRAW]), moves=rng.randint(28, 60), forfeit=False)
                results[b]["phone"] = color
                results[b]["phone_byname"] = True
        n_pre = plan["short_draw_pre"].count(r) + (preset["extra_short"] if r < a1 and r % 2 == 1 else 0)
        for _ in range(n_pre):
            b = take("sd_pre")
            if b:
                results[b] = dict(res=DRAW, moves=rng.randint(9, threshold - 1), forfeit=False)
        for _ in range(plan["short_draw_hit"].count(r)):
            b = take("sd_hit")
            if b:
                results[b] = dict(res=DRAW, moves=rng.randint(9, threshold - 1), forfeit=False)
        if r in plan["short_draw_boundary"]:
            b = take("sd_boundary")
            if b:
                results[b] = dict(res=DRAW, moves=threshold, forfeit=False)
        if r == plan["movecount_corr"]:
            b = take("mc")
            if b:
                true_moves = rng.randint(11, threshold - 2)
                results[b] = dict(res=DRAW, moves=true_moves + 10, forfeit=False, true_moves=true_moves)
        if r == plan["reversed"]:
            b = take("rev")
            if b:
                results[b] = dict(res="1-0", moves=rng.randint(30, 60), forfeit=False, true_res="0-1")
        if r == plan["second_corr"]:
            b = take("corr2")
            if b:
                results[b] = dict(res="1-0", moves=rng.randint(30, 60), forfeit=False, true_res=DRAW)
        if r in plan["phone_warn"]:
            b = take("phone_warn")
            if b:
                # offender must not already have lost, so a mis-scoped penalty would change the score
                results[b] = dict(res=rng.choice(["1-0", "0-1", DRAW]), moves=rng.randint(28, 60), forfeit=False)
                results[b]["phone"] = ("w" if results[b]["res"] == "1-0" else
                                       "b" if results[b]["res"] == "0-1" else rng.choice("wb"))
        for lr, m in plan["late"]:
            if lr != r:
                continue
            bb = next((b for b in free if not any(p in late_players for p in boards[b])), None)
            if bb is not None:
                free.remove(bb)
                plants[bb] = "late"
                b = bb
            else:
                b = take("late")
            if b:
                color = rng.choice("wb")
                late_players.add(boards[b][0] if color == "w" else boards[b][1])
                # late player should score, so that a retro forfeit changes something
                res = rng.choice([DRAW, "1-0" if color == "w" else "0-1"])
                results[b] = dict(res=res, moves=rng.randint(threshold + 5, 65), forfeit=False,
                                  late=(color, m))
        if r == plan["late_default"]:
            b = take("late_default")
            if b:
                color = rng.choice("wb")
                results[b] = dict(res="-/+" if color == "w" else "+/-", moves=None, forfeit=True,
                                  reason="late_default", late=(color, rng.randint(63, 75)))
        if r == plan["no_show"]:
            b = take("no_show")
            if b:
                color = rng.choice("wb")
                results[b] = dict(res="-/+" if color == "w" else "+/-", moves=None, forfeit=True,
                                  reason="no_show", late=(color, None))

        # ---- incident entries (before results), then results in random order
        for b in sorted(boards, key=int):
            rs = results[b]
            w, bl = boards[b]
            if "late" in rs and rs.get("reason") != "no_show":
                color, m = rs["late"]
                who = by_id[w if color == "w" else bl]["surname"]
                cname = "White" if color == "w" else "Black"
                if rs.get("reason") == "late_default":
                    eid = entry(f"R{r} B{int(b):02d}: {cname} ({who}) arrived {m} minutes after the scheduled "
                                "start, after the default time. Game not played; forfeit recorded below "
                                "(Reg. 9.1).")
                else:
                    eid = entry(f"R{r} B{int(b):02d}: {cname} ({who}) arrived {m} minutes after the "
                                "scheduled start; the clock had been started at the scheduled time. "
                                "Lateness recorded (Reg. 9.2); play proceeded.")
                events.append(dict(type="late", r=r, b=int(b), color=color, minutes=m, entry=eid))
            if "phone" in rs:
                color = rs["phone"]
                who = by_id[w if color == "w" else bl]["surname"]
                cname = "White" if color == "w" else "Black"
                mv = rng.randint(12, 35)
                if rs.get("phone_byname"):
                    eid = entry(f"The mobile phone of {who} sounded in the playing hall during play in round "
                                f"{r} (at move {mv} of that game). Incident recorded (Reg. 10.1).")
                else:
                    eid = entry(f"R{r} B{int(b):02d}: the mobile phone of {cname} ({who}) sounded during play "
                                f"at move {mv}. Incident recorded (Reg. 10.1).")
                events.append(dict(type="phone", r=r, b=int(b), color=color, entry=eid))
        order_b = list(boards)
        rng.shuffle(order_b)
        for b in order_b:
            rs = results[b]
            if rs["forfeit"]:
                reason = rs.get("reason")
                color = ("w" if rs["res"] == "-/+" else "b")
                cname = "White" if color == "w" else "Black"
                if reason == "withdrawn":
                    txt = f"R{r} B{int(b):02d}: {rs['res']} (forfeit — {cname} withdrawn, Reg. 11.2)"
                elif reason == "late_default":
                    txt = f"R{r} B{int(b):02d}: {rs['res']} (forfeit — {cname} exceeded the default time, Reg. 9.1)"
                else:
                    txt = f"R{r} B{int(b):02d}: {rs['res']} (forfeit — {cname} did not appear)"
                eid = entry(txt)
                events.append(dict(type="result", r=r, b=int(b), res=rs["res"], moves=None, forfeit=True,
                                   reason=reason, entry=eid))
            else:
                eid = entry(f"R{r} B{int(b):02d}: {rs['res']} ({rs['moves']} moves)")
                events.append(dict(type="result", r=r, b=int(b), res=rs["res"], moves=rs["moves"],
                                   entry=eid))
        # noise
        if r % 3 == 0:
            entry(f"Round {r} completed. Standings after round {r} were displayed in the playing hall "
                  "(provisional, subject to this log).")

        # ---- corrections logged after the round (or during the next round)
        # transposed pairing list: corrected after results of this round
        if swap_here:
            b1, b2 = swap_boards
            eid = entry(f"CORRECTION — Round {r} pairing list (entry {pairing_entry[r]:03d}): "
                        f"the White players of boards B{b1:02d} and B{b2:02d} were transposed when the list "
                        f"was typed. White on B{b1:02d} was {pname(boards[str(b1)][0])}; White on B{b2:02d} was "
                        f"{pname(boards[str(b2)][0])}. The Black players and the results entered for each board "
                        "are unaffected and stand as entered. — Deputy Arbiter")
            events.append(dict(type="corr_swap", r=r, b1=b1, b2=b2, entry=eid))
        # reversed result / second correction / move-count correction are logged during the NEXT round
        pending = []
        for b, rs in results.items():
            if "true_res" in rs:
                pending.append(("res", r, int(b), rs))
            if "true_moves" in rs:
                pending.append(("moves", r, int(b), rs))
        if r == R:
            # nothing follows: log them now
            for kind, rr, bb, rs in pending:
                _log_correction(kind, rr, bb, rs, entry, events)
            pending = []
        rounds[str(r)]["_pending"] = pending
        # log corrections pending from previous round in the middle of this round's results? They were
        # logged at the end of the previous round; to interleave, we append them now (after this round).
        if r > 1:
            for kind, rr, bb, rs in rounds[str(r - 1)].pop("_pending", []):
                _log_correction(kind, rr, bb, rs, entry, events)
        if r == R:
            rounds[str(r)].pop("_pending", None)

        if r == wr:
            active.discard(withdrawer)

    # ---- final announcement (retroactive late-arrival forfeits)
    eid = entry("ANNOUNCEMENT 5 — Retroactively from round 1, the default time under Reg. 9.1 is reduced "
                "from 60 minutes to 30 minutes. Any player recorded in this log as having arrived more than "
                "30 minutes after the scheduled start of a round is deemed to have lost that game by "
                "forfeit (Reg. 9.3); the opponent receives a forfeit win. — Chief Arbiter")
    events.append(dict(type="announce", id=5, by="CA", kind="late_forfeit", threshold=30,
                       scope=dict(type="retro"), entry=eid))
    entry("Final standings are to be computed from this log as it stands, applying the Regulations as "
          "amended by the announcements above. Prize-giving follows. — Chief Arbiter")

    T = dict(players=ids, player_names={p["id"]: p["name"] for p in players},
             rounds=rounds, events=events, rounds_n=R, withdrawer=withdrawer, late_entrant=late_entrant,
             plan=dict(a1=a1, wr=wr, threshold=threshold))
    return T, log, players


def _log_correction(kind, r, b, rs, entry, events):
    if kind == "res":
        if rs["true_res"] == "0-1":
            eid = entry(f"CORRECTION — R{r} B{b:02d}: the result was entered reversed. The correct result is "
                        f"0-1 ({rs['moves']} moves). — Deputy Arbiter")
        else:
            eid = entry(f"CORRECTION — R{r} B{b:02d}: the result slip was misread; the game ended in a draw. "
                        f"The correct result is {rs['true_res']} ({rs['moves']} moves). — Deputy Arbiter")
        events.append(dict(type="corr_result", r=r, b=b, res=rs["true_res"], entry=eid))
    else:
        eid = entry(f"CORRECTION — R{r} B{b:02d}: the move count was entered as {rs['moves']}; the correct "
                    f"move count is {rs['true_moves']}. The result ({rs['res']}) is unchanged. — Chief Arbiter")
        events.append(dict(type="corr_moves", r=r, b=b, moves=rs["true_moves"], entry=eid))


# --------------------------------------------------------------------------------------
# Prompt rendering
# --------------------------------------------------------------------------------------
def regulations(N, R, threshold):
    return f"""TOURNAMENT REGULATIONS — VISTULA AUTUMN OPEN 2026

1. GENERAL
1.1 The tournament is a Swiss-system event of {R} rounds with {N} registered players. Each player has a start number P01..P{N:02d} (start numbers are listed in the log).
1.2 The officials are the Chief Arbiter, the Deputy Arbiter, the Tournament Director and a three-member Appeals Committee.
1.3 These Regulations may be amended during the event ONLY by an announcement of the Chief Arbiter recorded in the arbiter log. An announcement or notice recorded by any other official, including the Tournament Director, has no effect whatsoever on the scoring, pairing or ranking of the event, even if it is never contradicted.
1.4 An announcement of the Chief Arbiter may be withdrawn by a later log entry of the Chief Arbiter or by a decision of the Appeals Committee recorded in the log. A withdrawn announcement has no effect on any round, including rounds played while it was in force.
1.5 Scope of announcements. "With effect from round r" means the announcement applies to round r and to every later round. "For rounds after round r" means it applies to round r+1 and every later round, and NOT to round r. "Retroactively from round 1" means it applies to every round of the event, including rounds already played, whose results are re-scored accordingly. An announcement is applied according to its stated scope irrespective of when it was recorded.

2. SCORING OF GAMES
2.1 A won game scores 1 point, a drawn game 1/2 point (0.5), a lost game 0.
2.2 Results are recorded from White's point of view: "1-0" White won; "0-1" Black won; "1/2-1/2" draw; "+/-" White wins by forfeit; "-/+" Black wins by forfeit.
2.3 Each result entry for a played game records the number of moves completed, e.g. "(18 moves)".
2.4 A result entry is final unless it is corrected by a later log entry headed CORRECTION, recorded by the Chief Arbiter or the Deputy Arbiter. A correction replaces the corrected information (result, move count or pairing) for ALL purposes: points, tie-breaks, and the questions in Section 12. A correction may also state that entered information is unchanged.

3. FORFEITS
3.1 A game is a forfeit when it is decided without over-the-board play: (a) a player fails to appear; (b) a player arrives after the default time (Section 9); (c) a player has withdrawn (Section 11). The opponent receives a forfeit win worth 1 point; the defaulting player receives 0.
3.2 A forfeit win counts as a win for Reg. 5.5. A forfeit game counts as a paired game for Buchholz and Sonneborn-Berger (Section 5): the paired opponent's final total is used exactly as for a played game.
3.3 A game whose result is changed by a penalty under Section 10 is NOT a forfeit. A game scored 0-0 under Reg. 8.2 is NOT a forfeit.

4. BYES
4.1 If the number of players to be paired in a round is odd, a pairing-allocated bye is given to one player (named in the pairing list). A pairing-allocated bye scores 1 point.
4.2 A player admitted to the tournament after the round-1 pairings were published receives a half-point bye for round 1, scoring 1/2 point (0.5).
4.3 A bye of either kind is not a game: it is not a win for Reg. 5.5, it is not a forfeit, and the player had no opponent in that round.
4.4 Byes are never re-scored by an announcement unless the announcement explicitly names byes.

5. FINAL RANKING AND TIE-BREAKS
5.1 Players are ranked by total points (games plus byes), highest first.
5.2 Players with equal points are ordered by, in this sequence: (a) Buchholz (Reg. 5.3), higher first; (b) Sonneborn-Berger (Reg. 5.4), higher first; (c) direct encounter (Reg. 5.6); (d) number of wins (Reg. 5.5), higher first; (e) lower start number ranks higher.
5.3 Buchholz (BH) of a player is the sum, over all {R} rounds, of the following round contribution: if the player was paired against an opponent in that round (whether the game was played over the board, forfeited, or re-scored by a penalty or by Reg. 8.2), the contribution is that OPPONENT'S final total points (Reg. 5.1 total, including any byes the opponent received); if the player received a bye of either kind in that round, or was not paired in that round (Reg. 11.3), the contribution is the PLAYER'S OWN final total points.
5.4 Sonneborn-Berger (SB) of a player is the sum, over the rounds in which the player was paired against an opponent, of: the opponent's final total points if the player's final scored result in that game is 1; half of the opponent's final total points if it is 1/2; 0 if it is 0. Rounds with a bye and rounds in which the player was not paired contribute 0 to SB.
5.5 Number of wins is the number of paired games in which the player's final scored result is 1, including forfeit wins and wins awarded by penalty. Byes are not counted.
5.6 Direct encounter applies only when EXACTLY two players remain tied after (a) and (b) and they were paired against each other in the event: the one whose final scored result in that game is 1 ranks higher. If that game was drawn, scored 0-0, or the two were never paired together, proceed to (d). If three or more players remain tied after (a) and (b), skip (c) and proceed to (d).
5.7 All tie-break values are computed from the final scored results, after every correction, announcement and penalty has been applied. BH values are multiples of 0.5; SB values are multiples of 0.25.

6. PAIRINGS AND RESULT ENTRIES
6.1 The pairings of each round are published in the log ("PAIRINGS — ROUND r") with board numbers, the White player and the Black player. A game is identified in the log as "Rr Bnn" (round r, board nn).
6.2 The pairing list is authoritative for who played whom and with which colour, subject to corrections (Reg. 2.4).
6.3 Result entries are recorded per board as games finish; the order in which result entries appear carries no meaning.

7. PLAYER IDENTIFICATION
7.1 Pairing lists identify players by start number and full name ("Surname, Given name"). Other log entries may refer to a player by surname only. Surnames are spelled exactly as in the registration list; players with similar surnames are distinct players.

8. DRAWS
8.1 A game may be drawn by agreement at any stage, unless an announcement provides otherwise.
8.2 Where an announcement provides that a game drawn in fewer than M moves is scored 0-0, the move count of the result entry (as corrected) is decisive: "fewer than M moves" means a move count of M-1 or less; a game drawn in exactly M moves is scored 1/2-1/2. A game scored 0-0 remains a paired game: for BH the opponent's final total is used; for SB each player scored 0; it is neither a win nor a forfeit.

9. LATE ARRIVAL
9.1 The default time is 60 minutes: a player who has not arrived at the board within 60 minutes after the scheduled start loses the game by forfeit (Section 3).
9.2 A player who arrives within the default time plays the game; the arbiter records the minutes of lateness in the log. Lateness within the default time has no effect on the result unless an announcement provides otherwise.
9.3 Where an announcement reduces the default time to T minutes, every player recorded in the log as having arrived MORE THAN T minutes after the scheduled start is deemed to have lost that game by forfeit; a player recorded as arriving exactly T minutes late is not affected. Whatever result was entered for such a game is replaced by the forfeit result (+/- or -/+). A forfeit is not subject to any other re-scoring.

10. CONDUCT PENALTIES
10.1 If a player's mobile phone or other electronic device produces a sound in the playing hall during play, the arbiter records the incident against that player. Unless an announcement provides otherwise, the penalty is a warning and the result of the game is not affected.
10.2 Where an announcement provides that such an incident is penalised by loss of the game, the offending player's final scored result in that game is 0 and the opponent's is 1, replacing whatever result was entered. The opponent's 1 counts as a win (Reg. 5.5). The game is not a forfeit (Reg. 3.3).
10.3 If a game is subject both to a penalty under Reg. 10.2 and to short-draw scoring under Reg. 8.2, the penalty applies and Reg. 8.2 does not. If a game is a forfeit, no other re-scoring applies to it.

11. WITHDRAWAL
11.1 A player may withdraw by notifying the Chief Arbiter; the withdrawal is recorded in the log. Results already scored stand.
11.2 If the withdrawal is recorded after the pairings of a round have been published, the withdrawn player's game in that round is a forfeit (Section 3): the opponent receives a forfeit win.
11.3 The withdrawn player is not paired in any subsequent round. Such rounds are "unpaired rounds": they score 0 points, contribute the player's own final total to BH (Reg. 5.3) and 0 to SB (Reg. 5.4).
11.4 The withdrawn player remains in the final ranking with the points scored.

12. QUESTIONS TO BE ANSWERED WITH THE FINAL STANDINGS
Q1 champion: the player ranked 1st.
Q2 third_place: the player ranked 3rd.
Q3 total_forfeits: the number of GAMES (not players) whose final scored result is a forfeit (Section 3, including forfeits created by an announcement).
Q4 most_points_lost: define each player's FIRST-ENTRY total as the sum of the points implied by every result entry at its ORIGINALLY ENTERED value, attributed according to the pairing list AS ORIGINALLY PUBLISHED, plus byes as stated in the pairing lists — ignoring every CORRECTION entry, every announcement and every penalty (forfeits written in result entries count as entered). Q4 asks for the player whose official final total (Reg. 5.1) is below their first-entry total by the LARGEST amount. If two players are tied for the largest amount, the lower start number is the answer.
Q5 withdrawn_player_points: the official final total points of the player who withdrew.
"""


def render_prompt(T, log, players, N, R):
    body = []
    body.append("IMPORTANT: Solve without any tools — no Bash, no Python, no code execution, no files, no web search. "
                "Work it out yourself, from the material below only.\n")
    body.append("You are the arbiter's assistant at a chess open. Below are (A) the TOURNAMENT REGULATIONS and (B) the "
                "chronological ARBITER LOG of the whole event: registration, pairings, results, incidents, corrections "
                "and announcements. Some entries change the meaning of earlier entries (corrections, retroactive or "
                "scoped announcements, withdrawals); some entries carry no authority. Apply the Regulations exactly "
                "as written, as amended by valid announcements, to produce the OFFICIAL FINAL STANDINGS of all "
                f"{N} players and answer the five questions of Section 12. Every value is determined exactly by the "
                "log and the Regulations; do not use outside knowledge of chess tie-break conventions — the "
                "definitions in Section 5 are the only ones that apply.\n")
    body.append("=" * 100)
    body.append("(A) " + regulations(N, R, T["plan"]["threshold"]))
    body.append("=" * 100)
    body.append("(B) ARBITER LOG (entries are numbered in chronological order)\n")
    for i, e in enumerate(log, 1):
        body.append(f"[{i:03d}] {e}")
    body.append("\n" + "=" * 100)
    body.append("OUTPUT FORMAT\n")
    body.append("Respond with a single JSON object and nothing else — no prose, no markdown fences, no commentary before "
                "or after. It must match this schema exactly:\n")
    body.append('{\n'
                '  "standings": [\n'
                '    {"rank": 1, "player_id": "P07", "points": 7.5, "buchholz": 41.5, "sonneborn_berger": 36.25, "wins": 6},\n'
                f'    ... one object per player, all {N} players, ordered by rank 1..{N} ...\n'
                '  ],\n'
                '  "answers": {\n'
                '    "champion": "P07",\n'
                '    "third_place": "P02",\n'
                '    "total_forfeits": 4,\n'
                '    "most_points_lost": "P11",\n'
                '    "withdrawn_player_points": 3.0\n'
                '  }\n'
                '}\n')
    body.append("Rules for the output: player_id and the player answers are start numbers in the form \"Pnn\" exactly as "
                "in the registration list. points, buchholz and sonneborn_berger are decimal numbers (e.g. 4.5, 0.5, "
                "12.25); wins and total_forfeits are integers; rank is an integer 1..N with every rank used exactly "
                "once. Include every player, including the withdrawn player.")
    return "\n".join(body)


SCHEMA = {
    "type": "object",
    "properties": {
        "standings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "player_id": {"type": "string"},
                    "points": {"type": "number"},
                    "buchholz": {"type": "number"},
                    "sonneborn_berger": {"type": "number"},
                    "wins": {"type": "integer"},
                },
                "required": ["rank", "player_id", "points", "buchholz", "sonneborn_berger", "wins"],
            },
        },
        "answers": {
            "type": "object",
            "properties": {
                "champion": {"type": "string"},
                "third_place": {"type": "string"},
                "total_forfeits": {"type": "integer"},
                "most_points_lost": {"type": "string"},
                "withdrawn_player_points": {"type": "number"},
            },
            "required": ["champion", "third_place", "total_forfeits", "most_points_lost",
                         "withdrawn_player_points"],
        },
    },
    "required": ["standings", "answers"],
}


# --------------------------------------------------------------------------------------
# Build key + checks
# --------------------------------------------------------------------------------------
def _attempt(sub_seed, preset, strict=True):
    """One simulation attempt; raises AssertionError if a structural requirement fails."""
    T, log, players = simulate(sub_seed, preset)
    official = score_tournament(T)
    naive = score_tournament(T, NAIVE_OPTS)
    # Q4 must have a unique answer
    diffs = {p: naive["stats"][p]["points"] - official["stats"][p]["points"] for p in T["players"]}
    mx = max(diffs.values())
    top = [p for p in T["players"] if abs(diffs[p] - mx) < 1e-9]
    assert mx > 0, "no player lost points to errata"
    assert len(top) == 1 or not strict, f"Q4 tie: {top}"
    q4 = min(top, key=T["players"].index)   # Section 12 tie rule: lower start number
    # every single-trap variant must change points, BH or SB of someone
    variants = {}
    for name, ov in VARIANTS.items():
        v = score_tournament(T, ov)
        st = {p: [v["stats"][p]["points"], v["stats"][p]["buchholz"], v["stats"][p]["sonneborn_berger"],
                  v["stats"][p]["wins"], v["stats"][p]["rank"]] for p in T["players"]}
        variants[name] = dict(stats=st, forfeits=v["forfeits"], order=v["order"])
        same = all(abs(v["stats"][p][k] - official["stats"][p][k]) < 1e-9
                   for p in T["players"] for k in ("points", "buchholz", "sonneborn_berger"))
        assert not same, f"trap {name} does not change anything"
    # the naive first-entry baseline must differ materially
    nb_bh_diff = sum(1 for p in T["players"]
                     if abs(naive["stats"][p]["buchholz"] - official["stats"][p]["buchholz"]) > 1e-9)
    assert naive["order"][:3] != official["order"][:3], "naive top-3 equals official top-3"
    assert nb_bh_diff >= 6, f"naive BH differs for only {nb_bh_diff} players"
    # the champion must be decided (no exact 3-way tie at the top on all tiebreaks)
    return T, log, players, official, naive, diffs, q4, variants, nb_bh_diff


def build(seed, difficulty, out, quiet=False):
    preset = PRESETS[difficulty]
    N, R = preset["players"], preset["rounds"]
    last = None
    found = False
    # first pass insists on a unique Q4 answer; second pass accepts a tie (the prompt's tie rule decides)
    for strict in (True, False):
        for k in range(200):
            sub_seed = seed * 1000 + k
            try:
                T, log, players, official, naive, diffs, q4, variants, nb_bh_diff = \
                    _attempt(sub_seed, preset, strict)
                found = True
                break
            except AssertionError as e:
                last = e
        if found:
            break
    if not found:
        raise RuntimeError(f"no valid instance in 400 sub-seeds; last failure: {last}")

    standings = []
    for p in official["order"]:
        s = official["stats"][p]
        standings.append(dict(rank=s["rank"], player_id=p, points=s["points"], buchholz=s["buchholz"],
                              sonneborn_berger=s["sonneborn_berger"], wins=s["wins"]))
    key = dict(
        task="adversarial-3", seed=seed, sub_seed=sub_seed, difficulty=difficulty, players=N, rounds=R,
        player_names=T["player_names"],
        standings=standings,
        answers=dict(champion=official["order"][0], third_place=official["order"][2],
                     total_forfeits=official["forfeits"], most_points_lost=q4,
                     withdrawn_player_points=official["stats"][T["withdrawer"]]["points"]),
        naive=dict(stats={p: [naive["stats"][p]["points"], naive["stats"][p]["buchholz"],
                              naive["stats"][p]["sonneborn_berger"], naive["stats"][p]["wins"],
                              naive["stats"][p]["rank"]] for p in T["players"]},
                   order=naive["order"], forfeits=naive["forfeits"]),
        variants=variants,
        first_entry_diffs=diffs,
        structured=dict(players=T["players"], rounds=T["rounds"], events=T["events"], rounds_n=R,
                        withdrawer=T["withdrawer"], late_entrant=T["late_entrant"], plan=T["plan"]),
    )
    prompt = render_prompt(T, log, players, N, R)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "prompt.txt"), "w") as f:
        f.write(prompt)
    with open(os.path.join(out, "key.json"), "w") as f:
        json.dump(key, f, indent=1)
    with open(os.path.join(out, "schema.json"), "w") as f:
        json.dump(SCHEMA, f, indent=1)
    if not quiet:
        print(f"seed={seed} sub_seed={sub_seed} difficulty={difficulty} players={N} rounds={R} log_entries={len(log)} "
              f"prompt_bytes={len(prompt.encode())} forfeits={official['forfeits']} q4={q4} "
              f"naive_bh_diff={nb_bh_diff} naive_top3={naive['order'][:3]} official_top3={official['order'][:3]}")
    return key, prompt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--difficulty", default="hard", choices=list(PRESETS))
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    build(a.seed, a.difficulty, a.out, a.quiet)
