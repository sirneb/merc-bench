#!/usr/bin/env python3
"""Generate the MERC report (site/report.html) from graded results.

Data-driven sections (regenerate automatically as results change):
  masthead stats, KPI floors, cost-vs-time scatter, the saturation map,
  per-task cards (from tasks/*/README.md).
Editorial sections (curated prose in report/fragments/*.html — update by hand
when the data changes materially): findings, method, decision charts,
external-claims scoreboard, limits.

Usage: python report/generate.py   ->  site/report.html
"""
import glob
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAG = os.path.join(ROOT, "report", "fragments")
CFG = json.load(open(os.path.join(ROOT, "report", "config.json")))
CORE = ["T1", "T2", "T3", "T4", "T5A", "T6", "T7", "T8", "T9", "T10"]
EXTRA = ["E", "T5B"]
TOTALS = {"T1": 16, "T2": 8, "T3": 6, "T4": 10, "T5A": 3, "T6": 13, "T7": 20,
          "T8": 8, "T9": 7, "T10": 7, "E": 5, "T5B": 6}
EFFORT_ORDER = ["none", "low", "medium", "high", "xhigh", "max"]


def config_sort_key(cfg):
    fam, eff = cfg.split("@")
    fams = [m["family"] for m in CFG["models"]]
    return (fams.index(fam) if fam in fams else 99,
            EFFORT_ORDER.index(eff) if eff in EFFORT_ORDER else 99)


def model_meta(fam):
    for m in CFG["models"]:
        if m["family"] == fam:
            return m
    return {"family": fam, "name": fam, "color": "var(--muted)",
            "price": "", "note": "community-added model"}


def cell(c, total):
    if c is None:
        return '<div class="cell na">—</div>'
    lo, hi, n = c["score_min"], c["score_max"], c["n"]
    txt = f"{lo}" if lo == hi else f"{lo}–{hi}"
    if lo == total and hi == total:
        klass = ""
    elif lo < 0:
        klass = " bad"
        txt = "✗"
    elif lo <= total * 0.6:
        klass = " bad"
        txt = f"{txt}"
    else:
        klass = " miss"
    return f'<div class="cell{klass}">{txt}</div>'


def build_map(summary):
    configs = sorted(summary.keys(), key=config_sort_key)
    rows = []
    floors = {}
    sweep_stats = {}
    last_fam = None
    for cfg in configs:
        fam, eff = cfg.split("@")
        tasks = summary[cfg]
        covered = [t for t in CORE if t in tasks]
        perfect = (len(covered) == len(CORE)
                   and all(tasks[t]["score_min"] == TOTALS[t] for t in CORE))
        tot_cost = sum((tasks[t]["cost_usd"] or 0) for t in covered)
        tot_dur = sum((tasks[t]["duration_s"] or 0) for t in covered)
        approx = any(tasks[t]["cost_usd"] is None for t in covered) or \
            any(tasks[t].get("cost_estimated") for t in covered)
        if perfect:
            sweep_stats[cfg] = (tot_cost, tot_dur)
            if fam not in floors or tot_cost < floors[fam][1]:
                floors[fam] = (cfg, tot_cost, tot_dur)
        meta = model_meta(fam)
        if fam != last_fam:
            rows.append(f'<div class="rl grp" style="color:{meta["color"]}">'
                        f'{html.escape(meta["name"])} · {meta["price"]}</div>')
            last_fam = fam
        star = " ★" if perfect else ""
        label = f'<b>@{eff}{star}</b>' if perfect else f'@{eff}'
        n_note = ""
        ns = {tasks[t]["n"] for t in covered} if covered else set()
        if ns and max(ns) > 1:
            n_note = f' <span style="color:var(--muted)">(n≤{max(ns)})</span>'
        cells = "".join(cell(tasks.get(t), TOTALS[t]) for t in CORE)
        cells += "".join(cell(tasks.get(t), TOTALS[t]) for t in EXTRA)
        cost_txt = (f"{'≈' if approx else ''}{tot_cost:.2f}"
                    if len(covered) == len(CORE) else "—")
        dur_txt = f"{tot_dur/60:.0f}m" if tot_dur and len(covered) == len(CORE) else "—"
        win = ' win' if fam in floors and floors[fam][0] == cfg else ''
        rows.append(f'<div class="rl">{label}{n_note}</div>{cells}'
                    f'<div class="cell stat{win}">{cost_txt}</div>'
                    f'<div class="cell stat">{dur_txt}</div>')
    return "\n".join(rows), floors, sweep_stats


def build_scatter(sweep_stats, summary):
    """Scatter of full-coverage configs: x=cost of 10 core batteries, y=time."""
    pts = []
    for cfg in sorted(summary.keys(), key=config_sort_key):
        tasks = summary[cfg]
        covered = [t for t in CORE if t in tasks]
        if len(covered) != len(CORE):
            continue
        cost = sum((tasks[t]["cost_usd"] or 0) for t in covered)
        dur = sum((tasks[t]["duration_s"] or 0) for t in covered) / 60
        dropped = sum(TOTALS[t] - tasks[t]["score_min"] for t in covered
                      if tasks[t]["score_min"] >= 0)
        failed = any(tasks[t]["score_min"] < 0 for t in covered)
        pts.append((cfg, cost, dur, dropped, failed, cfg in sweep_stats))
    max_c = max(p[1] for p in pts) * 1.15 or 1
    max_d = max(p[2] for p in pts) * 1.15 or 1

    placed = []  # (x0, y0, x1, y1) of claimed label boxes + point discs

    def claim(x, y, w, h):
        box = (x, y, x + w, y + h)
        for b in placed:
            if box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1]:
                return None
        placed.append(box)
        return box

    def place_label(px, py, text):
        w = len(text) * 6.2 + 4
        # candidates: above, below, right, left, then vertical nudges
        cands = [(px - w / 2, py - 24, "middle", px),
                 (px - w / 2, py + 12, "middle", px),
                 (px + 12, py - 6, "start", px + 14),
                 (px - w - 12, py - 6, "end", px - 14)]
        for dy in range(1, 12):
            cands.append((px - w / 2, py - 24 - dy * 9, "middle", px))
            cands.append((px - w / 2, py + 12 + dy * 9, "middle", px))
        for bx, by, anchor, tx in cands:
            if bx < 2 or bx + w > 718 or by < 12 or by + 11 > 372:
                continue
            if claim(bx, by, w, 11):
                return tx, by + 9, anchor, by + 9
        return px, py - 16, "middle", py - 16  # fallback: accept overlap

    coords = []
    for cfg, cost, dur, dropped, failed, perfect in pts:
        x = 60 + (cost / max_c) * 640
        y = 360 - (dur / max_d) * 340
        claim(x - 13, y - 13, 26, 26)  # reserve the disc + ring area
        coords.append((cfg, cost, dur, dropped, failed, perfect, x, y))

    svg = ['<svg viewBox="0 0 720 400" role="img" aria-label="cost vs time">']
    svg.append('<line class="grid" x1="60" y1="360" x2="700" y2="360"></line>')
    svg.append('<line class="grid" x1="60" y1="20" x2="60" y2="360"></line>')
    svg.append(f'<text class="axis" x="380" y="392" text-anchor="middle">'
               f'total cost, {len(CORE)} core tasks (USD) · hover a point for its stats</text>')
    svg.append('<text class="axis" x="18" y="190" transform="rotate(-90 18 190)" '
               'text-anchor="middle">total wall-clock (minutes)</text>')
    for cfg, cost, dur, dropped, failed, perfect, x, y in coords:
        fam = cfg.split("@")[0]
        color = model_meta(fam)["color"]
        note = "perfect sweep" if perfect else (f"−{dropped} pts" if not failed
                                               else "incl. failure")
        stats = f"${cost:.2f} · {dur:.0f} min · {note}"
        label = f"★ {cfg}" if perfect else cfg
        lx, ly, anchor, _ = place_label(x, y, label)
        ring = (f'<circle cx="{x:.0f}" cy="{y:.0f}" r="11" fill="none" '
                f'stroke="{color}" stroke-width="1.5"></circle>') if perfect else ""
        disc = (f'<circle class="dot" cx="{x:.0f}" cy="{y:.0f}" r="6" '
                f'fill="{color}"></circle>' if perfect else
                f'<circle class="dot" cx="{x:.0f}" cy="{y:.0f}" r="5.5" '
                f'fill="{color}" fill-opacity=".18" stroke="{color}" '
                f'stroke-width="1.4"></circle>')
        leader = ""
        if abs(ly - y) > 30:
            ey = ly + 2 if ly < y else ly - 9
            leader = (f'<line class="leader" x1="{x:.0f}" y1="{y:.0f}" '
                      f'x2="{lx:.0f}" y2="{ey:.0f}"></line>')
        svg.append(
            f'{leader}<g class="pt" data-stats="{html.escape(stats)}" '
            f'data-cfg="{html.escape(cfg)}">'
            f'<circle class="hit" cx="{x:.0f}" cy="{y:.0f}" r="14" fill="transparent"></circle>'
            f'{disc}{ring}'
            f'<text class="pt-label{" perf" if perfect else ""}" x="{lx:.0f}" y="{ly:.0f}" '
            f'text-anchor="{anchor}" fill="{color}">{html.escape(label)}</text></g>')
    svg.append("</svg>")
    return "\n".join(svg)


def build_cards():
    cards = []
    for d in sorted(glob.glob(os.path.join(ROOT, "tasks", "*", "README.md"))):
        md = open(d).read()
        title = re.search(r"^# (.+)$", md, re.M).group(1)
        sub = md.split("\n\n")[1].strip()
        why = re.search(r"## What it tests and why\n\n(.+?)\n\n", md, re.S)
        found = re.search(r"## What we found\n\n(.+?)\s*$", md, re.S)
        cards.append(
            f'<div class="tcard"><div class="tname">{html.escape(title)}</div>'
            f'<p><b>Design</b>{html.escape(sub)}</p>'
            f'<p><b>Why</b>{html.escape(why.group(1)) if why else ""}</p>'
            f'<p><b>Found</b>{html.escape(found.group(1)) if found else ""}</p></div>')
    return "\n".join(cards)


def main():
    summary = json.load(open(os.path.join(ROOT, "results", "summary.json")))
    scores = open(os.path.join(ROOT, "results", "scores.csv")).read().count("\n") - 1
    total_cost = 0.0
    for cfg, tasks in summary.items():
        for t, c in tasks.items():
            if c["cost_usd"]:
                total_cost += c["cost_usd"] * c["n"]
    map_html, floors, sweeps = build_map(summary)
    scatter = build_scatter(sweeps, summary)
    cards = build_cards()
    floor_html = " · ".join(
        f'<b>{html.escape(model_meta(f)["name"])}</b> {cfg.split("@")[1]} '
        f'(${c:.2f}/{d/60:.0f}m)'
        for f, (cfg, c, d) in sorted(
            floors.items(), key=lambda kv: [m["family"] for m in CFG["models"]].index(kv[0])
            if kv[0] in [m["family"] for m in CFG["models"]] else 99))

    def frag(name):
        p = os.path.join(FRAG, name)
        return open(p).read() if os.path.exists(p) else ""

    tpl = open(os.path.join(ROOT, "report", "template.html")).read()
    out = (tpl
           .replace("{{RUN_COUNT}}", str(scores))
           .replace("{{TOTAL_COST}}", f"{total_cost:.0f}")
           .replace("{{DATE}}", CFG.get("dates", ""))
           .replace("{{FLOORS}}", floor_html)
           .replace("{{SCATTER}}", scatter)
           .replace("{{MAP}}", map_html)
           .replace("{{CARDS}}", cards)
           .replace("{{FINDINGS}}", frag("findings.html"))
           .replace("{{METHOD}}", frag("method.html"))
           .replace("{{DECISIONS}}", frag("decisions.html"))
           .replace("{{SCOREBOARD}}", frag("scoreboard.html"))
           .replace("{{LIMITS}}", frag("limits.html")))
    os.makedirs(os.path.join(ROOT, "site"), exist_ok=True)
    dest = os.path.join(ROOT, "site", "report.html")
    open(dest, "w").write(out)
    print(f"wrote {dest} ({len(out)} bytes) — {scores} runs, "
          f"{len(summary)} configs, floors: " +
          ", ".join(f"{f}:{v[0]}" for f, v in floors.items()))


if __name__ == "__main__":
    main()
