# Checkpoint A Checklist (v6)

## PRESENT mode

### Preconditions
- [ ] `meta.current_phase == "phase2_running"`
- [ ] `phase2_ecf.top_event_candidates[]` has 1-3 entries
- [ ] Each candidate has: rank, is_primary, event, timestamp, layer,
  evidence, confidence, rejection_reason (null for primary)

### Determine recommendation
- [ ] Default: confirm rank 1 (primary)
- [ ] If primary confidence is LOW and any alternative is HIGH or MEDIUM,
  recommendation shifts to that alternative

### Render prompt
- [ ] Follow exact format in `_shared/checkpoint-presentation-formats.md`
- [ ] List ALL candidates (1-3 entries; never pad with hallucinated ones)
- [ ] Show evidence and confidence for each
- [ ] Show rejection_reason for non-primary candidates
- [ ] Clearly state agent recommendation
- [ ] List all 5 user options: confirm / use alternative N / refine /
  reject and restart / abort

### Transition
- [ ] Set `meta.current_phase = "phase2_pending_confirmation"`
- [ ] HALT — return to workflow

---

## RECORD mode

### Preconditions
- [ ] `meta.current_phase == "phase2_pending_confirmation"`
- [ ] Workflow invokes with parsed `user_action`

### Action: confirm
- [ ] Copy candidates[0] fields into `phase2_ecf.top_event`
- [ ] Write `phase2_ecf.user_confirmation` with selected_rank=1, overrode_recommendation=false
- [ ] Append to `user_decisions[]` with action="confirm_primary"
- [ ] Set `meta.current_phase = "phase2_confirmed"`

### Action: use alternative 2 or 3
- [ ] Copy candidates[selected_rank - 1] fields into `phase2_ecf.top_event`
- [ ] Write `phase2_ecf.user_confirmation` with overrode_recommendation=true
- [ ] Append to `user_decisions[]` with action="use_alternative"
- [ ] Set `meta.current_phase = "phase2_confirmed"`

### Action: refine
- [ ] Append refinement_text to `phase1_scope_filter.user_refinements[]`
- [ ] Clear `phase2_ecf` (will be re-populated by re-running event-timeline)
- [ ] Set `meta.current_phase = "phase2_running"`
- [ ] Workflow will re-trigger `3gpp-event-timeline` on next dispatch

### Action: reject_and_restart
- [ ] Halt with prompt: "Provide a fresh scope/description for re-analysis"
- [ ] Clear `phase1_scope_filter` and `phase2_ecf`
- [ ] Set `meta.current_phase = "phase1"`
- [ ] Workflow will re-trigger scoping on next dispatch

### Action: abort
- [ ] Write `phase4_rca_report` with termination_reason="User aborted at Checkpoint A"
- [ ] Set `meta.finished_at` and `meta.current_phase = "complete"`
- [ ] No report file generated

### Action: unparseable
- [ ] Re-render Checkpoint A prompt with note about parse failure
- [ ] State stays at `phase2_pending_confirmation`

## Hard NOT-do checks
- [ ] No tool calls (no spec_query, code_search, log_query)
- [ ] No new candidates invented
- [ ] No evidence modification
- [ ] No FTA work
- [ ] No fix recommendations
