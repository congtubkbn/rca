---
name: 3gpp-rca-evaluator
description: >
  Post-run quality evaluation for the 3GPP UE RCA pipeline v6. Use this skill
  AFTER a pipeline run reaches phase "complete" (or aborted) to: extract the
  anonymized eval record from the state file into the eval outbox, optionally
  score the run against the 6-dimension quality rubric (LLM-as-judge), and
  optionally ingest + refresh the quality dashboard when the central eval DB
  is reachable. Read-only over the state file — never modifies pipeline
  behavior or results. Triggers: "evaluate this RCA run", "run RCA quality
  evaluation", "score the RCA report", "/rca-eval". Invoked by the /rca-eval
  workflow.
---

# 3GPP RCA Evaluator Skill — Post-Run Quality Evaluation

## Role

Turn a finished RCA run into evaluation data. Scoring criteria (metric IDs,
RQS composite, gates): `evaluation/criteria/rca-agent-scoring-criteria.md`.
Four stages, each optional after the first:

1. **EXTRACT** (always) — state file → compact anonymized eval record in the
   outbox. Runs on the engineer's machine, no network.
2. **SWEEP** (coverage guarantee, criteria M-70) — scan the machine for ALL
   state files, extract anything missed, queue judge prompts, sync outbox.
3. **JUDGE** (fresh session only — spec IN-4) — score the final report
   against the rubric in `references/evaluation-rubric.md`. On ClineSR the
   judge model is Gauss: either via RCA_JUDGE_API_URL or agent-as-judge.
4. **INGEST + REPORT** (only on the aggregation machine, or when the central
   eval DB path is reachable) — pull outbox records into DuckDB and refresh
   the dashboard (`eval_dashboard.py` for HTML+JSON, `eval_report.py` for
   markdown/SQL).

## Hard constraints

- READ-ONLY over the RCA state file and report. Never write to them.
- Never evaluate a run into a different verdict — this skill measures, it
  does not re-litigate the root cause.
- When acting as judge, use ONLY the report + eval record. NO spec/code/log
  retrieval. The judge grades reasoning rigor and internal consistency; it
  does not redo the RCA.
- Never skip anonymization: only the eval record (hashed machine/user ids)
  leaves the machine, never the raw state file.

## Preconditions

- `<workspace>/.rca/current_state_path.txt` exists (or user supplies a state
  file path explicitly).
- `meta.current_phase == "complete"` — if not, extraction still runs but the
  record is flagged `outcome=incomplete`; report this to the user.
- `evaluation/scripts/` present in the workspace.

## Stage 1 — EXTRACT

```
<execute_command>
python evaluation/scripts/eval_extract.py <state_file_path> \
    [--golden <golden_case.json>]   # only for benchmark runs
</execute_command>
```

- For golden/benchmark runs, the user must name the golden case; pass its
  `case.json`. Never guess a golden case id.
- Report the written record path and the headline numbers back to the user:
  outcome, duration, iteration count, agreement rate, provenance pass rate,
  and the provisional RQS (`python evaluation/scripts/eval_score.py <record>`).

## Stage 2 — SWEEP (coverage guarantee)

```
<execute_command>
python evaluation/scripts/eval_sweep.py --make-prompts --quiet
</execute_command>
```

Idempotent; also triggered automatically by the ClineSR hook, the VS Code
folderOpen task, and Task Scheduler (see `evaluation/clinesr-windows-setup.md`).
Coverage < 100% in the sweep report is an incident (spec IN-1).

## Stage 3 — JUDGE (fresh session only)

HARD precondition (spec IN-4): the current session must NOT be the one that
produced the run being judged. Per-run judging happens via the
`/rca-eval judge-pending` flow in a task opened for judging.

```
<execute_command>
python evaluation/scripts/eval_judge.py \
    --report <report_path from phase4_rca_report> \
    --record <eval record from stage 1> \
    [--db <eval_db>]        # only where duckdb is installed
</execute_command>
```

- With `RCA_JUDGE_API_URL` set (Gauss gateway, OpenAI-compatible) or
  `ANTHROPIC_API_KEY`, the script calls the API and writes
  `scores_<run_id>.json` into `.rca/eval/scores/`.
- Otherwise the script writes a self-contained judge prompt file. Then YOU
  (running Gauss in ClineSR) act as the judge: read the prompt file, produce
  the scores JSON strictly in the rubric's output format with
  `"judge_model": "<your model name>"`, save it, and load it with
  `--load-scores`. You are bound by the judge constraints above (report +
  record only, no retrieval).
- Human review scores are loaded the same way with `"judge_model": "human"`.

## Stage 4 — INGEST + REPORT (aggregation machine only)

```
<execute_command>
python evaluation/scripts/eval_ingest.py --db <eval_db> --outbox .rca/eval/outbox
python evaluation/scripts/eval_report.py --db <eval_db> --out .rca/eval/dashboard.md
python evaluation/scripts/eval_dashboard.py \
    --records .rca/eval/outbox --records .rca/eval/ingested \
    --scores .rca/eval/scores --coverage .rca/eval/coverage \
    --out .rca/eval/dashboard.html --json .rca/eval/dashboard_data.json
</execute_command>
```

- Skip silently if the eval DB location is not configured/reachable —
  records stay in the outbox for later sync; that is the designed behavior.
- If `eval_report.py --gate` fails (exit 3), surface WHICH KPI gates failed.
  Gate failures after a skill change mean the change regressed quality and
  must not ship.

## Mandatory human-review routing

After stage 4, list runs in the review queue (dashboard section
"Human-review queue"). A run enters the queue when ANY of (criteria §6):
- `high_disagreement_run == true`
- provenance pass rate < 1.0
- outcome == aborted
- any LLM-judge dimension ≤ 2
- RQS grade D or F

Present the queue to the user; do not mark runs reviewed yourself.

## What this skill does NOT do (HARD)

- ❌ No modification of state files, reports, or pipeline results
- ❌ No re-running of RCA phases
- ❌ No retrieval tool calls when judging
- ❌ No fabrication of scores — every score needs a rationale citing the report
- ❌ No sending raw state files or logs off the machine
