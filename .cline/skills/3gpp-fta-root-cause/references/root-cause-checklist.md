# FTA Root Cause Checklist (Phase 3.5) — v6

## Preconditions
- [ ] `iteration_id` provided
- [ ] `fta_iterations[iteration_id - 1]` has all prior phase sections:
  `hybrid_tree`, `pruned_branches`, `base_events`, `rejected`,
  `open_items`, `cross_reference_findings`
- [ ] `meta.current_phase == "iteration_<N>_running"`
- [ ] Slice-read the iteration's data (do not load whole state file)

## Determine root_cause_class
- [ ] Check `cross_reference_findings[]` for VALUE_DISCREPANCY entries
- [ ] If yes → `root_cause_class = "VALUE_DISCREPANCY"`
- [ ] Else if multiple base_events linked via cross-ref → `MULTI_CAUSE`
- [ ] Else if 1 base_event matches timer pattern → `TIMER_EXPIRY`
- [ ] Else if ≥1 base_events → `ABSENCE`
- [ ] Else if base_events empty + rejected non-empty → `ALL_REJECTED`
- [ ] Else if base_events empty + open_items non-empty → `OPEN`

## Identify failing_phase
- [ ] Find branch with `status == "failure_here"` in `hybrid_tree.branches[]`
- [ ] If multiple → pick deepest

## Build pruned_phases list
- [ ] Iterate `pruned_branches[]`, collect names

## Build base_event_chain
- [ ] Iterate `base_events[]`
- [ ] For each, check cross_reference_findings for VALUE_DISCREPANCY linkage
- [ ] If linked: `relationship: "cause_of_<other_id>"`
- [ ] If not linked: `relationship: "symptom"`

## Compose description
- [ ] Use template matching `root_cause_class`
- [ ] All placeholder values from iteration's state file fields
- [ ] 2-4 sentences

## Pick implementation_location
- [ ] From cross_reference_findings if VALUE_DISCREPANCY
- [ ] Else from deepest base event evidence
- [ ] `null` if not derivable

## Pick spec_violation
- [ ] From cross_reference_findings.commanded_ie_lookup if VALUE_DISCREPANCY
- [ ] Else from base event's spec_ref
- [ ] `null` if not derivable

## Assemble evidence_chain
- [ ] Source iteration context
- [ ] Pruning evidence from `pruned_branches[*]`
- [ ] Gate A evidence for failing branch
- [ ] Gate B evidence for each base event
- [ ] Cross-reference evidence
- [ ] Implementation location reference
- [ ] Total ≤15 entries

## Iteration-specific
- [ ] Output written to `fta_iterations[iteration_id - 1].iteration_root_cause`
- [ ] `iteration_root_cause.iteration_id` set to `iteration_id`
- [ ] No cross-iteration synthesis attempted

## Hard NOT-do checks
- [ ] NO tool calls
- [ ] NO new keywords introduced
- [ ] NO fix recommendations
- [ ] NO code patches
- [ ] NO config value suggestions
- [ ] NO test case design
- [ ] NO engineering action items
- [ ] NO modifications to `phase3_root_cause_chain` (controller's job)
- [ ] NO modifications to `meta.current_phase`

## Final state-file write
- [ ] `iteration_root_cause.deduced_at` set
- [ ] All required fields present (some may be `null`)
- [ ] Atomic write completed
- [ ] After write: skill returns; workflow dispatches `3gpp-fta-iteration-controller`
