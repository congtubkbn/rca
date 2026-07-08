# /rca-eval — Post-Run Quality Evaluation for the RCA Pipeline

Companion workflow to `/rca`. Turns a finished run into evaluation data,
optionally scores it, and (on the aggregation machine) refreshes the fleet
quality dashboard. Read-only over pipeline state; safe to run anytime.

Invoke with `/rca-eval` followed by optional arguments:
- (nothing) — evaluate the most recent run (`.rca/current_state_path.txt`)
- `<state_file_path>` — evaluate a specific run
- `golden <case_id>` — benchmark run: compare against
  `evaluation/golden/cases/<case_id>/case.json`
- `judge` — additionally score the run against the rubric
- `aggregate` — ingest outbox into the central DuckDB store and rebuild
  the dashboard (aggregation machine only)
- `amend <run_id> confirmed|reopened` — record retrospective outcome
  (fix confirmed the RCA / case was reopened)

---

## Workflow steps

<explicit_instructions>

### Step 0 — Resolve target

1. If args contain `amend` → go to Step 4.
2. If args contain `aggregate` (and no state file) → go to Step 3.
3. Resolve the state file: explicit path from args, else read
   `.rca/current_state_path.txt`. If neither exists → HALT:
   "No RCA run found to evaluate. Provide a state file path."
4. Read `meta.current_phase` from the state file. If not `complete`, warn
   the user that the record will be flagged `incomplete`, then continue.

### Step 1 — Extract (always)

Trigger the evaluator skill:
```
Use the 3gpp-rca-evaluator skill, stage EXTRACT, on state file <path>.
Golden case: <case.json path if `golden <case_id>` was given, else none>.
```
Report to the user: record path, outcome, duration, iteration count,
agreement rate, provenance pass rate.

### Step 2 — Judge (only if `judge` in args)

```
Use the 3gpp-rca-evaluator skill, stage JUDGE, with the eval record from
Step 1 and the report at phase4_rca_report.report_path.
```
If the run has no report (aborted), skip with a note.

### Step 3 — Aggregate (only if `aggregate` in args)

```
Use the 3gpp-rca-evaluator skill, stage INGEST + REPORT.
Eval DB: $RCA_EVAL_DB (default: .rca/eval/rca_eval.duckdb)
Outbox:  .rca/eval/outbox
```
Present the KPI-vs-gates table and the human-review queue from the
dashboard. If any gate failed, state it prominently.

### Step 4 — Amend (only for `amend <run_id> <verdict>`)

```
<execute_command>
python evaluation/scripts/eval_ingest.py --db $RCA_EVAL_DB \
    --amend <run_id> --set <rca_confirmed_by_fix=true | reopened=true>
</execute_command>
```
`confirmed` → `rca_confirmed_by_fix=true`; `reopened` → `reopened=true`.

</explicit_instructions>

---

## Scheduling note

On the aggregation machine, run `/rca-eval aggregate` on a schedule (cron
or CI, e.g. hourly/nightly) so the dashboard stays current while engineer
machines only ever run the zero-cost extract step. Engineer machines sync
their `.rca/eval/outbox/` to the aggregation point (shared folder, git
branch, or object storage) — records are idempotent by run_id, so re-syncs
are harmless.
