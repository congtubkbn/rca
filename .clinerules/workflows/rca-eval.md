# /rca-eval — Post-Run Quality Evaluation for the RCA Pipeline

Companion workflow to `/rca`. Turns a finished run into evaluation data,
scores runs against the 6-dimension rubric, and refreshes the fleet quality
dashboard. Read-only over pipeline state; safe to run anytime. Designed for
ClineSR (Gauss) on Windows: every step below is stdlib-Python + this agent.

Invoke with `/rca-eval` followed by optional arguments:
- (nothing) — evaluate the most recent run (`.rca/current_state_path.txt`)
- `<state_file_path>` — evaluate a specific run
- `golden <case_id>` — benchmark run: compare against
  `evaluation/golden/cases/<case_id>/case.json`
- `judge` — additionally score the run against the rubric
- `judge-pending` — score ALL runs still waiting for judge scores
  (run this in a FRESH ClineSR task, never the task that produced a run)
- `sweep` — coverage sweep: extract every missed run on this machine,
  queue judge prompts, sync outbox (criteria M-70)
- `dashboard` — rebuild dashboard.html + dashboard_data.json from local
  (or synced) records
- `aggregate` — ingest outbox into the central DuckDB store and rebuild
  the dashboard (aggregation machine only)
- `amend <run_id> confirmed|reopened` — record retrospective outcome
  (fix confirmed the RCA / case was reopened)

Scoring criteria reference: `evaluation/criteria/rca-agent-scoring-criteria.md`.

---

## Workflow steps

<explicit_instructions>

### Step 0 — Resolve target

1. If args contain `amend` → go to Step 4.
2. If args contain `judge-pending` → go to Step 5.
3. If args contain `sweep` → go to Step 6.
4. If args contain `dashboard` → go to Step 7.
5. If args contain `aggregate` (and no state file) → go to Step 3.
6. Resolve the state file: explicit path from args, else read
   `.rca/current_state_path.txt`. If neither exists → HALT:
   "No RCA run found to evaluate. Provide a state file path."
7. Read `meta.current_phase` from the state file. If not `complete`, warn
   the user that the record will be flagged `incomplete`, then continue.

### Step 1 — Extract (always)

Trigger the evaluator skill:
```
Use the 3gpp-rca-evaluator skill, stage EXTRACT, on state file <path>.
Golden case: <case.json path if `golden <case_id>` was given, else none>.
```
Report to the user: record path, outcome, duration, iteration count,
agreement rate, provenance pass rate, and the run's provisional RQS:
```
<execute_command>python evaluation/scripts/eval_score.py <record_path></execute_command>
```

### Step 2 — Judge (only if `judge` in args)

```
Use the 3gpp-rca-evaluator skill, stage JUDGE, with the eval record from
Step 1 and the report at phase4_rca_report.report_path.
```
If the run has no report (aborted), skip with a note. IMPORTANT: only run
this stage if the current session did NOT produce the run being judged
(spec IN-4). If it did, tell the user to run `/rca-eval judge-pending`
in a fresh task instead.

### Step 3 — Aggregate (only if `aggregate` in args)

```
Use the 3gpp-rca-evaluator skill, stage INGEST + REPORT.
Eval DB: $RCA_EVAL_DB (default: .rca/eval/rca_eval.duckdb)
Outbox:  .rca/eval/outbox
```
Then rebuild the HTML dashboard (Step 7 commands). Present the KPI-vs-gates
table and the human-review queue. If any gate failed, state it prominently.

### Step 4 — Amend (only for `amend <run_id> <verdict>`)

```
<execute_command>
python evaluation/scripts/eval_ingest.py --db $RCA_EVAL_DB \
    --amend <run_id> --set <rca_confirmed_by_fix=true | reopened=true>
</execute_command>
```
`confirmed` → `rca_confirmed_by_fix=true`; `reopened` → `reopened=true`.

### Step 5 — Judge-pending (agent-as-judge on Gauss, fresh session)

Precondition: this session has NOT run any of the pending runs (it should
be a task opened just for judging — spec IN-4 isolation).

1. Refresh the pending queue:
   ```
   <execute_command>python evaluation/scripts/eval_sweep.py --make-prompts --quiet</execute_command>
   ```
2. List prompt files in `.rca/eval/scores/pending_prompts/`. If empty,
   report "no runs pending judge" and stop.
3. For EACH `judge_prompt_<run_id>.md`, one at a time:
   a. Read the prompt file. It is self-contained (rubric + record + report).
   b. Produce the scores JSON exactly in the rubric's output format —
      6 dimensions, integer 1–5, each with a rationale citing the report.
      You are bound by the judge constraints: report + record only, NO
      retrieval tools, no re-doing the RCA.
   c. Save as `.rca/eval/scores/pending_prompts/scores_draft_<run_id>.json`
      with `"run_id"` and `"judge_model": "<current model name, e.g. gauss>"`.
   d. Load it:
      ```
      <execute_command>python evaluation/scripts/eval_judge.py \
          --load-scores .rca/eval/scores/pending_prompts/scores_draft_<run_id>.json</execute_command>
      ```
   e. Delete the prompt file after a successful load.
4. Re-run the sweep once more so the scores sync out, then report: runs
   scored, overall averages, and any run with a dimension ≤ 2 (flag for
   mandatory human review).

### Step 6 — Sweep (coverage guarantee)

```
<execute_command>python evaluation/scripts/eval_sweep.py --make-prompts</execute_command>
```
Report: counts per status, coverage rate, pending-judge count, synced
count. Coverage < 100% is an incident (spec IN-1) — show which state files
failed extraction.

### Step 7 — Dashboard (local or aggregation machine)

```
<execute_command>
python evaluation/scripts/eval_dashboard.py \
    --records .rca/eval/outbox --records .rca/eval/ingested \
    --scores .rca/eval/scores --coverage .rca/eval/coverage \
    --out .rca/eval/dashboard.html --json .rca/eval/dashboard_data.json
</execute_command>
```
(On the aggregation machine, point --records/--scores/--coverage at the
synced share instead.) Present: fleet RQS, gates passing/failing, review
queue size, and the dashboard file paths. `dashboard_data.json` is the
upload payload for any external dashboard system.

</explicit_instructions>

---

## Scheduling note

Engineer machines are fully automated by the 4 layers in
`evaluation/clinesr-windows-setup.md` (workflow auto-extract, ClineSR hook,
VS Code folderOpen task, Task Scheduler) — they only accumulate and sync
records. On the aggregation machine, run `/rca-eval aggregate` (or the
Step 7 commands via cron/CI, e.g. hourly) so the dashboard stays current.
Records are idempotent by run_id, so re-syncs are harmless.
