#!/usr/bin/env python3
"""eval_ingest.py — Ingest eval records from an outbox directory into the
central DuckDB evaluation store. Idempotent: re-ingesting the same run_id
replaces its rows instead of duplicating them.

Usage:
    python eval_ingest.py --db rca_eval.duckdb --outbox DIR [--archive DIR]
    python eval_ingest.py --db rca_eval.duckdb --amend RUN_ID \
        --set rca_confirmed_by_fix=true [--set reopened=false]

Tables created (if missing):
    eval_runs        one row per run (KPIs + golden + amendments)
    eval_iterations  one row per FTA iteration
    eval_decisions   one row per user gate decision
    eval_judge_scores one row per (run, dimension, judge) — written by eval_judge.py
"""

import argparse
import glob
import json
import os
import shutil
import sys
from datetime import datetime, timezone

try:
    import duckdb
except ImportError:
    print("ERROR: duckdb python package required (pip install duckdb)", file=sys.stderr)
    sys.exit(1)

DDL = """
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_version TEXT,
    machine_id TEXT,
    user_id TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    duration_s DOUBLE,
    active_duration_s DOUBLE,
    outcome TEXT,
    termination_reason TEXT,
    candidates_count INTEGER,
    selected_rank INTEGER,
    rank1_accepted BOOLEAN,
    decision_count INTEGER,
    override_count INTEGER,
    agreement_rate DOUBLE,
    high_disagreement BOOLEAN,
    iteration_count INTEGER,
    final_root_cause_class TEXT,
    implementation_location TEXT,
    provenance_total INTEGER,
    provenance_verified INTEGER,
    provenance_pass_rate DOUBLE,
    golden_case_id TEXT,
    golden_class_match BOOLEAN,
    golden_file_match BOOLEAN,
    golden_function_match BOOLEAN,
    golden_top_event_recall BOOLEAN,
    rca_confirmed_by_fix BOOLEAN,
    reopened BOOLEAN,
    report_path TEXT,
    ingested_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS eval_iterations (
    run_id TEXT,
    iteration_id INTEGER,
    duration_s DOUBLE,
    spec_anchored BOOLEAN,
    spec_skeleton_returned_empty BOOLEAN,
    fallback_used TEXT,
    branches_count INTEGER,
    base_events_count INTEGER,
    rejected_count INTEGER,
    open_items_count INTEGER,
    root_cause_class TEXT,
    termination_signals TEXT
);
CREATE TABLE IF NOT EXISTS eval_decisions (
    run_id TEXT,
    checkpoint TEXT,
    action TEXT,
    agent_recommendation TEXT,
    overrode_recommendation BOOLEAN,
    decided_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS eval_judge_scores (
    run_id TEXT,
    dimension TEXT,
    score INTEGER,
    rationale TEXT,
    judge_model TEXT,
    scored_at TIMESTAMP,
    PRIMARY KEY (run_id, dimension, judge_model)
);
"""


def _ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def ingest_record(con, rec):
    run_id = rec["run_id"]
    ca = rec.get("checkpoint_a") or {}
    dec = rec.get("decisions") or {}
    frc = rec.get("final_root_cause") or {}
    prov = rec.get("provenance") or {}
    gold = rec.get("golden") or {}
    amend = rec.get("amendments") or {}

    con.execute("DELETE FROM eval_runs WHERE run_id = ?", [run_id])
    con.execute("DELETE FROM eval_iterations WHERE run_id = ?", [run_id])
    con.execute("DELETE FROM eval_decisions WHERE run_id = ?", [run_id])

    con.execute(
        "INSERT INTO eval_runs VALUES (" + ",".join(["?"] * 32) + ")",
        [
            run_id,
            rec.get("pipeline_version"),
            rec.get("machine_id"),
            rec.get("user_id"),
            _ts(rec.get("started_at")),
            _ts(rec.get("finished_at")),
            rec.get("duration_s"),
            rec.get("active_duration_s"),
            rec.get("outcome"),
            rec.get("termination_reason"),
            ca.get("candidates_count"),
            ca.get("selected_rank"),
            ca.get("rank1_accepted"),
            dec.get("total"),
            dec.get("overrides"),
            dec.get("agreement_rate"),
            dec.get("high_disagreement_run"),
            len(rec.get("iterations") or []),
            frc.get("root_cause_class"),
            frc.get("implementation_location"),
            prov.get("total_keywords"),
            prov.get("verified_keywords"),
            prov.get("pass_rate"),
            gold.get("case_id"),
            gold.get("class_match"),
            gold.get("file_match"),
            gold.get("function_match"),
            gold.get("top_event_in_candidates"),
            amend.get("rca_confirmed_by_fix"),
            amend.get("reopened"),
            rec.get("report_path"),
            datetime.now(timezone.utc).replace(tzinfo=None),
        ],
    )
    for it in rec.get("iterations") or []:
        con.execute(
            "INSERT INTO eval_iterations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                run_id, it.get("iteration_id"), it.get("duration_s"),
                it.get("spec_anchored"), it.get("spec_skeleton_returned_empty"),
                it.get("fallback_used"), it.get("branches_count"),
                it.get("base_events_count"), it.get("rejected_count"),
                it.get("open_items_count"), it.get("root_cause_class"),
                ",".join(it.get("termination_signals") or []),
            ],
        )
    for d in dec.get("log") or []:
        con.execute(
            "INSERT INTO eval_decisions VALUES (?,?,?,?,?,?)",
            [
                run_id, d.get("checkpoint"), d.get("action"),
                d.get("agent_recommendation"),
                bool(d.get("overrode_recommendation")), _ts(d.get("decided_at")),
            ],
        )


AMENDABLE = {"rca_confirmed_by_fix", "reopened"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--outbox")
    ap.add_argument("--archive", help="Move ingested files here (default: <outbox>/../ingested)")
    ap.add_argument("--amend", metavar="RUN_ID")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=true|false")
    args = ap.parse_args()

    con = duckdb.connect(args.db)
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            con.execute(stmt)

    if args.amend:
        if not args.set:
            print("ERROR: --amend requires at least one --set KEY=VALUE", file=sys.stderr)
            return 1
        for kv in args.set:
            key, _, val = kv.partition("=")
            if key not in AMENDABLE:
                print(f"ERROR: not amendable: {key} (allowed: {sorted(AMENDABLE)})", file=sys.stderr)
                return 1
            con.execute(
                f"UPDATE eval_runs SET {key} = ? WHERE run_id = ?",
                [val.lower() == "true", args.amend],
            )
        n = con.execute("SELECT count(*) FROM eval_runs WHERE run_id = ?", [args.amend]).fetchone()[0]
        print(f"Amended run {args.amend}" if n else f"WARNING: run {args.amend} not found")
        con.close()
        return 0

    if not args.outbox:
        print("ERROR: --outbox required (or use --amend)", file=sys.stderr)
        return 1

    files = sorted(glob.glob(os.path.join(args.outbox, "eval_*.json")))
    archive = args.archive or os.path.join(os.path.dirname(args.outbox.rstrip("/")), "ingested")
    ok = bad = 0
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
            ingest_record(con, rec)
            os.makedirs(archive, exist_ok=True)
            shutil.move(path, os.path.join(archive, os.path.basename(path)))
            ok += 1
        except (OSError, json.JSONDecodeError, KeyError, duckdb.Error) as e:
            print(f"SKIP {path}: {e}", file=sys.stderr)
            bad += 1
    con.close()
    print(f"Ingested {ok} record(s), skipped {bad}, db={args.db}")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
