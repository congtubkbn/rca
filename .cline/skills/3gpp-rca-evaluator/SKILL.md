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

Turn a finished RCA run into evaluation data. Three stages, each optional
after the first:

1. **EXTRACT** (always) — state file → compact anonymized eval record in the
   outbox. Runs on the engineer's machine, no network.
2. **JUDGE** (when requested / when API available) — score the final report
   against the rubric in `references/evaluation-rubric.md`.
3. **INGEST + REPORT** (only on the aggregation machine, or when the central
   eval DB path is reachable) — pull outbox records into DuckDB and refresh
   the dashboard.

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
  outcome, duration, iteration count, agreement rate, provenance pass rate.

## Stage 2 — JUDGE (optional)

Only when the user asks for scoring, or a scheduled evaluation is running.

```
<execute_command>
python evaluation/scripts/eval_judge.py --db <eval_db> \
    --report <report_path from phase4_rca_report> \
    --record <eval record from stage 1>
</execute_command>
```

- If no `ANTHROPIC_API_KEY`, the script writes the judge prompt to a file.
  In that case YOU may act as the judge: read the prompt file, produce the
  scores JSON strictly in the rubric's output format, save it, and load it
  with `--load-scores`. When doing so you are bound by the judge
  constraints above (report + record only, no retrieval).
- Human review scores are loaded the same way with `"judge_model": "human"`.

## Stage 3 — INGEST + REPORT (aggregation machine only)

```
<execute_command>
python evaluation/scripts/eval_ingest.py --db <eval_db> --outbox .rca/eval/outbox
python evaluation/scripts/eval_report.py --db <eval_db> --out .rca/eval/dashboard.md
</execute_command>
```

- Skip silently if the eval DB location is not configured/reachable —
  records stay in the outbox for later sync; that is the designed behavior.
- If `eval_report.py --gate` fails (exit 3), surface WHICH KPI gates failed.
  Gate failures after a skill change mean the change regressed quality and
  must not ship.

## Mandatory human-review routing

After stage 3, list runs in the review queue (dashboard section
"Human-review queue"). A run enters the queue when ANY of:
- `high_disagreement_run == true`
- provenance pass rate < 1.0
- outcome == aborted
- any LLM-judge dimension ≤ 2

Present the queue to the user; do not mark runs reviewed yourself.

## What this skill does NOT do (HARD)

- ❌ No modification of state files, reports, or pipeline results
- ❌ No re-running of RCA phases
- ❌ No retrieval tool calls when judging
- ❌ No fabrication of scores — every score needs a rationale citing the report
- ❌ No sending raw state files or logs off the machine
