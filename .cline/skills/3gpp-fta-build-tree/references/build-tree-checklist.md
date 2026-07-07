# FTA Build Tree Checklist (Phase 3.1) — v6

## Preconditions
- [ ] `iteration_id` provided by workflow
- [ ] State file exists; `fta_iterations[iteration_id - 1].input_top_event` populated
- [ ] `meta.current_phase == "iteration_<iteration_id>_running"`
- [ ] Read only `phase1_scope_filter` + the iteration's `input_top_event`

## Spec skeleton
- [ ] Invoke `3gpp-spec-retrieval` with `operation=skeleton`
- [ ] Verify tool exit code 0
- [ ] If `phases[]` empty:
  - [ ] Set `iteration.hybrid_tree.spec_skeleton_returned_empty = true`
  - [ ] Invoke fallback `3gpp-spec-retrieval generate_hypotheses`
  - [ ] Set `iteration.hybrid_tree.fallback_used = "generate_hypotheses + code-only"`
  - [ ] Treat each hypothesis as a top-level branch
- [ ] `spec_skeleton_source` written to state file

## Module binding per phase/hypothesis
For each branch:
- [ ] Invoke `3gpp-code-retrieval` with `operation=bind_module`
- [ ] Pass `phase_name`, `phase_ref`, `scope_layer`
- [ ] If `modules[]` empty: mark branch as `unbindable` but include in tree
- [ ] Tool exit code 0

## Construct tree
- [ ] `gate_at_top` = "OR" (default — override only if spec dictates AND)
- [ ] Each branch has: id, name, spec_ref, mandatory_messages[], modules[]
- [ ] Each branch has `status: "unevaluated"`
- [ ] Each branch has `children: []` (empty — populated later in 3.3)
- [ ] Each branch has `gate_a_result: null`

## Iteration-specific
- [ ] All output written to `fta_iterations[iteration_id - 1].hybrid_tree`
- [ ] NOT to `phase3_hybrid_tree` (that was the v5 path)
- [ ] All audit entries tagged with current `iteration_id`

## Hard NOT-do checks
- [ ] No log queries issued
- [ ] No `expand_failure_modes` called
- [ ] No `find_commanded_values` called
- [ ] No sub-branches in `children[]` (Phase 3.3's job)
- [ ] No pruning decisions (Phase 3.2's job)
- [ ] No root cause synthesis
- [ ] No modifications to other iterations

## Final state-file write
- [ ] `iteration.hybrid_tree.constructed_at` set
- [ ] All fields present per schema
- [ ] `meta.current_phase` NOT changed (stays at `iteration_<N>_running`)
- [ ] Atomic write completed
