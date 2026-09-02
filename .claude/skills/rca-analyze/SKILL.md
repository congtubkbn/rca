---
name: rca-analyze
description: >
  Analyze a scoped RCA run through hypothesis-driven rounds across protocol layers, locate failure points, evaluate checkpoints, and process engineer guidance (dig, redirect, accept, abort).
  Triggers: "analyze PLM-12345", "dig <direction>", "redirect <info>", "accept", "abort run", "continue analysis".
  Preconditions: Target run exists with `scope.json` (`rca-scope` completed).
  Anti-triggers: scoping analysis window or issue type (use `rca-scope`), synthesizing conclusions (use `rca-conclude`), recording case studies (use `rca-learn`).
---

# rca-analyze

Part of the PLM-issue pipeline: `rca-intake → rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`.
Executes iterative, hypothesis-driven analysis rounds ending at checkpoints, evaluates autonomy loop gates, and records engineer decision pairs.

**Contracts & Reference Docs**:
- Run bundle schema & round format: `.claude/skills/_shared/run-bundle-layout.md`
- Resolution ladder (rungs 1–6): `.claude/skills/_shared/resolution-ladder.md`
- Keyword provenance & hint rules: `.claude/skills/_shared/keyword-provenance.md`
- Checkpoint presentation format: `.claude/skills/_shared/checkpoint-format.md`
- Tool invocations: `.claude/skills/_shared/log-query-invocation.md`, `.claude/skills/_shared/code-graph-invocation.md`, `.claude/skills/_shared/notebooklm-invocation.md`
- Evidence tiers: `.claude/skills/_shared/evidence-tiers.md`

```yaml
contract:
  requires: [issue_id, existing_run, scope]
  optional: [run_id, verb, direction, redirect_info, override, case_base]
  produces:
    - .rca/issues/<issue_id>/runs/run-NN/analysis/round-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/evidence/tools.jsonl (appended)
    - .rca/issues/<issue_id>/runs/run-NN/raw/rca-analyze-q-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, updated_at, current_round, standing_recommendation, decisions; next_step, status on accept/abort)
  self_seedable: false
```

## Inputs

- `issue_id` (required): PLM issue identifier (e.g. `PLM-12345`).
- `run_id` (optional): Target run ID. Defaults to `issue.json.active_run` if set, else highest entry in `issue.json.runs`.
- `verb` (optional): Engineer reply to standing checkpoint (`dig`, `redirect`, `accept`, `abort`). Absent on fresh start or bare re-ask.
- `direction` (optional): Hypothesis ID or statement to pursue (with `dig` or direct bare invocation).
- `redirect_info` (optional): Verbatim premise/information text supplied by engineer (with `redirect`).
- `override` (optional): Boolean and rationale string when overriding the round budget gate.

## Steps

### 1. Resolve issue_id and target run

1. If `issue_id` is missing: HALT with `"Need a PLM issue ID to analyze. Which issue?"`.
2. If `.rca/issues/<issue_id>/` does not exist: HALT with `"No run bundle for <issue_id> — run rca-intake first."`.
3. Read `issue.json`. Resolve target run: explicit `run_id` → `active_run` → highest `runs` entry. If none: HALT with `"<issue_id> has no runs yet — run rca-intake first."`.
4. Read target run's `manifest.json`. If missing: HALT with `"Run <run_id> has no manifest.json — bundle incomplete."`.
5. If `manifest.json.status == "aborted"`: HALT with `"Run <run_id> was aborted. Start a new run with rca-intake."`.

### 2. Check scope precondition

Read `runs/run-NN/scope.json`. If missing: HALT with `"Run <run_id> has no scope.json — run rca-scope first."`.

### 3. Resolve invocation verb against standing checkpoint

- **`manifest.json.current_round == 0`** (fresh run):
  - Set `direction = null`, `engineer_redirect = null`. Proceed directly to Step 4 (record any supplied verb as an `open_notes` comment).
- **`manifest.json.current_round > 0`**:
  - Read standing round `runs/run-NN/analysis/round-<current_round>.json`.
  - **`verb == "accept"`**: Jump to **Branch: Handling `accept`**.
  - **`verb == "abort"`**: Jump to **Branch: Handling `abort`**.
  - **`verb == "dig"`**:
    - If `direction` is missing: HALT with `"dig needs a direction — which candidate? [list checkpoint.candidate_directions]"`.
    - If standing round has `forced_by_round_budget == true` and `override` is absent/lacks rationale: HALT restating the round budget gate.
    - Set `direction = supplied_direction`, `engineer_redirect = null`.
  - **`verb == "redirect"`**:
    - If `redirect_info` is missing: HALT with `"redirect needs information — what should the agent know?"`.
    - Set `engineer_redirect = {"text": redirect_info, "tier": "ENGINEER_PROVIDED", "recorded_at": <ISO 8601 now>}`.
    - Set `direction = standing_round.checkpoint.recommendation.direction`.
  - **Bare `direction`** (no verb): Treat as `dig` (round budget gate applies).
  - **Implicit continue** (no verb, no direction): Set `direction = standing_round.checkpoint.recommendation.direction`, `engineer_redirect = null`, note in `open_notes`.
  - **Record Decision**: Append entry to `manifest.json.decisions[]` (skip if entry for this round already exists):
    `round: current_round`, `agent_recommendation: standing_round.checkpoint.recommendation`, `engineer_response: {"verb": <verb>, "input": <direction | redirect_info | null>, "recorded_at": <now>}`, `override: <boolean>`, `override_rationale: <string | null>`.

### 4. Determine round number and read prior rounds

1. `round_number = manifest.json.current_round + 1`.
2. If `round_number > manifest.json.round_budget` without a valid override: HALT with `"Round budget (<round_budget>) reached for run <run_id> — reply accept, abort, or dig override <direction> with rationale."`.
3. If `round_number > 1`: Read all `analysis/round-<01..N-1>.json` in order to aggregate cumulative findings into the causal chain.

### 5. Locate failure point

Skip if any prior round already has `failure_point.located == true` (reuse prior round's `failure_point` unchanged).
Otherwise, resolve using the resolution ladder:

1. **Scope Log Event**: If `scope.json.failure_time.origin == "log"` (`tier == "VERIFIED_LOG"`): Set `located: true`, event details from `scope.json.failure_time.evidence_ref`, `tier: "VERIFIED_LOG"`, copy `evidence_ref`. Stop search.
2. **Rung 1+2 (Spec & Log)**: Query NotebookLM (spec corpus) for failure indicators of `scope.json.classification.issue_type`. Take keywords (plus `failure_indicator_keywords` from `rca-scope/references/known-issue-types.md` if `matched_playbook` non-null) and issue one locate query across `tables_in_scope` within `scope.json.window`.
   - Hit: `located: true`, `tier: "VERIFIED_LOG"`, record ledger/raw ref. Stop search.
   - Miss: Note miss in `open_notes` and proceed to Rung 4.
3. **Rung 4 (Vendor Docs)**: Query vendor-doc NotebookLM corpus for chip-series failure indicators. If keywords suggest a target, issue one locate query across `tables_in_scope`.
   - Hit: `located: true`, `tier: "VERIFIED_LOG"`, record ledger/raw ref of the fresh log hit. Stop search.
   - Miss / no mapping: Note in `open_notes` and proceed to Rung 6.
4. **Rung 6 (Cases & Playbooks)**: Read `.rca/knowledge/cases/*.json` and `.rca/knowledge/playbooks/*.md` matching `issue_type`. Record all read entries in `case_hints[]` with `used_for: "failure_point"`. If a match suggests a keyword/table, run one locate query.
   - Hit: `located: true`, `tier: "VERIFIED_LOG"`, record ledger/raw ref of the fresh log hit (never the case tier). Stop search.
   - Miss / no match: Proceed to Concession.
5. **Concession**: If all rungs miss, set `failure_point.located: false`, `event: null`, `tier: null`. Add `open_notes` entry stating all rungs failed to pin failure point (trips Gate 3 in Step 7).

### 6. Generate and test hypotheses

1. **Generate Hypotheses** (produce 2–4 competing hypotheses):
   - *Layer Coverage*: If `scope.json.layers` has > 1 layer, hypotheses must address each layer or document a reasoned exclusion in `open_notes`.
   - *Sources*:
     - `engineer_redirect` (read first; at least one hypothesis incorporates it).
     - `direction` (at least one hypothesis narrows on it).
     - Rungs 1/4 (NotebookLM cited answers).
     - Guess (FORBIDDEN origin, allowed for query framing only per `keyword-provenance.md`).
     - Rung 6 (Cases/playbooks matching `issue_type` → record all read in `case_hints[]`).
   - For each hypothesis, define `statement`, `predicted_evidence`, and `testing_query`. If no viable query can be formulated, set `untested_tier: "ASSUMED"`, `queries: []`.
2. **Test Hypotheses** (execute each `testing_query` and append to `queries[]`):
   - `log-query`: Hit → `{ledger_ref, outcome: "hit", tier: "VERIFIED_LOG"}` (status `surviving`). Miss → `{ledger_ref, outcome: "miss", tier: null}` (status `surviving`).
   - `code-search`: `resolved: true` → `tier: "CODE_BOUND"`. `is_lib: true` → record `CODE_UNAVAILABLE` in `open_notes`, `queries[]` entry with `tier: null` (status `surviving`).
   - `notebooklm`: Answer → `tier: "SPEC_INFERRED"` with citation (status `surviving`).
3. **Eliminate Hypotheses**:
   - Set status to `eliminated` only when a HARD finding (`VERIFIED_LOG` or `CODE_BOUND`) positively contradicts the premise. Record ledger ref in `eliminated_by`. (Keyword misses never eliminate).
4. **Extend Causal Chain**:
   - Append independent, confirmed findings to `causal_chain_additions` with `statement`, `tier`, `evidence_ref`.
5. **Record Documentation Contradictions**:
   - If a HARD check contradicts a NotebookLM spec/vendor citation, append entry to `contradicted_findings[]` (`document`, `section`, `claim`, `log_showed`, `tier: "CONTRADICTED"`, `evidence_ref`) and note in `open_notes`.

### 7. Case hint scan, write round-NN.json, build checkpoint, and evaluate gates

1. **Case Hint Scan**: Scan all `evidence_ref` / `ledger_ref` fields in this round (`failure_point`, `queries[]`, `eliminated_by`, `causal_chain_additions`). If any points to `.rca/knowledge/`: drop that ref and treat claim as unresolved (cases are hints, never evidence).
2. **Write `analysis/round-NN.json`**: Write zero-padded `round-NN.json` per schema in `run-bundle-layout.md`. Never overwrite existing round files.
3. **Compute Budget Status**: `forced_by_round_budget = (round_number >= manifest.json.round_budget)`.
4. **Build Checkpoint**:
   - *Causal Chain*: Cumulative links across all rounds so far with tiers and refs.
   - *Candidate Directions*: Surviving hypotheses ranked with predicted evidence and query summary.
   - *Recommendation*: Top-ranked surviving direction (or forced acceptance notice if budget reached, or unblocking information if nothing survived).
   - *Evidence Gaps*: All non-HARD findings (`SPEC_INFERRED`, `ASSUMED`, `TESTER_REPORTED`, `ENGINEER_PROVIDED`, `CODE_UNAVAILABLE`, `CONTRADICTED`, unlocated failure point, case hints used).
5. **Evaluate 4 Never-Bypassable Gates** (in order):
   1. **Round budget**: `forced_by_round_budget == true`. Always halts (overridable only via explicit `dig override <direction>` + rationale).
   2. **ASSUMED finding**: Recommended direction carries `untested_tier: "ASSUMED"`. Always halts (no override).
   3. **Ladder reached "ask the engineer"**: `failure_point.located == false` or recommendation depends on unresolved rung 1–4 question. Always halts (no override).
   4. **Final acceptance**: `forced_by_round_budget == true` OR all hypotheses eliminated with nothing left to test. Always halts (no override).
6. **Update `manifest.json`**: Update `current_step: "rca-analyze"`, `current_round: <round_number>`, `standing_recommendation: <checkpoint.recommendation>`, `updated_at: <now>`. Keep `next_step` and `status` untouched.

### 8. Decide: halt, or continue automatically

1. If any gate from Step 7.5 tripped, OR `manifest.json.autonomy == "review_all"`: Halt and proceed to **Report to engineer and HALT**.
2. Otherwise (`autonomy` is `"auto"` or `"auto_until_blocked"`, and no gate tripped):
   - Append `manifest.json.decisions[]`: `round: round_number`, `agent_recommendation: checkpoint.recommendation`, `engineer_response: {"verb": "auto_continue", "input": checkpoint.recommendation.direction, "recorded_at": <now>}`, `override: false`, `override_rationale: null`.
   - Set `direction = checkpoint.recommendation.direction`, `engineer_redirect = null`.
   - Loop back to Step 4 to execute next round within the same invocation.

---

### Branch: Handling `accept`

Reached when `verb == "accept"`:
1. Append `manifest.json.decisions[]`: `round: current_round`, `agent_recommendation: standing_recommendation`, `engineer_response: {"verb": "accept", "input": null, "recorded_at": <now>}`, `override: (standing_recommendation.direction != null)`, `override_rationale: <supplied rationale | null>`.
2. Update `manifest.json`: `current_step: "rca-analyze"`, `next_step: "rca-conclude"`, `updated_at: <now>`. Keep `status: "in_progress"`.
3. Report decision recorded and handoff to `rca-conclude`. HALT.

### Branch: Handling `abort`

Reached when `verb == "abort"`:
1. Append `manifest.json.decisions[]`: `round: current_round`, `agent_recommendation: standing_recommendation`, `engineer_response: {"verb": "abort", "input": <supplied reason | "no reason given">, "recorded_at": <now>}`, `override: false`, `override_rationale: null`.
2. Update `manifest.json`: `status: "aborted"`, `next_step: null`, `current_step: "rca-analyze"`, `updated_at: <now>`.
3. Report run aborted without conclusion. HALT.

### Report to engineer and HALT

Render `checkpoint` in 5-section form per `checkpoint-format.md` (Causal Chain, Candidate Directions, Recommendation, Evidence Gaps, How to Respond). If multi-round auto-continue ran, summarize prior rounds briefly before displaying the final checkpoint.

## Completion Criteria

- `analysis/round-NN.json` written per schema with append-only integrity (never mutating prior rounds).
- Multi-layer exhaustiveness verified: every layer in `scope.json.layers` is covered by a hypothesis or has an explicit exclusion recorded in `open_notes`.
- All tool queries recorded in `raw/` and appended to `evidence/tools.jsonl`.
- Resolution ladder rigorously executed without skipping rungs or treating hints as evidence.
- Case hint scan verified zero `.rca/knowledge/` pointers in evidence fields.
- 4 never-bypassable gates strictly evaluated before auto-continuing.
- `manifest.json` updated with `current_round`, `standing_recommendation`, and complete `decisions[]` audit trail.
- On `accept`: `manifest.json.next_step == "rca-conclude"`. On `abort`: `manifest.json.status == "aborted"`.
- Full checkpoint rendered and execution halted whenever a gate trips or review is required.

## Invariants and Behavioral Guardrails

- **Hypothesis-Driven Investigation**: Formulate falsifiable hypotheses addressing each layer in `scope.json.layers` and test them using targeted log queries, code-graph traces, and cited NotebookLM specs. Boundary definition belongs strictly to `rca-scope`.
- **Provenance and Citation Rigor**: Ground all keywords in prior tool hits or verbatim engineer inputs, and cite specific spec sections for NotebookLM findings. Guesses may frame queries but never supply factual answers.
- **Hints, Never Evidence**: Treat cases and playbooks strictly as search hints to suggest query keywords or tables. Never record `.rca/knowledge/` paths in `evidence_ref` or `ledger_ref`.
- **Positive Elimination Only**: Eliminate hypotheses exclusively via positive HARD findings (`VERIFIED_LOG` or `CODE_BOUND`) that directly contradict predicted evidence. Query misses leave hypotheses surviving.
- **Append-Only Round Audit**: Record each round in a distinct, immutable `round-NN.json` and maintain a complete audit trail in `manifest.json.decisions[]`.
- **Strict Gate Enforcement**: Halt unconditionally whenever any of the 4 never-bypassable gates trip, or when `autonomy == "review_all"`. Transition to `rca-conclude` only upon explicit engineer `accept`.
