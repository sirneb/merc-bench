#!/usr/bin/env python3
"""Pilot a candidate task package against a list of model configs.

Reuses the shipped runner's Claude Code path (same CLI flags, validation,
retries, provenance capture and pricing) so pilot numbers are directly
comparable with results/runs. Records land in <candidate>/<outdir>/ using the
results-format shape plus a `score`/`total` pair from the candidate's grader.

Usage:
  python3 candidates/pilot.py candidates/simulation-3 \
      --configs sonnet:claude-sonnet-5:low,medium opus55:claude-opus-5-5:low,medium \
      --reps 3 --workers 4 --outdir pilot2
  python3 candidates/pilot.py candidates/simulation-3 --table   # summarise outdir
"""
import argparse
import concurrent.futures as cf
import glob
import importlib.util
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "runner"))
sys.path.insert(0, os.path.join(ROOT, "tasks"))
import run as runner  # noqa: E402


def load_grader(cdir):
    sys.path.insert(0, cdir)
    spec = importlib.util.spec_from_file_location("cand_grade", os.path.join(cdir, "grade.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def grade_answer(grader, ans):
    if isinstance(ans, str):
        try:
            ans = json.loads(ans)
        except Exception:
            ans = {"_text": ans}
    if not isinstance(ans, dict):
        ans = {}
    try:
        score, total, detail = grader.grade(ans)
    except Exception as e:
        score, total, detail = 0, 0, {"grade_error": str(e)[:200]}
    return score, total, detail


def one_run(cdir, slug, prompt, schema, family, model, effort, rep, outdir):
    fname = f"{slug}_{family}_{effort}_r{rep}.json"
    path = os.path.join(cdir, outdir, fname)
    if os.path.exists(path):
        rec = json.load(open(path))
        if not rec.get("invalid"):
            return rec
    # CLI_ATTEMPTS is module-global in the runner; give each worker its own list.
    attempts = []
    runner.CLI_ATTEMPTS = attempts
    answer, usage, dur, n_att, fail = runner.attempt_with_retries(
        runner.run_claude_code, model, effort, prompt, schema)
    notes = []
    if fail:
        notes.append(f"answer failed validation after {n_att} attempts: {fail}")
    elif n_att > 1:
        notes.append(f"validated after {n_att} attempts (usage includes retries)")
    rec = {
        "task": slug, "model": model, "family": family, "effort": effort,
        "sample": f"r{rep}", "harness": "claude-code",
        "date": time.strftime("%Y-%m-%d"), "answer": answer, "usage": usage,
        "duration_s": round(dur, 1),
        "cost_usd": runner.cost_usd(usage, family, "claude-code"),
        "cost_basis": "standard list prices, USD/MTok",
        "cost_estimated": usage is None, "notes": "",
    }
    if fail:
        rec["invalid"] = True
    if attempts:
        served = sorted({m for a in attempts for m in a["served"]})
        rec["cli"] = {"attempts": attempts, "served_models": served,
                      "total_cost_usd": round(sum(a["total_cost_usd"] or 0 for a in attempts), 4)}
        if any(a["stop_reason"] == "refusal" for a in attempts):
            notes.append("attempt(s) ended with stop_reason=refusal")
        if any(a["num_turns"] and a["num_turns"] > 1 for a in attempts):
            notes.append("multi-turn continuation (output cap hit)")
        wrong = [m for m in served if m != model]
        if wrong:
            rec["invalid"] = True
            notes.append(f"served by {','.join(wrong)} instead of {model} (harness fallback)")
    rec["notes"] = "; ".join(notes)
    return rec, path


def table(cdir, outdir):
    rows = {}
    for f in sorted(glob.glob(os.path.join(cdir, outdir, "*.json"))):
        r = json.load(open(f))
        if "score" not in r:
            continue
        k = f"{r['family']}@{r['effort']}"
        rows.setdefault(k, []).append(r)
    print(f"{'config':18}{'n':>3}{'valid':>6}{'mean%':>7}{'min':>6}{'max':>6}{'P(clean)':>9}"
          f"{'med $':>8}{'med s':>7}{'out tok':>9}")
    for k, rs in rows.items():
        valid = [r for r in rs if not r.get("invalid")]
        if not valid:
            print(f"{k:18}{len(rs):>3}{0:>6}  (all invalid)")
            continue
        pct = [100 * r["score"] / r["total"] for r in valid if r["total"]]
        clean = sum(1 for r in valid if r["score"] == r["total"]) / len(valid)
        print(f"{k:18}{len(rs):>3}{len(valid):>6}{statistics.mean(pct):>7.1f}"
              f"{min(pct):>6.0f}{max(pct):>6.0f}{clean:>9.2f}"
              f"{statistics.median(r['cost_usd'] or 0 for r in valid):>8.2f}"
              f"{statistics.median(r['duration_s'] or 0 for r in valid):>7.0f}"
              f"{statistics.median((r.get('usage') or {}).get('output', 0) for r in valid):>9.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--configs", nargs="*", default=[],
                    help="family:model_id:effort[,effort...]")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--outdir", default="pilot2")
    ap.add_argument("--table", action="store_true", help="only print the summary table")
    args = ap.parse_args()
    cdir = os.path.abspath(args.candidate)
    slug = os.path.basename(cdir)
    if args.table:
        table(cdir, args.outdir)
        return
    os.makedirs(os.path.join(cdir, args.outdir), exist_ok=True)
    prompt = open(os.path.join(cdir, "prompt.txt")).read()
    schema = json.load(open(os.path.join(cdir, "schema.json")))
    grader = load_grader(cdir)
    jobs = []
    for spec in args.configs:
        fam, model, efforts = spec.split(":")
        for e in efforts.split(","):
            for rep in range(1, args.reps + 1):
                jobs.append((fam, model, e, rep))
    print(f"[{slug}] {len(jobs)} runs, {args.workers} workers", flush=True)

    def work(j):
        fam, model, e, rep = j
        res = one_run(cdir, slug, prompt, schema, fam, model, e, rep, args.outdir)
        if isinstance(res, dict):
            return f"{fam}@{e} r{rep}: cached {res.get('score')}/{res.get('total')}"
        rec, path = res
        score, total, detail = grade_answer(grader, rec.get("answer"))
        rec.update({"score": score, "total": total, "grade_detail": detail})
        json.dump(rec, open(path, "w"), indent=1)
        flag = " INVALID" if rec.get("invalid") else ""
        return (f"{fam}@{e} r{rep}: {score}/{total}{flag} ${rec['cost_usd']} "
                f"{rec['duration_s']}s out={(rec.get('usage') or {}).get('output')} {rec['notes']}")

    with cf.ThreadPoolExecutor(args.workers) as ex:
        for line in ex.map(work, jobs):
            print(f"[{slug}] {line}", flush=True)
    table(cdir, args.outdir)


if __name__ == "__main__":
    main()
