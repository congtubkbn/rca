---
name: 3gpp-fta-evaluate-branches
description: >
  Phase 3.2 + 3.3 of the 3GPP UE RCA pipeline v6 — per-iteration branch
  evaluation with pivot-pruning + dynamic expansion. Accepts iteration_id
  parameter. For each top-level branch of the iteration's hybrid_tree: run
  Gate A signaling check; if normal_passage → prune; if failure_here →
  call code expand_failure_modes and run Gate B trace check on each
  failure mode. Reads from and writes to fta_iterations[iteration_id - 1]
  exclusively. Calls 3gpp-spec-retrieval (extract_ies for Gate A
  refinement, optional), 3gpp-code-retrieval (expand_failure_modes for
  sub-branches), and 3gpp-log-queries (Gate A signaling, Gate B trace).
  Triggers: "evaluate FTA branches for iteration N", "Gate A signaling
  evaluation for iteration", "expand failure modes with Gate B for iteration",
  "Phase 3.2 + 3.3 for iteration".
---

# 3GPP Phase 3.2 + 3.3 — Branch Evaluation (v6, per iteration)

## Role

Walk each top-level branch of the iteration's tree. Gate A (signaling)
classifies; Gate B (trace) verifies failure modes. Pivot-prune
confirmed-normal branches; dynamically expand confirmed-failure branches.

## v6 Change from v5

Accepts `iteration_id`. Reads/writes `fta_iterations[iteration_id - 1].*`.
All anti-hallucination and table isolation invariants preserved.

## Hard constraints

1. Tool calls allowed:
   - `3gpp-spec-retrieval` (extract_ies operation, optional)
   - `3gpp-code-retrieval` (expand_failure_modes, plus expand_sub_causes fallback)
   - `3gpp-log-queries` (phase3_gate_a, phase3_gate_b)
2. Tool calls FORBIDDEN:
   - `3gpp-spec-retrieval skeleton / find_commanded_values / lightweight_procedure`
   - `3gpp-code-retrieval bind_module / find_implementation`
   - `3gpp-log-queries phase1 / phase2 / phase3_cross_ref`
3. Within an expanded branch, ALL failure modes must be evaluated
4. All audit entries tagged with `iteration_id`

## Preconditions

- `iteration_id` provided by workflow
- `fta_iterations[iteration_id - 1].hybrid_tree` exists with top-level branches
- Each branch has `modules[]`, `mandatory_messages[]`, `status: "unevaluated"`
- `meta.current_phase == "iteration_<iteration_id>_running"`

## Output

Updates `fta_iterations[iteration_id - 1]`:
- `hybrid_tree.branches[*].gate_a_result` for each branch
- `hybrid_tree.branches[*].status` (pruned_normal | failure_here | absent | open)
- `hybrid_tree.branches[*].children[*]` for failure_here / absent branches
- `hybrid_tree.branches[*].children[*].gate_b_result` for each child
- `pruned_branches[]`, `base_events[]`, `rejected[]`, `open_items[]`

---

## Execution — Phase 3.2 (Gate A with Pivot-Pruning)

For each branch in priority order (prioritize branches whose
`mandatory_messages` appear in `phase2_ecf.observable_symptoms.missing_events`,
when iteration 1; for iteration ≥ 2, follow tree order):

### Step 2.1 — Refine IEs (optional)
If `mandatory_messages` is generic, optionally call `3gpp-spec-retrieval extract_ies`.

### Step 2.2 — Gate A: Query signaling

```
Use the 3gpp-log-queries skill with:
  phase_tag: phase3_gate_a
  table: UE_3gpp_signaling_log
  keywords: <branch.mandatory_messages>
  ie_names: <from extract_ies if any>
  time_window: <scope_filter.time_window>
  hypothesis_id: <branch.id>
```

(For iterations ≥ 2 with code-only fallback: Gate A may have no defined
signaling messages. In that case, skip Gate A for those branches and
proceed directly to Gate B; mark `gate_a_result.result = "not_applicable"`.)

### Step 2.3 — Interpret Gate A result

| Case | Result | Action |
|---|---|---|
| A | Messages clean, no failure indicators | **PRUNE.** status=`pruned_normal`. Append to `pruned_branches[]`. Skip Step 3. |
| B | Messages with failure indicators | **CONFIRM as failure location.** status=`failure_here`. Proceed to Step 3. |
| C | Messages absent entirely | status=`absent`. Proceed to Step 3 (Gate B may find evidence). |
| D | Unclear / partial | status=`open`. Append to `open_items[]`. Skip Step 3. |
| N/A | No signaling messages defined (iter ≥ 2 code-only) | Skip Gate A, go to Step 3 directly. |

If ALL branches are Case A → halt with
`"all_phases_normal_failure_not_in_skeleton"`. The iteration controller
will recommend `abort` or `accept_terminal` depending on signals.

---

## Execution — Phase 3.3 (Dynamic Expansion of Surviving Branches)

For each surviving branch (Case B, C, or N/A):

### Step 3.1 — Expand failure modes

```
Use the 3gpp-code-retrieval skill with:
  operation: expand_failure_modes
  module: <branch.modules[0].file>
  phase_context: <branch.name>
```

Returns `failure_modes[]` with literal log_keywords from log macros.

**Fallback:** If empty, call `3gpp-spec-retrieval expand_sub_causes`.

### Step 3.2 — Append failure modes to tree
For each failure mode:
- Assign id: `<branch.id>.<n>`
- Add to `branch.children[]`
- Initial `status: "unevaluated"`, `gate_b_result: null`

### Step 3.3 — Gate B: Query trace per failure mode

```
Use the 3gpp-log-queries skill with:
  phase_tag: phase3_gate_b
  table: UE_Trace_log
  keywords: <failure_mode.log_keywords>
  log_tags: <failure_mode.log_tags>
  time_window: <scope_filter.time_window>
  hypothesis_id: <failure_mode.id>
```

### Step 3.4 — Interpret Gate B
| Gate B | Action |
|---|---|
| Matched events | status=`base_event_confirmed`. Append to `base_events[]`. |
| No matches | status=`rejected`. Append to `rejected[]`. |
| Unclear | status=`open`. Append to `open_items[]`. |

**Anti-laziness within expanded branch:** evaluate ALL failure modes even
if one is confirmed.

---

## Anti-Hallucination

- Gate A keywords from `branch.mandatory_messages` (originated in spec output)
- Gate A IE names from spec_query.py extract_ies output
- Sub-branch names + log_keywords from code_search.py expand_failure_modes
- Gate B keywords from `failure_mode.log_keywords` (macro literals only)
- All audit entries tagged with `iteration_id`
- NEVER invent function names, log strings, IE names, or failure mode names

---

## What this skill does NOT do (HARD)

- ❌ Does NOT cross-reference commanded vs actual values (Phase 3.4's job)
- ❌ Does NOT determine root cause class (Phase 3.5's job)
- ❌ Does NOT generate fixes
- ❌ Does NOT bypass empty-result halts by fabrication
- ❌ Does NOT prune children — only top-level branches are pivot-pruned
- ❌ Does NOT touch other iterations' state

See `references/evaluate-branches-checklist.md`.
