#!/usr/bin/env python3
"""eval_score.py — Compute the per-run composite RQS (RCA Quality Score,
0-100) from an eval record + optional judge scores, per the scoring criteria
in evaluation/criteria/rca-agent-scoring-criteria.md (section 4).

Deterministic: the same record + scores always produce the same scorecard
(spec AC-2). Stdlib-only so it runs on every engineer machine (ClineSR on
Windows included).

Usage:
    python eval_score.py <eval_record.json> [--scores SCORES.json] [--out FILE]

SCORES.json format (same as eval_judge.py --load-scores):
    {"run_id": "...", "judge_model": "...", "scores":
     [{"dimension": "scope_quality", "score": 4, "rationale": "..."}]}

Exit codes: 0 ok, 1 bad input.
"""

import argparse
import json
import sys

CRITERIA_VERSION = "1.0"

JUDGE_DIMENSIONS = [
    "scope_quality",
    "top_event_quality",
    "tree_quality",
    "evidence_rigor",
    "causal_chain_coherence",
    "report_clarity",
]

# Component weights — criteria doc section 4.1. Changing these = changing the
# criteria doc = PR review (spec IN-8).
WEIGHTS = {
    "C1_completion": 5,
    "C2_provenance": 15,
    "C3_top_event": 10,
    "C4_agreement": 15,
    "C5_anchoring": 8,
    "C6_fta_efficiency": 7,
    "C7_judge": 40,
}

GRADE_BANDS = [(85, "A"), (70, "B"), (55, "C"), (40, "D")]

RANK_SCORE = {1: 1.0, 2: 0.6, 3: 0.4}


def _grade(rqs):
    for threshold, grade in GRADE_BANDS:
        if rqs >= threshold:
            return grade
    return "F"


def _component_values(record):
    """Deterministic component scores in [0,1], or None when the record has
    no data for that component (criteria doc section 4.2 rule 1)."""
    comps = {}

    comps["C1_completion"] = 1.0 if record.get("outcome") == "complete" else 0.0

    prov = record.get("provenance") or {}
    total = prov.get("total_keywords") or 0
    comps["C2_provenance"] = (
        prov.get("pass_rate") if total else 1.0
    )  # no keywords used => nothing unverified

    rank = (record.get("checkpoint_a") or {}).get("selected_rank")
    comps["C3_top_event"] = RANK_SCORE.get(rank, 0.0) if rank is not None else None

    dec = record.get("decisions") or {}
    comps["C4_agreement"] = dec.get("agreement_rate")

    iters = record.get("iterations") or []
    if iters:
        anchored = sum(1 for i in iters if i.get("spec_anchored") is True)
        fallback = sum(1 for i in iters if i.get("fallback_used"))
        anchored_ratio = anchored / len(iters)
        fallback_rate = fallback / len(iters)
        comps["C5_anchoring"] = 0.7 * anchored_ratio + 0.3 * (1 - fallback_rate)
        pool = sum(
            (i.get("base_events_count") or 0)
            + (i.get("rejected_count") or 0)
            + (i.get("open_items_count") or 0)
            for i in iters
        )
        open_items = sum(i.get("open_items_count") or 0 for i in iters)
        comps["C6_fta_efficiency"] = 1 - (open_items / pool) if pool else 1.0
    else:
        comps["C5_anchoring"] = None
        comps["C6_fta_efficiency"] = None

    return comps


def _judge_component(judge_scores):
    """(value in [0,1] or None, per-dimension dict, min score or None)."""
    if not judge_scores:
        return None, {}, None
    by_dim = {}
    for s in judge_scores:
        dim, score = s.get("dimension"), s.get("score")
        if dim in JUDGE_DIMENSIONS and isinstance(score, (int, float)) and 1 <= score <= 5:
            by_dim[dim] = score
    if not by_dim:
        return None, {}, None
    mean = sum(by_dim.values()) / len(by_dim)
    return mean / 5.0, by_dim, min(by_dim.values())


def compute_scorecard(record, judge_scores=None):
    """record: parsed eval record dict. judge_scores: list of score dicts
    (the "scores" array of a SCORES.json). Returns the scorecard dict."""
    outcome = record.get("outcome")
    comps = _component_values(record)
    judge_value, judge_by_dim, judge_min = _judge_component(judge_scores)
    comps["C7_judge"] = judge_value
    provisional = judge_value is None

    caps = []
    if outcome == "aborted":
        return {
            "criteria_version": CRITERIA_VERSION,
            "run_id": record.get("run_id"),
            "rqs": None,
            "grade": None,
            "provisional": False,
            "components": comps,
            "judge_by_dimension": judge_by_dim,
            "caps_applied": ["aborted_run_not_scored"],
            "needs_human_review": True,
        }

    present = {k: v for k, v in comps.items() if v is not None}
    weight_sum = sum(WEIGHTS[k] for k in present)
    raw = sum(WEIGHTS[k] * v for k, v in present.items())
    rqs = 100.0 * raw / weight_sum if weight_sum else 0.0

    prov_rate = comps.get("C2_provenance")
    if prov_rate is not None and prov_rate < 1.0 and rqs > 49:
        rqs = 49.0
        caps.append("provenance_below_100_cap_49")
    if judge_min is not None and judge_min <= 2 and rqs > 69:
        rqs = 69.0
        caps.append("judge_dimension_le_2_cap_69")

    rqs = round(rqs, 1)
    # Groundedness failure outranks the numeric bands (criteria section 4.2/4.3).
    grade = "F" if "provenance_below_100_cap_49" in caps else _grade(rqs)
    needs_review = (
        bool(caps)
        or grade in ("D", "F")
        or bool((record.get("decisions") or {}).get("high_disagreement_run"))
    )

    return {
        "criteria_version": CRITERIA_VERSION,
        "run_id": record.get("run_id"),
        "rqs": rqs,
        "grade": grade,
        "provisional": provisional,
        "components": comps,
        "components_missing": [k for k, v in comps.items() if v is None],
        "judge_by_dimension": judge_by_dim,
        "caps_applied": caps,
        "needs_human_review": needs_review,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("record")
    ap.add_argument("--scores", help="judge SCORES.json for this run")
    ap.add_argument("--out", help="write scorecard JSON here (default: stdout)")
    args = ap.parse_args()

    try:
        with open(args.record, encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read record: {e}", file=sys.stderr)
        return 1

    judge_scores = None
    if args.scores:
        try:
            with open(args.scores, encoding="utf-8") as f:
                payload = json.load(f)
            judge_scores = payload.get("scores") or []
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot read scores: {e}", file=sys.stderr)
            return 1

    card = compute_scorecard(record, judge_scores)
    text = json.dumps(card, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"Scorecard written: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
