#!/usr/bin/env python3
"""eval_dashboard.py — Build the RCA agent quality dashboard as a single
self-contained HTML file + a machine-readable dashboard_data.json.

Stdlib-only (no duckdb, no network, no CDN) so it runs on any machine —
including the ClineSR (Samsung) + VS Code on Windows user machines — straight
from the eval record files. On the aggregation machine point it at the synced
outbox/scores/coverage folders.

Metrics and gates implement evaluation/criteria/rca-agent-scoring-criteria.md
(metric IDs M-xx / J-x, composite RQS section 4, fleet gates section 5).

Usage:
    python eval_dashboard.py --records DIR [--records DIR ...]
                             [--scores DIR ...] [--coverage DIR ...]
                             [--out dashboard.html] [--json dashboard_data.json]
                             [--gate]      # exit 3 if any fleet gate fails

Typical:
    python eval_dashboard.py --records .rca/eval/outbox --records .rca/eval/ingested \\
        --scores .rca/eval/scores --coverage .rca/eval/coverage \\
        --out .rca/eval/dashboard.html --json .rca/eval/dashboard_data.json
"""

import argparse
import glob
import html
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_score import compute_scorecard, JUDGE_DIMENSIONS  # noqa: E402

# Fleet gates — criteria doc section 5. Changing a threshold = PR review (IN-8).
GATES = [
    ("G-1", "agreement_rate", "Agreement rate (Checkpoint B)", 0.70, ">=", True),
    ("G-2", "rank1_acceptance", "Rank-1 acceptance (Checkpoint A)", 0.60, ">=", True),
    ("G-3", "provenance_pass", "Provenance pass rate", 1.00, ">=", True),
    ("G-4", "golden_l1", "Golden accuracy L1 (class)", 0.80, ">=", True),
    ("G-5", "golden_l2", "Golden accuracy L2 (file)", 0.60, ">=", True),
    ("G-6", "reopen_rate", "Re-open rate", 0.10, "<=", True),
    ("G-7", "judge_overall", "Judge overall (LLM, 1-5)", 3.5, ">=", False),
    ("G-8", "coverage_rate", "Extraction coverage", 1.00, ">=", True),
]


# ---------------------------------------------------------------- loading

def load_records(dirs):
    by_run = {}
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "eval_*.json"))):
            try:
                with open(path, encoding="utf-8") as f:
                    rec = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            rid = rec.get("run_id")
            if not rid:
                continue
            prev = by_run.get(rid)
            if not prev or (rec.get("extracted_at") or "") >= (prev.get("extracted_at") or ""):
                by_run[rid] = rec
    return by_run


def load_scores(dirs):
    """run_id -> {"llm": payload, "human": payload}"""
    out = defaultdict(dict)
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "scores_*.json"))):
            try:
                with open(path, encoding="utf-8") as f:
                    payload = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            rid = payload.get("run_id")
            if not rid:
                continue
            kind = "human" if payload.get("judge_model") == "human" else "llm"
            out[rid][kind] = payload
    return out


def load_coverage(dirs):
    """Latest coverage report per machine."""
    latest = {}
    for d in dirs:
        for path in glob.glob(os.path.join(d, "coverage_*.json")):
            if os.path.basename(path) == "coverage_latest.json":
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    rep = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            m = rep.get("machine_id", "?")
            if m not in latest or (rep.get("sweep_at") or "") > (latest[m].get("sweep_at") or ""):
                latest[m] = rep
    return latest


# ------------------------------------------------------------- aggregation

def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def _week(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except ValueError:
        return None


def aggregate(records, scores, coverage):
    runs = []
    for rid, rec in sorted(records.items()):
        llm = (scores.get(rid) or {}).get("llm")
        card = compute_scorecard(rec, (llm or {}).get("scores"))
        dec = rec.get("decisions") or {}
        prov = rec.get("provenance") or {}
        gold = rec.get("golden") or {}
        runs.append({
            "run_id": rid,
            "machine_id": rec.get("machine_id"),
            "started_at": rec.get("started_at"),
            "week": _week(rec.get("started_at")),
            "outcome": rec.get("outcome"),
            "duration_min": round(rec["duration_s"] / 60, 1) if rec.get("duration_s") else None,
            "agreement_rate": dec.get("agreement_rate"),
            "rank1_accepted": (rec.get("checkpoint_a") or {}).get("rank1_accepted"),
            "provenance_pass_rate": prov.get("pass_rate"),
            "high_disagreement": dec.get("high_disagreement_run"),
            "golden_case_id": gold.get("case_id"),
            "golden_class_match": gold.get("class_match"),
            "golden_file_match": gold.get("file_match"),
            "reopened": (rec.get("amendments") or {}).get("reopened"),
            "judge_scored": llm is not None,
            "judge_overall": (
                round(_mean([s["score"] for s in llm["scores"]]), 2) if llm and llm.get("scores") else None
            ),
            "rqs": card["rqs"],
            "grade": card["grade"],
            "provisional": card["provisional"],
            "needs_human_review": card["needs_human_review"],
            "caps_applied": card["caps_applied"],
        })

    complete = [r for r in runs if r["outcome"] == "complete"]
    scored = [r for r in runs if r["rqs"] is not None]
    judge_dims = {d: {"llm": [], "human": []} for d in JUDGE_DIMENSIONS}
    for rid in records:
        for kind in ("llm", "human"):
            payload = (scores.get(rid) or {}).get(kind)
            for s in (payload or {}).get("scores", []):
                if s.get("dimension") in judge_dims:
                    judge_dims[s["dimension"]][kind].append(s["score"])

    retro = [r for r in runs if r["reopened"] is not None]
    cov_rates = [c.get("coverage_rate") for c in coverage.values()]
    kpis = {
        "runs_total": len(runs),
        "runs_complete": len(complete),
        "runs_aborted": sum(1 for r in runs if r["outcome"] == "aborted"),
        "completion_rate": _mean([1.0 if r["outcome"] == "complete" else 0.0 for r in runs]),
        "agreement_rate": _mean([r["agreement_rate"] for r in runs]),
        "rank1_acceptance": _mean(
            [1.0 if r["rank1_accepted"] else 0.0 for r in runs if r["rank1_accepted"] is not None]),
        "provenance_pass": _mean([r["provenance_pass_rate"] for r in runs]),
        "golden_l1": _mean(
            [1.0 if r["golden_class_match"] else 0.0 for r in runs if r["golden_class_match"] is not None]),
        "golden_l2": _mean(
            [1.0 if r["golden_file_match"] else 0.0 for r in runs if r["golden_file_match"] is not None]),
        "reopen_rate": _mean([1.0 if r["reopened"] else 0.0 for r in retro]),
        "judge_overall": _mean([r["judge_overall"] for r in runs]),
        "judge_coverage": _mean([1.0 if r["judge_scored"] else 0.0 for r in complete]) if complete else None,
        "coverage_rate": _mean(cov_rates),
        "median_duration_min": _median([r["duration_min"] for r in complete]),
        "rqs_mean": _mean([r["rqs"] for r in scored]),
        "rqs_final_count": sum(1 for r in scored if not r["provisional"]),
        "rqs_provisional_count": sum(1 for r in scored if r["provisional"]),
    }

    gates = []
    failures = []
    for gid, key, label, threshold, op, pct in GATES:
        v = kpis.get(key)
        if v is None:
            status = "no data"
        else:
            ok = v >= threshold if op == ">=" else v <= threshold
            status = "pass" if ok else "fail"
            if not ok:
                failures.append(f"{gid} {label}")
        gates.append({"id": gid, "label": label, "value": v,
                      "threshold": threshold, "op": op, "pct": pct, "status": status})

    weekly = []
    by_week = defaultdict(list)
    for r in runs:
        if r["week"]:
            by_week[r["week"]].append(r)
    for wk in sorted(by_week)[-12:]:
        rs = by_week[wk]
        weekly.append({
            "week": wk,
            "runs": len(rs),
            "agreement_rate": _mean([r["agreement_rate"] for r in rs]),
            "rank1_acceptance": _mean(
                [1.0 if r["rank1_accepted"] else 0.0 for r in rs if r["rank1_accepted"] is not None]),
            "rqs_mean": _mean([r["rqs"] for r in rs if r["rqs"] is not None]),
        })

    machines = []
    by_machine = defaultdict(list)
    for r in runs:
        by_machine[r["machine_id"] or "?"].append(r)
    for m, rs in sorted(by_machine.items(), key=lambda kv: -len(kv[1])):
        cov = coverage.get(m, {})
        machines.append({
            "machine_id": m,
            "runs": len(rs),
            "agreement_rate": _mean([r["agreement_rate"] for r in rs]),
            "abort_rate": _mean([1.0 if r["outcome"] == "aborted" else 0.0 for r in rs]),
            "provenance_pass": _mean([r["provenance_pass_rate"] for r in rs]),
            "rqs_mean": _mean([r["rqs"] for r in rs if r["rqs"] is not None]),
            "coverage_rate": cov.get("coverage_rate"),
            "last_sweep": cov.get("sweep_at"),
        })

    grades = {g: sum(1 for r in runs if r["grade"] == g) for g in "ABCDF"}

    queue = []
    for r in runs:
        reasons = []
        if r["high_disagreement"]:
            reasons.append("high disagreement")
        if r["provenance_pass_rate"] is not None and r["provenance_pass_rate"] < 1.0:
            reasons.append("provenance < 100%")
        if r["outcome"] == "aborted":
            reasons.append("aborted")
        if any(c.startswith("judge_dimension") for c in r["caps_applied"]):
            reasons.append("judge dimension <= 2")
        if r["grade"] in ("D", "F"):
            reasons.append(f"grade {r['grade']}")
        if reasons:
            queue.append({"run_id": r["run_id"], "machine_id": r["machine_id"],
                          "reasons": reasons})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "criteria_version": "1.0",
        "kpis": kpis,
        "gates": gates,
        "gate_failures": failures,
        "weekly": weekly,
        "machines": machines,
        "grades": grades,
        "judge_dimensions": {
            d: {"llm": round(_mean(v["llm"]), 2) if v["llm"] else None,
                "human": round(_mean(v["human"]), 2) if v["human"] else None,
                "n_llm": len(v["llm"]), "n_human": len(v["human"])}
            for d, v in judge_dims.items()
        },
        "review_queue": queue,
        "runs": runs,
    }


# ------------------------------------------------------------------ charts

def _esc(s):
    return html.escape(str(s), quote=True)


def _fmt(v, pct=False, digits=2):
    if v is None:
        return "—"
    return f"{v * 100:.0f}%" if pct else f"{v:.{digits}f}".rstrip("0").rstrip(".")


def _col_path(x, y, w, h, r=4):
    """Column with rounded top corners, square baseline (mark spec)."""
    if h <= r:
        return f"M{x},{y + h} v{-h} h{w} v{h} Z"
    return (f"M{x},{y + h} v{-(h - r)} q0,-{r} {r},-{r} h{w - 2 * r} "
            f"q{r},0 {r},{r} v{h - r} Z")


def columns_svg(labels, values, vmax, unit_pct=False, series_var="--series-1",
                height=200, tooltip_name="value", count_axis=False, ticks=None,
                slot=44):
    """Single-series column chart with hover tooltips + selective labels.
    count_axis=True rounds vmax up so quarter gridlines land on integers."""
    n = max(len(values), 1)
    pad_l, pad_r, pad_t, pad_b = 34, 8, 16, 26
    width = pad_l + pad_r + slot * n
    plot_h = height - pad_t - pad_b
    bw = min(24, slot - 20)
    if count_axis:
        vmax = max(4, -4 * (-int(vmax) // 4))  # ceil to a multiple of 4
    if ticks is None:
        ticks = [vmax * i / 4 for i in range(5)]
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'style="width:100%;max-width:{width * 1.6}px;height:auto">']
    for gv in ticks:
        gy = pad_t + plot_h * (1 - gv / vmax)
        lab = (f"{gv * 100:.0f}%" if unit_pct
               else f"{gv:.0f}" if count_axis else _fmt(gv, digits=1))
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 5}" y="{gy + 3:.1f}" text-anchor="end" '
                     f'class="axis">{lab}</text>')
    peak = max(range(len(values)), key=lambda i: values[i] or 0, default=0) if values else 0
    for i, (lab, v) in enumerate(zip(labels, values)):
        cx = pad_l + slot * i + slot / 2
        parts.append(f'<text x="{cx:.1f}" y="{height - 8}" text-anchor="middle" '
                     f'class="axis">{_esc(lab)}</text>')
        if v is None:
            continue
        h = plot_h * (v / vmax) if vmax else 0
        x = cx - bw / 2
        y = pad_t + plot_h - h
        val_lab = _fmt(v, unit_pct) if unit_pct else _fmt(v, digits=1)
        parts.append(f'<path d="{_col_path(x, y, bw, h)}" fill="var({series_var})" '
                     f'class="hit" tabindex="0" '
                     f'data-tt="{_esc(lab)}|{tooltip_name}: {val_lab}"/>')
        if i == peak and y - 5 > 8:
            parts.append(f'<text x="{cx:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
                         f'class="dlabel">{val_lab}</text>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - pad_r}" '
                 f'y2="{pad_t + plot_h}" stroke="var(--baseline)" stroke-width="1"/>')
    parts.append("</svg>")
    return "".join(parts)


def lines_svg(labels, series, height=220, unit_pct=True, vmax=1.0):
    """Multi-series line chart with crosshair-style hover bands.
    series: list of (name, css_var, values)."""
    n = max(len(labels), 1)
    pad_l, pad_r, pad_t, pad_b = 40, 14, 10, 26
    step = 58
    width = pad_l + pad_r + step * max(n - 1, 1)
    plot_h = height - pad_t - pad_b
    xs = [pad_l + step * i for i in range(n)] if n > 1 else [pad_l]

    def sy(v):
        return pad_t + plot_h * (1 - v / vmax)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'style="width:100%;max-width:{width * 1.5}px;height:auto">']
    for i in range(5):
        gy = pad_t + plot_h * i / 4
        gv = vmax * (1 - i / 4)
        lab = f"{gv * 100:.0f}%" if unit_pct else _fmt(gv, digits=1)
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 5}" y="{gy + 3:.1f}" text-anchor="end" '
                     f'class="axis">{lab}</text>')
    for i, lab in enumerate(labels):
        parts.append(f'<text x="{xs[i]:.1f}" y="{height - 8}" text-anchor="middle" '
                     f'class="axis">{_esc(lab)}</text>')
    for name, var, vals in series:
        pts = [(xs[i], sy(v)) for i, v in enumerate(vals) if v is not None]
        if len(pts) > 1:
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(f'<path d="{d}" fill="none" stroke="var({var})" '
                         f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var({var})" '
                         f'stroke="var(--surface)" stroke-width="2"/>')
    # hover bands: one per x, crosshair hairline + all-series tooltip
    for i, lab in enumerate(labels):
        rows = [f"{_esc(lab)}"]
        for name, _var, vals in series:
            v = vals[i] if i < len(vals) else None
            rows.append(f"{name}: {_fmt(v, unit_pct) if unit_pct else _fmt(v, digits=1)}")
        bx = xs[i] - step / 2 if n > 1 else pad_l - step / 2
        parts.append(
            f'<g class="band"><rect x="{bx:.1f}" y="{pad_t}" width="{step}" '
            f'height="{plot_h}" fill="transparent" class="hit" tabindex="0" '
            f'data-tt="{_esc("|".join(rows))}"/>'
            f'<line x1="{xs[i]:.1f}" y1="{pad_t}" x2="{xs[i]:.1f}" '
            f'y2="{pad_t + plot_h}" stroke="var(--baseline)" stroke-width="1" '
            f'class="hairline"/></g>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - pad_r}" '
                 f'y2="{pad_t + plot_h}" stroke="var(--baseline)" stroke-width="1"/>')
    parts.append("</svg>")
    return "".join(parts)


def legend_html(series):
    """series: list of (name, css_var, kind) — kind 'line' or 'rect'."""
    items = []
    for name, var, kind in series:
        swatch = (f'<span class="key-line" style="background:var({var})"></span>'
                  if kind == "line" else
                  f'<span class="key-rect" style="background:var({var})"></span>')
        items.append(f'<span class="key">{swatch}{_esc(name)}</span>')
    return f'<div class="legend">{"".join(items)}</div>'


def table_html(headers, rows):
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    trs = []
    for row in rows:
        tds = "".join(f"<td>{_esc(c) if c is not None else '—'}</td>" for c in row)
        trs.append(f"<tr>{tds}</tr>")
    return (f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def details_table(summary, headers, rows):
    return (f"<details><summary>{_esc(summary)}</summary>"
            f"{table_html(headers, rows)}</details>")


# -------------------------------------------------------------------- html

CSS = """
:root{
  --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --baseline:#c3c2b7;
  --border:rgba(11,11,11,.10);
  --series-1:#2a78d6; --series-2:#1baf7a; --series-3:#eda100;
  --series-5:#4a3aa7;
  --good:#0ca30c; --critical:#d03b3b; --warning:#fab219;
}
@media (prefers-color-scheme: dark){:root{
  --surface:#1a1a19; --page:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --baseline:#383835;
  --border:rgba(255,255,255,.10);
  --series-1:#3987e5; --series-2:#199e70; --series-3:#c98500;
  --series-5:#9085e9;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
  font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:20px}
h1{font-size:19px;margin:0 0 2px}
h2{font-size:15px;margin:26px 0 10px}
.sub{color:var(--ink2);font-size:12.5px;margin-bottom:18px}
.hero{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:18px 22px;display:flex;gap:28px;align-items:center;flex-wrap:wrap}
.hero .big{font-size:52px;font-weight:600;line-height:1}
.hero .hlabel{color:var(--ink2);font-size:12.5px;margin-bottom:4px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
  gap:10px;margin-top:12px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:11px 13px}
.tile .tlabel{color:var(--ink2);font-size:11.5px}
.tile .tval{font-size:21px;font-weight:600;margin-top:2px}
.tile .tgate{font-size:11px;color:var(--muted);margin-top:2px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:14px 16px;margin-top:10px;overflow-x:auto}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:10px}
.axis{font-size:10px;fill:var(--muted)}
.dlabel{font-size:10.5px;fill:var(--ink2)}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin:2px 0 8px;color:var(--ink2);
  font-size:12px;align-items:center}
.key{display:inline-flex;align-items:center;gap:6px}
.key-line{width:14px;height:2px;border-radius:1px;display:inline-block}
.key-rect{width:10px;height:10px;border-radius:2px;display:inline-block}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th{color:var(--ink2);font-weight:600;text-align:left}
th,td{padding:5px 10px;border-bottom:1px solid var(--grid);white-space:nowrap}
td{font-variant-numeric:tabular-nums}
.status{font-weight:600}
.status.pass{color:var(--good)} .status.fail{color:var(--critical)}
.status.nodata{color:var(--muted);font-weight:400}
details{margin-top:8px} summary{cursor:pointer;color:var(--ink2);font-size:12px}
.hit{outline:none} .hit:hover,.hit:focus{opacity:.85}
.band .hairline{opacity:0}
.band:hover .hairline,.band:focus-within .hairline{opacity:1}
#tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);
  border:1px solid var(--border);border-radius:6px;padding:7px 10px;font-size:12px;
  box-shadow:0 2px 10px rgba(0,0,0,.18);display:none;z-index:9;max-width:260px}
#tt .v{font-weight:600}
footer{color:var(--muted);font-size:11.5px;margin-top:26px}
"""

JS = """
const tt = document.getElementById('tt');
function showTT(el, x, y){
  const parts = (el.getAttribute('data-tt')||'').split('|');
  tt.replaceChildren();
  parts.forEach((p,i)=>{const d=document.createElement('div');
    if(i>0)d.className='v'; d.textContent=p; tt.appendChild(d);});
  tt.style.display='block';
  const r = tt.getBoundingClientRect();
  tt.style.left = Math.min(x+14, innerWidth-r.width-8)+'px';
  tt.style.top  = Math.min(y+14, innerHeight-r.height-8)+'px';
}
document.querySelectorAll('[data-tt]').forEach(el=>{
  el.addEventListener('pointermove', e=>showTT(el, e.clientX, e.clientY));
  el.addEventListener('pointerleave', ()=>tt.style.display='none');
  el.addEventListener('focus', ()=>{const r=el.getBoundingClientRect();
    showTT(el, r.left+r.width/2, r.top);});
  el.addEventListener('blur', ()=>tt.style.display='none');
});
"""


def build_html(data):
    k = data["kpis"]
    hero_val = _fmt(k["rqs_mean"], digits=1) if k["rqs_mean"] is not None else "—"
    gate_fail = len(data["gate_failures"])
    gate_total = sum(1 for g in data["gates"] if g["status"] != "no data")

    tiles = []
    tile_defs = [
        ("Runs (total / complete)", f'{k["runs_total"]} / {k["runs_complete"]}', None),
        ("Agreement rate — M-20", _fmt(k["agreement_rate"], True), "gate ≥ 70%"),
        ("Rank-1 acceptance — M-10", _fmt(k["rank1_acceptance"], True), "gate ≥ 60%"),
        ("Provenance pass — M-40", _fmt(k["provenance_pass"], True), "gate = 100%"),
        ("Judge overall — J-1…J-6", _fmt(k["judge_overall"]), "gate ≥ 3.5"),
        ("Judge coverage — M-72", _fmt(k["judge_coverage"], True), "target ≥ 90%"),
        ("Extraction coverage — M-70", _fmt(k["coverage_rate"], True), "gate = 100%"),
        ("Median duration — M-03", f'{_fmt(k["median_duration_min"], digits=1)} min', "target ≤ 60"),
    ]
    for label, val, gate in tile_defs:
        g = f'<div class="tgate">{_esc(gate)}</div>' if gate else ""
        tiles.append(f'<div class="tile"><div class="tlabel">{_esc(label)}</div>'
                     f'<div class="tval">{_esc(val)}</div>{g}</div>')

    gate_rows = []
    for g in data["gates"]:
        v = _fmt(g["value"], g["pct"])
        thr = _fmt(g["threshold"], g["pct"])
        cls = {"pass": "pass", "fail": "fail"}.get(g["status"], "nodata")
        icon = {"pass": "✅ PASS", "fail": "❌ FAIL"}.get(g["status"], "· no data")
        gate_rows.append(
            f'<tr><td>{g["id"]}</td><td>{_esc(g["label"])}</td>'
            f'<td>{v}</td><td>{g["op"]} {thr}</td>'
            f'<td class="status {cls}">{icon}</td></tr>')
    gates_table = ('<div class="tablewrap"><table><thead><tr><th>Gate</th><th>KPI</th>'
                   '<th>Value</th><th>Threshold</th><th>Status</th></tr></thead>'
                   f'<tbody>{"".join(gate_rows)}</tbody></table></div>')

    wk = data["weekly"]
    wk_labels = [w["week"][5:] for w in wk]
    trend_series = [
        ("Agreement", "--series-1", [w["agreement_rate"] for w in wk]),
        ("Rank-1 acc.", "--series-2", [w["rank1_acceptance"] for w in wk]),
    ]
    trend_chart = (
        legend_html([(n, v, "line") for n, v, _ in trend_series])
        + lines_svg(wk_labels, trend_series)
        + details_table("Table view — weekly rates",
                        ["Week", "Runs", "Agreement", "Rank-1", "RQS mean"],
                        [[w["week"], w["runs"], _fmt(w["agreement_rate"], True),
                          _fmt(w["rank1_acceptance"], True), _fmt(w["rqs_mean"], digits=1)]
                         for w in wk])
    ) if wk else "<p class='sub'>No dated runs yet.</p>"

    runs_chart = (
        columns_svg(wk_labels, [w["runs"] for w in wk],
                    vmax=max((w["runs"] for w in wk), default=1) or 1,
                    tooltip_name="runs", count_axis=True)
        + details_table("Table view — runs per week", ["Week", "Runs"],
                        [[w["week"], w["runs"]] for w in wk])
    ) if wk else "<p class='sub'>No dated runs yet.</p>"

    grades = data["grades"]
    grade_labels = list("ABCDF")
    grade_vals = [grades.get(g, 0) for g in grade_labels]
    grade_chart = (
        columns_svg(grade_labels, grade_vals,
                    vmax=max(grade_vals + [1]), series_var="--series-5",
                    tooltip_name="runs", count_axis=True)
        + details_table("Table view — RQS grades", ["Grade", "Runs"],
                        [[g, grades.get(g, 0)] for g in grade_labels]))

    jd = data["judge_dimensions"]
    # short axis labels — full dimension names live in the table view + tooltip
    jd_short = {"scope_quality": "scope", "top_event_quality": "top event",
                "tree_quality": "tree", "evidence_rigor": "evidence",
                "causal_chain_coherence": "chain", "report_clarity": "clarity"}
    jd_labels = [jd_short[d] for d in JUDGE_DIMENSIONS]
    jd_vals = [jd[d]["llm"] for d in JUDGE_DIMENSIONS]
    has_judge = any(v is not None for v in jd_vals)
    judge_chart = (
        columns_svg(jd_labels, jd_vals, vmax=5, series_var="--series-1",
                    tooltip_name="LLM avg", ticks=[0, 1, 2, 3, 4, 5], slot=64)
        + details_table("Table view — judge dimensions",
                        ["Dimension", "LLM avg", "Human avg", "N (LLM/H)"],
                        [[d, _fmt(jd[d]["llm"]), _fmt(jd[d]["human"]),
                          f'{jd[d]["n_llm"]}/{jd[d]["n_human"]}'] for d in JUDGE_DIMENSIONS])
    ) if has_judge else "<p class='sub'>No judge scores yet — run /rca-eval judge-pending.</p>"

    machine_rows = [[m["machine_id"], m["runs"], _fmt(m["agreement_rate"], True),
                     _fmt(m["abort_rate"], True), _fmt(m["provenance_pass"], True),
                     _fmt(m["rqs_mean"], digits=1), _fmt(m["coverage_rate"], True),
                     (m["last_sweep"] or "—")[:16]] for m in data["machines"]]
    machines_table = table_html(
        ["Machine", "Runs", "Agreement", "Aborts", "Provenance", "RQS", "Coverage", "Last sweep"],
        machine_rows)

    queue_rows = [[q["run_id"], q["machine_id"], ", ".join(q["reasons"])]
                  for q in data["review_queue"]]
    queue_table = (table_html(["Run", "Machine", "Reason"], queue_rows)
                   if queue_rows else "<p class='sub'>Queue empty.</p>")

    run_rows = [[r["run_id"], (r["started_at"] or "—")[:16], r["outcome"],
                 _fmt(r["agreement_rate"], True),
                 _fmt(r["provenance_pass_rate"], True),
                 _fmt(r["judge_overall"]),
                 _fmt(r["rqs"], digits=1) + (" (prov.)" if r["provisional"] and r["rqs"] is not None else ""),
                 r["grade"] or "—"]
                for r in sorted(data["runs"], key=lambda r: r["started_at"] or "", reverse=True)[:50]]
    runs_table = details_table("All runs (latest 50)",
                               ["Run", "Started", "Outcome", "Agreement", "Provenance",
                                "Judge", "RQS", "Grade"], run_rows)

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RCA Agent Quality Dashboard</title><style>{CSS}</style></head><body>
<h1>RCA Agent Quality Dashboard</h1>
<div class="sub">Generated {_esc(data["generated_at"])} · criteria v{data["criteria_version"]}
 · pipeline v6 · ClineSR/Gauss fleet</div>

<div class="hero">
  <div><div class="hlabel">Fleet RQS (mean, 0–100)</div>
  <div class="big">{hero_val}</div>
  <div class="hlabel">{k["rqs_final_count"]} final · {k["rqs_provisional_count"]} provisional (awaiting judge)</div></div>
  <div><div class="hlabel">Fleet gates</div>
  <div class="big">{gate_total - gate_fail}<span style="font-size:24px;color:var(--ink2)">/{gate_total}</span></div>
  <div class="hlabel">gates passing{" · failing: " + _esc("; ".join(data["gate_failures"])) if gate_fail else ""}</div></div>
</div>

<div class="tiles">{"".join(tiles)}</div>

<h2>KPI vs gates (criteria §5)</h2><div class="card">{gates_table}</div>

<div class="grid2">
<div><h2>Weekly trend — agreement &amp; rank-1</h2><div class="card">{trend_chart}</div></div>
<div><h2>Runs per week</h2><div class="card">{runs_chart}</div></div>
<div><h2>RQS grade distribution (§4.3)</h2><div class="card">{grade_chart}</div></div>
<div><h2>Judge scores by dimension (1–5)</h2><div class="card">{judge_chart}</div></div>
</div>

<h2>Per machine</h2><div class="card">{machines_table}</div>
<h2>Human-review queue (criteria §6)</h2><div class="card">{queue_table}{runs_table}</div>

<footer>Data path: state file → eval_extract/eval_sweep → outbox → this dashboard.
Thresholds live in code (spec IN-8). Online KPIs are proxies; official verdicts
need golden set + human review (spec AC-4).</footer>
<div id="tt"></div><script>{JS}</script></body></html>"""


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--records", action="append", required=True)
    ap.add_argument("--scores", action="append", default=[])
    ap.add_argument("--coverage", action="append", default=[])
    ap.add_argument("--out", default="dashboard.html")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args()

    records = load_records(args.records)
    if not records:
        print("No eval records found in: " + ", ".join(args.records))
        return 0
    scores = load_scores(args.scores or [])
    coverage = load_coverage(args.coverage or [])
    data = aggregate(records, scores, coverage)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_html(data))
    print(f"Dashboard written: {args.out}")

    if args.json_out:
        export = {key: data[key] for key in
                  ("generated_at", "criteria_version", "kpis", "gates",
                   "gate_failures", "weekly", "machines", "grades",
                   "judge_dimensions", "review_queue", "runs")}
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        print(f"Dashboard data written: {args.json_out}")

    if data["gate_failures"]:
        print("GATE FAILURES: " + "; ".join(data["gate_failures"]), file=sys.stderr)
        if args.gate:
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
