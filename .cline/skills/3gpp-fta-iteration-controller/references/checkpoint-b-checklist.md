# Checkpoint B Checklist (v6)

## PRESENT mode (after 3gpp-fta-root-cause completes for iteration N)

### Preconditions
- [ ] `meta.current_phase == "iteration_<N>_running"`
- [ ] `fta_iterations[N-1].iteration_root_cause` is populated
- [ ] `fta_iterations[N-1].agent_recommendation` is NOT yet populated

### Compute termination signals
- [ ] `spec_skeleton_returned_empty_and_code_only_no_failure_modes`
- [ ] `single_branch_tree`
- [ ] `find_implementation_returned_same_file_as_prior_iteration`
- [ ] `no_commanded_value_ies_relevant`
- [ ] `iteration_budget_near_exhaustion`
- [ ] `all_base_events_rejected`
- [ ] `iteration_open`

### Apply recommendation logic (first match wins)
- [ ] All-rejected → abort
- [ ] Open items only → abort
- [ ] ≥2 termination signals → accept_terminal
- [ ] Budget near exhaustion → accept_terminal
- [ ] VALUE_DISCREPANCY → dig_deeper into cause-side base event
- [ ] MULTI_CAUSE → dig_deeper into highest-confidence base event
- [ ] ABSENCE at depth 1 → dig_deeper
- [ ] ABSENCE at depth ≥ 2 → accept_terminal
- [ ] TIMER_EXPIRY with impl location → accept_terminal
- [ ] TIMER_EXPIRY without impl location → dig_deeper
- [ ] Else → accept_terminal

### Write agent_recommendation
- [ ] `computed_at`, `action`, `recommended_base_event_id`, `rationale`,
  `termination_signals_detected` populated

### Render prompt
- [ ] Per `_shared/checkpoint-presentation-formats.md` Section "Checkpoint B"
- [ ] Iteration summary (top event, root cause class, failing phase, pruned phases)
- [ ] Base events confirmed (one line each)
- [ ] Cross-reference findings (one block per finding)
- [ ] Iteration root cause description
- [ ] Causal chain so far (iterations 1..N)
- [ ] Agent recommendation with rationale
- [ ] Termination signals list
- [ ] All 3 user options: dig deeper / accept / abort
- [ ] Iteration budget status

### Transition
- [ ] Set `meta.current_phase = "iteration_<N>_pending_decision"`
- [ ] HALT — return to workflow

---

## RECORD mode (after user response)

### Preconditions
- [ ] `meta.current_phase == "iteration_<N>_pending_decision"`
- [ ] Workflow supplies `user_action` and `user_selected_id` (if applicable)

### Action: dig_deeper
- [ ] Determine if override (selected_id ≠ recommended_id OR rec was accept_terminal)
- [ ] If override AND override_confirmation_received==false → emit override prompt and HALT
- [ ] If aligned OR override confirmed → proceed:
  - [ ] Look up selected base event in `iter.base_events` (validate)
  - [ ] Write `iter.user_decision`
  - [ ] Append to `user_decisions[]`
  - [ ] Increment `meta.current_iteration_id`
  - [ ] Set `meta.current_phase = "iteration_<N+1>_running"`
  - [ ] Append new entry to `fta_iterations[]` with `input_top_event` from selected base event
  - [ ] Add cross-iteration carry-over entry to `keyword_provenance_audit`

### Action: accept_terminal
- [ ] If override (rec was dig_deeper) AND override_confirmation_received==false → emit override prompt and HALT
- [ ] Write `iter.user_decision`
- [ ] Append to `user_decisions[]`
- [ ] Synthesize `phase3_root_cause_chain`:
  - [ ] `iterations_traversed`
  - [ ] `terminal_iteration_id`
  - [ ] `termination_reason`
  - [ ] `causal_chain` (one entry per iteration)
  - [ ] `final_root_cause` (copy of terminal iteration's iteration_root_cause)
  - [ ] Leave `user_override_count` and `high_disagreement_run` for orchestrator finalize
- [ ] Set `meta.current_phase = "phase4_finalizing"`

### Action: abort
- [ ] Write `iter.user_decision` with action=abort
- [ ] Append to `user_decisions[]`
- [ ] Write `phase3_root_cause_chain` with abort termination_reason
- [ ] Write `phase4_rca_report` with termination_reason and report_path=null
- [ ] Set `meta.current_phase = "complete"`
- [ ] Set `meta.finished_at`

### Action: confirm_override
- [ ] Verify pending_override exists
- [ ] Treat as the original action with override_confirmation_received=true
- [ ] Clear pending_override

### Action: cancel
- [ ] Clear pending_override
- [ ] Re-render Checkpoint B prompt (workflow re-dispatches)

### Action: unparseable
- [ ] Re-render Checkpoint B prompt with parse-error note

## Hard NOT-do checks
- [ ] No tool calls (no spec_query, code_search, log_query)
- [ ] No modification of iteration_root_cause
- [ ] No invention of base events
- [ ] No bypass of override confirmation
- [ ] No fix recommendations
- [ ] No "next steps" beyond capture suggestions in iteration_root_cause
