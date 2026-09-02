---
name: rca-scope
description: >
  Give an existing PLM-issue RCA run its analysis boundary: classify the
  issue type from the PLM title/description, settle a failure time
  (engineer-supplied or determined from the log), and narrow the log to a
  time window, a set of DuckDB tables, and a set of protocol layers. Writes
  `scope.json` under an existing run created by `rca-intake`. Use ONLY when
  an engineer wants to scope, narrow, re-narrow, or adjust the boundary of
  an existing PLM-issue run (e.g. "scope PLM-12345", "narrow the window on
  this run", "re-run scoping with a tighter window", "what kind of issue is
  this"). Requires a run bundle that already exists — invoke `rca-intake`
  first if `.rca/issues/<issue_id>/` does not yet exist. `rca-analyze` is
  what locates a failure point in signalling/trace, generates hypotheses,
  and reaches a conclusion — do not use this skill for those. `rca-intake`
  is what fetches and re-fetches anything from PLM — do not use this skill
  for that; re-invoking this skill never touches PLM.
---

# rca-scope

Part of the PLM-issue pipeline (issue #5): `rca-intake → rca-scope →
rca-analyze ⟲ → rca-conclude → rca-learn`. This is the pipeline's second
step (issue #7). Read `.claude/skills/_shared/run-bundle-layout.md` before
changing anything below — it is the authoritative schema for `scope.json`
and this skill's other writes. This skill's only tool dependency is the
log-query capability, documented in
`.claude/skills/_shared/log-query-invocation.md` — read that before
changing how this skill calls it.

```yaml
contract:
  requires: [issue_id, existing_run, duckdb_path, tables]
  optional: [run_id, failure_time, classification_hint, window_before_ms, window_after_ms]
  produces:
    - .rca/issues/<issue_id>/runs/run-NN/scope.json
    - .rca/issues/<issue_id>/runs/run-NN/evidence/tools.jsonl (appended)
    - .rca/issues/<issue_id>/runs/run-NN/raw/rca-scope-q-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, next_step, status, updated_at only)
  self_seedable: false
```

Unlike `rca-intake`'s `requires`, none of these (besides `issue_id`) are
supplied at invocation — `existing_run` means a run must already exist
under `runs/` with a `manifest.json`; `duckdb_path` and `tables` are read
from that issue's `input/log-pointers.json`, not passed as arguments here.
`self_seedable: false` — this skill operates on a run bundle `rca-intake`
already created. There is nothing for an engineer to seed directly that
would let this skill skip that precondition; if the bundle doesn't exist,
the fix is to run `rca-intake`, not to pass more arguments to this skill.

## What this delivers

The boundary everything downstream queries inside: what kind of issue this
is, when it happened (and how that's known), and which time window, tables,
and layers are in scope. It is also this suite's first skill to make real
log queries, so it is where the query discipline starts — every log-query
call names the table it touched and the keywords it used, per
`log-query-invocation.md` and `tool-ledger-format.md`.

## Inputs

- `issue_id` (required, from invocation or `/rca`'s dispatch) — which issue
  this run belongs to.
- `run_id` (optional) — which run to scope. Defaults to `issue.json`'s
  `active_run` if set, else the highest-numbered entry in `issue.json.runs`.
- `failure_time` (optional) — an ISO 8601 timestamp (or something
  unambiguously convertible to one) the engineer already knows. When
  supplied, this skill does not query the log to determine a failure time
  at all — see Step 4.
- `classification_hint` (optional) — an issue type the engineer asserts
  directly (e.g. "treat this as sms_failure"), overriding whatever
  `known-issue-types.md` would otherwise match.
- `window_before_ms` / `window_after_ms` (optional) — override the default
  window margins used in Step 5 (30000 / 10000).

## Steps

### 1. Resolve `issue_id` and the target run

1. If `issue_id` is missing, HALT: "Need a PLM issue ID to scope. Which
   issue?" Do not guess one from conversation context.
2. If `.rca/issues/<issue_id>/` does not exist, HALT: "No run bundle for
   `<issue_id>` — run `rca-intake` first." Never create one here.
3. Read `issue.json`. Resolve the target run: the supplied `run_id`, else
   `active_run` if set, else the highest-numbered entry in `runs`. If none
   resolves (empty `runs`), HALT: "`<issue_id>` has no runs yet — run
   `rca-intake` first."
4. Read that run's `manifest.json`. If it is missing, HALT: "Run `<run_id>`
   has no `manifest.json` — its bundle looks incomplete; re-run
   `rca-intake` or check for a partial write."

### 2. Check the log-pointers precondition

Read `input/log-pointers.json`.

- If `duckdb_path` is `null`: HALT: "`input/log-pointers.json.duckdb_path`
  is not set. Supply it (or edit that file directly) before `rca-scope` can
  query the log." Never assume a workspace-default path.
- If `tables` is empty: HALT: "`input/log-pointers.json.tables` is empty.
  Supply at least one table before `rca-scope` can query the log."
- Otherwise proceed with `duckdb_path`, `tables`, and `time_range` (which
  may still have `null` `start`/`end` — that's handled in Step 5, not an
  error here).

This is this skill's contract `requires` check — a missing precondition
here means HALT and state exactly what's missing, never assume a default
or proceed with a guess.

### 3. Classify the issue

1. Read `input/plm-snapshot.json` (already on disk from the most recent
   `rca-intake` fetch — **never re-fetch from PLM here**, on a fresh scope
   or a re-run alike).
2. Determine `issue_type` and `classification.tier`:
   - **`classification_hint` supplied**: `issue_type` = that value,
     `classification.tier = "ENGINEER_PROVIDED"`, `classification.evidence`
     records the engineer's assertion.
   - **No hint**: check `title` and `description` (case-insensitive
     substring match) against `references/known-issue-types.md`'s
     `trigger_keywords`, first matching row wins. On a match, `issue_type`
     = that row's `issue_type`, `classification.tier = "TESTER_REPORTED"`
     (the match came from the PLM text, i.e. the tester's own words),
     `classification.evidence` records which keyword matched and where
     (`plm-snapshot.title` or `plm-snapshot.description`). On no match,
     `issue_type = "generic"`, `classification.tier = null` (nothing is
     being claimed).
3. Resolve `matched_playbook`: whichever row in
   `references/known-issue-types.md` has `issue_type` equal to the value
   just determined, or `null` if none does. This step runs regardless of
   how `issue_type` was determined — a `classification_hint` naming an
   `issue_type` absent from that file resolves `matched_playbook` to
   `null` exactly like the auto-classified `"generic"` case does.
4. `reduced_tier = (matched_playbook is null)`. When true,
   `reduced_tier_reason` states plainly why — either "PLM text matched no
   known issue type" or "the engineer-supplied classification hint
   '`<value>`' names no known issue type" — and this run proceeds
   generically for Step 6's table/layer defaults: never force it into the
   nearest-looking row. Append a matching `open_notes[]` entry.

### 4. Determine the failure time

- **Engineer-supplied** (`failure_time` input given): `failure_time.value`
  = that timestamp, `origin = "engineer"`, `tier = "ENGINEER_PROVIDED"`,
  `evidence_ref = null`. No log query runs for this step.
- **Not supplied**: determine it from the log.
  1. Build the keyword list: the matched row's `failure_indicator_keywords`
     when `matched_playbook` is non-null; otherwise the generic fallback
     list, both from `references/known-issue-types.md`. Record which list
     was used — this is the keyword's stated origin for the ledger line,
     per `log-query-invocation.md`.
  2. Call the log-query capability once per table in
     `input/log-pointers.json.tables`, with those keywords and
     `time_window` set to `input/log-pointers.json.time_range` (pass
     through its `null`s as-is if the loaded range isn't known either —
     an unbounded query is still a valid one).
  3. For each call: write the raw result to
     `raw/rca-scope-q-<NN>.json` and append a ledger line, per
     `log-query-invocation.md`. This applies to every call, including one
     that returns zero hits.
  4. If any call returned a hit: take the earliest matching event's
     timestamp as `failure_time.value`, `origin = "log"`, `tier =
     "VERIFIED_LOG"`, `evidence_ref` pointing at the ledger line + the
     `raw/` file that produced it.
  5. If no call returned a hit: `failure_time.value = null`, `origin =
     "undetermined"`, `tier = null`. Append an `open_notes[]` entry stating
     the failure time could not be pinned from the log and the window
     (Step 5) is falling back to the full loaded range as a result. This
     is not a HALT — a vague report must still be analysable, just with a
     wider, explicitly-flagged window instead of a precise one.

### 5. Compute the window

- If `failure_time.value` is set (either origin): `window.start` =
  `failure_time.value` minus `window_before_ms` (default 30000ms),
  `window.end` = `failure_time.value` plus `window_after_ms` (default
  10000ms). If `input/log-pointers.json.time_range` has non-null bounds,
  clip `window.start`/`window.end` to them — the window can never exceed
  what's actually loaded. `window.basis` states the margins used and
  whether clipping applied.
- If `failure_time.value` is `null` (undetermined): `window` = the full
  `input/log-pointers.json.time_range`, whatever it is (including `null`
  bounds, if that's genuinely unknown too). `window.basis` states this
  explicitly: "failure time undetermined — using full loaded log range."

### 6. Set `tables_in_scope` and `layers`

- `matched_playbook` is non-null: use that row's `tables_in_scope` and
  `layers` from `references/known-issue-types.md`, intersected with what's
  actually available in `input/log-pointers.json.tables` (never claim a
  table that isn't loaded).
- `matched_playbook` is `null` (whether `issue_type` is `"generic"` or an
  engineer hint that named no known row): `tables_in_scope` = all of
  `input/log-pointers.json.tables` (no narrowing to justify), `layers` =
  `[]` with an `open_notes[]` entry stating layer narrowing wasn't
  possible generically — a later skill reading `scope.json` should treat
  an empty `layers` as "unnarrowed", not "no layers matter".

### 7. Write `scope.json`

Fully overwrite `runs/run-NN/scope.json` per the schema in
`run-bundle-layout.md` — a re-run **replaces** the file, it does not merge
with a prior scope.

### 8. Update `manifest.json`

Update in place (not a full rewrite): `current_step: "rca-scope"`,
`next_step: "rca-analyze"`, `updated_at` to now. Leave `status`,
`current_round`, `standing_recommendation`, and `decisions` untouched —
those belong to `rca-analyze`'s checkpoint/loop logic (issues #8/#9), not
this skill's.

### 9. Report to the engineer

State plainly:
- `issue_type` and whether it matched a playbook or is proceeding
  generically (and why, if generic).
- `failure_time.value`, its `origin`, and its `tier` — or that it's
  undetermined and the window fell back to the full loaded range.
- `window.start`/`window.end`, `tables_in_scope`, `layers`.
- Every entry in `open_notes[]`.
- That the next pipeline step is `rca-analyze` — do not imply it will run
  automatically; that is a separate invocation (or `/rca`'s dispatch), not
  something this skill chains into.

## What this skill does not do

- `rca-analyze` owns hypothesis generation, failure-point location within
  a message exchange, and reaching a root cause — not this skill.
- A failure-time query that finds no hit stays a miss: `failure_time.value`
  is set to `null` (`origin: "undetermined"`) — never inferred or
  fabricated into a timestamp.
- `manifest.json.autonomy` governs only `rca-analyze`'s checkpoints and
  loop — this skill halts after Step 9 regardless of that field's value.
