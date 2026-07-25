"""Grader for Task B (TTLLRUCache build-to-spec).

Usage: python3 grade_b.py <path-to-module.py>
Prints JSON with per-test pass/fail and totals.
"""
import importlib.util
import json
import sys


def load(path):
    spec = importlib.util.spec_from_file_location("ttl_lru_impl", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def main():
    m = load(sys.argv[1])
    C = m.TTLLRUCache
    results = {}

    def check(name, fn):
        try:
            results[name] = bool(fn())
        except Exception as e:
            results[name] = False
            results.setdefault("_errors", {})[name] = f"{type(e).__name__}: {e}"

    def t01():
        clk = FakeClock()
        c = C(2, clock=clk)
        c.put("a", 1)
        c.put("b", 2)
        return c.get("a") == 1 and c.get("b") == 2

    def t02():  # LRU eviction order
        clk = FakeClock()
        c = C(2, clock=clk)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")            # a becomes MRU
        c.put("c", 3)         # evicts b
        ok_b = False
        try:
            c.get("b")
        except KeyError:
            ok_b = True
        return ok_b and c.get("a") == 1 and c.get("c") == 3

    def t03():  # put existing key refreshes recency
        clk = FakeClock()
        c = C(2, clock=clk)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 10)        # a MRU
        c.put("c", 3)         # evicts b
        return "b" not in c and c.get("a") == 10

    def t04():  # missing key raises KeyError + miss counted
        clk = FakeClock()
        c = C(2, clock=clk)
        try:
            c.get("nope")
            return False
        except KeyError:
            return c.stats()["misses"] == 1

    def t05():  # ttl expiry via get
        clk = FakeClock()
        c = C(2, default_ttl=10, clock=clk)
        c.put("a", 1)
        clk.advance(10)       # boundary: clock() >= inserted+ttl -> expired
        try:
            c.get("a")
            return False
        except KeyError:
            s = c.stats()
            return s["expirations"] == 1 and s["misses"] == 1

    def t06():  # per-entry ttl overrides default
        clk = FakeClock()
        c = C(2, default_ttl=5, clock=clk)
        c.put("a", 1, ttl=20)
        clk.advance(10)
        return c.get("a") == 1

    def t07():  # default_ttl None -> never expires
        clk = FakeClock()
        c = C(2, clock=clk)
        c.put("a", 1)
        clk.advance(10**6)
        return c.get("a") == 1

    def t08():  # update resets expiry from now
        clk = FakeClock()
        c = C(2, default_ttl=10, clock=clk)
        c.put("a", 1)
        clk.advance(8)
        c.put("a", 2)
        clk.advance(8)        # 16s after first put, 8 after refresh
        return c.get("a") == 2

    def t09():  # contains: no recency update, no hit/miss counting
        clk = FakeClock()
        c = C(2, clock=clk)
        c.put("a", 1)
        c.put("b", 2)
        _ = "a" in c          # must NOT make a MRU
        c.put("c", 3)         # evicts a (contains didn't touch recency)
        s = c.stats()
        return "a" not in c and s["hits"] == 0 and s["misses"] == 0

    def t10():  # len purges expired and counts expirations
        clk = FakeClock()
        c = C(3, default_ttl=5, clock=clk)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3, ttl=100)
        clk.advance(6)
        n = len(c)
        return n == 1 and c.stats()["expirations"] == 2

    def t11():  # expired entries purged before evicting live ones
        clk = FakeClock()
        c = C(2, clock=clk)
        c.put("a", 1, ttl=5)
        c.put("b", 2)
        clk.advance(6)        # a expired
        c.put("c", 3)         # should purge a, NOT evict b
        s = c.stats()
        return c.get("b") == 2 and c.get("c") == 3 and s["evictions"] == 0 \
            and s["expirations"] == 1

    def t12():  # eviction counting
        clk = FakeClock()
        c = C(1, clock=clk)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        s = c.stats()
        return s["evictions"] == 2 and s["expirations"] == 0

    def t13():  # capacity validation
        try:
            C(0)
            return False
        except ValueError:
            return True

    def t14():  # hit counting
        clk = FakeClock()
        c = C(2, clock=clk)
        c.put("a", 1)
        c.get("a")
        c.get("a")
        try:
            c.get("x")
        except KeyError:
            pass
        s = c.stats()
        return s["hits"] == 2 and s["misses"] == 1

    for i, fn in enumerate([t01, t02, t03, t04, t05, t06, t07, t08, t09,
                            t10, t11, t12, t13, t14], 1):
        check(f"t{i:02d}", fn)

    passed = sum(v for k, v in results.items() if k.startswith("t"))
    print(json.dumps({"passed": passed, "total": 14, "detail": results}, indent=1))


if __name__ == "__main__":
    main()
