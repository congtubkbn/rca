---
name: rca-intake
description: >
  Start or resume a PLM-issue root-cause-analysis run bundle: fetch a PLM
  issue's title, description, and tester reproduction steps via the PLM
  MCP connection, then open (or add a new run under) its
  `.rca/issues/<issue_id>/` folder on disk. Use ONLY when the engineer
  names a PLM issue ID and wants to start or restart analysis on it (e.g.
  "start analysis on PLM-12345", "open a new run for PLM-12345 with the
  new logs", "intake this PLM issue"). Do NOT use
  this mid-analysis to advance an existing run to its next step — that is
  `/rca`'s job, and the next step after intake is `rca-scope`, not this
  skill again. Do NOT use this to classify the issue, narrow a time
  window, query logs, or reach any conclusion — this skill only records
  what PLM says and opens a place to work; it does no analysis at all.
---

# rca-intake

Part of the PLM-issue pipeline (issue #5): `rca-intake → rca-scope →
rca-analyze ⟲ → rca-conclude → rca-learn`. This skill is the pipeline's
sole entry point and the only skill this ticket (issue #6) implements.
Read `.claude/skills/_shared/run-bundle-layout.md` before changing
anything below — it is the authoritative schema for every file this skill
writes.

```yaml
contract:
  requires: [issue_id]
  optional: [label, duckdb_path, tables, time_range, build, model, source_checkout]
  produces:
    - .rca/issues/<issue_id>/issue.json
    - .rca/issues/<issue_id>/input/plm-snapshot.json
    - .rca/issues/<issue_id>/input/log-pointers.json
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json
    - .rca/issues/<issue_id>/runs/run-NN/evidence/tools.jsonl
  self_seedable: true
```

## What this delivers

A durable, inspectable starting point later steps read from — never a
conclusion, never even a classification. The engineer's tester-reported
account is recorded as a claim (`TESTER_REPORTED`), not as fact, and the
PLM text is snapshotted as it read at the moment of this fetch, so a later
edit in PLM cannot silently change what a conclusion ends up resting on.
Logs are never copied — they already live in DuckDB, so what is recorded
is a pointer (database, tables, time range) alongside build/model and the
source checkout and commit id, wherever the engineer or invocation
supplies them.

## Inputs

- `issue_id` (required) — the PLM issue ID, e.g. `PLM-12345`. Taken from
  the engineer's invocation. If absent, HALT: "Need a PLM issue ID to
  start intake. Which issue?" Do not guess one from conversation context.
- `label` (optional) — free text describing this run's intent (e.g. "first
  pass", "re-run with corrected build"). Defaults to `"run <N>"` if not
  supplied.
- `duckdb_path`, `tables`, `time_range`, `build`, `model`,
  `source_checkout` (all optional) — whatever the engineer already knows
  about where the log lives and what produced it. Any field not supplied
  is recorded as `null` in `input/log-pointers.json`, never guessed or
  defaulted to a workspace convention this skill hasn't actually checked.

## Steps

### 1. Resolve `issue_id`

If missing, HALT per above. Otherwise proceed.

### 2. Fetch the issue via PLM MCP

Call the PLM MCP connection's issue-fetch operation for `issue_id`,
requesting title, description, and tester reproduction steps.

This connection is a workspace dependency, not part of this repository (see
root `CLAUDE.md`): it is expected to already be configured in the
environment this skill runs in, and this skill does not attempt to
configure or discover it.

- **If the PLM MCP connection is unavailable** (not configured, fails to
  connect): append an `error` line to this run's `evidence/tools.jsonl`
  (see step 3 — the run directory must exist first; see step 5's ordering
  note) and HALT: "PLM MCP is not available: `<reason>`. Cannot fetch
  `<issue_id>`." Never fabricate an issue record to keep going.
- **If `issue_id` is unknown to PLM** (fetch succeeds but returns not-found):
  HALT: "PLM has no issue `<issue_id>`. Check the ID and try again." Never
  invent a title, description, or reproduction steps to fill the gap.
- **On success**, hold the returned title, description, and tester
  reproduction steps verbatim — do not rephrase, summarize, or correct
  them here. Rephrasing is analysis; this skill does none.

### 3. Determine the issue folder and next run number

1. Check whether `.rca/issues/<issue_id>/` exists.
2. If it does not exist, this is the first intake for this issue: create
   `.rca/issues/<issue_id>/`, `input/`, and `runs/`. The next run is
   `run-01`.
3. If it does exist, this is a re-run: list `runs/` and take one past the
   highest existing run number (zero-padded to two digits). **Never
   overwrite an existing run's directory or `manifest.json`** — a new run
   is always created, per `run-bundle-layout.md`'s numbering rule.

### 4. Write the ledger line

Create `runs/run-NN/evidence/` and append one line to `tools.jsonl` for
the PLM MCP call made in step 2, per
`.claude/skills/_shared/tool-ledger-format.md` — including on failure,
before halting. This is the run's sole tool-call ledger entry from this
skill.

### 5. Write `issue.json`

Create it (first intake) or refresh `plm.title`/`plm.url` in place
(re-run), per the schema in `run-bundle-layout.md`. `active_run` is left
`null` — this skill never sets it. Append the new run ID to `runs`.

### 6. Write `input/plm-snapshot.json`

Fully overwrite with this fetch's `fetched_at` timestamp, verbatim
`title`, verbatim `description`, and
`tester_reproduction_steps: {text: <verbatim>, tier: "TESTER_REPORTED"}`,
per the schema in `run-bundle-layout.md`.

### 7. Write `input/log-pointers.json`

Fully overwrite from whatever optional inputs were supplied
(`duckdb_path`, `tables`, `time_range`, `build`, `model`,
`source_checkout`), with any field not supplied written as `null`. The
schema (`run-bundle-layout.md`) has no per-field tier — every non-null
value here is implicitly `ENGINEER_PROVIDED`, since this skill verifies
none of it itself; that is a property of this file, not something this
step records per field.

### 8. Write `runs/run-NN/manifest.json`

Create it per the schema in `run-bundle-layout.md`:
`status: "in_progress"`, `current_step: "rca-intake"`,
`next_step: "rca-scope"`, `input_snapshot_fetched_at` copied from step 6's
`fetched_at`, `autonomy: "review_all"`, `round_budget: 5`,
`current_round: 0`, `standing_recommendation: null`, and `label` from the
optional input or the `"run <N>"` default.

### 9. Report to the engineer

State plainly:
- The issue folder path and run ID just created/opened.
- A short summary of what was fetched (title; that description and tester
  reproduction steps were snapshotted verbatim).
- Which `log-pointers.json` fields are still `null` and therefore still
  need to be supplied before log-dependent steps can run.
- That the next pipeline step is `rca-scope` — do not imply it will run
  automatically; that is a separate invocation (or `/rca`'s dispatch).

## What this skill does not do

- ❌ No log queries, spec queries, or code search of any kind.
- ❌ No classification of the issue, no time-window narrowing — that is
  `rca-scope`.
- ❌ No hypothesis generation, no root cause, no reproduction scenario.
- ❌ No chaining into any other skill — it halts after step 9 regardless
  of autonomy settings (there are none yet to consult; `manifest.json`'s
  `autonomy` field is a default for later skills to read, not something
  this skill acts on).
- ❌ Never fabricates a PLM record when the connection is down or the ID
  is unknown (step 2) — a stated reason beats an invented one every time.
