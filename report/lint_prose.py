#!/usr/bin/env python3
"""Check that every model family in report/config.json is at least mentioned in
the hand-written parts of the report and README.

The data sections regenerate; the conclusions do not. This lint catches the
common failure of adding a model's runs without revisiting the prose that
interprets them. It checks presence only — it cannot tell whether what the
prose says about a model is still true. See docs/adding-a-model.md, step 5.

Exit 1 if any family is missing from any checked file.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "report", "config.json")))

# Files that must name every family, with a short reason shown on failure.
# (scoreboard.html is deliberately not here: it only carries claims actually
# made about a model, so a new family may legitimately be absent.)
CHECKS = [
    ("README.md", "headline reliability-floor table"),
    ("report/fragments/findings.html", "F2 lists every family's floor"),
    ("report/fragments/decisions.html", "recommendations name configs"),
]


def mentions(text, model):
    """A family counts as mentioned by display name ('Opus 5.5'), family key
    ('opus55', as in 'opus55@xhigh') or model id ('claude-opus-5-5')."""
    text = text.lower()
    return any(needle.lower() in text for needle in
               (model["name"], model["family"], model["model_id"]))


def main():
    bad = 0
    for rel, why in CHECKS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print(f"lint-prose: missing file {rel}")
            bad += 1
            continue
        text = re.sub(r"<[^>]+>", " ", open(path).read())
        for m in CFG["models"]:
            if m.get("prior_generation") and rel.startswith("report/fragments/decisions"):
                continue  # retired tiers need not be recommended
            if not mentions(text, m):
                print(f"lint-prose: {rel}: no mention of {m['name']} "
                      f"({m['family']}) — {why}")
                bad += 1
    if bad:
        print(f"lint-prose: {bad} gap(s). The report's conclusions are hand-written; "
              "see docs/adding-a-model.md step 5.")
        sys.exit(1)
    print("lint-prose OK: every grid family appears in the curated prose")


if __name__ == "__main__":
    main()
