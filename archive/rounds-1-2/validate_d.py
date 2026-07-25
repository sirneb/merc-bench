"""Cross-validate ref_d against the independent oracle on all cases,
plus a randomized fuzz sweep. Exits nonzero on any disagreement."""
import random
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_d
import oracle_d
from cases_d import CASES

fails = 0
for name, rule, dts, limit in CASES:
    a = ref_d.expand(dict(rule), dts, limit)
    b = oracle_d.expand(dict(rule), dts, limit)
    if a != b:
        fails += 1
        print(f"DISAGREE {name}: ref={a[:6]} oracle={b[:6]}")

random.seed(7)
codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
for i in range(400):
    freq = random.choice(["DAILY", "WEEKLY", "MONTHLY"])
    rule = {"FREQ": freq, "INTERVAL": random.randint(1, 5)}
    if random.random() < 0.4:
        rule["BYMONTH"] = sorted(random.sample(range(1, 13),
                                               random.randint(1, 3)))
    if freq == "WEEKLY" and random.random() < 0.7:
        rule["BYDAY"] = random.sample(codes, random.randint(1, 3))
    if freq == "MONTHLY":
        r = random.random()
        if r < 0.4:
            rule["BYMONTHDAY"] = random.sample(
                list(range(1, 32)) + list(range(-31, 0)),
                random.randint(1, 3))
        elif r < 0.75:
            rule["BYDAY"] = [f"{random.choice([1,2,3,4,5,-1,-2])}"
                             f"{random.choice(codes)}"
                             for _ in range(random.randint(1, 2))]
    if random.random() < 0.3:
        rule["COUNT"] = random.randint(1, 12)
    dts = date(2025, 1, 1) + __import__("datetime").timedelta(
        days=random.randint(0, 700))
    if random.random() < 0.3:
        rule["UNTIL"] = dts + __import__("datetime").timedelta(
            days=random.randint(10, 400))
    limit = random.randint(1, 6 if freq == "MONTHLY" else 12)
    a = ref_d.expand(dict(rule), dts, limit)
    b = oracle_d.expand(dict(rule), dts, limit)
    if a != b:
        fails += 1
        print(f"FUZZ DISAGREE {rule} dts={dts} limit={limit}\n"
              f"  ref={a}\n  oracle={b}")
        if fails > 5:
            break

print(f"validate_d: {'OK' if fails == 0 else 'FAILURES'} "
      f"({len(CASES)} cases + 400 fuzz)")
sys.exit(1 if fails else 0)
