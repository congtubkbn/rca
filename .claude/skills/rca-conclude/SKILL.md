---
name: rca-conclude
description: >
  Synthesize an existing RCA run's accepted analysis into conclusion artifacts
  (problem, root cause, causal chain, protocol reproduction scenario) and handle engineer `accept` or `abort`.
  Triggers: "conclude PLM-12345", "what is the root cause", "accept conclusion", "abort conclusion", "draft reproduction scenario".
  Preconditions: Target run exists with `manifest.json.next_step == "rca-conclude"` or unconfirmed `conclusion.json`.
  Anti-triggers: log/code analysis (use `rca-analyze`), creating case studies (use `rca-learn`), writing Technical Reports (use `tr-creator`).
---

# rca-conclude

Part of the PLM-issue pipeline: `rca-intake → rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`.
Synthesizes verified findings from `scope.json` and `analysis/round-NN.json` into problem statement, root cause, causal chain, and protocol-level reproduction scenario.

**Contracts & Reference Docs**:
- Run bundle schema & conclusion format: `.claude/skills/_shared/run-bundle-layout.md`
- Evidence tiers & contradiction rules: `.claude/skills/_shared/evidence-tiers.md`

```yaml
contract:
  requires: [issue_id, existing_run, accepted_analysis]
  optional: [run_id, verb]
  produces:
    - .rca/issues/<issue_id>/runs/run-NN/conclusion.json
    - .rca/issues/<issue_id>/runs/run-NN/CONCLUSION.md
    - .rca/issues/<issue_id>/issue.json (active_run on accept)
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, updated_at; next_step, status on accept/abort)
  self_seedable: false
```

## Inputs

- `issue_id` (required): PLM issue identifier (e.g. `PLM-12345`).
- `run_id` (optional): Defaults to `issue.json.active_run` if set, else highest-numbered entry in `issue.json.runs`.
- `verb` (optional): `"accept"` or `"abort"` from user invocation. Omitted when drafting or re-rendering.

## Steps

### 1. Resolve issue_id and target run

1. If `issue_id` is missing: HALT with `"Need a PLM issue ID to conclude. Which issue?"`.
2. If `.rca/issues/<issue_id>/` does not exist: HALT with `"No run bundle for <issue_id> — run rca-intake first."`.
3. Read `issue.json`. Resolve target run: explicit `run_id` → `active_run` → highest `runs` entry. If none resolves: HALT with `"<issue_id> has no runs yet — run rca-intake first."`.
4. Read target run's `manifest.json`. If missing: HALT with `"Run <run_id> has no manifest.json — bundle incomplete."`.
5. If `manifest.json.status == "aborted"`: HALT with `"Run <run_id> was aborted. Start a new run with rca-intake."`.

### 2. Check accepted-analysis precondition

Read `runs/run-NN/conclusion.json` if it exists:
- If `conclusion.json` does not exist AND `manifest.json.next_step != "rca-conclude"`: HALT with `"Run <run_id> analysis not accepted yet (next_step: <value>). Reply accept to rca-analyze first."`.
- If `conclusion.json` exists and `confirmed == true`: HALT with `"Run <run_id> already has a confirmed conclusion (at <confirmed_at>). Start a new run via rca-intake to re-analyze."`.
- Otherwise: proceed.

### 3. Resolve invocation against standing draft

- **No `conclusion.json` exists**: Proceed to Step 4 (Synthesize draft).
- **`conclusion.json` exists with `confirmed: false`**:
  - `verb == "accept"`: Jump to **Branch: Handling `accept`**.
  - `verb == "abort"`: Jump to **Branch: Handling `abort`**.
  - No `verb` (re-ask): Skip Steps 4–7 and jump directly to Step 8 to re-render existing draft report.

### 4. Synthesize conclusion draft

Read `input/plm-snapshot.json`, `runs/run-NN/scope.json`, and all `runs/run-NN/analysis/round-NN.json` in round order:
1. **`problem`**:
   - If any round has `failure_point.located == true`: use latest round's `failure_point` (`statement`, verbatim `tier`, verbatim `evidence_ref`).
   - Else if `scope.json.failure_time.tier` is non-null: `located: true`, `statement` references scoped failure time, copy `tier`/`evidence_ref` from `scope.json.failure_time`.
   - Else: `located: false`, `statement: "Failure point not pinned in this run"`, `tier: null`, `evidence_ref: null`.
2. **`causal_chain`**: Concatenate all rounds' `causal_chain_additions` in round order, preserving `round` number, `tier`, and `evidence_ref`. (`[]` if none).
3. **`root_cause`**:
   - If `causal_chain` non-empty: `established: true`, `statement` synthesizes terminal link and upstream causation, verbatim `tier` and `evidence_ref` copied from terminal link (never upgraded).
   - If `causal_chain` empty: `established: false`, `statement: "No causal-chain finding established"`, `tier: null`, `evidence_ref: null`.
4. **`reproduction_scenario`** (protocol level):
   - `preconditions[]`: Required network/device state backed by `causal_chain`/`scope.json` with verbatim tiers (interpolated items tagged `ASSUMED`, `evidence_ref: null`).
   - `steps[]`: Ordered numbered sequence leading to failure point with verbatim tiers (interpolated items tagged `ASSUMED`).
   - `expected_failure`: Restates `problem` statement, tier, and evidence_ref.
   - `tester_comparison`: `tester_reported_text` = verbatim `input/plm-snapshot.json.description` (never engineer clarification).
     - `matches[]`: Claims aligning with scenario.
     - `divergences[]`: Discrepancies or missing details. Tag `tier: "CONTRADICTED"` when HARD evidence (`VERIFIED_LOG`/`CODE_BOUND`) directly contradicts tester text.
5. **`evidence_gaps` & weak evidence notice**:
   - Collect all `SPEC_INFERRED`/`ASSUMED`/`TESTER_REPORTED`/`CODE_UNAVAILABLE`/`CONTRADICTED` items across conclusion fields.
   - If any item in `root_cause`, `causal_chain`, or `reproduction_scenario` carries `ASSUMED` or `CODE_UNAVAILABLE`: set `rests_on_weak_evidence: true` and write explicit `weak_evidence_notice`. Otherwise `rests_on_weak_evidence: false`, `weak_evidence_notice: null`.

### 5. Run forbidden-pattern scan

Scan all authored strings in the draft (case-insensitive substring match) for remediation and fix patterns:
`"fix:"`, `"the fix is"`, `"to fix this"`, `"suggested fix"`, `"proposed fix"`, `"patch:"`, `"proposed patch"`, `"workaround"`, `"configuration change"`, `"config change"`, `"config parameter should"`, `"test case"`, `"regression test"`, `"verification procedure"`, `"recommend"`, `"recommendation:"`, `"action item:"`, `"remediation:"`, `"next step:"`, `"should be changed"`, `"should be modified"`, `"should be updated to"`.

- **Exemption**: Verbatim `tester_reported_text` is exempt from scan.
- **On match**: Do not write files. HALT with `"Conclusion draft blocked — contains forbidden remediation pattern (<pattern> in <field>). RCA terminates at root cause without proposing fixes."`.

### 6. Write conclusion.json

Write `runs/run-NN/conclusion.json` per schema in `run-bundle-layout.md`:
- `drafted_at: <ISO 8601 now>`, `confirmed: false`, `confirmed_at: null`.
- Fields from Step 4 (`problem`, `root_cause`, `causal_chain`, `reproduction_scenario`, `evidence_gaps`, `rests_on_weak_evidence`, `weak_evidence_notice`).

### 7. Write CONCLUSION.md

Write `runs/run-NN/CONCLUSION.md` with the following structure:
```markdown
# RCA Conclusion — <issue_id> / <run_id>

Status: DRAFT — awaiting engineer confirmation

[If rests_on_weak_evidence: "⚠ This conclusion rests on unverified (ASSUMED) or code-unavailable findings: <weak_evidence_notice>"]

## Problem
<problem.statement>  [<problem.tier>, <problem.evidence_ref>]

## Root Cause
<root_cause.statement>  [<root_cause.tier>, <root_cause.evidence_ref>]

## Causal Chain
1. (round <N>) <statement>  [<tier>, <evidence_ref>]
...

## Reproduction Scenario
### Preconditions
- <statement>  [<tier>, <evidence_ref>]
### Steps
1. <statement>  [<tier>, <evidence_ref>]
### Expected Failure
<expected_failure.statement>  [<tier>, <evidence_ref>]
### Compared to the Tester's Reported Steps
Tester reported: "<tester_reported_text>"
Matches: <matches[]>
Divergences:
- <tester_claim> vs. <scenario_says>  [<tier>, <evidence_ref>]

## Evidence Gaps
- <evidence_gaps[]>

---
This conclusion ends here. It does not propose fixes, patches, configuration changes, or test cases. Downstream engineering owns remediation.
```

### 8. Update manifest.json and present draft report

1. Update `runs/run-NN/manifest.json`: `current_step: "rca-conclude"`, `updated_at: <ISO 8601 now>`. Keep `next_step: "rca-conclude"`, `status: "in_progress"`. (Skip update on re-ask).
2. Present full `CONCLUSION.md` report to engineer. If `rests_on_weak_evidence == true`, display the weak evidence warning at the very top.
3. Prompt engineer: Reply `accept` to confirm conclusion (sets `active_run` and advances to `rca-learn`) or `abort` to terminate run. HALT.

---

### Branch: Handling `accept`

Reached when `verb == "accept"` on an existing unconfirmed draft:
1. Re-run Step 5 forbidden-pattern scan on `conclusion.json`.
2. Update `conclusion.json` in place: `confirmed: true`, `confirmed_at: <ISO 8601 now>`.
3. Update `CONCLUSION.md` in place: change status line to `Status: CONFIRMED at <confirmed_at>`.
4. Update `issue.json`: set `active_run: "<run_id>"`.
5. Update `manifest.json`: `current_step: "rca-conclude"`, `next_step: "rca-learn"`, `updated_at: <ISO 8601 now>`. Keep `status: "in_progress"`.
6. Report confirmation: conclusion confirmed, `active_run` set, next step is `rca-learn`. (State that TR generation remains separate via `tr-creator`). HALT.

### Branch: Handling `abort`

Reached when `verb == "abort"` on an existing unconfirmed draft:
1. Leave `conclusion.json` untouched (`confirmed: false`).
2. Update `manifest.json`: `status: "aborted"`, `next_step: null`, `current_step: "rca-conclude"`, `updated_at: <ISO 8601 now>`.
3. Do **not** set `issue.json.active_run`.
4. Report abort: run is closed without confirmed conclusion. Start new run via `rca-intake` to re-analyze. HALT.

## Completion Criteria

- `runs/run-NN/conclusion.json` and `runs/run-NN/CONCLUSION.md` written per schema and format specifications.
- All authored strings pass forbidden-pattern scan with zero remediation, fix, patch, or config change violations.
- Evidence tiers faithfully copied forward without upward promotion.
- `rests_on_weak_evidence` and `weak_evidence_notice` prominently highlighted if weak findings exist.
- Discrepancies between scenario and log-verified facts vs tester report tagged with `CONTRADICTED` where applicable.
- On `accept`: `confirmed: true`, `issue.json.active_run` set, `manifest.json.next_step == "rca-learn"`.
- On `abort`: `manifest.json.status == "aborted"`, `next_step == null`, `issue.json.active_run` unassigned.
- Clear draft or confirmation summary presented to engineer followed by mandatory HALT.

## What this skill does not do

- ❌ Never writes or proposes code fixes, patches, workarounds, or test cases.
- ❌ Never auto-confirms a conclusion or auto-triggers `rca-learn` without explicit user `accept`.
- ❌ Never performs log, code, or spec queries (synthesis only from `scope.json` and `round-NN.json`).
- ❌ Never promotes or upgrades evidence tiers when consolidating findings.
- ❌ Never overwrites raw tester description in PLM snapshot with engineer clarifications.
