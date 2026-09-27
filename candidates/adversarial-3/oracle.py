#!/usr/bin/env python3
"""Independent oracle for adversarial-3.

Recomputes the final standings and the five answers FROM prompt.txt ALONE (parsing the rendered
arbiter log with regexes, and applying the regulations as this file's author read them) and compares
with key.json. Shares no code with generator.py: different data model (per-round records per player,
a mutable game table edited chronologically), comparison-sort ranking with an explicit comparator,
announcements recognised from their wording and signature.

    python oracle.py [--prompt prompt.txt] [--key key.json] [--quiet]
Exit status 0 iff every value matches the key exactly.
"""
import argparse
import functools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PTS = {"1-0": (1.0, 0.0), "0-1": (0.0, 1.0), "1/2-1/2": (0.5, 0.5), "+/-": (1.0, 0.0), "-/+": (0.0, 1.0)}


def parse_log(prompt):
    log_txt = prompt.split("(B) ARBITER LOG", 1)[1].split("\nOUTPUT FORMAT", 1)[0]
    parts = re.split(r"^\[(\d{3})\] ", log_txt, flags=re.M)
    entries = []
    for i in range(1, len(parts), 2):
        entries.append((int(parts[i]), parts[i + 1].rstrip("\n").rstrip("=").rstrip()))
    return entries


def compute(prompt):
    entries = parse_log(prompt)
    names = {}
    pairings = {}      # round -> {board: [white, black]}  (as published, later corrected in place)
    pub_pairings = {}  # as originally published (for Q4)
    byes = {}          # round -> {pid: 'half'|'full'}
    entered = {}       # (r,b) -> (res, moves)   first-entered value
    current = {}       # (r,b) -> [res, moves]   after corrections
    late = {}          # (r,b) -> {color: minutes}
    phone = []         # (r, board or None, color or None, surname or None)
    anns = []          # dicts: kind, scope, params, active, by
    rounds_seen = 0
    for num, text in entries:
        first = text.split("\n")[0]
        signed_ca = text.rstrip().endswith("— Chief Arbiter")
        signed_da = text.rstrip().endswith("— Deputy Arbiter")
        if first.startswith("REGISTRATION CLOSED"):
            for m in re.finditer(r"^\s*(P\d\d) (.+)$", text, flags=re.M):
                names[m.group(1)] = m.group(2).strip()
        elif first.startswith("Late admission"):
            m = re.search(r"Late admission \(Reg\. 4\.2\): (P\d\d) ([^()]+?) was admitted", first)
            names[m.group(1)] = m.group(2).strip()
        elif first.startswith("PAIRINGS — ROUND"):
            r = int(re.search(r"ROUND (\d+)", first).group(1))
            rounds_seen = max(rounds_seen, r)
            pairings[r], byes[r] = {}, {}
            for m in re.finditer(r"B(\d+): (P\d\d) .*? \(White\) — (P\d\d) .*? \(Black\)", text):
                pairings[r][int(m.group(1))] = [m.group(2), m.group(3)]
            for m in re.finditer(r"Half-point bye[^:]*: (P\d\d)", text):
                byes[r][m.group(1)] = "half"
            for m in re.finditer(r"Pairing-allocated bye[^:]*: (P\d\d)", text):
                byes[r][m.group(1)] = "full"
            pub_pairings[r] = {b: list(v) for b, v in pairings[r].items()}
        elif re.match(r"R(\d+) B(\d+): (1-0|0-1|1/2-1/2|\+/-|-/\+)", first):
            m = re.match(r"R(\d+) B(\d+): (1-0|0-1|1/2-1/2|\+/-|-/\+)(?: \((\d+) moves\))?", first)
            k = (int(m.group(1)), int(m.group(2)))
            mv = int(m.group(4)) if m.group(4) else None
            entered[k] = (m.group(3), mv)
            current[k] = [m.group(3), mv]
        elif re.match(r"R(\d+) B(\d+): (White|Black) \((\S+)\) arrived (\d+) minutes", first):
            m = re.match(r"R(\d+) B(\d+): (White|Black) \((\S+)\) arrived (\d+) minutes", first)
            late.setdefault((int(m.group(1)), int(m.group(2))), {})[m.group(3)[0].lower()] = int(m.group(5))
        elif re.match(r"R(\d+) B(\d+): the mobile phone of (White|Black)", first):
            m = re.match(r"R(\d+) B(\d+): the mobile phone of (White|Black)", first)
            phone.append((int(m.group(1)), int(m.group(2)), m.group(3)[0].lower(), None))
        elif first.startswith("The mobile phone of"):
            m = re.match(r"The mobile phone of (\S+) sounded .* in round (\d+)", first)
            phone.append((int(m.group(2)), None, None, m.group(1)))
        elif first.startswith("CORRECTION"):
            assert signed_ca or signed_da, f"correction by unknown official: {first}"
            m = re.match(r"CORRECTION — R(\d+) B(\d+): .*The correct result is (1-0|0-1|1/2-1/2)", first)
            if m:
                current[(int(m.group(1)), int(m.group(2)))][0] = m.group(3)
                continue
            m = re.match(r"CORRECTION — R(\d+) B(\d+): the move count was entered as \d+; the correct move count is (\d+)", first)
            if m:
                current[(int(m.group(1)), int(m.group(2)))][1] = int(m.group(3))
                continue
            m = re.match(r"CORRECTION — Round (\d+) pairing list .*?White on B(\d+) was (P\d\d).*?White on B(\d+) was (P\d\d)", first)
            if m:
                r = int(m.group(1))
                pairings[r][int(m.group(2))][0] = m.group(3)
                pairings[r][int(m.group(4))][0] = m.group(5)
                continue
            raise ValueError("unparsed correction: " + first)
        elif re.match(r"ANNOUNCEMENT (\d+) is withdrawn", first):
            n = int(re.match(r"ANNOUNCEMENT (\d+) is withdrawn", first).group(1))
            for a in anns:
                if a["n"] == n:
                    a["active"] = False
        elif first.startswith("ANNOUNCEMENT") or "NOTICE" in first:
            by = "CA" if signed_ca else "other"
            n = int(re.match(r"ANNOUNCEMENT (\d+)", first).group(1)) if first.startswith("ANNOUNCEMENT") else None
            # scope
            if re.search(r"With effect from round (\d+)", text):
                r0 = int(re.search(r"With effect from round (\d+)", text).group(1))
                scope = lambda r, r0=r0: r >= r0
            elif re.search(r"For rounds after round (\d+)", text):
                r0 = int(re.search(r"For rounds after round (\d+)", text).group(1))
                scope = lambda r, r0=r0: r > r0
            elif re.search(r"[Rr]etroactively from round 1", text):
                scope = lambda r: True
            elif re.search(r"suspended for rounds (\d+) and (\d+)", text):
                mm = re.search(r"suspended for rounds (\d+) and (\d+)", text)
                rs = {int(mm.group(1)), int(mm.group(2))}
                scope = lambda r, rs=rs: r in rs
            else:
                raise ValueError("no scope: " + first)
            # kind
            if re.search(r"drawn in fewer than (\d+) moves shall be scored 0-0", text):
                kind, param = "short_draw", int(re.search(r"fewer than (\d+) moves", text).group(1))
            elif re.search(r"Announcement 1 \(short-draw scoring\) shall apply retroactively", text):
                kind, param = "short_draw", int(re.search(r"fewer than (\d+) moves", text).group(1))
            elif re.search(r"penalised by loss of the game", text):
                kind, param = "phone_loss", None
            elif re.search(r"default time .* reduced from \d+ minutes to (\d+) minutes", text):
                kind, param = "late_forfeit", int(re.search(r"to (\d+) minutes", text).group(1))
            elif re.search(r"short-draw scoring .* is suspended", text):
                kind, param = "suspend", None
            else:
                raise ValueError("unknown announcement: " + first)
            anns.append(dict(n=n, by=by, kind=kind, param=param, scope=scope, active=True))
        # everything else is noise / withdrawal notice (the forfeit is in the result entry, and the
        # unpaired rounds are visible from the pairing lists)
    R = rounds_seen
    players = sorted(names)
    start = {p: i for i, p in enumerate(players)}

    def valid(a):
        return a["by"] == "CA" and a["active"]

    # resolve by-name phone incidents using corrected pairings
    sur2id = {}
    for pid, full in names.items():
        sur2id[full.split(",")[0].strip()] = pid
    phone_at = {}
    for r, b, color, sur in phone:
        if b is None:
            pid = sur2id[sur]
            for bb, (w, bl) in pairings[r].items():
                if pid == w:
                    b, color = bb, "w"
                elif pid == bl:
                    b, color = bb, "b"
        phone_at[(r, b)] = color

    # final scoring of every game
    def final(r, b, res, moves, use_ann=True):
        pw, pb = PTS[res]
        forfeit = res in ("+/-", "-/+")
        if forfeit or not use_ann:
            return pw, pb, forfeit
        for a in anns:
            if a["kind"] == "late_forfeit" and valid(a) and a["scope"](r):
                for color, mins in late.get((r, b), {}).items():
                    if mins > a["param"]:
                        return ((0.0, 1.0) if color == "w" else (1.0, 0.0)) + (True,)
        for a in anns:
            if a["kind"] == "phone_loss" and valid(a) and a["scope"](r) and (r, b) in phone_at:
                c = phone_at[(r, b)]
                return ((0.0, 1.0) if c == "w" else (1.0, 0.0)) + (False,)
        if res == "1/2-1/2":
            if any(a["kind"] == "suspend" and valid(a) and a["scope"](r) for a in anns):
                return pw, pb, False
            for a in anns:
                if a["kind"] == "short_draw" and valid(a) and a["scope"](r) and moves < a["param"]:
                    return 0.0, 0.0, False
        return pw, pb, False

    def tally(pair_src, res_src, use_ann):
        rec = {p: {} for p in players}     # p -> r -> (opp, my, forfeit)
        total = {p: 0.0 for p in players}
        nff = 0
        for r in range(1, R + 1):
            for b, (w, bl) in pair_src[r].items():
                res, mv = res_src[(r, b)]
                pw, pb, ff = final(r, b, res, mv, use_ann)
                nff += ff
                rec[w][r] = (bl, pw, ff)
                rec[bl][r] = (w, pb, ff)
                total[w] += pw
                total[bl] += pb
            for pid, kind in byes[r].items():
                total[pid] += 1.0 if kind == "full" else 0.5
        return rec, total, nff

    rec, total, nforf = tally(pairings, {k: tuple(v) for k, v in current.items()}, True)
    bh, sb, wins = {}, {}, {}
    for p in players:
        bh[p] = sum(total[rec[p][r][0]] if r in rec[p] else total[p] for r in range(1, R + 1))
        sb[p] = sum(total[opp] * my for opp, my, _ in rec[p].values())
        wins[p] = sum(1 for opp, my, _ in rec[p].values() if my == 1.0)

    # ranking via explicit comparator (5.2), with the "exactly two tied" check done on groups
    grp = {}
    for p in players:
        grp.setdefault((total[p], bh[p], sb[p]), []).append(p)

    def cmp(a, c):
        ka, kc = (total[a], bh[a], sb[a]), (total[c], bh[c], sb[c])
        if ka != kc:
            return -1 if ka > kc else 1
        if len(grp[ka]) == 2:
            for r, (opp, my, _) in rec[a].items():
                if opp == c:
                    if my == 1.0:
                        return -1
                    if my == 0.0 and rec[c][r][1] == 1.0:
                        return 1
        if wins[a] != wins[c]:
            return -1 if wins[a] > wins[c] else 1
        return -1 if start[a] < start[c] else 1

    order = sorted(players, key=functools.cmp_to_key(cmp))
    standings = [dict(rank=i + 1, player_id=p, points=total[p], buchholz=bh[p],
                      sonneborn_berger=sb[p], wins=wins[p]) for i, p in enumerate(order)]
    # Q4: first-entry tally
    _, naive_total, _ = tally(pub_pairings, entered, False)
    loss = {p: naive_total[p] - total[p] for p in players}
    mx = max(loss.values())
    q4 = min((p for p in players if loss[p] == mx), key=lambda p: start[p])
    # withdrawn player: paired in some round, absent from a later round's pairings and byes
    withdrawn = None
    for p in players:
        for r in range(2, R + 1):
            paired = any(p in v for v in pairings[r].values()) or p in byes[r]
            if not paired and any(p in v for v in pairings[r - 1].values()):
                withdrawn = p
    answers = dict(champion=order[0], third_place=order[2], total_forfeits=nforf,
                   most_points_lost=q4, withdrawn_player_points=total[withdrawn])
    return dict(standings=standings, answers=answers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=os.path.join(HERE, "prompt.txt"))
    ap.add_argument("--key", default=os.path.join(HERE, "key.json"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    got = compute(open(a.prompt).read())
    key = json.load(open(a.key))
    ok = True
    for g, k in zip(got["standings"], key["standings"]):
        for f in ("rank", "player_id", "points", "buchholz", "sonneborn_berger", "wins"):
            if g[f] != k[f]:
                ok = False
                print(f"MISMATCH standings {k['player_id']} {f}: oracle={g[f]} key={k[f]}")
    if len(got["standings"]) != len(key["standings"]):
        ok = False
        print("MISMATCH: player count")
    for q, v in key["answers"].items():
        if got["answers"].get(q) != v:
            ok = False
            print(f"MISMATCH answer {q}: oracle={got['answers'].get(q)} key={v}")
    if not a.quiet:
        print("ORACLE AGREES WITH KEY" if ok else "ORACLE DISAGREES WITH KEY")
        print(json.dumps(got["answers"]))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
