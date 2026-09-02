---
name: rca-scope
description: >
  Scope an existing PLM-issue RCA run to set its analysis boundary (issue type,
  failure time, time window, DuckDB tables, protocol layers) and write `scope.json`.
  Triggers: "scope PLM-12345", "narrow window/tables", "re-scope run", "what issue type".
  Precondition: `.rca/issues/<issue_id>/` exists (run `rca-intake` first).
  Anti-triggers: fetching PLM data (use `rca-intake`), hypothesis testing or root cause (use `rca-analyze`).
---

# rca-scope

Part of the PLM-issue pipeline: `rca-intake → rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`.
Establishes the analysis boundary in `scope.json` for downstream skills.

**Contracts & Reference Docs**:
- Run bundle schema & write ownership: `.claude/skills/_shared/run-bundle-layout.md`
- Log query invocation: `.claude/skills/_shared/log-query-invocation.md`

```yaml
contract:
  requires: [issue_id, existing_run, duckdb_path, tables]
  optional: [run_id, failure_time, classification_hint, window_before_ms, window_after_ms]
  produces:
    - .rca/issues/<issue_id>/runs/run-NN/scope.json
    - .rca/issues/<issue_id>/runs/run-NN/evidence/tools.jsonl (appended)
    - .rca/issues/<issue_id>/runs/run-NN/raw/rca-scope-q-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, next_step, status, updated_at)
  self_seedable: false
```

## Inputs

- `issue_id` (required): PLM issue identifier.
- `run_id` (optional): Defaults to `issue.json.active_run`, or highest-numbered run in `issue.json.runs`.
- `failure_time` (optional): Known ISO 8601 timestamp; skips log queries for failure time.
- `classification_hint` (optional): Explicit issue type (e.g. `sms_failure`), overrides keyword matching.
- `window_before_ms` / `window_after_ms` (optional): Window margins in ms (default: `30000` / `10000`).

## Steps

### 1. Resolve issue_id and target run

1. If `issue_id` is missing: HALT with `"Need a PLM issue ID to scope. Which issue?"`.
2. If `.rca/issues/<issue_id>/` is missing: HALT with `"No run bundle for <issue_id> — run rca-intake first."`.
3. Read `issue.json`. Resolve target run: explicit `run_id` → `active_run` → highest `runs` entry. If `runs` is empty: HALT with `"<issue_id> has no runs yet — run rca-intake first."`.
4. Read target run's `manifest.json`. If missing: HALT with `"Run <run_id> has no manifest.json — bundle incomplete."`.

### 2. Check log-pointers precondition

Read `input/log-pointers.json`:
- If `duckdb_path` is `null`: HALT with `"input/log-pointers.json.duckdb_path is not set."`.
- If `tables` is empty: HALT with `"input/log-pointers.json.tables is empty."`.
- Otherwise: proceed using `duckdb_path`, `tables`, and `time_range`.

### 3. Classify issue

1. Read `input/plm-snapshot.json` exclusively from disk (never invoke PLM fetch).
2. Determine `issue_type` and `classification.tier`:
   - **`classification_hint` provided**: `issue_type` = hint value, `tier` = `"ENGINEER_PROVIDED"`, `evidence` = engineer assertion.
   - **No hint**: match `title` and `description` (case-insensitive substring) against `references/known-issue-types.md` `trigger_keywords`. First match wins → `issue_type` = row value, `tier` = `"TESTER_REPORTED"`, `evidence` = matched field + keyword. If no match → `issue_type` = `"generic"`, `tier` = `null`.
3. Resolve `matched_playbook`: row in `references/known-issue-types.md` matching `issue_type`, else `null`.
4. If `matched_playbook` is `null`: set `reduced_tier = true` with `reduced_tier_reason` stating why ("PLM text matched no known issue type" or "hint '<value>' names no known issue type"). Append entry to `open_notes[]`.

### 4. Determine failure time

- **Engineer-supplied** (`failure_time` given): `value` = input timestamp, `origin = "engineer"`, `tier = "ENGINEER_PROVIDED"`, `evidence_ref = null`. Skip log queries.
- **Log-determined** (`failure_time` omitted):
  1. Keywords = `matched_playbook.failure_indicator_keywords` if non-null, else generic fallback list from `references/known-issue-types.md`.
  2. Query log capability once per table in `input/log-pointers.json.tables` using selected keywords and `time_window = input/log-pointers.json.time_range`.
  3. Write raw response to `raw/rca-scope-q-<NN>.json` and append line to `evidence/tools.jsonl` per `log-query-invocation.md` for every call.
  4. On hit: `value` = timestamp of earliest matching event, `origin = "log"`, `tier = "VERIFIED_LOG"`, `evidence_ref` = ledger line + raw file.
  5. On no hit: `value = null`, `origin = "undetermined"`, `tier = null`. Append note to `open_notes[]` indicating failure time could not be pinned and window falls back to loaded range.

### 5. Compute window

- **If failure time set**: `window.start` = `failure_time` - `window_before_ms` (default 30000), `window.end` = `failure_time` + `window_after_ms` (default 10000). Clip bounds to `input/log-pointers.json.time_range` if non-null. Record margin and clipping status in `window.basis`.
- **If failure time null**: `window` = full `input/log-pointers.json.time_range`. `window.basis` = `"failure time undetermined — using full loaded log range."`.

### 6. Set tables_in_scope and layers

- **`matched_playbook` non-null**: `tables_in_scope` = playbook tables intersected with `input/log-pointers.json.tables`. `layers` = playbook layers.
- **`matched_playbook` null**: `tables_in_scope` = all `input/log-pointers.json.tables`. `layers` = `[]` with an `open_notes[]` entry indicating unnarrowed layers.

### 7. Write scope.json

Overwrite `runs/run-NN/scope.json` per schema in `run-bundle-layout.md`.

### 8. Update manifest.json

Update fields in place: `current_step: "rca-scope"`, `next_step: "rca-analyze"`, `updated_at` = current timestamp. Retain all other manifest fields untouched.

### 9. Report summary

Present report to engineer:
- `issue_type` and classification basis (playbook name or generic reason).
- `failure_time` value, origin, tier (or undetermined fallback).
- `window` bounds (`start`/`end`), `tables_in_scope`, `layers`.
- All `open_notes[]` items.
- Next step indicator: `rca-analyze`.

## Completion Criteria

- `runs/run-NN/scope.json` exists, matches `run-bundle-layout.md` schema, and accurately reflects inputs/log evidence.
- Every log query issued is recorded in `raw/rca-scope-q-NN.json` and appended to `evidence/tools.jsonl`.
- `manifest.json` updated with `current_step: "rca-scope"` and `next_step: "rca-analyze"`.
- Summary report presented to engineer containing issue_type, failure_time, window, tables, layers, and open_notes.

