"""Shared grading helpers."""
import json
import re
import sys


def load_answer(path):
    rec = json.load(open(path))
    ans = rec.get("answer")
    if isinstance(ans, str):
        try:
            ans = json.loads(ans)
        except Exception:
            ans = {"_text": ans}
    return rec, (ans if isinstance(ans, dict) else {})


def emit(task, score, total, detail):
    print(json.dumps({"task": task, "score": score, "total": total,
                      "detail": detail}))


def norm(s):
    return re.sub(r"[\s,]+", " ", str(s).strip().lower()).strip()


def numeq(a, b, tol=0.005):
    try:
        return abs(float(str(a).replace(",", "")) - float(b)) <= tol
    except Exception:
        return False
