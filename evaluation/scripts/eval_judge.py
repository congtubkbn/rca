#!/usr/bin/env python3
"""eval_judge.py — LLM-as-judge scoring of a completed RCA run against the
6-dimension rubric in .cline/skills/3gpp-rca-evaluator/references/evaluation-rubric.md.

The judge reads ONLY the final report + the eval record. It must not re-run
retrieval — it grades reasoning rigor and internal consistency, it does not
redo the RCA.

Modes:
  1. With ANTHROPIC_API_KEY set: calls the Claude API directly and writes
     scores into the DuckDB store.
  2. Without a key: writes the fully-assembled judge prompt to a file so a
     human or an interactive agent session can produce the scores, then
     scores can be loaded with --load-scores.

Usage:
    python eval_judge.py --db rca_eval.duckdb --report REPORT.md --record EVAL_RECORD.json
    python eval_judge.py --db rca_eval.duckdb --load-scores SCORES.json
    (SCORES.json: {"run_id": "...", "judge_model": "human", "scores":
                   [{"dimension": "...", "score": 4, "rationale": "..."}]})
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

DIMENSIONS = [
    "scope_quality",
    "top_event_quality",
    "tree_quality",
    "evidence_rigor",
    "causal_chain_coherence",
    "report_clarity",
]

RUBRIC_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", ".cline", "skills", "3gpp-rca-evaluator", "references",
    "evaluation-rubric.md",
)

PROMPT_TEMPLATE = """You are a strict senior 3GPP modem engineer reviewing a \
Root Cause Analysis report produced by an automated RCA pipeline. Grade it \
against the rubric below. You may ONLY use the report and the metrics record \
provided — do not invent facts, do not attempt to redo the analysis, and do \
not reward confident-sounding but unsupported claims. Unsupported claims \
lower evidence_rigor.

== RUBRIC ==
{rubric}

== METRICS RECORD (extracted from the run's state file) ==
{record}

== RCA REPORT ==
{report}

== OUTPUT FORMAT ==
Return ONLY a JSON object, no prose around it:
{{"scores": [{{"dimension": "<one of {dims}>", "score": <1-5 integer>,
"rationale": "<2-3 sentences citing specific report content>"}}, ...]}}
Include exactly one entry per dimension.
"""


def build_prompt(report_text, record):
    try:
        with open(RUBRIC_PATH, encoding="utf-8") as f:
            rubric = f.read()
    except OSError:
        rubric = "(rubric file missing — grade each dimension 1-5, 5 = flawless)"
    return PROMPT_TEMPLATE.format(
        rubric=rubric,
        record=json.dumps(record, indent=2, ensure_ascii=False),
        report=report_text,
        dims=", ".join(DIMENSIONS),
    )


def call_claude(prompt, model):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }).encode(),
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.load(resp)
    text = "".join(b.get("text", "") for b in body.get("content", []))
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def store_scores(db, run_id, judge_model, scores):
    import duckdb
    con = duckdb.connect(db)
    con.execute("""
        CREATE TABLE IF NOT EXISTS eval_judge_scores (
            run_id TEXT, dimension TEXT, score INTEGER, rationale TEXT,
            judge_model TEXT, scored_at TIMESTAMP,
            PRIMARY KEY (run_id, dimension, judge_model))
    """)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for s in scores:
        dim = s["dimension"]
        if dim not in DIMENSIONS:
            print(f"SKIP unknown dimension: {dim}", file=sys.stderr)
            continue
        score = int(s["score"])
        if not 1 <= score <= 5:
            print(f"SKIP out-of-range score for {dim}: {score}", file=sys.stderr)
            continue
        con.execute(
            "DELETE FROM eval_judge_scores WHERE run_id=? AND dimension=? AND judge_model=?",
            [run_id, dim, judge_model])
        con.execute(
            "INSERT INTO eval_judge_scores VALUES (?,?,?,?,?,?)",
            [run_id, dim, score, s.get("rationale", ""), judge_model, now])
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--report")
    ap.add_argument("--record")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--load-scores", metavar="SCORES.json")
    ap.add_argument("--prompt-out", help="Where to write the prompt in no-API mode "
                                         "(default: judge_prompt_<run_id>.md next to record)")
    args = ap.parse_args()

    if args.load_scores:
        with open(args.load_scores, encoding="utf-8") as f:
            payload = json.load(f)
        store_scores(args.db, payload["run_id"],
                     payload.get("judge_model", "human"), payload["scores"])
        print(f"Stored {len(payload['scores'])} score(s) for run {payload['run_id']}")
        return 0

    if not (args.report and args.record):
        print("ERROR: need --report and --record (or --load-scores)", file=sys.stderr)
        return 1

    with open(args.record, encoding="utf-8") as f:
        record = json.load(f)
    with open(args.report, encoding="utf-8") as f:
        report_text = f.read()
    run_id = record["run_id"]
    prompt = build_prompt(report_text, record)

    if os.environ.get("ANTHROPIC_API_KEY"):
        result = call_claude(prompt, args.model)
        store_scores(args.db, run_id, args.model, result["scores"])
        avg = sum(int(s["score"]) for s in result["scores"]) / len(result["scores"])
        print(f"Judge scored run {run_id}: overall {avg:.2f}")
        for s in result["scores"]:
            print(f"  {s['dimension']}: {s['score']}")
        return 0

    out = args.prompt_out or os.path.join(
        os.path.dirname(os.path.abspath(args.record)), f"judge_prompt_{run_id}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"No ANTHROPIC_API_KEY — judge prompt written to {out}\n"
          f"Have a human or agent produce the scores JSON, then run:\n"
          f"  python eval_judge.py --db {args.db} --load-scores SCORES.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
