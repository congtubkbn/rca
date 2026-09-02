---
name: rca-intake
description: >
  Start or resume a PLM-issue root-cause-analysis run bundle: fetch a PLM
  issue's title, description, and comments via the PLM MCP connection
  (three separate operations — title, description, comments; see
  `.claude/skills/_shared/plm-invocation.md`), then open (or add a new run
  under) its `.rca/issues/<issue_id>/` folder on disk. Use ONLY when the
  engineer names a PLM issue ID and wants to start or restart analysis on
  it (e.g. "start analysis on PLM-12345", "open a new run for PLM-12345
  with the new logs", "intake this PLM issue"), or wants to record/correct
  an `engineer_clarification` on an existing issue's PLM text (this always
  goes through a normal intake invocation — see Inputs). Advancing an
  existing run to its next step is `/rca`'s dispatch job — the next step
  after intake is `rca-scope`, never this skill again — so do not reach
  for this mid-analysis for that. This skill only records what PLM says
  (plus, optionally, an engineer's explicit clarification of it) and opens
  a place to work, doing no analysis of any kind — do not use it to
  classify the issue, narrow a time window, query logs, or reach any
  conclusion.
---

# rca-intake

Part of the PLM-issue pipeline (issue #5): `rca-intake → rca-scope →
rca-analyze ⟲ → rca-conclude → rca-learn`. This skill is the pipeline's
sole entry point. Read `.claude/skills/_shared/run-bundle-layout.md` and
`.claude/skills/_shared/plm-invocation.md` before changing anything below
— together they are the authoritative schema and external-call contract
for every file this skill writes.

```yaml
contract:
  requires: [issue_id]
  optional: [label, duckdb_path, tables, time_range, build, model, source_checkout, title_clarification, description_clarification, comments_clarification]
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
conclusion, never even a classification. PLM's `title`/`description`/
`comments` are snapshotted verbatim as read at the moment of this fetch,
so a later edit in PLM cannot silently change what a conclusion ends up
resting on; none of the three is tagged with an evidence tier at this
point, because none is yet a claim used in analysis (`rca-scope`/
`rca-analyze`/`rca-conclude` assign `TESTER_REPORTED` later, at the point
one of them is actually used as a claim). An engineer may additionally
supply an `engineer_clarification` for any of the three — a correction or
clarification used only because a tester's raw account can be unclear or
technically imprecise — recorded separately, tier `ENGINEER_PROVIDED`,
never overwriting the verbatim PLM text it clarifies. Logs are never
copied — they already live in DuckDB, so what is recorded is a pointer
(database, tables, time range) alongside build/model and the source
checkout and commit id, wherever the engineer or invocation supplies them.

## Inputs

- `issue_id` (required) — the PLM issue ID, e.g. `PLM-12345`. Taken
  from the engineer's invocation. If absent, HALT: "Need a PLM issue ID to
  start intake. Which issue?" Do not guess one from conversation context.
- `label` (optional) — free text describing this run's intent (e.g. "first
  pass", "re-run with corrected build"). Defaults to `"run <N>"` if not
  supplied.
- `duckdb_path`, `tables`, `time_range`, `build`, `model`,
  `source_checkout` (all optional) — whatever the engineer already knows
  about where the log lives and what produced it. Any field not supplied
  is recorded as `null` in `input/log-pointers.json`, never guessed or
  defaulted to a workspace convention this skill hasn't actually checked.
- `title_clarification`, `description_clarification`,
  `comments_clarification` (all optional) — an engineer's own correction
  or clarification of the corresponding PLM text, supplied only when the
  tester's account is unclear or technically imprecise. Each is
  independent: supplying one does not require supplying the others. A
  field not supplied at this invocation is **not** reset to `null` — see
  step 6's carry-forward rule.

## Steps

### 1. Resolve `issue_id`

If missing, HALT per above. Otherwise proceed.

### 2. Fetch the issue via PLM MCP

Call the PLM MCP capability's three operations for `issue_id` —
`fetch_title`, `fetch_description`, `fetch_comments` — per
`.claude/skills/_shared/plm-invocation.md`. That file is a workspace
dependency, not part of this repository (see root `CLAUDE.md`): it is
expected to already be configured in the environment this skill runs in,
and this skill does not attempt to configure or discover it.

Which failures HALT this step and which merely degrade it is
`plm-invocation.md`'s "When it is unavailable" — follow that exactly; the
one thing specific to this skill (not restated there) is *where* the
resulting ledger line goes: append it under `runs/run-NN/evidence/`,
which step 3 must have created first (see step 5's ordering note).

On success, hold each returned value verbatim — do not rephrase,
summarize, or correct it here. Rephrasing is analysis; this skill does
none (see `plm-invocation.md`'s "What this capability does not provide"
for why there is no separate "reproduction steps" value to request).

### 3. Determine the issue folder and next run number

1. Check whether `.rca/issues/<issue_id>/` exists.
2. If it does not exist, this is the first intake for this issue: create
   `.rca/issues/<issue_id>/`, `input/`, and `runs/`. The next run is
   `run-01`. There is no prior `plm-snapshot.json` to read in step 6 —
   every `engineer_clarification` field starts `null` unless supplied at
   this invocation.
3. If it does exist, this is a re-run: list `runs/` and take one past the
   highest existing run number (zero-padded to two digits). **Never
   overwrite an existing run's directory or `manifest.json`** — a new run
   is always created, per `run-bundle-layout.md`'s numbering rule. Read
   the existing `input/plm-snapshot.json` before overwriting it in step 6
   — its `engineer_clarification` is this step's carry-forward source.

### 4. Write the ledger lines

Create `runs/run-NN/evidence/` and append one line to `tools.jsonl` **per
PLM MCP operation actually called** in step 2 (up to three: `fetch_title`,
`fetch_description`, `fetch_comments`, including a failed one — see step
2's HALT/degrade rule), per
`.claude/skills/_shared/tool-ledger-format.md`. These are the run's sole
tool-call ledger entries from this skill.

### 5. Write `issue.json`

Create it (first intake) or refresh `plm.title`/`plm.url` in place
(re-run), per the schema in `run-bundle-layout.md`. `active_run` is left
`null` — this skill never sets it. Append the new run ID to `runs`.

### 6. Write `input/plm-snapshot.json`

Fully overwrite with this fetch's `fetched_at` timestamp and verbatim
`title`/`description`/`comments`, per the schema in `run-bundle-layout.md`.

Then set `engineer_clarification`, per field, **independently**:

- If this invocation supplied `title_clarification` /
  `description_clarification` / `comments_clarification`: write
  `{"text": <verbatim as supplied>, "tier": "ENGINEER_PROVIDED"}` for that
  field.
- If this invocation did not supply it: carry forward that field's value
  from the `input/plm-snapshot.json` read in step 3 (whatever it already
  was, `null` included). On a first intake (no prior file), it is `null`.

A field is never rephrased or merged with its prior value — a newly
supplied value fully replaces the old one for that field; an unsupplied
field is left exactly as it was.

### 7. Write `input/log-pointers.json`

Fully overwrite from whatever optional inputs were supplied
(`duckdb_path`, `tables`, `time_range`, `build`, `model`,
`source_checkout`), with any field not supplied written as `null`. The
schema (`run-bundle-layout.md`) has no per-field tier — every non-null
value here is implicitly `ENGINEER_PROVIDED`, since this skill verifies
none of it itself; that is a property of this file, not something this
step records per field. PLM's `fetch_comments` result is never used to
populate this file, even if a comment happens to mention a build or model
— see `plm-invocation.md`'s "What this capability does not provide."

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
- A short summary of what was fetched (title; that description and
  comments were snapshotted verbatim; the comment count, or that
  `fetch_comments` failed and comments are empty for this run).
- Which `engineer_clarification` fields are set (and whether newly
  supplied this invocation or carried forward from a prior run) and which
  are still `null`.
- Which `log-pointers.json` fields are still `null` and therefore still
  need to be supplied before log-dependent steps can run.
- That the next pipeline step is `rca-scope` — do not imply it will run
  automatically; that is a separate invocation (or `/rca`'s dispatch).

## What this skill does not do

- ❌ The only outside calls this skill makes are the three PLM MCP
  operations in step 2 — no log queries, spec queries, or code search of
  any kind.
- ❌ It never parses or extracts a "reproduction steps" section out of
  `description` — PLM descriptions follow no fixed template here, and
  slicing one out would require judgment this skill does not exercise
  (see `plm-invocation.md`).
- ❌ It never overwrites `title`/`description`/`comments` with an
  engineer's clarification — the verbatim PLM text and the clarification
  are always recorded side by side, never merged, so `rca-conclude`'s
  later comparison of the tester's own account against the log stays
  intact.
- ❌ Classifying the issue and narrowing the time window is `rca-scope`'s
  job — this skill does neither.
- ❌ Hypothesis generation, root cause, and reproduction scenarios belong
  to `rca-analyze`/`rca-conclude` downstream of intake — this skill
  produces none of them.
- ❌ This skill halts after step 9 regardless of autonomy settings —
  `manifest.json`'s `autonomy` field is a default for later skills to
  read, not something this skill acts on; the next skill is never
  chained automatically.
