---
name: 3gpp-fta-root-cause
description: >
  Phase 3.5 of the 3GPP UE RCA pipeline v6 — per-iteration root cause
  deduction. Accepts iteration_id parameter. Synthesizes the
  iteration-local root cause from fta_iterations[iteration_id - 1]'s prior
  phase sections (hybrid_tree, base_events, cross_reference_findings,
  etc.). NO tool calls — this skill is pure synthesis logic. Determines
  root_cause_class for THIS iteration (VALUE_DISCREPANCY | ABSENCE |
  TIMER_EXPIRY | MULTI_CAUSE | OPEN | ALL_REJECTED), builds the evidence
  chain, and writes iteration_root_cause. NOTE: this is NOT the final
  root cause — the final root cause chain is synthesized later by
  3gpp-fta-iteration-controller after the user accepts terminal. Triggers:
  "deduce iteration N root cause", "synthesize iteration-local RCA",
  "Phase 3.5 for iteration", "determine iteration root cause class".
---

# 3GPP Phase 3.5 — Iteration Root Cause Deduction (v6, per iteration)

## Role

Synthesize the iteration-local root cause from prior FTA findings in the
SAME iteration. Pure synthesis — no tool calls.

## v6 Critical Change from v5

v5 wrote a SINGLE `phase3_root_cause` block that was THE answer.
v6 writes `fta_iterations[iter-1].iteration_root_cause` which is the
answer FOR THIS ITERATION ONLY. The pipeline-level causal chain is
synthesized later by the iteration controller after the user accepts
terminal.

## Hard constraints

1. **NO tool calls.** No `3gpp-spec-retrieval`, `3gpp-code-retrieval`,
   `3gpp-log-queries`. All inputs from state file.
2. **NO new keywords introduced.** All facts from state file fields
   already populated by prior iteration phases.
3. **NO fix generation.**
4. **NO cross-iteration synthesis** — that's the controller's job.

## Preconditions

- `iteration_id` provided
- `fta_iterations[iteration_id - 1]` exists with:
  - `hybrid_tree` complete with statuses
  - `pruned_branches`, `base_events`, `rejected`, `open_items` populated
  - `cross_reference_findings` populated
- `meta.current_phase == "iteration_<iteration_id>_running"`

## Output

Writes `fta_iterations[iteration_id - 1].iteration_root_cause`:

```json
{
  "deduced_at": "<ISO>",
  "iteration_id": <N>,
  "input_top_event": "<copy of iteration.input_top_event.event>",
  "failing_phase": "<branch.name where status == failure_here>",
  "pruned_phases": [<branch.name for each pruned branch>],
  "base_event_chain": [
    {"id": "P2.1", "name": "...", "relationship": "symptom"},
    {"id": "P2.2", "name": "...", "relationship": "cause_of_P2.1"}
  ],
  "root_cause_class": "VALUE_DISCREPANCY | ABSENCE | TIMER_EXPIRY | MULTI_CAUSE | OPEN | ALL_REJECTED",
  "description": "<synthesized text>",
  "commanded_value": "<from cross_reference if VALUE_DISCREPANCY>",
  "actual_value": "<from cross_reference if VALUE_DISCREPANCY>",
  "implementation_location": "<from cross_reference or code search>",
  "spec_violation": "<spec_ref + obligation>",
  "evidence_chain": [<list of evidence strings from prior phases>]
}
```

---

## Synthesis Logic

### Step 1 — Read iteration slice
Read `fta_iterations[iteration_id - 1]`:
- `input_top_event`
- `hybrid_tree.branches[*]` (statuses + names)
- `pruned_branches[]`, `base_events[]`, `rejected[]`, `open_items[]`
- `cross_reference_findings[]`

### Step 2 — Determine root_cause_class for this iteration

```
findings = iteration.cross_reference_findings
base_events = iteration.base_events

if base_events is empty AND iteration.rejected is non-empty:
  root_cause_class = "ALL_REJECTED"

elif base_events is empty AND iteration.open_items is non-empty:
  root_cause_class = "OPEN"

elif any finding has root_cause_class == "VALUE_DISCREPANCY":
  root_cause_class = "VALUE_DISCREPANCY"
  # pick discrepancy with largest |delta| or deepest base event

elif len(base_events) > 1 AND at least one cross-ref finding relates them:
  root_cause_class = "MULTI_CAUSE"

elif len(base_events) == 1 AND base_event.name matches timer pattern:
  root_cause_class = "TIMER_EXPIRY"

elif len(base_events) >= 1:
  root_cause_class = "ABSENCE"

else:
  root_cause_class = "OPEN"
```

### Step 3 — Identify failing phase
- Branch in `hybrid_tree.branches[]` with `status == "failure_here"`
- Multiple failure_here → deepest one

### Step 4 — Build base_event_chain
Iterate `base_events[]`; assign relationships using cross_reference_findings:
- VALUE_DISCREPANCY in cross_ref → `relationship: "cause_of_<other>"`
- No matching commanded-value IE → `relationship: "symptom"`

### Step 5 — Compose description
Use templates matching `root_cause_class` (see v5 root-cause SKILL.md for
templates — same patterns apply to iteration-local).

All placeholder values from state file fields. Do NOT invent failure
mechanisms or consequences not in `evidence_chain`.

### Step 6 — Assemble evidence_chain (within this iteration)
Concatenate evidence strings in order:
1. Scope discriminator (cross-iteration, from phase1_scope_filter.discriminator)
   — only for iteration 1; later iterations cite the prior iteration's outcome
2. Iteration input_top_event source
3. Pruning evidence from `pruned_branches[*].evidence`
4. Gate A evidence for failing branch
5. Gate B evidence for each base event
6. Cross-reference evidence (commanded/actual/delta)
7. Implementation location

Keep total chain ≤15 entries.

### Step 7 — Pick implementation_location and spec_violation
- `implementation_location` from cross_reference_findings if VALUE_DISCREPANCY;
  else from deepest base event
- `spec_violation` from cross_reference_findings.commanded_ie_lookup if
  VALUE_DISCREPANCY; else from base event's spec_ref

### Step 8 — Write state file
Atomic write of full `iteration.iteration_root_cause` block.

**Do NOT change `meta.current_phase`** — workflow next dispatches
`3gpp-fta-iteration-controller`.

---

## Anti-Hallucination

- Every string field uses values already in iteration's state slice
- If a field cannot be filled → set to `null` and add notes — never invent
- Synthesis combines existing values; does not invent new facts

---

## What this skill does NOT do (HARD)

- ❌ NO tool calls of any kind
- ❌ NO new keywords introduced
- ❌ NO cross-iteration synthesis (controller's job)
- ❌ NO recommendation logic (controller's job)
- ❌ NO fix generation, code patches, or remediation
- ❌ NO test case design
- ❌ NO engineering action items
- ❌ NO "next steps" beyond capture suggestions in open_items
- ❌ NO modifications to other iterations

After this skill writes `iteration_root_cause`, the iteration controller
takes over for Checkpoint B.

See `references/root-cause-checklist.md`.
