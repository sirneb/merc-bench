#!/usr/bin/env python3
"""Grader for T9. Usage: python grade.py <run-record.json>
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
    spec = importlib.util.spec_from_file_location("sol_t9_" + str(id(path)), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Clk:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _main(path):
    
    results, errors = {}, {}

    def check(name, fn):
        try:
            results[name] = bool(fn())
        except Exception as e:
            results[name] = False
            errors[name] = f"{type(e).__name__}: {e}"

    def p1():  # limit enforced at exactly `limit`
        m = load(path); c = Clk()
        sw = m.SlidingWindowLimiter(1, 10, clock=c)
        a = sw.allow("k")
        c.t += 5
        return a is True and sw.allow("k") is False

    def p2():  # third event under limit 2 denied
        m = load(path); c = Clk()
        sw = m.SlidingWindowLimiter(2, 10, clock=c)
        r = [sw.allow("k")]
        c.t += 1; r.append(sw.allow("k"))
        c.t += 1; r.append(sw.allow("k"))
        return r == [True, True, False]

    def p3():  # event exactly window old is expired (via retry_after)
        m = load(path); c = Clk()
        sw = m.SlidingWindowLimiter(2, 10, clock=c)
        sw.allow("k")          # t=100
        c.t = 104; sw.allow("k")
        c.t = 110              # first event exactly 10s old -> expired
        return sw.retry_after("k") == 0.0

    def p4():  # retry_after based on OLDEST event
        m = load(path); c = Clk()
        sw = m.SlidingWindowLimiter(2, 10, clock=c)
        sw.allow("k")          # t=100
        c.t = 106; sw.allow("k")
        c.t = 107
        return abs(sw.retry_after("k") - 3.0) < 1e-9

    def p5():  # fractional refill accrues
        m = load(path); c = Clk()
        tb = m.TokenBucket(5, 1, clock=c)
        tb.take("k", 5)
        c.t += 0.5
        return abs(tb.tokens("k") - 0.5) < 1e-9

    def p6():  # never exceeds capacity after long idle
        m = load(path); c = Clk()
        tb = m.TokenBucket(5, 1, clock=c)
        tb.take("k", 5)
        c.t += 100
        return abs(tb.tokens("k") - 5.0) < 1e-9

    def p7():  # buckets independent across instances
        m = load(path); c = Clk()
        t1 = m.TokenBucket(3, 1, clock=c)
        t1.take("shared", 3)
        t2 = m.TokenBucket(3, 1, clock=c)
        return abs(t2.tokens("shared") - 3.0) < 1e-9

    def r1():  # fresh bucket starts full
        m = load(path); c = Clk()
        tb = m.TokenBucket(4, 2, clock=c)
        return abs(tb.tokens("fresh") - 4.0) < 1e-9

    def r2():  # allow under limit
        m = load(path); c = Clk()
        sw = m.SlidingWindowLimiter(3, 10, clock=c)
        return sw.allow("k") and sw.allow("k")

    def r3():  # slot frees after window fully passes
        m = load(path); c = Clk()
        sw = m.SlidingWindowLimiter(1, 10, clock=c)
        sw.allow("k")
        c.t += 10.1
        return sw.allow("k") is True

    def r4():  # insufficient tokens -> False, nothing removed
        m = load(path); c = Clk()
        tb = m.TokenBucket(2, 1, clock=c)
        ok = tb.take("k", 3)
        return ok is False and abs(tb.tokens("k") - 2.0) < 1e-9

    def r5():  # init validation
        m = load(path)
        try:
            m.SlidingWindowLimiter(0, 10)
            return False
        except ValueError:
            pass
        try:
            m.TokenBucket(0, 1)
            return False
        except ValueError:
            return True

    for name, fn in [("P1_limit_boundary", p1), ("P2_overflow", p2),
                     ("P3_window_exact_expiry", p3), ("P4_retry_oldest", p4),
                     ("P5_fractional_refill", p5), ("P6_capacity_clamp", p6),
                     ("P7_instance_isolation", p7),
                     ("R1_fresh_full", r1), ("R2_allow_basic", r2),
                     ("R3_window_frees", r3), ("R4_insufficient", r4),
                     ("R5_validation", r5)]:
        check(name, fn)

    bugs = sum(v for k, v in results.items() if k.startswith("P"))
    regs = sum(v for k, v in results.items() if k.startswith("R"))
    return bugs, results




def grade(ans):
    code = html.unescape(ans.get("fixed_code", "") or "")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    bugs, results = _main(path)
    os.unlink(path)
    return bugs, 7, {k: v for k, v in results.items() if not v}


if __name__ == "__main__":
    _, ans = load_answer(sys.argv[1])
    s, t, d = grade(ans)
    emit("T9", s, t, d)
