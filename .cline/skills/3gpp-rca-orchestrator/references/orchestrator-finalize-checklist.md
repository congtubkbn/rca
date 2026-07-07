# Phase 4 Finalize Checklist — v6

Run through this list when invoked in finalize mode. ALL items must be
satisfied before writing the final report and terminating.

## Preconditions
- [ ] `<workspace>/.rca/current_state_path.txt` exists
- [ ] State file exists and is valid JSON
- [ ] `meta.current_phase == "phase4_finalizing"`
- [ ] State file contains `meta`, `phase1_scope_filter`, `phase2_ecf`,
  `user_decisions[]` (≥1 entry for Checkpoint A), `fta_iterations[]`
  (≥1 entry), `phase3_root_cause_chain` (populated by iteration controller)

## Validation: keyword provenance (v6 iteration-scoped)
For every keyword referenced in:
- `phase3_root_cause_chain.causal_chain[*]`
- `phase3_root_cause_chain.final_root_cause.evidence_chain[*]`
- Each `fta_iterations[i].iteration_root_cause.evidence_chain[*]`

Verify:
- [ ] Matching entry exists in `keyword_provenance_audit`
- [ ] `iteration_id` on the audit entry matches the iteration where the
  keyword was used (or is `null` for pre-FTA phase keywords)
- [ ] Cross-iteration carry-over keywords (top event derivation) are
  explicitly flagged in their audit entry
- [ ] HALT if any keyword lacks valid provenance

## Validation: termination boundary (preserved from v5)
- [ ] Scan all string values across the state file for forbidden patterns
  (case-insensitive): `"fix:"`, `"recommendation:"`, `"patch:"`,
  `"remediation:"`, `"action item:"`, `"next step:"`, `"should be changed"`,
  `"should be modified"`, `"to fix this"`, `"the fix is"`
- [ ] HALT if any forbidden pattern found
- [ ] EXCEPTION: pattern matches inside `engineer_input` are allowed
  (the engineer may have used these words in their description)

## Validation: completeness
- [ ] `phase3_root_cause_chain.final_root_cause.root_cause_class` is valid
  (one of: VALUE_DISCREPANCY, ABSENCE, TIMER_EXPIRY, MULTI_CAUSE, OPEN,
  ALL_REJECTED)
- [ ] If `root_cause_class == "VALUE_DISCREPANCY"`, the terminal iteration's
  `cross_reference_findings` has at least one entry with matching
  `commanded_value` and `actual_value`
- [ ] `phase3_root_cause_chain.causal_chain` has at least 1 entry
- [ ] Every `fta_iterations[i]` has a `user_decision` populated (no
  orphaned iterations)
- [ ] Every `fta_iterations[i]` has an `iteration_root_cause` populated
- [ ] Every `fta_iterations[i]` has an `agent_recommendation` populated

## Compute report-level statistics
- [ ] `iteration_count = len(fta_iterations)`
- [ ] `user_override_count = sum(d.overrode_recommendation == true for d in user_decisions)`
- [ ] `high_disagreement_run = (user_override_count >= len(user_decisions) * 0.5)`
- [ ] Write these to `phase3_root_cause_chain.user_override_count` and
  `phase3_root_cause_chain.high_disagreement_run`

## Report assembly
- [ ] Read template at `.cline/skills/_shared/rca-report-template.md`
- [ ] Section 1 (Problem Scope) — fill from `phase1_scope_filter`
- [ ] Section 2 (Top Event) — include `top_event_candidates[]` table and
  `user_confirmation`
- [ ] Section 3 (FTA Iterations) — render ONE subsection per iteration:
  - 3.0 iteration overview table
  - 3.N detail per iteration: tree, pruned branches, base events,
    cross-reference findings, iteration root cause, agent rec vs user decision
- [ ] Section 4 (Causal Chain) — fill from `phase3_root_cause_chain`
- [ ] Section 5 (Keyword Provenance Audit) — table from
  `keyword_provenance_audit`, grouped by `iteration_id`
- [ ] Section 6 (User Decision Audit) — table from `user_decisions[]`
- [ ] Section 7 (Pipeline Metadata) — counts and reasons
- [ ] Section 8 (Termination Notice) — verbatim from template

## Write report
- [ ] Path: `<workspace>/.rca/report_${TS}.md` where TS is from `meta.started_at`
- [ ] Atomic write (`.tmp` → `mv`)
- [ ] Verify file is non-empty and renders as Markdown

## Update state file
- [ ] Append `phase4_rca_report` block with all 4 fields:
  - `finalized_at`, `iteration_count`, `report_path`, `termination_reason`
- [ ] Set `meta.finished_at` to current ISO timestamp
- [ ] Set `meta.current_phase = "complete"`
- [ ] Atomic state-file write

## Termination
- [ ] Display report path to user
- [ ] Display iteration count and high_disagreement_run flag
- [ ] Confirm pipeline termination
- [ ] DO NOT offer fix design, code patches, configuration suggestions,
  test cases, or next steps
- [ ] If user requests any of the above, respond with the v6 termination notice

## Halt conditions
- Missing state file section → halt with "Pipeline incomplete: <section>"
- Keyword provenance failure → halt with "Provenance audit failed: <keyword>
  in iteration <N>"
- Forbidden pattern found → halt with "v6 termination policy violation: <pattern>"
- Cannot write report → halt with file error
- Orphaned iteration (no user_decision) → halt with "Iteration <N> has no
  user_decision; pipeline cannot finalize"
