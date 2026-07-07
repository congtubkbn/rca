---
name: 3gpp-fta-build-tree
description: >
  Phase 3.1 of the 3GPP UE RCA pipeline v6 — Hybrid Fault Tree construction
  per iteration. Build the initial fault tree skeleton from 3GPP spec
  (standardized procedure phases) and bind UE source modules to each phase
  via code search. Accepts iteration_id parameter — reads input_top_event
  from fta_iterations[iteration_id - 1] and writes hybrid_tree to that same
  iteration slot. For iterations ≥ 2 the spec skeleton commonly returns
  empty; this is expected and the skill falls back to generate_hypotheses
  (records fallback_used in iteration record). Calls 3gpp-spec-retrieval
  (skeleton or fallback) and 3gpp-code-retrieval (bind_module). Does NOT
  query logs and does NOT evaluate branches. Triggers: "build hybrid fault
  tree for iteration N", "construct FTA skeleton for iteration", "Phase 3.1
  of iteration", "bind spec phases to code modules for iteration".
---

# 3GPP Phase 3.1 — Hybrid Fault Tree Construction (v6, per iteration)

## Role

Build the initial fault tree skeleton for one iteration. Children
(failure modes) are NOT added here — they're added in 3.3 on branches
that survive evaluation.

## v6 Change from v5

| Aspect | v5 | v6 |
|---|---|---|
| Parameter | None (single tree) | `iteration_id` (which iteration's tree) |
| State read | `phase2_ecf.top_event` | `fta_iterations[iter-1].input_top_event` |
| State write | `phase3_hybrid_tree` | `fta_iterations[iter-1].hybrid_tree` |
| Fallback | Documented but rare | Expected for iterations ≥ 2 |

## Hard constraints

1. Tool calls allowed:
   - `3gpp-spec-retrieval` (skeleton or generate_hypotheses fallback)
   - `3gpp-code-retrieval` (bind_module operation only)
2. Tool calls FORBIDDEN:
   - `3gpp-log-queries` (Phase 3.1 does no log queries)
   - Other spec or code operations
3. Tree contains ONLY top-level phases — no sub-branches, no failure modes
4. All audit entries scoped to `iteration_id`

## Preconditions

- `iteration_id` provided by workflow
- `fta_iterations[iteration_id - 1]` exists with `input_top_event` populated
- `meta.current_phase == "iteration_<N>_running"` where N = iteration_id

## Output

Writes to `fta_iterations[iteration_id - 1].hybrid_tree`:

```json
{
  "constructed_at": "<ISO>",
  "spec_skeleton_returned_empty": false | true,
  "fallback_used": null | "generate_hypotheses + code-only",
  "gate_at_top": "OR",
  "spec_skeleton_source": {...},
  "branches": [
    {
      "id": "P1",
      "name": "<spec phase name OR hypothesis cause>",
      "spec_ref": "<TS XX.XXX §Y.Y>",
      "mandatory_messages": ["..."],
      "modules": [...],
      "gate_a_result": null,
      "status": "unevaluated",
      "children": []
    }
  ]
}
```

---

## Execution

### Step 1 — Read state file slice
Read ONLY `meta.current_iteration_id` confirmation, `phase1_scope_filter`,
and `fta_iterations[iteration_id - 1].input_top_event`.

Determine if this is a spec-anchored iteration (iteration 1, usually) or
not (iteration ≥ 2, usually):
- Iteration 1: input_top_event came from Phase 2 signaling; spec skeleton
  applies
- Iteration ≥ 2: input_top_event came from a base event in prior iteration
  (e.g. "Preamble_Power_Error"); spec skeleton may not apply

### Step 2 — Get spec skeleton

```
Use the 3gpp-spec-retrieval skill with:
  operation: skeleton
  procedure: <scope_filter.procedure>
  rat: <scope_filter.rat>
  top_event: <iteration.input_top_event.event>
```

The shared skill runs `spec_query.py --operation skeleton` and writes to
`fta_iterations[iteration_id - 1].hybrid_tree.spec_skeleton_source`.

### Step 3 — Detect empty skeleton (v6 expected behavior at depth)

If skeleton returns `phases: []`:
- Set `iteration.hybrid_tree.spec_skeleton_returned_empty = true`
- Invoke fallback:

```
Use the 3gpp-spec-retrieval skill with:
  operation: generate_hypotheses
  event: <iteration.input_top_event.event>
  procedure: <scope_filter.procedure>
  rat: <scope_filter.rat>
```

- Set `iteration.hybrid_tree.fallback_used = "generate_hypotheses + code-only"`
- Treat each hypothesis from the fallback as a top-level branch in the tree

### Step 4 — Bind code modules to each phase/hypothesis

For each phase (or fallback hypothesis), call code retrieval:

```
Use the 3gpp-code-retrieval skill with:
  operation: bind_module
  phase_name: <phase.name>
  phase_ref: <phase.spec_ref>
  scope_layer: <phase.protocol_layer>
```

Returns module bindings; written to `branch.modules`.

**If a branch returns no modules:** Mark `branch.modules = []` and add a
note. Branch will still be evaluated in Phase 3.2 (Gate A) without code
binding for later expansion. This is unbindable but valid.

### Step 5 — Construct hybrid tree
Assemble `fta_iterations[iteration_id - 1].hybrid_tree`:
- `gate_at_top` = "OR" (default)
- `branches` = phases or fallback hypotheses with their bindings
- Each branch: `status = "unevaluated"`, `children = []`, `gate_a_result = null`

### Step 6 — Write state file
Atomic write. Set `iteration.hybrid_tree.constructed_at`.

**Do NOT change `meta.current_phase`** — workflow dispatches the next step
(`3gpp-fta-evaluate-branches`) based on the iteration's tree being
present-but-unevaluated.

See `references/build-tree-checklist.md`.

---

## Anti-Hallucination

- Phase names from spec_query.py skeleton or generate_hypotheses output
- Spec refs verbatim from spec_query.py
- Module file paths from code_search.py bind_module
- Primary function names from snippet signatures
- All audit entries tagged with `iteration_id`
- If any field cannot be filled from tool output, leave it `null` or `[]`
  and document — never invent

---

## What this skill does NOT do (HARD)

- ❌ Does NOT query logs (Phase 3.2's job)
- ❌ Does NOT evaluate branches (Phase 3.2's job)
- ❌ Does NOT add failure modes / sub-branches (Phase 3.3's job)
- ❌ Does NOT prune branches (Phase 3.2's job)
- ❌ Does NOT cross-reference values (Phase 3.4's job)
- ❌ Does NOT deduce root cause (Phase 3.5's job)
- ❌ Does NOT generate fixes
- ❌ Does NOT touch other iterations' trees

Output is the initial hybrid tree skeleton for ONE iteration. Nothing more.
