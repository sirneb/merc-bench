"""Grader for Task D. Usage: python3 grade_d.py <solution.py> [--expected ref|oracle]

Compares solution output to ref_d (which must equal oracle_d — run
validate_d.py first). Prints JSON: per-case pass/fail + totals.
"""
import importlib.util
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_d  # noqa: E402
from cases_d import CASES, ERROR_CASES  # noqa: E402


def load(path):
    spec = importlib.util.spec_from_file_location("solution_d", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    sol = load(sys.argv[1])
    results, errors = {}, {}
    for name, rule, dts, limit in CASES:
        try:
            expected = ref_d.expand(dict(rule), dts, limit)
            got = sol.expand(dict(rule), dts, limit)
            results[name] = list(got) == list(expected)
            if not results[name]:
                errors[name] = {"expected": [str(d) for d in expected[:8]],
                                "got": [str(d) for d in list(got)[:8]]}
        except Exception as e:
            results[name] = False
            errors[name] = f"{type(e).__name__}: {e}"
    for name, rule, dts, limit in ERROR_CASES:
        try:
            sol.expand(dict(rule), dts, limit)
            results[name] = False
            errors[name] = "no ValueError raised"
        except ValueError:
            results[name] = True
        except Exception as e:
            results[name] = False
            errors[name] = f"wrong exception {type(e).__name__}: {e}"
    passed = sum(results.values())
    print(json.dumps({"passed": passed, "total": len(results),
                      "detail": results, "errors": errors}, indent=1))


if __name__ == "__main__":
    main()
