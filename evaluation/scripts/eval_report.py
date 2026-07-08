#!/usr/bin/env python3
"""eval_report.py — Aggregate the DuckDB evaluation store into a markdown
quality dashboard: fleet KPIs vs thresholds, weekly trend, per-machine
breakdown, golden-set accuracy, judge scores, and the human-review queue.

Usage:
    python eval_report.py --db rca_eval.duckdb [--out DASHBOARD.md]
                          [--gate]   # exit 3 if any hard KPI gate fails

Intended to run on a schedule (cron / CI) after eval_ingest.py.
"""

import argparse
import sys
from datetime import datetime, timezone

try:
    import duckdb
except ImportError:
    print("ERROR: duckdb python package required (pip install duckdb)", file=sys.stderr)
    sys.exit(1)

# KPI gates — tune after the first baseline (framework doc §6).
GATES = {
    "agreement_rate": ("avg agreement rate (Checkpoint B)", 0.70, ">="),
    "rank1_acceptance": ("Checkpoint A rank-1 acceptance", 0.60, ">="),
    "provenance_pass": ("provenance pass rate", 1.00, ">="),
    "golden_l1": ("golden accuracy L1 (class)", 0.80, ">="),
    "golden_l2": ("golden accuracy L2 (file)", 0.60, ">="),
    "reopen_rate": ("re-open rate", 0.10, "<="),
    "judge_overall": ("judge overall (LLM)", 3.5, ">="),
}


def one(con, sql, params=None):
    row = con.execute(sql, params or []).fetchone()
    return row[0] if row else None


def fmt(v, pct=False):
    if v is None:
        return "—"
    return f"{v:.1%}" if pct else f"{v:.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="rca_eval_dashboard.md")
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    total = one(con, "SELECT count(*) FROM eval_runs") or 0
    if total == 0:
        print("No runs in eval store yet.")
        return 0

    kpi = {
        "agreement_rate": one(con, "SELECT avg(agreement_rate) FROM eval_runs WHERE agreement_rate IS NOT NULL"),
        "rank1_acceptance": one(con, "SELECT avg(CASE WHEN rank1_accepted THEN 1.0 ELSE 0.0 END) FROM eval_runs WHERE rank1_accepted IS NOT NULL"),
        "provenance_pass": one(con, "SELECT avg(provenance_pass_rate) FROM eval_runs WHERE provenance_pass_rate IS NOT NULL"),
        "golden_l1": one(con, "SELECT avg(CASE WHEN golden_class_match THEN 1.0 ELSE 0.0 END) FROM eval_runs WHERE golden_class_match IS NOT NULL"),
        "golden_l2": one(con, "SELECT avg(CASE WHEN golden_file_match THEN 1.0 ELSE 0.0 END) FROM eval_runs WHERE golden_file_match IS NOT NULL"),
        "reopen_rate": one(con, "SELECT avg(CASE WHEN reopened THEN 1.0 ELSE 0.0 END) FROM eval_runs WHERE reopened IS NOT NULL"),
        "judge_overall": one(con, "SELECT avg(score) FROM eval_judge_scores WHERE judge_model != 'human'"),
    }
    median_dur = one(con, "SELECT median(duration_s)/60 FROM eval_runs WHERE outcome='complete'")
    abort_rate = one(con, "SELECT avg(CASE WHEN outcome='aborted' THEN 1.0 ELSE 0.0 END) FROM eval_runs")

    n_complete = one(con, "SELECT count(*) FROM eval_runs WHERE outcome='complete'")
    n_aborted = one(con, "SELECT count(*) FROM eval_runs WHERE outcome='aborted'")
    lines = [
        "# RCA Agent Quality Dashboard",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ",
        f"Runs in store: **{total}** (complete: {n_complete}, aborted: {n_aborted})",
        "",
        "## KPI vs gates",
        "",
        "| KPI | Value | Gate | Status |",
        "|---|---|---|---|",
    ]
    gate_failures = []
    for key, (label, threshold, op) in GATES.items():
        v = kpi[key]
        if v is None:
            status = "no data"
        else:
            passed = v >= threshold if op == ">=" else v <= threshold
            status = "✅ pass" if passed else "❌ FAIL"
            if not passed:
                gate_failures.append(label)
        pct = key != "judge_overall"
        lines.append(f"| {label} | {fmt(v, pct)} | {op} {fmt(threshold, pct)} | {status} |")

    lines += [
        "",
        f"Median time-to-RCA (complete runs): **{fmt(median_dur)} min** · "
        f"Abort rate: **{fmt(abort_rate, True)}**",
        "",
        "## Weekly trend",
        "",
        "| Week | Runs | Agreement | Rank-1 acc. | Median dur (min) |",
        "|---|---|---|---|---|",
    ]
    for wk, n, agr, r1, dur in con.execute("""
        SELECT date_trunc('week', started_at) wk, count(*),
               avg(agreement_rate),
               avg(CASE WHEN rank1_accepted THEN 1.0 ELSE 0.0 END),
               median(duration_s)/60
        FROM eval_runs WHERE started_at IS NOT NULL
        GROUP BY 1 ORDER BY 1 DESC LIMIT 12
    """).fetchall():
        lines.append(f"| {str(wk)[:10]} | {n} | {fmt(agr, True)} | {fmt(r1, True)} | {fmt(dur)} |")

    lines += ["", "## Per-machine", "", "| Machine | Runs | Agreement | Aborts | Provenance |", "|---|---|---|---|---|"]
    for m, n, agr, ab, pv in con.execute("""
        SELECT machine_id, count(*), avg(agreement_rate),
               avg(CASE WHEN outcome='aborted' THEN 1.0 ELSE 0.0 END),
               avg(provenance_pass_rate)
        FROM eval_runs GROUP BY 1 ORDER BY 2 DESC
    """).fetchall():
        lines.append(f"| {m} | {n} | {fmt(agr, True)} | {fmt(ab, True)} | {fmt(pv, True)} |")

    lines += ["", "## Root-cause class distribution", "", "| Class | Runs |", "|---|---|"]
    for cls, n in con.execute("""
        SELECT coalesce(final_root_cause_class, '(none)'), count(*)
        FROM eval_runs GROUP BY 1 ORDER BY 2 DESC
    """).fetchall():
        lines.append(f"| {cls} | {n} |")

    lines += ["", "## Judge scores by dimension", "", "| Dimension | LLM avg | Human avg | N (LLM/H) |", "|---|---|---|---|"]
    for dim, llm, hum, nl, nh in con.execute("""
        SELECT dimension,
               avg(CASE WHEN judge_model != 'human' THEN score END),
               avg(CASE WHEN judge_model  = 'human' THEN score END),
               count(CASE WHEN judge_model != 'human' THEN 1 END),
               count(CASE WHEN judge_model  = 'human' THEN 1 END)
        FROM eval_judge_scores GROUP BY 1 ORDER BY 1
    """).fetchall():
        lines.append(f"| {dim} | {fmt(llm)} | {fmt(hum)} | {nl}/{nh} |")

    lines += [
        "", "## Human-review queue",
        "", "Runs requiring mandatory human review (high disagreement, provenance",
        "failure, aborted, or any LLM-judge dimension ≤ 2):", "",
        "| Run | Reason |", "|---|---|",
    ]
    for run_id, reason in con.execute("""
        SELECT run_id, 'high disagreement' FROM eval_runs WHERE high_disagreement
        UNION ALL
        SELECT run_id, 'provenance < 100%' FROM eval_runs WHERE provenance_pass_rate < 1.0
        UNION ALL
        SELECT run_id, 'aborted' FROM eval_runs WHERE outcome = 'aborted'
        UNION ALL
        SELECT DISTINCT j.run_id, 'judge score <= 2' FROM eval_judge_scores j
            WHERE j.score <= 2 AND j.judge_model != 'human'
        ORDER BY 1
    """).fetchall():
        lines.append(f"| {run_id} | {reason} |")

    con.close()
    text = "\n".join(lines) + "\n"
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Dashboard written: {args.out}")

    if gate_failures:
        print("GATE FAILURES: " + "; ".join(gate_failures), file=sys.stderr)
        if args.gate:
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
