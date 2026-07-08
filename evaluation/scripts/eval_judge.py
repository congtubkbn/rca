#!/usr/bin/env python3
"""eval_judge.py — LLM-as-judge scoring of a completed RCA run against the
6-dimension rubric in .cline/skills/3gpp-rca-evaluator/references/evaluation-rubric.md.

The judge reads ONLY the final report + the eval record. It must not re-run
retrieval — it grades reasoning rigor and internal consistency, it does not
redo the RCA. It must also run in a FRESH context, never the session that
produced the run (spec IN-4, anti self-grading).

Judge backends, tried in this order:
  1. Gauss / any OpenAI-compatible chat endpoint — set RCA_JUDGE_API_URL
     (e.g. the Samsung-internal Gauss gateway's /v1/chat/completions),
     optional RCA_JUDGE_API_KEY, RCA_JUDGE_MODEL (default "gauss").
  2. Claude API — ANTHROPIC_API_KEY set.
  3. No API (default on ClineSR machines): writes a self-contained judge
     prompt file. A FRESH ClineSR task (running Gauss) or a human produces
     the scores JSON, loaded back with --load-scores. The /rca-eval
     judge-pending workflow automates this loop.

Score storage: always written as a file scores_<run_id>.json into --scores-out
(default <cwd>/.rca/eval/scores) so the stdlib dashboard can read it; ALSO
written to DuckDB when --db is given and duckdb is installed (aggregation
machine).

Usage:
    python eval_judge.py --report REPORT.md --record EVAL_RECORD.json
                         [--db rca_eval.duckdb] [--scores-out DIR] [--model M]
    python eval_judge.py --load-scores SCORES.json [--db ...] [--scores-out DIR]
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


def _parse_json_block(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("judge response contains no JSON object")
    return json.loads(text[start:end + 1])


def call_openai_compatible(prompt, url, model, api_key=None):
    """Gauss gateway / any OpenAI-compatible /v1/chat/completions endpoint."""
    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps({
            "model": model,
            "max_tokens": 2000,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.load(resp)
    text = body["choices"][0]["message"]["content"]
    return _parse_json_block(text)


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
    return _parse_json_block(text)


def validate_scores(scores):
    """Keep only known dimensions with in-range scores (spec V8)."""
    valid = []
    for s in scores:
        dim = s.get("dimension")
        if dim not in DIMENSIONS:
            print(f"SKIP unknown dimension: {dim}", file=sys.stderr)
            continue
        try:
            score = int(s["score"])
        except (KeyError, TypeError, ValueError):
            print(f"SKIP non-integer score for {dim}", file=sys.stderr)
            continue
        if not 1 <= score <= 5:
            print(f"SKIP out-of-range score for {dim}: {score}", file=sys.stderr)
            continue
        valid.append({"dimension": dim, "score": score,
                      "rationale": s.get("rationale", "")})
    return valid


def store_scores_file(scores_dir, run_id, judge_model, scores):
    os.makedirs(scores_dir, exist_ok=True)
    out = os.path.join(scores_dir, f"scores_{run_id}.json")
    payload = {
        "run_id": run_id,
        "judge_model": judge_model,
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scores": scores,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out


def store_scores_db(db, run_id, judge_model, scores):
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
        con.execute(
            "DELETE FROM eval_judge_scores WHERE run_id=? AND dimension=? AND judge_model=?",
            [run_id, s["dimension"], judge_model])
        con.execute(
            "INSERT INTO eval_judge_scores VALUES (?,?,?,?,?,?)",
            [run_id, s["dimension"], s["score"], s["rationale"], judge_model, now])
    con.close()
    return len(scores)


def store_scores(args, run_id, judge_model, scores):
    path = store_scores_file(args.scores_out, run_id, judge_model, scores)
    print(f"Scores file written: {path}")
    if args.db:
        try:
            store_scores_db(args.db, run_id, judge_model, scores)
            print(f"Scores stored in DB: {args.db}")
        except ImportError:
            print("WARN: duckdb not installed — DB write skipped "
                  "(scores file is authoritative for sync)", file=sys.stderr)
    return len(scores)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="optional DuckDB store (aggregation machine)")
    ap.add_argument("--report")
    ap.add_argument("--record")
    ap.add_argument("--model", default=None,
                    help="judge model id (default: RCA_JUDGE_MODEL / 'gauss' "
                         "for the Gauss endpoint, 'claude-sonnet-5' for Claude)")
    ap.add_argument("--scores-out",
                    default=os.path.join(os.getcwd(), ".rca", "eval", "scores"))
    ap.add_argument("--load-scores", metavar="SCORES.json")
    ap.add_argument("--prompt-out", help="Where to write the prompt in no-API mode "
                                         "(default: judge_prompt_<run_id>.md next to record)")
    args = ap.parse_args()

    if args.load_scores:
        with open(args.load_scores, encoding="utf-8") as f:
            payload = json.load(f)
        scores = validate_scores(payload["scores"])
        n = store_scores(args, payload["run_id"],
                         payload.get("judge_model", "human"), scores)
        print(f"Stored {n} of {len(payload['scores'])} score(s) for run {payload['run_id']}")
        return 0 if n == len(payload["scores"]) else 2

    if not (args.report and args.record):
        print("ERROR: need --report and --record (or --load-scores)", file=sys.stderr)
        return 1

    with open(args.record, encoding="utf-8") as f:
        record = json.load(f)
    with open(args.report, encoding="utf-8") as f:
        report_text = f.read()
    run_id = record["run_id"]
    prompt = build_prompt(report_text, record)

    gauss_url = os.environ.get("RCA_JUDGE_API_URL")
    if gauss_url:
        model = args.model or os.environ.get("RCA_JUDGE_MODEL", "gauss")
        result = call_openai_compatible(
            prompt, gauss_url, model, os.environ.get("RCA_JUDGE_API_KEY"))
        scores = validate_scores(result["scores"])
    elif os.environ.get("ANTHROPIC_API_KEY"):
        model = args.model or "claude-sonnet-5"
        result = call_claude(prompt, model)
        scores = validate_scores(result["scores"])
    else:
        out = args.prompt_out or os.path.join(
            os.path.dirname(os.path.abspath(args.record)), f"judge_prompt_{run_id}.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"No judge API configured — judge prompt written to {out}\n"
              f"Have a FRESH ClineSR task (Gauss) or a human produce the scores\n"
              f"JSON, then run:\n"
              f"  python eval_judge.py --load-scores SCORES.json "
              f"[--scores-out {args.scores_out}]")
        return 0

    if not scores:
        print("ERROR: judge returned no valid scores", file=sys.stderr)
        return 2
    store_scores(args, run_id, model, scores)
    avg = sum(s["score"] for s in scores) / len(scores)
    print(f"Judge ({model}) scored run {run_id}: overall {avg:.2f}")
    for s in scores:
        print(f"  {s['dimension']}: {s['score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
