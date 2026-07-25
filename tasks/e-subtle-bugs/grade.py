#!/usr/bin/env python3
"""Grader for E. Usage: python grade.py <run-record.json>
Prints: {"task","score","total","detail"}. Self-contained; ground truth in this directory."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _common import load_answer, emit, norm, numeq

HERE = os.path.dirname(os.path.abspath(__file__))
import html
import importlib.util
import tempfile

def load(path):
    spec = importlib.util.spec_from_file_location("solution_e", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(path):
    m = load(path)
    results, errors = {}, {}

    def check(name, fn):
        try:
            results[name] = bool(fn())
        except Exception as e:
            results[name] = False
            errors[name] = f"{type(e).__name__}: {e}"

    def corpus_freq():
        ix = m.MiniSearch()
        ix.add(1, "wolf wolf wolf wolf moon")
        ix.add(2, "fox moon")
        ix.add(3, "moon river")
        return ix

    def corpus_norm():
        ix = m.MiniSearch()
        ix.add(10, "the wolf is in the den")
        ix.add(11, "wolf den")
        ix.add(12, "moon river")
        return ix

    def corpus_bool():
        ix = m.MiniSearch()
        ix.add(30, "apple")
        ix.add(31, "banana cherry")
        ix.add(32, "apple cherry")
        return ix

    def corpus_phrase():
        ix = m.MiniSearch()
        ix.add(20, "quick brown fox")
        return ix

    def corpus_case():
        ix = m.MiniSearch()
        ix.add(40, "Rust is great for systems programming")
        return ix

    # --- bug tests ---
    check("B1_idf_df_documents",
          lambda: corpus_freq().search("wolf OR fox") == [1, 2])
    check("B2_phrase_adjacency",
          lambda: corpus_phrase().phrase("quick fox") == [])
    check("B3_and_precedence",
          lambda: 30 in corpus_bool().search("apple OR banana AND cherry"))
    check("B4_query_case",
          lambda: corpus_case().search("Rust") == [40])
    check("B5_indexed_len_norm",
          lambda: corpus_norm().search("wolf") == [10, 11])

    # --- regression tests (pass on the original buggy module too) ---
    check("R1_and_basic",
          lambda: corpus_bool().search("banana AND cherry") == [31])
    check("R2_or_basic",
          lambda: set(corpus_bool().search("apple OR banana"))
          == {30, 31, 32})
    check("R3_phrase_positive",
          lambda: corpus_phrase().phrase("brown fox") == [20]
          and corpus_phrase().phrase("quick brown fox") == [20])
    check("R4_stopword_query",
          lambda: corpus_norm().search("the") == [])
    check("R5_missing_term",
          lambda: corpus_freq().search("zebra") == [])

    return results, errors


def grade(ans):
    code = html.unescape(ans.get("fixed_code", "") or "")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        results, errors = _run(path)
    except Exception as e:
        os.unlink(path)
        return 0, 5, {"load_error": f"fixed_code failed to import: {type(e).__name__}: {e}"[:160]}
    os.unlink(path)
    bugs = sum(v for k, v in results.items() if k.startswith("B"))
    return bugs, 5, {k: v for k, v in results.items() if not v}


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("E", s, t, d)
