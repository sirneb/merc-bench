#!/usr/bin/env python3
"""Self-test for the Q2 grader.

1. Build a run record whose answer IS the key           -> must score total/total.
2. Corrupt parts of the answer in controlled ways       -> must score less, by
   the expected amount (checks partial credit and tolerant parsing).
3. Feed the answer as a prose/text blob                 -> still graded.
Prints a table and exits non-zero on any failure.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import grade  # noqa: E402


def key_answer(key):
    return {
        "legs": [{"id": l["id"], "arr_utc": l["arr_utc"],
                  "arr_local": l["arr_local"]} for l in key["legs"]],
        "duty_periods": [{"id": d["id"], "start_utc": d["start_utc"],
                          "end_utc": d["end_utc"], "minutes": d["minutes"]}
                         for d in key["duty_periods"]],
        "violations": list(key["violations"]),
        "home_base_month_minutes": key["home_base_month_minutes"],
    }


def shift(s, minutes):
    """Shift a 'YYYY-MM-DD HH:MM' string by whole minutes (same month only)."""
    d, t = s.split(" ")
    y, mo, da = map(int, d.split("-"))
    h, mi = map(int, t.split(":"))
    tot = da * 1440 + h * 60 + mi + minutes
    da, rem = divmod(tot, 1440)
    return "%04d-%02d-%02d %02d:%02d" % (y, mo, da, rem // 60, rem % 60)


def main():
    key = json.load(open(os.path.join(HERE, "key.json")))
    full = key_answer(key)
    n_legs = len(key["legs"])
    n_duty = len(key["duty_periods"])
    total_expected = n_legs + n_duty + 4 + 6
    cases = []

    # 1. perfect answer via the CLI, exactly as the runner would store it
    rec = {"task": "Q2", "model": "selftest", "family": "selftest",
           "effort": "none", "sample": "selftest", "harness": "selftest",
           "date": "2026-09-26", "answer": full, "usage": None,
           "duration_s": None, "cost_usd": None, "cost_estimated": True,
           "notes": ""}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(rec, f)
        path = f.name
    out = subprocess.run([sys.executable, os.path.join(HERE, "grade.py"), path],
                         capture_output=True, text=True)
    os.unlink(path)
    cli = json.loads(out.stdout)
    cases.append(("key answer via CLI", cli["score"], cli["total"],
                  cli["score"] == cli["total"] == total_expected))

    def run(name, ans, expect):
        s, t, _ = grade.grade(ans)
        cases.append((name, s, t, abs(s - expect) < 1e-6))

    run("key answer (direct)", full, total_expected)

    # 2a. one leg: wrong local rendering, right instant -> lose 0.5
    a = copy.deepcopy(full)
    a["legs"][3]["arr_local"] = shift(a["legs"][3]["arr_local"], 60)
    run("1 leg local off by 1h (utc right)", a, total_expected - 0.5)

    # 2b. five legs entirely wrong (both fields) -> lose 5
    a = copy.deepcopy(full)
    for i in range(5):
        a["legs"][i]["arr_local"] = shift(a["legs"][i]["arr_local"], 60)
        a["legs"][i]["arr_utc"] = shift(a["legs"][i]["arr_utc"], 60)
    run("5 legs both fields wrong", a, total_expected - 5)

    # 2c. duty minutes off by 60 on one period -> 0.5; off by 200 on another -> 0
    a = copy.deepcopy(full)
    a["duty_periods"][0]["minutes"] += 60
    a["duty_periods"][1]["minutes"] += 200
    run("duty D1 +60min, D2 +200min", a, total_expected - 1.5)

    # 2d. violations: drop one, add a wrong one
    a = copy.deepcopy(full)
    want = set(key["violations"])
    wrong = [d["id"] for d in key["duty_periods"] if d["id"] not in want][0]
    have = sorted(want)[1:] + [wrong]
    a["violations"] = have
    jac = len(want & set(have)) / len(want | set(have))
    run("violations drop 1 add 1", a, total_expected - 4 + 4 * jac)

    # 2e. home total off by 0.5 % -> 3 of 6; off by 10 % -> 0
    a = copy.deepcopy(full)
    a["home_base_month_minutes"] = key["home_base_month_minutes"] + \
        int(0.005 * key["home_base_month_minutes"])
    run("home minutes within 1%", a, total_expected - 3)
    a["home_base_month_minutes"] = int(1.1 * key["home_base_month_minutes"])
    run("home minutes off 10%", a, total_expected - 6)

    # 2f. missing duty section entirely and empty violations
    a = copy.deepcopy(full)
    a["duty_periods"] = []
    a["violations"] = []
    run("no duty periods, no violations", a, total_expected - n_duty - 4)

    # 2g. a wrong duty split: model merges D1 and D2 -> only those two suffer
    a = copy.deepcopy(full)
    d1, d2 = a["duty_periods"][0], a["duty_periods"][1]
    merged = {"id": "D1", "start_utc": d1["start_utc"], "end_utc": d2["end_utc"],
              "minutes": grade.to_minutes(d2["end_utc"]) - grade.to_minutes(d1["start_utc"])}
    a["duty_periods"] = [merged] + a["duty_periods"][2:]
    for i, d in enumerate(a["duty_periods"], 1):
        d["id"] = "D%d" % i
    # renumbered violations shift by one -> Jaccard drops; that's intended
    s, t, _ = grade.grade(a)
    cases.append(("merged D1+D2 (renumbered)", s, t,
                  total_expected - 6.5 <= s < total_expected - 1))

    # 3. tolerant formats: ISO 'T', seconds, Z suffix, lowercase ids, 'L1'
    a = copy.deepcopy(full)
    for l in a["legs"]:
        l["arr_utc"] = l["arr_utc"].replace(" ", "T") + ":00Z"
        l["arr_local"] = l["arr_local"] + ":00"
        l["id"] = "l" + str(int(l["id"][1:]))
    a["violations"] = [v.lower() for v in a["violations"]]
    run("tolerant datetime/id formats", a, total_expected)

    # 4. answer arrives as text (prose around JSON)
    text = "Here is my answer:\n```json\n" + json.dumps(full) + "\n```\nDone."
    run("JSON wrapped in prose", {"_text": text}, total_expected)

    ok = all(c[3] for c in cases)
    print("%-36s %7s %6s  %s" % ("case", "score", "total", "ok"))
    for name, s, t, good in cases:
        print("%-36s %7s %6s  %s" % (name, s, t, "ok" if good else "FAIL"))
    print("SELFTEST", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
