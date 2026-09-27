#!/usr/bin/env python3
"""Generator for candidate task deduction-3 ("Crib Slide").

Builds a synthetic A-Z shipping manifest, encrypts it with a periodic Vigenere
key of unknown period, chooses a few crib labels (each with a coarse position
window) and 10 extraction questions, and verifies by brute force that the
(period, key) pair is the UNIQUE solution consistent with the cribs within the
stated period range and windows.

Usage:
    python generator.py --seed 20260926 --difficulty hard [--out DIR]

Writes prompt.txt, key.json and schema.json into --out (default: this directory).
Deterministic given (--seed, --difficulty).  Knobs behind the presets can be
overridden individually (--length, --pmin, --pmax, --cribs, --window).
"""
import argparse
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
A = ord("A")

# ----------------------------------------------------------------------------
# Difficulty presets (the knob).  window = width of the position hint in letters
# (0 = no hint, the crib may be anywhere).  crib_maxlen "short" forces every
# crib to be shorter than the smallest admissible period, so no single crib can
# reveal the whole key or the period on its own: cross-crib consistency is the
# only way in.
# ----------------------------------------------------------------------------
PRESETS = {
    "easy":   dict(length=700,  pmin=7,  pmax=9,  cribs=5, window=10, crib_maxlen="any"),
    "medium": dict(length=1000, pmin=8,  pmax=11, cribs=4, window=25, crib_maxlen="any"),
    "hard":   dict(length=1300, pmin=10, pmax=14, cribs=4, window=40, crib_maxlen="short"),
    "max":    dict(length=2000, pmin=12, pmax=17, cribs=3, window=0,  crib_maxlen="short"),
}

SEP = "STOP"

# ----------------------------------------------------------------------------
# Numbers in words (A-Z only, American style, no AND, no hyphens)
# ----------------------------------------------------------------------------
ONES = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE",
        "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN",
        "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
TENS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]
DIGITS = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]


def words_under_1000(n):
    out = ""
    if n >= 100:
        out += ONES[n // 100] + "HUNDRED"
        n %= 100
    if n >= 20:
        out += TENS[n // 10]
        n %= 10
    out += ONES[n]
    return out


def num_words(n):
    assert 0 < n < 1_000_000
    out = ""
    if n >= 1000:
        out += words_under_1000(n // 1000) + "THOUSAND"
        n %= 1000
    out += words_under_1000(n)
    return out


# ----------------------------------------------------------------------------
# Pseudo-English proper nouns (no recall possible)
# ----------------------------------------------------------------------------
ONSETS = ["B", "BR", "C", "CL", "CR", "D", "DR", "F", "FL", "FR", "G", "GR", "H", "J",
          "K", "KR", "L", "M", "N", "P", "PR", "R", "S", "SK", "SL", "SP", "T", "TR",
          "V", "W", "Z", "TH", "SH", "CH", "QU"]
VOWELS = ["A", "E", "I", "O", "U", "A", "E", "O", "AI", "EA", "OU", "EE", "OO"]
CODAS = ["", "", "", "N", "R", "L", "S", "T", "D", "M", "K", "ND", "RN", "LD", "RT",
         "NT", "SK", "X", "NG"]
SUFFIX = ["TRADING", "IMPORTS", "EXPORTS", "LOGISTICS", "HOLDINGS", "BROTHERS",
          "MARINE", "FOODS", "INDUSTRIES", "AGENCIES", "AND SONS", "COMPANY",
          "PARTNERS", "SUPPLY", "MILLS", "TEXTILES"]
CITY_END = ["", "", "PORT", "HAVEN", "BAY", "MOUTH", "BURG", "TON", "VILLE", "CREEK"]
COMMODITIES = ["CANNED PEACHES", "COTTON YARN", "CERAMIC TILES", "FROZEN SHRIMP",
               "COPPER WIRE", "RUBBER GLOVES", "OLIVE OIL", "STEEL BOLTS",
               "PAPER PULP", "GLASS BEADS", "LEATHER BELTS", "WOODEN CRATES",
               "NYLON ROPE", "PLASTIC PELLETS", "DRIED MANGO", "TEA LEAVES",
               "SESAME SEEDS", "BRASS FITTINGS", "WOOL BLANKETS", "CORK SHEETS"]
PACKAGES = ["CARTONS", "DRUMS", "BALES", "SACKS", "CRATES", "PAILS", "BUNDLES", "REELS"]


def pseudo_word(rng, syl=None):
    syl = syl or rng.choice([2, 2, 3])
    w = ""
    for i in range(syl):
        w += rng.choice(ONSETS) + rng.choice(VOWELS)
        if i == syl - 1 or rng.random() < 0.4:
            w += rng.choice(CODAS)
    return w


def code(rng, n):
    return "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(n))


# ----------------------------------------------------------------------------
# Manifest fields.  Values are given with spaces (the "display" form used for
# answers); the plaintext strips the spaces.
# ----------------------------------------------------------------------------
def make_values(rng):
    v = {}
    v["SHIPPER"] = pseudo_word(rng) + " " + rng.choice(SUFFIX)
    v["CONSIGNEE"] = pseudo_word(rng) + " " + rng.choice(SUFFIX)
    v["NOTIFYPARTY"] = pseudo_word(rng) + " " + rng.choice(SUFFIX)
    v["AGENT"] = pseudo_word(rng) + " " + rng.choice(SUFFIX)
    v["VESSEL"] = pseudo_word(rng, 3)
    v["FLAG"] = pseudo_word(rng, 3)
    v["VOYAGE"] = code(rng, 2) + " " + num_words(rng.randint(101, 999))
    v["PORTOFLOADING"] = pseudo_word(rng) + rng.choice(CITY_END)
    v["PORTOFDISCHARGE"] = pseudo_word(rng) + rng.choice(CITY_END)
    v["PLACEOFDELIVERY"] = pseudo_word(rng) + rng.choice(CITY_END)
    v["CONTAINER"] = code(rng, 7)
    v["SEALNO"] = code(rng, 6)
    v["BOOKINGREF"] = code(rng, 8)
    v["BILLOFLADINGNO"] = code(rng, 9)
    v["CUSTOMSREF"] = code(rng, 7)
    v["MARKSANDNUMBERS"] = code(rng, 5) + " " + num_words(rng.randint(11, 99))
    v["PALLETS"] = num_words(rng.randint(12, 99))
    v["CARTONS"] = num_words(rng.randint(120, 9999))
    gross = rng.randint(2000, 99999)
    v["GROSSMASSKG"] = num_words(gross)
    v["NETMASSKG"] = num_words(rng.randint(1000, gross - 500))
    v["TAREMASSKG"] = num_words(rng.randint(1800, 4500))
    v["DECLAREDVALUE"] = num_words(rng.randint(10000, 999999))
    v["INSUREDVALUE"] = num_words(rng.randint(10000, 999999))
    v["FREIGHTCHARGES"] = num_words(rng.randint(1000, 99999))
    v["QUAYNUMBER"] = num_words(rng.randint(1, 40))
    v["HSCODE"] = "".join(DIGITS[rng.randint(0, 9)] for _ in range(6))
    v["COMMODITY"] = rng.choice(COMMODITIES)
    v["PACKAGETYPE"] = rng.choice(PACKAGES)
    v["REMARKS"] = " ".join(pseudo_word(rng) for _ in range(rng.randint(3, 6)))
    # mostly numeric extra fields used to pad longer instances (long values in words)
    v["INVOICENUMBER"] = "".join(DIGITS[rng.randint(0, 9)] for _ in range(7))
    v["PURCHASEORDER"] = code(rng, 3) + " " + num_words(rng.randint(1000, 99999))
    v["LETTEROFCREDITNO"] = "".join(DIGITS[rng.randint(0, 9)] for _ in range(8))
    v["DUTYPAYABLE"] = num_words(rng.randint(1000, 99999))
    v["WEIGHTPERCARTONGRAMS"] = num_words(rng.randint(500, 29999))
    v["VOLUMECUBICDECIMETRES"] = num_words(rng.randint(10000, 99999))
    v["LENGTHCM"] = num_words(rng.randint(100, 1300))
    v["WIDTHCM"] = num_words(rng.randint(100, 260))
    v["HEIGHTCM"] = num_words(rng.randint(100, 290))
    v["DEMURRAGEPERDAY"] = num_words(rng.randint(100, 999))
    v["FREEDAYS"] = num_words(rng.randint(3, 21))
    v["STORAGEDAYS"] = num_words(rng.randint(1, 60))
    v["RECEIVINGCLERK"] = pseudo_word(rng) + " " + pseudo_word(rng)
    v["INSPECTOR"] = pseudo_word(rng) + " " + pseudo_word(rng)
    v["WAREHOUSE"] = pseudo_word(rng) + " " + rng.choice(["DEPOT", "YARD", "TERMINAL", "SHED"])
    v["TRUCKER"] = pseudo_word(rng) + " " + rng.choice(SUFFIX)
    v["ORIGINCOUNTRY"] = pseudo_word(rng, 3)
    v["DESTINATIONCOUNTRY"] = pseudo_word(rng, 3)
    v["UNITSPERCARTON"] = num_words(rng.randint(2, 144))
    v["ITEMCOUNT"] = num_words(rng.randint(1000, 999999))
    return v


CORE_FIELDS = ["SHIPPER", "CONSIGNEE", "VESSEL", "VOYAGE", "PORTOFLOADING",
               "PORTOFDISCHARGE", "CONTAINER", "SEALNO", "PALLETS", "CARTONS",
               "GROSSMASSKG", "DECLAREDVALUE", "COMMODITY", "REMARKS"]
OPTIONAL_FIELDS = ["NOTIFYPARTY", "PLACEOFDELIVERY", "BOOKINGREF", "NETMASSKG",
                   "FREIGHTCHARGES", "INSUREDVALUE", "TAREMASSKG", "BILLOFLADINGNO",
                   "HSCODE", "PACKAGETYPE", "MARKSANDNUMBERS", "CUSTOMSREF", "AGENT",
                   "FLAG", "QUAYNUMBER", "INVOICENUMBER", "PURCHASEORDER",
                   "LETTEROFCREDITNO", "DUTYPAYABLE", "WEIGHTPERCARTONGRAMS",
                   "VOLUMECUBICDECIMETRES", "LENGTHCM", "WIDTHCM", "HEIGHTCM",
                   "DEMURRAGEPERDAY", "FREEDAYS", "STORAGEDAYS", "RECEIVINGCLERK",
                   "INSPECTOR", "WAREHOUSE", "TRUCKER", "ORIGINCOUNTRY",
                   "DESTINATIONCOUNTRY", "UNITSPERCARTON", "ITEMCOUNT"]
ALL_LABELS = CORE_FIELDS + OPTIONAL_FIELDS

# id, label, type, question text
QUESTIONS = [
    (1, "CONTAINER", "code", "The container code (a string of letters)."),
    (2, "SEALNO", "code", "The seal number (a string of letters)."),
    (3, "PALLETS", "num", "The number of pallets."),
    (4, "CARTONS", "num", "The number of cartons."),
    (5, "GROSSMASSKG", "num", "The gross mass in kilograms."),
    (6, "DECLAREDVALUE", "num", "The declared value (a whole number)."),
    (7, "CONSIGNEE", "name", "The consignee (the full name as written)."),
    (8, "PORTOFDISCHARGE", "name", "The port of discharge (as written)."),
    (9, "VESSEL", "name", "The vessel name (as written)."),
    (10, "SHIPPER", "name", "The shipper (the full name as written)."),
]

# crib candidates ranked by usefulness (longer first); "short" preset filters
CRIB_POOL = ["PORTOFDISCHARGE", "DECLAREDVALUE", "PORTOFLOADING", "GROSSMASSKG",
             "CONSIGNEE", "CONTAINER", "COMMODITY", "SHIPPER", "PALLETS", "CARTONS",
             "VESSEL", "SEALNO", "VOYAGE"]


# ----------------------------------------------------------------------------
# Cipher
# ----------------------------------------------------------------------------
def vig(text, key, sign):
    p = len(key)
    return "".join(chr((ord(c) - A + sign * (ord(key[i % p]) - A)) % 26 + A)
                   for i, c in enumerate(text))


def encrypt(pt, key):
    return vig(pt, key, +1)


def decrypt(ct, key):
    return vig(ct, key, -1)


def minimal_period(key):
    for d in range(1, len(key)):
        if len(key) % d == 0 and key == key[:d] * (len(key) // d):
            return d
    return len(key)


# ----------------------------------------------------------------------------
# Brute-force uniqueness: enumerate every (period, crib offsets) combination in
# the stated period range and windows whose implied key letters are mutually
# consistent.  Returns a list of (p, offsets, partial_key_tuple).
# ----------------------------------------------------------------------------
def enumerate_solutions(ct, cribs, pmin, pmax, cap=20000):
    """cribs: list of (text, lo, hi) with 0-based inclusive offset bounds."""
    sols = []
    n = len(ct)
    for p in range(pmin, pmax + 1):
        cand = []
        for text, lo, hi in cribs:
            L = len(text)
            lst = []
            for o in range(lo, min(hi, n - L) + 1):
                part = [None] * p
                ok = True
                for j, ch in enumerate(text):
                    k = (ord(ct[o + j]) - ord(ch)) % 26
                    r = (o + j) % p
                    if part[r] is None:
                        part[r] = k
                    elif part[r] != k:
                        ok = False
                        break
                if ok:
                    lst.append((o, part))
            cand.append(lst)
        order = sorted(range(len(cribs)), key=lambda i: len(cand[i]))

        def dfs(idx, merged, offs):
            if len(sols) > cap:
                return
            if idx == len(order):
                sols.append((p, tuple(offs), tuple(merged)))
                return
            for o, part in cand[order[idx]]:
                new = list(merged)
                ok = True
                for r in range(p):
                    if part[r] is not None:
                        if new[r] is None:
                            new[r] = part[r]
                        elif new[r] != part[r]:
                            ok = False
                            break
                if ok:
                    offs.append((order[idx], o))
                    dfs(idx + 1, new, offs)
                    offs.pop()

        dfs(0, [None] * p, [])
    return sols


# ----------------------------------------------------------------------------
# Build one instance
# ----------------------------------------------------------------------------
def build(seed, cfg):
    rng = random.Random(f"deduction-3:{seed}")
    for attempt in range(2000):
        vals = make_values(rng)
        fields = list(CORE_FIELDS)
        # add optional fields until the target length is reached
        pool = list(OPTIONAL_FIELDS)
        rng.shuffle(pool)

        def plain_len(fs):
            return (len(rng_header) + len(SEP)
                    + sum(len(f) + len(vals[f].replace(" ", "")) + len(SEP) for f in fs))
        rng_header = pseudo_word(rng) + pseudo_word(rng) + rng.choice(["LINES", "SHIPPINGCO", "CARRIERS", "NAVIGATION"])
        while plain_len(fields) < cfg["length"] and pool:
            fields.append(pool.pop())
        while plain_len(fields) < cfg["length"]:
            vals["REMARKS"] += " " + pseudo_word(rng)
        rng.shuffle(fields)
        plaintext = rng_header + SEP + "".join(f + vals[f].replace(" ", "") + SEP for f in fields)
        plaintext = plaintext[:-len(SEP)]  # no trailing separator
        if not re.fullmatch(r"[A-Z]+", plaintext):
            continue
        # every label must occur exactly once; separator only as separator
        if any(plaintext.count(lb) != 1 for lb in fields):
            continue
        if plaintext.count(SEP) != len(fields):
            continue
        if any(lb in plaintext for lb in ALL_LABELS if lb not in fields):
            continue

        p = rng.randint(cfg["pmin"], cfg["pmax"])
        key = code(rng, p)
        if minimal_period(key) != p or len(set(key)) < max(3, p // 2):
            continue
        ct = encrypt(plaintext, key)
        assert decrypt(ct, key) == plaintext

        # cribs
        pool_c = [c for c in CRIB_POOL if c in fields]
        if cfg["crib_maxlen"] == "short":
            pool_c = [c for c in pool_c if len(c) < cfg["pmin"]]
        if len(pool_c) < cfg["cribs"]:
            continue
        crib_labels = rng.sample(pool_c, cfg["cribs"])
        n = len(ct)
        cribs = []
        for lb in crib_labels:
            o = plaintext.index(lb)
            L = len(lb)
            W = cfg["window"]
            if W <= 0:
                lo, hi = 0, n - L
            else:
                lo = o - rng.randint(0, W - 1)
                lo = max(0, min(lo, n - L - (W - 1)))
                hi = lo + W - 1
            cribs.append({"text": lb, "offset0": o, "lo0": lo, "hi0": hi})

        sols = enumerate_solutions(ct, [(c["text"], c["lo0"], c["hi0"]) for c in cribs],
                                   cfg["pmin"], cfg["pmax"])
        if len(sols) != 1:
            continue
        sp, soffs, spart = sols[0]
        if sp != p or None in spart:
            continue
        if "".join(chr(A + k) for k in spart) != key:
            continue
        # deterministic instance found
        return dict(plaintext=plaintext, ciphertext=ct, period=p, key=key,
                    fields=fields, vals=vals, cribs=cribs, header=rng_header,
                    attempts=attempt + 1)
    raise SystemExit("could not build a unique instance; try another seed")


# ----------------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------------
def format_ciphertext(ct):
    lines = []
    for i in range(0, len(ct), 50):
        chunk = ct[i:i + 50]
        groups = " ".join(chunk[j:j + 5] for j in range(0, len(chunk), 5))
        lines.append(f"{i + 1:04d}  {groups}")
    return "\n".join(lines)


def make_prompt(inst, cfg):
    ct = inst["ciphertext"]
    n = len(ct)
    crib_lines = []
    for c in inst["cribs"]:
        if cfg["window"] <= 0:
            crib_lines.append(f"  - {c['text']}  (position unknown; anywhere in the text)")
        else:
            crib_lines.append(f"  - {c['text']}  (its first letter is at some position between "
                              f"{c['lo0'] + 1} and {c['hi0'] + 1} inclusive)")
    qs = "\n".join(f"Q{i}. {q}" for i, _, _, q in QUESTIONS)
    ex_key = "".join(chr(A + (i * 7) % 26) for i in range(cfg["pmin"]))
    return f"""IMPORTANT: Solve without any tools — no Bash, no Python, no code execution, no files, no web. Work it out yourself.

CRIB SLIDE — recover a Vigenere key from cribs and read the plaintext.

The text below is a ciphertext of {n} letters (A-Z only, shown in groups of five, with the
1-based position of the first letter of each line at the left). It was produced from a
plaintext of {n} letters by a periodic Vigenere cipher:

  letters are numbered A=0, B=1, ..., Z=25;
  the key is a string K of p letters (an arbitrary letter string, NOT a dictionary word);
  ciphertext letter i (1-based) = (plaintext letter i + K[(i-1) mod p]) mod 26,
  so K[0] shifts positions 1, p+1, 2p+1, ...; K[1] shifts positions 2, p+2, ...; etc.

The period p is unknown, but it is between {cfg['pmin']} and {cfg['pmax']} inclusive.

WHAT THE PLAINTEXT IS
The plaintext is a synthetic shipping manifest written with capital letters only (no spaces,
digits or punctuation). All proper names in it are invented, so they cannot be guessed. It
consists of a short carrier header followed by a sequence of fields in an UNKNOWN order. Each
field is a LABEL immediately followed by its VALUE, and consecutive fields are separated by
the word {SEP} (which occurs nowhere else). Numbers are written in words without AND or
hyphens, e.g. 2417 -> TWOTHOUSANDFOURHUNDREDSEVENTEEN, 40 -> FORTY, 105 -> ONEHUNDREDFIVE.
Container, seal and reference codes are strings of random letters.

CRIBS
Each of the following {len(inst['cribs'])} labels occurs EXACTLY ONCE in the plaintext (as a field label).
Their exact positions are not given, only a window for the position of their first letter:
{chr(10).join(crib_lines)}

Within the stated period range and windows, exactly one (period, key) pair is consistent
with all the cribs simultaneously; that is the key you must find.

CIPHERTEXT
{format_ciphertext(ct)}

QUESTIONS (answer from the decrypted manifest)
{qs}

OUTPUT FORMAT
Return ONLY a single JSON object, with no commentary before or after it, exactly of this form:

{{"period": <integer p>,
 "key": "<the p key letters, K[0] first, i.e. the letter that shifts position 1>",
 "answers": [{{"id": 1, "value": "..."}}, {{"id": 2, "value": "..."}}, ..., {{"id": 10, "value": "..."}}]}}

Rules for "value": numbers (Q3-Q6) as plain digits, e.g. "2417"; codes (Q1-Q2) as the exact
letters; names (Q7-Q10) as the letters of the value exactly as they appear in the plaintext
(spaces optional, e.g. "HARVOLD TRADING" and "HARVOLDTRADING" are both accepted).
Every value must be a string. Example shape only (the values are NOT hints):
{{"period": {cfg['pmin']}, "key": "{ex_key}", "answers": [{{"id": 1, "value": "QWERTYU"}}, {{"id": 3, "value": "42"}}]}}
"""


SCHEMA = {
    "type": "object",
    "properties": {
        "period": {"type": "integer"},
        "key": {"type": "string"},
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "value": {"type": "string"}},
                "required": ["id", "value"],
            },
        },
    },
    "required": ["period", "key", "answers"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--difficulty", choices=list(PRESETS), default="hard")
    ap.add_argument("--out", default=HERE)
    ap.add_argument("--length", type=int)
    ap.add_argument("--pmin", type=int)
    ap.add_argument("--pmax", type=int)
    ap.add_argument("--cribs", type=int)
    ap.add_argument("--window", type=int)
    ap.add_argument("--no-full-check", action="store_true",
                    help="skip the (slower) uniqueness count over all offsets")
    args = ap.parse_args()
    cfg = dict(PRESETS[args.difficulty])
    for k in ("length", "pmin", "pmax", "cribs", "window"):
        if getattr(args, k) is not None:
            cfg[k] = getattr(args, k)

    inst = build(args.seed, cfg)
    ct, pt = inst["ciphertext"], inst["plaintext"]

    # (a) each crib exactly once, (c) round trip
    for c in inst["cribs"]:
        assert pt.count(c["text"]) == 1
    assert decrypt(ct, inst["key"]) == pt
    # (b) uniqueness within windows was enforced in build(); also count how many
    # consistent combinations exist with NO window hint at all (information only)
    full_count = None
    if not args.no_full_check:
        sols = enumerate_solutions(ct, [(c["text"], 0, len(ct) - len(c["text"])) for c in inst["cribs"]],
                                   cfg["pmin"], cfg["pmax"])
        full_count = len(sols)

    answers = []
    for qid, label, typ, q in QUESTIONS:
        answers.append({"id": qid, "label": label, "type": typ, "question": q,
                        "value": inst["vals"][label]})

    key = {
        "task": "D3",
        "seed": args.seed,
        "difficulty": args.difficulty,
        "config": cfg,
        "period": inst["period"],
        "key": inst["key"],
        "plaintext": pt,
        "ciphertext": ct,
        "cribs": [{"text": c["text"], "position": c["offset0"] + 1,
                   "window": [c["lo0"] + 1, c["hi0"] + 1]} for c in inst["cribs"]],
        "field_order": inst["fields"],
        "answers": answers,
        "meta": {"length": len(ct), "unique_within_windows": True,
                 "consistent_combinations_without_windows": full_count,
                 "build_attempts": inst["attempts"]},
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "prompt.txt"), "w") as f:
        f.write(make_prompt(inst, cfg))
    with open(os.path.join(args.out, "key.json"), "w") as f:
        json.dump(key, f, indent=1)
    with open(os.path.join(args.out, "schema.json"), "w") as f:
        json.dump(SCHEMA, f, indent=1)
    print(json.dumps({"period": inst["period"], "key": inst["key"], "length": len(ct),
                      "cribs": key["cribs"], "attempts": inst["attempts"],
                      "without_windows": full_count}, indent=1))


if __name__ == "__main__":
    main()
