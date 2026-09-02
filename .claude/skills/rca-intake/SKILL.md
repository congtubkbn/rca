---
name: rca-intake
description: >
  Initialize or add a run to a PLM-issue RCA bundle by fetching verbatim PLM snapshot data via PLM MCP and recording optional engineer clarifications and log pointers.
  Triggers: "start analysis on PLM-12345", "open run for PLM-12345", "intake PLM-12345", "clarify PLM text".
  Preconditions: None (sole pipeline entry point; creates `.rca/issues/<issue_id>/`).
  Anti-triggers: scoping analysis window or issue type (use `rca-scope`), hypothesis testing (use `rca-analyze`), synthesizing conclusions (use `rca-conclude`).
---

# rca-intake

Part of the PLM-issue pipeline: `rca-intake → rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`.
Sole entry point for creating or updating a run bundle under `.rca/issues/<issue_id>/`.

**Contracts & Reference Docs**:
- Run bundle schema & write ownership: `.claude/skills/_shared/run-bundle-layout.md`
- PLM MCP operations & availability: `.claude/skills/_shared/plm-invocation.md`
- Tool call ledger format: `.claude/skills/_shared/tool-ledger-format.md`
- Evidence tiers & clarification: `.claude/skills/_shared/evidence-tiers.md`

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

## Inputs

- `issue_id` (required): PLM issue identifier (e.g. `PLM-12345`).
- `label` (optional): Intent of this run (e.g. `"first pass"`, `"re-run with corrected build"`). Defaults to `"run <N>"`.
- `duckdb_path`, `tables`, `time_range`, `build`, `model`, `source_checkout` (optional): Known log and build pointers. Unsupplied fields record as `null`.
- `title_clarification`, `description_clarification`, `comments_clarification` (optional): Engineer corrections/clarifications of PLM text. Unsupplied fields carry forward from prior runs (or default to `null` on first intake).

## Steps

### 1. Resolve issue_id

1. If `issue_id` is missing: HALT with `"Need a PLM issue ID to start intake. Which issue?"`.
2. Do not infer `issue_id` from unconfirmed conversation context.

### 2. Fetch issue via PLM MCP

Call PLM MCP capability for `issue_id` per `plm-invocation.md`:
1. Call `fetch_title` and `fetch_description`. If either fails or issue is not found: record error ledger line and HALT.
2. Call `fetch_comments`. If it fails: record error ledger line, continue in degraded mode with `comments: []`, and note the gap for the final report.
3. Hold returned strings verbatim in memory. Do not rephrase, summarize, or extract sub-sections.

### 3. Determine directory layout and run number

1. Check if `.rca/issues/<issue_id>/` exists:
   - **First intake (does not exist)**: Create `.rca/issues/<issue_id>/`, `input/`, `runs/run-01/evidence/`, `runs/run-01/raw/`, and `runs/run-01/analysis/`. Target run is `run-01`. Prior clarifications default to `null`.
   - **Re-run (exists)**: Read existing `input/plm-snapshot.json` to hold prior `engineer_clarification` for Step 6. List `runs/`, determine highest `run-NN`, and set next run to zero-padded `run-(NN+1)`. Create `runs/run-(NN+1)/evidence/`, `raw/`, `analysis/`. Never overwrite existing run folders or manifests.

### 4. Write ledger lines

Append one entry per PLM operation called (`fetch_title`, `fetch_description`, `fetch_comments`, including failed calls) to `runs/run-NN/evidence/tools.jsonl` per `tool-ledger-format.md`.

### 5. Write issue.json

- **First intake**: Create `.rca/issues/<issue_id>/issue.json` with `created_at`, `plm: {title, url}`, `active_run: null`, `runs: ["run-01"]`.
- **Re-run**: Update `plm.title` and `plm.url` with latest fetch, append new `run-NN` to `runs[]`, keep `active_run` untouched.

### 6. Write input/plm-snapshot.json

Fully overwrite `input/plm-snapshot.json` per `run-bundle-layout.md`:
- Set `fetched_at` to current ISO 8601 timestamp.
- Write verbatim `title`, `description`, and `comments[]`.
- Resolve `engineer_clarification` independently per field (`title`, `description`, `comments`):
  - If supplied this invocation: write `{"text": "<verbatim>", "tier": "ENGINEER_PROVIDED"}`.
  - If omitted: carry forward value from Step 3's read of prior `plm-snapshot.json` (or `null` if first intake).

### 7. Write input/log-pointers.json

Fully overwrite `input/log-pointers.json` with supplied log parameters (`duckdb_path`, `tables`, `time_range`, `build`, `model`, `source_checkout`). Set unsupplied fields to `null`.

### 8. Write runs/run-NN/manifest.json

Create `runs/run-NN/manifest.json` per `run-bundle-layout.md`:
- `status: "in_progress"`, `current_step: "rca-intake"`, `next_step: "rca-scope"`.
- `input_snapshot_fetched_at: <fetched_at from Step 6>`.
- `autonomy: "review_all"`, `round_budget: 5`, `current_round: 0`, `standing_recommendation: null`.
- `label: <supplied label or "run <N>">`.

### 9. Report summary to engineer

Present status to the engineer:
- Issue folder path and created/opened `run-NN`.
- Summary of fetched PLM data (title, description status, comment count, or comment degradation notice).
- Clarification status (which fields are active with `ENGINEER_PROVIDED` vs `null`).
- Log pointers status (which parameters are set vs `null` and needed before scoping/analysis).
- Next pipeline step: `rca-scope`.

## Completion Criteria

- `.rca/issues/<issue_id>/` exists with valid `issue.json`, `input/plm-snapshot.json`, and `input/log-pointers.json`.
- Target `runs/run-NN/` directory created with zero-padded run index without mutating previous runs.
- `runs/run-NN/manifest.json` written with `status: "in_progress"`, `current_step: "rca-intake"`, `next_step: "rca-scope"`.
- `runs/run-NN/evidence/tools.jsonl` contains ledger entries for all executed PLM MCP operations.
- Verbatim PLM snapshot and independent `engineer_clarification` fields properly stored side by side.
- Summary report presented to engineer specifying created run, PLM fetch state, and missing log pointers.

## Invariants and Behavioral Guardrails

- **Verbatim Capture Discipline** — enforced in Step 2, 6; analysis/classification stays downstream.
- **Pure Intake Boundary**: Intake interacts strictly with the PLM MCP to capture issue text and record log pointers. Log queries, spec repositories, and code graphs belong exclusively to downstream skills.
- **ADR-0001 Side-by-Side Separation** — enforced in Step 6; never merge PLM text with clarifications, so unedited tester accounts survive for downstream contradiction checks.
- **Append-Only Run Bundles** — enforced in Step 3.
- **Discrete Step Execution**: Halt unconditionally after presenting the intake summary report. Never auto-advance or trigger `rca-scope` automatically.
