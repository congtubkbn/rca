#!/usr/bin/env python3
"""eval_judge.py — LLM-as-judge scoring of a completed RCA run against the
6-dimension rubric in .cline/skills/3gpp-rca-evaluator/references/evaluation-rubric.md.

The judge reads ONLY the final report + the eval record. It must not re-run
retrieval — it grades reasoning rigor and internal consistency, it does not
redo the RCA.

Modes (checked in this order):
  1. Local / self-hosted LLM: with RCA_JUDGE_BASE_URL set (or --base-url),
     calls any OpenAI-compatible chat endpoint — Ollama (http://localhost:11434/v1),
     vLLM, LM Studio, llama.cpp server… — and writes scores into DuckDB.
     Model comes from --model or RCA_JUDGE_MODEL; API key (only if the server
     requires one) from RCA_JUDGE_API_KEY.
  2. With ANTHROPIC_API_KEY set: calls the Claude API directly and writes
     scores into the DuckDB store.
  3. Without either: writes the fully-assembled judge prompt to a file so a
     human or an interactive agent session can produce the scores, then
     scores can be loaded with --load-scores.

Usage:
    python eval_judge.py --db rca_eval.duckdb --report REPORT.md --record EVAL_RECORD.json
    python eval_judge.py --db rca_eval.duckdb --report R.md --record E.json \
        --base-url http://localhost:11434/v1 --model qwen2.5:32b
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


def _extract_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"No JSON object in judge output: {text[:200]!r}")
    return json.loads(text[start:end + 1])


def call_openai_compatible(prompt, model, base_url, api_key=None):
    """Score via any OpenAI-compatible /chat/completions endpoint (Ollama,
    vLLM, LM Studio, llama.cpp server, …). Keeps the whole eval loop local —
    no report content leaves the machine."""
    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps({
            "model": model,
            "temperature": 0,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.load(resp)
    text = body["choices"][0]["message"]["content"] or ""
    return _extract_json(text)


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
    return _extract_json(text)


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
    stored = 0
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
        stored += 1
    con.close()
    return stored


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--report")
    ap.add_argument("--record")
    ap.add_argument("--model", default=None,
                    help="Judge model. Default: RCA_JUDGE_MODEL when a local "
                         "endpoint is used, else claude-sonnet-5")
    ap.add_argument("--base-url",
                    default=os.environ.get("RCA_JUDGE_BASE_URL"),
                    help="OpenAI-compatible endpoint for a local/self-hosted "
                         "judge (e.g. http://localhost:11434/v1 for Ollama). "
                         "Also settable via RCA_JUDGE_BASE_URL.")
    ap.add_argument("--load-scores", metavar="SCORES.json")
    ap.add_argument("--prompt-out", help="Where to write the prompt in no-API mode "
                                         "(default: judge_prompt_<run_id>.md next to record)")
    args = ap.parse_args()

    if args.load_scores:
        with open(args.load_scores, encoding="utf-8") as f:
            payload = json.load(f)
        n = store_scores(args.db, payload["run_id"],
                         payload.get("judge_model", "human"), payload["scores"])
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

    result = judge_model = None
    if args.base_url:
        judge_model = args.model or os.environ.get("RCA_JUDGE_MODEL")
        if not judge_model:
            print("ERROR: local judge needs --model or RCA_JUDGE_MODEL "
                  "(the endpoint can host several models)", file=sys.stderr)
            return 1
        result = call_openai_compatible(
            prompt, judge_model, args.base_url,
            api_key=os.environ.get("RCA_JUDGE_API_KEY"))
    elif os.environ.get("ANTHROPIC_API_KEY"):
        judge_model = args.model or "claude-sonnet-5"
        result = call_claude(prompt, judge_model)

    if result is not None:
        store_scores(args.db, run_id, judge_model, result["scores"])
        avg = sum(int(s["score"]) for s in result["scores"]) / len(result["scores"])
        print(f"Judge ({judge_model}) scored run {run_id}: overall {avg:.2f}")
        for s in result["scores"]:
            print(f"  {s['dimension']}: {s['score']}")
        return 0

    out = args.prompt_out or os.path.join(
        os.path.dirname(os.path.abspath(args.record)), f"judge_prompt_{run_id}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"No RCA_JUDGE_BASE_URL / ANTHROPIC_API_KEY — judge prompt written to {out}\n"
          f"Have a human or agent produce the scores JSON, then run:\n"
          f"  python eval_judge.py --db {args.db} --load-scores SCORES.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
