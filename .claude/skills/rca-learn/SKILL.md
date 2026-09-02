---
name: rca-learn
description: >
  Record an accepted PLM-issue RCA conclusion into `.rca/knowledge/cases/` or promote reviewed patterns into `.rca/knowledge/playbooks/`.
  Triggers: "learn from PLM-12345", "record this case", "promote playbook from <case_id>", "confirm playbook <id>", "discard playbook <id>".
  Preconditions: `issue.json.active_run` set with confirmed conclusion (case write) or existing cases (playbook promotion).
  Anti-triggers: log/code analysis (use `rca-analyze`), synthesizing conclusions (use `rca-conclude`), creating technical reports (use `tr-creator`).
---

# rca-learn

Part of the PLM-issue pipeline: `rca-intake → rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`.
This is the pipeline's fifth and final step, reached only after an engineer has replied `accept` to `rca-conclude`'s standing draft. Its job is capture, not investigation: it runs no new log, code, or NotebookLM queries, but records verified findings into a durable, reusable case record.

**Contracts & Reference Docs**:
- Run bundle schema & knowledge case/playbook formats: `.claude/skills/_shared/run-bundle-layout.md`
- Playbook promotion workflow & customer-data check: `references/playbook-promotion.md`
- Evidence tiers & tier immutability: `.claude/skills/_shared/evidence-tiers.md`
- Keyword provenance & hint rules: `.claude/skills/_shared/keyword-provenance.md`

```yaml
contract:
  requires: [issue_id, active_run, confirmed_conclusion]
  optional: [run_id, promote]
  produces:
    - .rca/knowledge/cases/<case_id>.json
    - .rca/knowledge/.drafts/<playbook_id>.md (only via "Handling promote")
    - .rca/knowledge/playbooks/<playbook_id>.md (only via "Handling confirm playbook")
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, next_step, updated_at only)
  self_seedable: false
```

## What this delivers

Two distinct deliverables, reached by different invocations:

1. **A case record** (default pipeline step): `.rca/knowledge/cases/<case_id>.json` per accepted conclusion, capturing verified findings without re-derivation or tier upgrade.
2. **A promoted playbook** (separate engineer-initiated action): Reviewed Markdown prose drafted from one or more existing cases into `.rca/knowledge/playbooks/<playbook_id>.md` (the sole part of `.rca/` tracked in git) after passing the customer-data check.

Per `_shared/keyword-provenance.md`, **cases and playbooks are hints, never evidence** for future runs. Per `_shared/evidence-tiers.md`, recorded evidence tiers remain strictly immutable.

## Inputs

- `issue_id` (required for case-write; not needed for playbook operations): PLM issue identifier.
- `run_id` (optional, case-write only): Must equal `issue.json.active_run` if supplied. Only the active accepted run may be recorded.
- `promote` (optional): Playbook drafting request (e.g. `promote qc9205_ims_timeout from PLM-12345-run-01, PLM-19090-run-02` or `promote generic_sms_cp_error for issue_type sms_failure`).
- Standing draft actions: `confirm playbook <playbook_id>` or `discard playbook <playbook_id>`.

---

## Playbook Promotion Routing

If invocation text contains `promote`, `confirm playbook`, or `discard playbook`:
**Read and follow [`references/playbook-promotion.md`](references/playbook-promotion.md) directly.**
These actions operate across existing `.rca/knowledge/cases/` and do not require `issue_id` or `active_run`.

---

## Steps (Default: Write a Case Record)

### 1. Resolve `issue_id` and the active run

1. If `issue_id` is missing: HALT: `"Need a PLM issue ID to learn from. Which issue?"`. Do not guess from conversation context.
2. If `.rca/issues/<issue_id>/` does not exist: HALT: `"No run bundle for <issue_id> — run rca-intake first."`.
3. Read `issue.json`. If `active_run` is `null`: HALT: `"No accepted conclusion for <issue_id> yet — active_run is not set. rca-learn only writes a case for a run with an accepted conclusion; run rca-conclude and reply accept first."`.
4. If `run_id` was supplied and does not equal `active_run`: HALT: `"Only the active run (<active_run>) may be written into the case base — run <run_id> is not the accepted conclusion for <issue_id>."`.
5. Set `run_id = active_run` for subsequent steps.

### 2. Check confirmed-conclusion precondition

Read `runs/<run_id>/manifest.json` and `runs/<run_id>/conclusion.json`:
- If `manifest.json` is missing: HALT: `"Run <run_id> has no manifest.json — bundle is incomplete."`.
- If `manifest.json.status == "aborted"`: HALT: `"Run <run_id> is marked aborted — aborted runs cannot be recorded into the case base."`.
- If `conclusion.json` does not exist or `confirmed != true`: HALT: `"Run <run_id> has no confirmed conclusion — conclusion.json is missing or unconfirmed."`.

### 3. Check for existing case record

Compute `case_id = "<issue_id>-<run_id>"`.
If `.rca/knowledge/cases/<case_id>.json` already exists:
- The run has already been learned from. Case records are immutable once written.
- Report its existing contents in full to the engineer and HALT. Do not proceed to Step 4.

### 4. Assemble the case record

Slice-read required files only: `input/plm-snapshot.json`, `input/log-pointers.json`, `runs/<run_id>/scope.json`, `runs/<run_id>/conclusion.json`, all `runs/<run_id>/analysis/round-NN.json` in round order, and referenced lines in `runs/<run_id>/evidence/tools.jsonl`.

1. **`issue_type` & `symptom`**: `issue_type` from `scope.json.classification.issue_type`; `symptom` copied verbatim from `input/plm-snapshot.json.title`.
2. **`failure_point`, `root_cause`, `causal_chain`**: Copied verbatim (with evidence tiers and refs intact) from `conclusion.json.problem`, `conclusion.json.root_cause`, and `conclusion.json.causal_chain`. Tiers never upgrade.
3. **`useful_queries` & `meaningful_keywords`**:
   - Collect every `hypotheses[].queries[]` entry with `outcome: "hit"` across all rounds whose finding directly supported `failure_point`, `causal_chain_additions`, or the accepted recommendation. (Hits supporting eliminated hypotheses are excluded).
   - Match `ledger_ref` in `evidence/tools.jsonl` to record `tool`, `table`, `ledger_ref`, and a one-line `why_useful`.
   - `meaningful_keywords` is the deduplicated union of keywords from those ledger lines (`params`/`keywords_in`).
4. **`contradicted_docs`**:
   - Extract every entry from `analysis/round-NN.json.contradicted_findings[]` across all rounds.
   - Populate `chip_series` verbatim from `input/log-pointers.json.build` / `.model` (or `"unknown"` if neither is set; never guessed).
   - Copy `document`, `section`, `claim`, `log_showed`, and `evidence_ref` verbatim from the round record.
5. **Pure capture discipline**: Author no new analytical claims or fix suggestions.

### 5. Write `knowledge/cases/<case_id>.json`

Create `.rca/knowledge/cases/` if it does not exist. Write `.rca/knowledge/cases/<case_id>.json` matching the schema in `_shared/run-bundle-layout.md` with `written_at = <ISO 8601 now>`. Once written, this file is immutable.

### 6. Update `manifest.json` and report

1. Update `runs/<run_id>/manifest.json` in place:
   - `current_step: "rca-learn"`
   - `next_step: "complete"`
   - `updated_at: <ISO 8601 now>`
   - Leave `status: "in_progress"` untouched.
2. Report summary to engineer:
   - Case path and `case_id`.
   - Summary of captured findings (issue type, failure point, root cause, count of useful queries/keywords, count of contradicted docs).
   - State that the pipeline for this issue run has completed.
   - Note that `promote` is available separately if this case forms part of a recurring pattern.
3. HALT.

## Completion Criteria

- Target run validated with confirmed `conclusion.json` and `active_run` match.
- `.rca/knowledge/cases/<case_id>.json` written adhering strictly to schema without modifying existing case files.
- Evidence tiers and references copied verbatim without tier inflation.
- `manifest.json.next_step` updated to `"complete"`.
- Playbook promotion requests cleanly delegated to `references/playbook-promotion.md`.
- Case write summary presented to engineer followed by mandatory HALT.

## Invariants and Behavioral Guardrails

- **Pure Capture Boundary**: Runs no new log, code, or NotebookLM queries. Writes durable records solely from upstream verified artifacts.
- **Strict Tier Immutability**: All evidence tiers are copied verbatim. Upstream `ASSUMED` or `SPEC_INFERRED` tiers never upgrade.
- **Case Record Immutability**: `.rca/knowledge/cases/<case_id>.json` is written once and never overwritten. Subsequent analyses on the same issue produce new numbered runs and case files.
- **Hints, Never Evidence**: Cases and playbooks serve exclusively as search hints for future runs, never as evidence.
- **Isolated Git Tracking**: Only reviewed playbooks in `.rca/knowledge/playbooks/` are tracked by git. Staging drafts and case records remain git-ignored.
