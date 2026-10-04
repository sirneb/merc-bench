#!/usr/bin/env python3
"""Fuzz the generator against the independent oracle.

For each seed (and a rotation of difficulty presets / knobs) generate a roster
into a temp dir and check that oracle.compute(prompt.txt) reproduces key.json
exactly. Also reports how often a seed fails to build (constraint rejection).

Usage: /tmp/merc-venv/bin/python fuzz.py [N=300]
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generator                                   # noqa: E402
import oracle                                      # noqa: E402

CONFIGS = [
    [],
    ["--difficulty", "easy"],
    ["--difficulty", "medium"],
    ["--difficulty", "extreme"],
    ["--legs", "48", "--ambiguity", "5"],
    ["--no-decree"],
    ["--no-odd-offsets"],
    ["--transition-proximity", "0.6"],
    ["--no-chain"],
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    tmp = tempfile.mkdtemp(prefix="q2fuzz-")
    ok = bad = unbuildable = 0
    stats = {"near": [], "amb": [], "viol": []}
    try:
        for i in range(n):
            seed = 1000 + i
            cfg = CONFIGS[i % len(CONFIGS)]
            out = os.path.join(tmp, str(i))
            try:
                generator.main(["--seed", str(seed), "--out", out, "--quiet"]
                               + cfg)
            except (RuntimeError, AssertionError) as e:
                unbuildable += 1
                print("seed %d %s: unbuildable (%s)" % (seed, cfg, e))
                continue
            key = json.load(open(os.path.join(out, "key.json")))
            mine = oracle.compute(open(os.path.join(out, "prompt.txt")).read())
            diffs = oracle.compare(mine, key)
            if diffs:
                bad += 1
                print("seed %d %s: MISMATCH" % (seed, cfg))
                for d in diffs[:5]:
                    print("   ", d)
            else:
                ok += 1
            s = key["stats"]
            stats["near"].append(s["near_transition_legs"])
            stats["amb"].append(s["engineered_departures"])
            stats["viol"].append(s["violations"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("fuzz: %d agree, %d mismatch, %d unbuildable out of %d" % (
        ok, bad, unbuildable, n))
    if stats["near"]:
        print("near-transition legs: min %d mean %.1f max %d | engineered "
              "departures: min %d max %d | violations: min %d max %d" % (
                  min(stats["near"]),
                  sum(stats["near"]) / len(stats["near"]), max(stats["near"]),
                  min(stats["amb"]), max(stats["amb"]), min(stats["viol"]),
                  max(stats["viol"])))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
