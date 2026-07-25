"""Grader for Task A (bug hunt on eventstats).

Usage: python3 grade_a.py <path-to-fixed-module.py>
Prints JSON: per-bug pass/fail + regression checks + totals.

Planted bugs (key):
  B1 mean:            no empty guard (spec: return 0.0)                 -> mean([]) == 0.0
  B2 median:          even case uses ys[mid]+ys[mid+1] (s/b mid-1,mid)  -> median([1,2,3,4]) == 2.5
  B3 sample_variance: divisor n (s/b n-1) and no <2 guard               -> var([2,4]) == 2.0 and var([5]) == 0.0
  B4 normalize:       denominator max (s/b max-min); equal-values case  -> normalize([2,4]) == [0,1]; normalize([3,3]) == [.5,.5]
  B5 rolling_max:     slice max(0,i-w):i+1 (s/b i-w+1) -> window w+1    -> rolling_max([1,5,2,1],2) == [1,5,5,2]
  B6 top_k:           sorted asc, takes smallest k (s/b largest desc)   -> top_k([1,9,5,7],2) == [9,7]
  B7 merge_intervals: input not sorted before merging                   -> merge([[5,6],[1,3],[2,4]]) == [[1,4],[5,6]]
  B8 ewma:            s = a*x+(1-a)*x  (s/b (1-a)*s)                    -> ewma([0,10],0.5) == [0,5.0]
"""
import importlib.util
import json
import sys


def load(path):
    spec = importlib.util.spec_from_file_location("fixed_eventstats", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def close(a, b, eps=1e-9):
    return abs(a - b) <= eps


def seqclose(a, b, eps=1e-9):
    return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))


def main():
    m = load(sys.argv[1])
    results = {}

    def check(name, fn):
        try:
            results[name] = bool(fn())
        except Exception as e:
            results[name] = False
            results.setdefault("_errors", {})[name] = f"{type(e).__name__}: {e}"

    # Bug fixes
    check("B1_mean_empty", lambda: m.mean([]) == 0.0)
    check("B2_median_even", lambda: close(m.median([1, 2, 3, 4]), 2.5)
          and close(m.median([1, 2]), 1.5))
    check("B3_variance", lambda: close(m.sample_variance([2.0, 4.0]), 2.0)
          and m.sample_variance([5.0]) == 0.0 and m.sample_variance([]) == 0.0)
    check("B4_normalize", lambda: seqclose(m.normalize([2, 4]), [0.0, 1.0])
          and seqclose(m.normalize([3, 3]), [0.5, 0.5]))
    check("B5_rolling_max", lambda: m.rolling_max([1, 5, 2, 1], 2) == [1, 5, 5, 2]
          and m.rolling_max([3, 1, 4, 1, 5], 3) == [3, 3, 4, 4, 5])
    check("B6_top_k", lambda: m.top_k([1, 9, 5, 7], 2) == [9, 7]
          and m.top_k([4, 2], 5) == [4, 2])
    check("B7_merge_unsorted", lambda: m.merge_intervals([[5, 6], [1, 3], [2, 4]]) == [[1, 4], [5, 6]]
          or m.merge_intervals([[5, 6], [1, 3], [2, 4]]) == [(1, 4), (5, 6)])
    check("B8_ewma", lambda: seqclose(m.ewma([0, 10], 0.5), [0, 5.0])
          and seqclose(m.ewma([2, 2, 8], 0.5), [2, 2, 5.0]))

    # Regressions (already-correct behavior must survive)
    check("R1_mean_basic", lambda: close(m.mean([1, 2, 3]), 2.0))
    check("R2_median_odd", lambda: m.median([3, 1, 2]) == 2)
    check("R3_count_above", lambda: m.count_above([1, 5, 5, 9], 5) == 1)
    check("R4_argmax_first", lambda: m.argmax([1, 7, 7, 2]) == 1)
    check("R5_merge_touching", lambda: m.merge_intervals([[1, 2], [2, 3]]) == [[1, 3]]
          or m.merge_intervals([[1, 2], [2, 3]]) == [(1, 3)])
    check("R6_rolling_w1", lambda: m.rolling_max([4, 2, 9], 1) == [4, 2, 9])

    bugs = [k for k in results if k.startswith("B")]
    regs = [k for k in results if k.startswith("R")]
    out = {
        "bugs_fixed": sum(results[k] for k in bugs),
        "bugs_total": len(bugs),
        "regressions_passed": sum(results[k] for k in regs),
        "regressions_total": len(regs),
        "detail": results,
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
