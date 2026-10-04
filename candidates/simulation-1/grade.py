#!/usr/bin/env python3
"""Grader for candidate simulation-1 (Quarry Duel). Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in key.json next to it.

Scoring (1000 points at the default `hard` preset: 200 turns, resync after turn 50,
19 checkpoints):
  plays        2 points per turn, awarded as the LONGEST CORRECT PREFIX of two segments
               graded independently: turns 1..R and turns R+1..N, where R is the resync
               turn whose full state is printed in the prompt (key.json: resync_turn).
               A slip at turn 37 therefore costs the rest of segment 1 only; the second
               segment is earned from the printed state.            200 turns -> 400
  checkpoints  every checkpoint x 2 players x 12 points: position 2, coins 3, hand_size 1,
               hand_total 3, stockpile total 1, exact 4-suit stockpile vector 2; each
               field independently, exact match.                    19 x 24   -> 456
  final block  p1_score, p2_score, total_captures, total_tolls_paid, discard_pile_size,
               deck_remaining: 24 each, exact match. `winner` is implied by the two
               scores and is NOT scored (it is a coin flip across seeds by construction
               and was a free 2 points before); it is reported in detail.   -> 144
detail.first_divergence_turn is the first checkpoint with any miss; detail.plays carries
the per-segment prefix lengths and first wrong turn; detail.floors publishes what a
constant guess earns against this key (constant_guess_floor: zeros + hand_size 4;
best_constant_floor: the best per-field constant, i.e. the ceiling of any lazy answer).

Tolerances (all verified by the self-test in README): JSON embedded in prose or fences
(the balanced object that contains both `checkpoints` and `final` is preferred);
`answer`/`result` wrappers; missing suit keys count as 0; a stockpile given as a 4-list
in Ore, Wood, Grain, Gem order; players nested under `players`/`state` (dict or 2-list);
checkpoints as a dict keyed by turn; positional fallback when turn labels do not match;
plays as strings ("Grain-4", "grain 4"), [suit, value] pairs, {suit, value} or
{turn, card} objects, or a dict keyed by turn; alternate key spellings throughout.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tasks"))
from _common import load_answer, emit, numeq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TASK_ID = "S1"
SUITS = ["Ore", "Wood", "Grain", "Gem"]
PLAY_W = 2
PLAYER_FIELDS = {"position": 2, "coins": 3, "hand_size": 1, "hand_total": 3}
STOCK_TOTAL_W, STOCK_VECTOR_W = 1, 2
FINAL_WEIGHTS = {"p1_score": 24, "p2_score": 24, "total_captures": 24,
                 "total_tolls_paid": 24, "discard_pile_size": 24, "deck_remaining": 24}
FIELD_ALIASES = {
    "position": ["position", "pos", "space", "location"],
    "coins": ["coins", "coin", "money", "gold"],
    "hand_size": ["hand_size", "handsize", "hand size", "hand_count", "cards_in_hand", "hand_cards",
                  "hand_len"],
    "hand_total": ["hand_total", "handtotal", "hand total", "hand_sum", "hand_value", "hand_values"],
    "stockpile": ["stockpile", "stock", "stockpiles", "stockpile_counts", "banked"],
    "checkpoints": ["checkpoints", "checkpoint", "check_points", "states"],
    "final": ["final", "final_block", "finalblock", "final_state", "end_state", "end_of_game",
              "game_end", "endgame"],
    "plays": ["plays", "played", "played_cards", "play_log", "log", "cards_played", "moves", "turns"],
    "winner": ["winner"],
    "p1_score": ["p1_score", "p1score", "p1 score", "score_p1", "player1_score"],
    "p2_score": ["p2_score", "p2score", "p2 score", "score_p2", "player2_score"],
    "total_captures": ["total_captures", "totalcaptures", "captures", "total captures"],
    "total_tolls_paid": ["total_tolls_paid", "totaltollspaid", "tolls_paid", "tolls", "total_tolls",
                         "total tolls paid"],
    "discard_pile_size": ["discard_pile_size", "discardpilesize", "discard_size", "discard_pile",
                          "discard", "discard pile size"],
    "deck_remaining": ["deck_remaining", "deckremaining", "deck_size", "deck", "deck remaining",
                       "cards_in_deck"],
}
CARD_RE = re.compile(r"(ore|wood|grain|gem)\s*[-_ :/]?\s*([1-9])\b", re.I)
CARD_RE2 = re.compile(r"\b([1-9])\s*(?:of\s*)?[-_ :/]?\s*(ore|wood|grain|gem)", re.I)


# ---------------------------------------------------------------- tolerant parsing
def _balanced_objects(text):
    """Yield every balanced, string-aware {...} span that parses as a JSON object."""
    starts = [m.start() for m in re.finditer(r"\{", text)]
    seen_end = -1
    for start in starts:
        if start < seen_end:          # nested inside an object we already returned
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except Exception:
                        break
                    if isinstance(obj, dict):
                        seen_end = i + 1
                        yield obj
                    break


def has_answer_keys(obj):
    keys = {nk(k) for k in obj}
    return (bool(keys & {nk(a) for a in FIELD_ALIASES["checkpoints"]})
            and bool(keys & {nk(a) for a in FIELD_ALIASES["final"]}))


def looks_like_answer(obj):
    if not isinstance(obj, dict):
        return False
    return (isinstance(geta(obj, "checkpoints"), (list, dict))
            or isinstance(geta(obj, "final"), dict)
            or isinstance(geta(obj, "plays"), (list, dict)))


def extract_json(text):
    """Prefer the balanced object that carries both checkpoints and final (largest if several,
    which also covers a corrected re-emission); otherwise the largest parseable object."""
    text = re.sub(r"```(?:json)?", "", text)
    objs = list(_balanced_objects(text))
    if not objs:
        return {}
    good = [o for o in objs if has_answer_keys(o)]
    pool = good or objs
    return max(pool, key=lambda o: len(json.dumps(o)))


def nk(k):
    """Normalised key: lowercase alphanumerics only, so 'Hand Size' == 'hand_size' == 'handsize'."""
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def lower_keys(d):
    """Normalised-key view of a dict (first spelling wins on collision)."""
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.setdefault(nk(k), v)
    return out


def getk(d, *names, default=None):
    d = lower_keys(d)
    for n in names:
        if nk(n) in d:
            return d[nk(n)]
    return default


def geta(d, field, default=None):
    return getk(d, *FIELD_ALIASES[field], default=default)


def unwrap(ans):
    """Descend through `answer`/`result`-style wrappers until the answer keys appear."""
    for _ in range(3):
        if not isinstance(ans, dict) or looks_like_answer(ans):
            break
        inner = [v for v in ans.values() if looks_like_answer(v)]
        if not inner:
            inner = [v for v in ans.values() if isinstance(v, dict)]
            if len(inner) != 1:
                break
        ans = max(inner, key=lambda o: len(json.dumps(o)))
    return ans if isinstance(ans, dict) else {}


def to_int(x):
    try:
        if isinstance(x, bool):
            return None
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None


def norm_card(x):
    """Canonical 'Suit-v' for any reasonable card spelling; None if unrecognisable."""
    if x is None:
        return None
    if isinstance(x, dict):
        d = lower_keys(x)
        for k in ("card", "played", "play", "played_card"):
            if k in d:
                return norm_card(d[k])
        suit = d.get("suit")
        val = d.get("value", d.get("val", d.get("rank")))
        if suit is not None and val is not None:
            return norm_card(f"{suit}-{val}")
        return None
    if isinstance(x, (list, tuple)):
        if len(x) == 2:
            return norm_card(f"{x[0]}-{x[1]}")
        return None
    s = str(x)
    m = CARD_RE.search(s) or None
    if m:
        return f"{m.group(1).capitalize()}-{m.group(2)}"
    m = CARD_RE2.search(s)
    if m:
        return f"{m.group(2).capitalize()}-{m.group(1)}"
    return None


def turn_of(x):
    """Turn label from a dict entry or a dict key like 'turn_20' / 't20' / '20'."""
    if isinstance(x, dict):
        t = getk(x, "turn", "after_turn", "t", "turn_number")
        return to_int(t)
    m = re.search(r"(\d+)", str(x))
    return int(m.group(1)) if m else None


def parse_plays(ans, n_turns):
    raw = geta(ans, "plays")
    out = [None] * n_turns
    if raw is None:
        return out, 0
    if isinstance(raw, str):
        raw = [t for t in re.split(r"[,\n;]+", raw) if t.strip()]
    entries = []                     # (turn or None, card)
    if isinstance(raw, dict):
        for k, v in raw.items():
            entries.append((turn_of(k), norm_card(v)))
    elif isinstance(raw, list):
        labelled = sum(1 for e in raw if isinstance(e, dict) and turn_of(e) is not None)
        for i, e in enumerate(raw):
            t = turn_of(e) if isinstance(e, dict) and labelled == len(raw) else None
            entries.append((t, norm_card(e)))
    else:
        return out, 0
    if entries and all(t is not None for t, _ in entries):
        for t, c in entries:
            if 1 <= t <= n_turns and out[t - 1] is None:
                out[t - 1] = c
    else:
        for i, (_, c) in enumerate(entries[:n_turns]):
            out[i] = c
    return out, len(entries)


def parse_checkpoints(ans):
    """Return a list of (turn label or None, checkpoint dict)."""
    raw = geta(ans, "checkpoints")
    items = []
    if isinstance(raw, dict):
        # dict keyed by turn, or a single checkpoint object mistakenly not wrapped in a list
        if getk(raw, "p1", "player1", "players", "state") is not None:
            items.append((turn_of(raw), raw))
        else:
            for k, v in raw.items():
                if isinstance(v, dict):
                    items.append((turn_of(v) if turn_of(v) is not None else turn_of(k), v))
    elif isinstance(raw, list):
        for e in raw:
            if isinstance(e, dict):
                items.append((turn_of(e), e))
    return items


def player_block(cp, idx):
    """Find player idx (1 or 2) under any common spelling or one nesting level."""
    names = (f"P{idx}", f"player{idx}", f"player_{idx}", f"player {idx}", f"p{idx}", f"player-{idx}")

    def body(d):
        # {"P1": {"state": {...}}} style: descend one level if the fields are not here
        if isinstance(d, dict) and geta(d, "position") is None and geta(d, "coins") is None:
            inner = [v for v in d.values() if isinstance(v, dict)
                     and (geta(v, "position") is not None or geta(v, "coins") is not None)]
            if len(inner) == 1:
                return inner[0]
        return d
    direct = getk(cp, *names)
    if isinstance(direct, dict):
        return body(direct)
    for container in ("players", "state", "player_states", "player_state", "states"):
        inner = getk(cp, container)
        if isinstance(inner, dict):
            d = getk(inner, *names)
            if isinstance(d, dict):
                return body(d)
        if isinstance(inner, list) and len(inner) >= idx and isinstance(inner[idx - 1], dict):
            return body(inner[idx - 1])
    return {}


def stock_vector(gp):
    """[Ore, Wood, Grain, Gem] counts, missing suits as 0; None if no stockpile was given."""
    st = geta(gp, "stockpile")
    if isinstance(st, dict):
        d = lower_keys(st)
        vec = []
        for s in SUITS:
            v = d.get(nk(s), 0)
            vec.append(to_int(v) if v is not None else 0)
        return vec
    if isinstance(st, list):
        if len(st) == 4 and all(not isinstance(v, (dict, list)) for v in st):
            return [to_int(v) for v in st]
        if all(isinstance(v, dict) for v in st):   # [{"suit": "Ore", "count": 1}, ...]
            counts = {s: 0 for s in SUITS}
            for v in st:
                d = lower_keys(v)
                suit = str(d.get("suit", "")).capitalize()
                if suit in counts:
                    counts[suit] = to_int(d.get("count", d.get("cards", d.get("n", 0)))) or 0
            return [counts[s] for s in SUITS]
    if isinstance(st, (int, float)) and not isinstance(st, bool):
        return None
    return None


# ---------------------------------------------------------------- grading
def _grade(ans, key, want_floors=True):
    n_turns = len(key["plays"])
    resync = key.get("resync_turn") or n_turns
    detail = {"misses": {}, "checkpoints_found": 0, "first_divergence_turn": None,
              "per_checkpoint": {}, "plays": {}}
    score = 0
    total = 0

    # ---- plays: longest correct prefix, per segment
    got_plays, n_reported = parse_plays(ans, n_turns)
    segs = [(1, resync), (resync + 1, n_turns)] if resync < n_turns else [(1, n_turns)]
    pointwise = 0
    for si, (a, b) in enumerate(segs, 1):
        prefix = 0
        first_wrong = None
        for t in range(a, b + 1):
            hit = got_plays[t - 1] is not None and got_plays[t - 1] == key["plays"][t - 1]
            pointwise += hit
            if hit and first_wrong is None:
                prefix += 1
            elif first_wrong is None:
                first_wrong = t
        total += PLAY_W * (b - a + 1)
        score += PLAY_W * prefix
        detail["plays"][f"segment{si}"] = {"turns": f"{a}-{b}", "correct_prefix": prefix,
                                          "first_wrong_turn": first_wrong,
                                          "points": f"{PLAY_W * prefix}/{PLAY_W * (b - a + 1)}"}
    detail["plays"]["entries_reported"] = n_reported
    detail["plays"]["pointwise_matches"] = f"{pointwise}/{n_turns}"

    # ---- checkpoints: match by turn label, positional fallback for the rest
    items = parse_checkpoints(ans)
    key_turns = [kcp["turn"] for kcp in key["checkpoints"]]
    by_turn = {}
    unlabelled = []
    matched = sum(1 for t, _ in items if t in key_turns)
    if items and matched >= max(1, len(items) // 2):
        # labels are usable: match by turn, positional fill for the unmatched remainder
        for t, cp in items:
            if t in key_turns and t not in by_turn:
                by_turn[t] = cp
            else:
                unlabelled.append(cp)
    else:
        # labels absent or mostly wrong (e.g. checkpoints numbered 1..19): positional
        unlabelled = [cp for _, cp in items]
    detail["checkpoint_matching"] = f"{matched}/{len(items)} turn labels matched" + \
        ("" if by_turn else "; positional")
    for i, kcp in enumerate(key["checkpoints"]):
        turn = kcp["turn"]
        gcp = by_turn.get(turn)
        if gcp is None and unlabelled:
            gcp = unlabelled.pop(0)
        gcp = gcp or {}
        if gcp:
            detail["checkpoints_found"] += 1
        cp_ok = 0
        cp_total = 0
        for p in (1, 2):
            kp = kcp[f"P{p}"]
            gp = player_block(gcp, p)
            for f, w in PLAYER_FIELDS.items():
                total += w
                cp_total += w
                g = geta(gp, f)
                if numeq(g, kp[f], tol=0):
                    score += w
                    cp_ok += w
                else:
                    detail["misses"][f"t{turn}.P{p}.{f}"] = {"want": kp[f], "got": g}
            gvec = stock_vector(gp)
            kvec = [kp["stockpile"][s] for s in SUITS]
            total += STOCK_TOTAL_W + STOCK_VECTOR_W
            cp_total += STOCK_TOTAL_W + STOCK_VECTOR_W
            gtot = sum(gvec) if gvec is not None and all(v is not None for v in gvec) else None
            if gtot is not None and gtot == sum(kvec):
                score += STOCK_TOTAL_W
                cp_ok += STOCK_TOTAL_W
            else:
                detail["misses"][f"t{turn}.P{p}.stockpile_total"] = {"want": sum(kvec), "got": gtot}
            if gvec is not None and gvec == kvec:
                score += STOCK_VECTOR_W
                cp_ok += STOCK_VECTOR_W
            else:
                detail["misses"][f"t{turn}.P{p}.stockpile"] = {"want": kp["stockpile"], "got": gvec}
        detail["per_checkpoint"][str(turn)] = f"{cp_ok}/{cp_total}"
        if cp_ok < cp_total and detail["first_divergence_turn"] is None:
            detail["first_divergence_turn"] = turn

    # ---- final block
    gfin = geta(ans, "final") or {}
    if not isinstance(gfin, dict):
        gfin = {}
    for f, w in FINAL_WEIGHTS.items():
        total += w
        want = key["final"][f]
        g = geta(gfin, f)
        if numeq(g, want, tol=0):
            score += w
        else:
            detail["misses"][f"final.{f}"] = {"want": want, "got": g}
    gw = geta(gfin, "winner")
    detail["winner"] = {"reported": gw, "want": key["final"]["winner"], "scored": False,
                        "correct": (str(gw).strip().lower().replace("player", "p").replace(" ", "")
                                    == str(key["final"]["winner"]).lower())}

    if want_floors:
        detail["floors"] = floors(key)
    return score, total, detail


def floors(key):
    """What lazy answers earn against this key, for calibration."""
    zeros = {s: 0 for s in SUITS}
    naive_player = {"position": 0, "coins": 0, "hand_size": 4, "hand_total": 0, "stockpile": zeros}
    naive = {"plays": [], "final": {f: 0 for f in FINAL_WEIGHTS},
             "checkpoints": [{"turn": c["turn"], "P1": naive_player, "P2": naive_player}
                             for c in key["checkpoints"]]}
    naive_score, total, _ = _grade(naive, key, want_floors=False)
    # best constant per field: the modal key value of every checkpoint field, and the
    # longest run of one repeated card at the start of each play segment; final block 0.
    cells = [c[f"P{p}"] for c in key["checkpoints"] for p in (1, 2)]

    def mode_count(vals):
        return max(vals.count(v) for v in set(vals)) if vals else 0
    best = 0
    for f, w in PLAYER_FIELDS.items():
        best += w * mode_count([c[f] for c in cells])
    best += STOCK_TOTAL_W * mode_count([sum(c["stockpile"].values()) for c in cells])
    best += STOCK_VECTOR_W * mode_count([json.dumps(c["stockpile"], sort_keys=True) for c in cells])
    n = len(key["plays"])
    resync = key.get("resync_turn") or n
    for a, b in ([(1, resync), (resync + 1, n)] if resync < n else [(1, n)]):
        seg = key["plays"][a - 1:b]
        run = 0
        while run < len(seg) and seg[run] == seg[0]:
            run += 1
        best += PLAY_W * run
    return {"constant_guess_floor": naive_score, "best_constant_floor": best, "total": total,
            "note": "constant_guess_floor = zeros with hand_size 4; best_constant_floor = modal "
                    "value of every checkpoint field plus the best repeated card, final block 0"}


def grade(ans):
    if "_text" in ans:
        ans = extract_json(ans["_text"])
    ans = unwrap(ans)
    key = json.load(open(os.path.join(HERE, "key.json")))
    return _grade(ans, key)


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit(TASK_ID, s, t, d)
