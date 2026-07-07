# FTA Evaluate Branches Checklist (Phase 3.2 + 3.3) — v6

## Preconditions
- [ ] `iteration_id` provided
- [ ] `fta_iterations[iteration_id - 1].hybrid_tree.branches[]` exists
- [ ] Each branch has `status: "unevaluated"`, `children: []`
- [ ] `meta.current_phase == "iteration_<N>_running"`

## For each top-level branch (Phase 3.2)

### Priority sorting
- [ ] If iteration 1: branches whose `mandatory_messages` appear in
  `phase2_ecf.observable_symptoms.missing_events` come first
- [ ] If iteration ≥ 2: follow tree order

### Gate A
- [ ] (Optional) Invoke `3gpp-spec-retrieval extract_ies` for IE refinement
- [ ] Invoke `3gpp-log-queries phase3_gate_a` with branch's mandatory messages
- [ ] Tool exit code 0
- [ ] `branch.gate_a_result` populated
- [ ] For code-only fallback iterations: skip Gate A, mark `not_applicable`

### Classification (5 cases)
- [ ] Case A normal_passage → append to `pruned_branches[]`, set status, SKIP Step 3
- [ ] Case B failure_here → set status, proceed to Step 3
- [ ] Case C absent → set status, proceed to Step 3
- [ ] Case D unclear → append to `open_items[]`, set status, SKIP Step 3
- [ ] N/A code-only iter ≥ 2 → skip Gate A, go to Step 3

### All-Case-A guard
- [ ] If all branches Case A: halt with `"all_phases_normal_failure_not_in_skeleton"`;
  iteration controller will recommend appropriate action

## For each surviving branch (Phase 3.3)

### Failure mode expansion
- [ ] Invoke `3gpp-code-retrieval expand_failure_modes`
- [ ] If empty: fallback to `3gpp-spec-retrieval expand_sub_causes`
- [ ] Each failure mode gets id `<branch.id>.<n>`, added to `branch.children[]`

### Gate B per failure mode
- [ ] Invoke `3gpp-log-queries phase3_gate_b`
- [ ] `child.gate_b_result` populated
- [ ] Classify: confirmed → `base_events[]`; absent → `rejected[]`;
  unclear → `open_items[]`

### Anti-laziness
- [ ] ALL failure modes evaluated even if one confirmed

## Iteration-specific
- [ ] All output written to `fta_iterations[iteration_id - 1].*`
- [ ] All audit entries tagged with current `iteration_id`

## Hard NOT-do checks
- [ ] No cross-reference queries (Phase 3.4)
- [ ] No `find_commanded_values` calls
- [ ] No `bind_module` calls (Phase 3.1)
- [ ] No `find_implementation` calls (Phase 3.4)
- [ ] No root cause determined (Phase 3.5)
- [ ] No fabricated keywords if tools return empty (use fallback chain)
- [ ] No modifications to other iterations

## Final state-file write
- [ ] All branches' gate_a_result, status, children set
- [ ] `pruned_branches[]`, `base_events[]`, `rejected[]`, `open_items[]` updated
- [ ] `meta.current_phase` NOT changed
- [ ] Atomic write completed
