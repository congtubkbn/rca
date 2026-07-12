#!/usr/bin/env python3
"""eval_extract.py — Extract a compact, anonymized evaluation record from a
completed (or aborted) RCA v6 state file.

Runs on the engineer's machine, per run, read-only over the state file.
Output goes to the eval outbox for later sync + ingest.

Usage:
    python eval_extract.py <state_file.json> [--outbox DIR] [--salt SALT]
                           [--golden GOLDEN_CASE.json] [--stdout]

    --outbox   Output directory (default: <cwd>/.rca/eval/outbox)
    --salt     Anonymization salt shared by the team (default: env RCA_EVAL_SALT
               or "rca-eval"). Same salt => same machine/user ids across runs.
    --golden   Golden case file for benchmark runs; adds accuracy fields.
    --stdout   Print record to stdout instead of writing to outbox.

Exit codes: 0 ok, 1 bad input, 2 state file not terminal (still extracted,
flagged outcome=incomplete).
"""

import argparse
import getpass
import hashlib
import json
import os
import socket
import sys
from datetime import datetime, timezone


EXTRACTOR_VERSION = "1.1"


def _sha12(text: str, salt: str) -> str:
    return hashlib.sha256((salt + ":" + text).encode()).hexdigest()[:12]


def _file_sha256(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_s(start, end):
    a, b = _parse_iso(start), _parse_iso(end)
    if a and b:
        return round((b - a).total_seconds(), 1)
    return None


def _norm_path(p):
    if not p:
        return None
    return str(p).replace("\\", "/").lower()


def extract(state: dict, salt: str, golden: dict | None,
            state_path: str | None = None) -> dict:
    meta = state.get("meta", {})
    now = datetime.now(timezone.utc).isoformat()

    started = meta.get("started_at")
    finished = meta.get("finished_at")
    engineer_input = meta.get("engineer_input", "")
    run_id = "{}_{}".format(
        (started or now).replace(":", "").replace("-", "")[:15],
        _sha12(engineer_input, salt)[:8],
    )

    phase = meta.get("current_phase", "")
    if phase == "complete":
        term = (state.get("phase4_rca_report") or {}).get("termination_reason") or \
               (state.get("phase3_root_cause_chain") or {}).get("termination_reason")
        outcome = "aborted" if term and "abort" in term.lower() else "complete"
    else:
        outcome, term = "incomplete", None

    # --- Checkpoint A ---
    ecf = state.get("phase2_ecf") or {}
    candidates = ecf.get("top_event_candidates") or []
    conf = ecf.get("user_confirmation") or {}
    selected_rank = conf.get("selected_rank")
    checkpoint_a = {
        "candidates_count": len(candidates),
        "selected_rank": selected_rank,
        "rank1_accepted": (selected_rank == 1) if selected_rank is not None else None,
        "overrode_recommendation": conf.get("overrode_recommendation"),
    }

    # --- User decisions ---
    decisions = state.get("user_decisions") or []
    overrides = sum(1 for d in decisions if d.get("overrode_recommendation"))
    chain = state.get("phase3_root_cause_chain") or {}
    dec_block = {
        "total": len(decisions),
        "overrides": overrides,
        "agreement_rate": round(1 - overrides / len(decisions), 3) if decisions else None,
        "high_disagreement_run": chain.get("high_disagreement_run"),
        "log": [
            {
                "checkpoint": d.get("checkpoint"),
                "action": d.get("action"),
                "agent_recommendation": d.get("agent_recommendation"),
                "overrode_recommendation": bool(d.get("overrode_recommendation")),
                "decided_at": d.get("decided_at"),
            }
            for d in decisions
        ],
    }

    # --- Iterations ---
    iterations = []
    active = 0.0
    for it in state.get("fta_iterations") or []:
        tree = it.get("hybrid_tree") or {}
        dur = _duration_s(it.get("started_at"), it.get("completed_at"))
        if dur:
            active += dur
        rec = it.get("agent_recommendation") or {}
        rc = it.get("iteration_root_cause") or {}
        iterations.append({
            "iteration_id": it.get("iteration_id"),
            "duration_s": dur,
            "spec_anchored": (it.get("input_top_event") or {}).get("spec_anchored"),
            "spec_skeleton_returned_empty": tree.get("spec_skeleton_returned_empty"),
            "fallback_used": tree.get("fallback_used"),
            "branches_count": len(tree.get("branches") or []) if tree else None,
            "base_events_count": len(it.get("base_events") or []),
            "rejected_count": len(it.get("rejected") or []),
            "open_items_count": len(it.get("open_items") or []),
            "root_cause_class": rc.get("root_cause_class"),
            "termination_signals": rec.get("termination_signals_detected") or [],
        })

    # --- Final root cause ---
    final_rc = chain.get("final_root_cause") or {}
    final_block = {
        "root_cause_class": final_rc.get("root_cause_class"),
        "implementation_location": final_rc.get("implementation_location"),
        "iterations_traversed": len(chain.get("iterations_traversed") or iterations),
    }

    # --- Provenance ---
    audit = state.get("keyword_provenance_audit") or []
    verified = sum(1 for k in audit if k.get("verified"))
    provenance = {
        "total_keywords": len(audit),
        "verified_keywords": verified,
        "pass_rate": round(verified / len(audit), 3) if audit else None,
    }

    # --- Golden comparison ---
    golden_block = None
    if golden:
        g_loc = _norm_path(golden.get("root_cause", {}).get("implementation_location"))
        a_loc = _norm_path(final_rc.get("implementation_location"))
        g_file = g_loc.split(":")[0].split("/")[-1] if g_loc else None
        a_file = a_loc.split(":")[0].split("/")[-1] if a_loc else None
        g_func = (golden.get("root_cause", {}).get("function") or "").lower() or None
        g_top = (golden.get("top_event") or "").lower()
        golden_block = {
            "case_id": golden.get("case_id"),
            "class_match": (
                final_rc.get("root_cause_class") == golden.get("root_cause", {}).get("root_cause_class")
                if final_rc.get("root_cause_class") else None
            ),
            "file_match": (g_file == a_file) if (g_file and a_file) else None,
            "function_match": (g_func in (a_loc or "")) if g_func else None,
            "top_event_in_candidates": (
                any(g_top in (c.get("event") or "").lower() for c in candidates)
                if g_top and candidates else None
            ),
        }

    # --- Integrity (spec IN-2): tamper-evidence hashes ---
    report_path = (state.get("phase4_rca_report") or {}).get("report_path")
    integrity = {
        "extractor_version": EXTRACTOR_VERSION,
        "state_sha256": _file_sha256(state_path) if state_path else None,
        "report_sha256": _file_sha256(report_path) if report_path else None,
    }

    return {
        "record_version": 1,
        "run_id": run_id,
        "pipeline_version": meta.get("pipeline_version", "v6"),
        "machine_id": _sha12(socket.gethostname(), salt),
        "user_id": _sha12(getpass.getuser(), salt),
        "extracted_at": now,
        "started_at": started,
        "finished_at": finished,
        "duration_s": _duration_s(started, finished),
        "active_duration_s": round(active, 1) if active else None,
        "outcome": outcome,
        "termination_reason": term,
        "checkpoint_a": checkpoint_a,
        "decisions": dec_block,
        "iterations": iterations,
        "final_root_cause": final_block,
        "provenance": provenance,
        "golden": golden_block,
        "amendments": {"rca_confirmed_by_fix": None, "reopened": None},
        "integrity": integrity,
        "report_path": report_path,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state_file")
    ap.add_argument("--outbox", default=os.path.join(os.getcwd(), ".rca", "eval", "outbox"))
    ap.add_argument("--salt", default=os.environ.get("RCA_EVAL_SALT", "rca-eval"))
    ap.add_argument("--golden")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    try:
        with open(args.state_file, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read state file: {e}", file=sys.stderr)
        return 1

    golden = None
    if args.golden:
        with open(args.golden, encoding="utf-8") as f:
            golden = json.load(f)

    record = extract(state, args.salt, golden, state_path=args.state_file)

    if args.stdout:
        json.dump(record, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        os.makedirs(args.outbox, exist_ok=True)
        out = os.path.join(args.outbox, f"eval_{record['run_id']}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        print(f"Eval record written: {out}")

    return 0 if record["outcome"] != "incomplete" else 2


if __name__ == "__main__":
    sys.exit(main())
