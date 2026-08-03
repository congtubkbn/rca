# Keyword Provenance Rules — v6 (iteration-scoped)

## Core principle (preserved from v3/v4/v5)

Every keyword used in any DB query or downstream search MUST trace back to a
specific Python tool invocation in the same pipeline run. NO keyword may
originate from the model's pre-trained memory.

## v6 Change: Iteration Scoping

In v5, every audit entry had `used_by: "Phase 3 Gate A P1"` (or similar).
In v6, every audit entry additionally has `iteration_id: <N>` so the
provenance trail tells you not just *which phase* used a keyword but
*which iteration of FTA*.

This matters because:
- Iteration 1 may use spec-anchored keywords (mandatory_messages from skeleton)
- Iteration 2+ often uses code-anchored keywords (function names from
  `find_implementation`) because the spec skeleton returns empty
- Phase 4 audit needs to validate provenance **per iteration** to avoid
  false positives (e.g. a keyword introduced in iteration 1 cannot be used
  to query for iteration 3's evidence unless explicitly re-derived)

---

## Per-Phase Keyword Origin Rules (with v6 iteration field)

### Phase 1 (3gpp-scoping) — unchanged from v5

| Keyword class | Origin | Tool | Audit `iteration_id` |
|---|---|---|---|
| Procedure name | Engineer description | (orchestrator parses) | `null` (pre-FTA) |
| Primary layers | spec_query.py lightweight_procedure | `--need is_is_not` | `null` |
| Initiating message | spec_query.py lightweight_procedure | `--need is_is_not` | `null` |
| Key timers | spec_query.py lightweight_procedure | `--need is_is_not` | `null` |

Must NOT touch: UE_Trace_log, code search, other spec modes.

### Phase 2 (3gpp-event-timeline) — unchanged from v5 (but v6 produces alternatives)

| Keyword class | Origin | Audit `iteration_id` |
|---|---|---|
| Expected message flow | spec_query.py lightweight_procedure (need=ecf) | `null` |
| Signaling timeline keywords | expected_flow from state file | `null` |
| top_event_candidates[].event | actual signaling rows | `null` |
| missing_events | comparison logic | `null` |

Must NOT touch: UE_Trace_log, code search.

### Iteration N — Phase 3.1 (3gpp-fta-build-tree)

| Keyword class | Origin | Tool | Audit `iteration_id` |
|---|---|---|---|
| Skeleton phases | spec_query.py skeleton operation | `--operation skeleton` | `N` |
| Mandatory messages per phase | (same call) | (same call) | `N` |
| Module bindings | code_search.py bind_module | `--operation bind_module` | `N` |
| File paths in modules | (same call) | (same call) | `N` |

If skeleton returns empty (common at iteration ≥ 2):
| Keyword class | Origin | Tool | Audit `iteration_id` |
|---|---|---|---|
| Hypothesis names (fallback) | spec_query.py generate_hypotheses | `--operation generate_hypotheses` | `N` |
| Module bindings | code_search.py bind_module (still) | `--operation bind_module` | `N` |

### Iteration N — Phase 3.2 + 3.3 (3gpp-fta-evaluate-branches)

| Keyword class | Origin | Tool | Audit `iteration_id` |
|---|---|---|---|
| IE names (Gate A) | spec_query.py extract_ies (optional) | `--operation extract_ies` | `N` |
| Gate A signaling keywords | `hybrid_tree.branches[*].mandatory_messages` | (state file slice) | `N` |
| Failure mode names | code_search.py expand_failure_modes | `--operation expand_failure_modes` | `N` |
| Gate B trace keywords | (same call, macro literals) | (same call) | `N` |
| Gate B trace tags | (same call, macro tags) | (same call) | `N` |

Fallback chain for Gate B keyword misses (stop at first hit, NEVER invent):
1. `failure_mode.log_keywords` from code_search.py
2. `failure_mode.function_signature` (as `message LIKE` pattern)
3. `extract_ies` IE names
4. STOP — mark Gate B unclear

### Iteration N — Phase 3.4 (3gpp-fta-cross-reference)

| Keyword class | Origin | Tool | Audit `iteration_id` |
|---|---|---|---|
| Commanded-value IE names | spec_query.py find_commanded_values | `--operation find_commanded_values` | `N` |
| Commanded value (signaling) | log_query.py phase3_cross_ref signaling | `--return-ie-values true` | `N` |
| Actual-value log keywords | code_search.py find_implementation | `--operation find_implementation` | `N` |
| Actual value (trace) | log_query.py phase3_cross_ref trace | `--return-ie-values true` | `N` |
| Implementation file location | code_search.py find_implementation output | (same call) | `N` |

### Iteration N — Phase 3.5 (3gpp-fta-root-cause)

| Field | Origin | Audit `iteration_id` |
|---|---|---|
| Root cause class | Skill logic over iteration's `cross_reference_findings` | `N` (synthesis only) |
| Spec violation reference | Already-populated state file fields | `N` |
| Implementation location | Already-populated state file fields | `N` |
| Description | Synthesized from values populated above | `N` |
| Evidence chain | Concatenation of prior phases' summaries (within iteration) | `N` |

NO new keywords introduced. NO tool calls in this skill.

### Checkpoint B (3gpp-fta-iteration-controller)

| Field | Origin | Audit `iteration_id` |
|---|---|---|
| Termination signals | Logic over iteration's state | `N` (synthesis only) |
| Recommendation | Logic over root_cause_class + signals | `N` |
| Causal chain (when accept_terminal) | Concatenation across iterations 1..N | `N..1` (multi-iteration) |

NO new keywords. NO tool calls.

### Inter-Iteration Boundary

When iteration N's user_decision is `dig_deeper` and the controller starts
iteration N+1, the new iteration's `input_top_event` is derived from a
base event confirmed in iteration N. The base event name was originally
produced by `code_search.py expand_failure_modes` (or fallback) in
iteration N.

Iteration N+1 SHOULD re-derive this top event from the state file slice
(no new tool calls needed). The audit entry for the new iteration's first
spec call records the input top event with `derived_from_iteration_<N>`.

**Cross-iteration keyword reuse rule:** A keyword produced in iteration N
is valid for use as INPUT to iteration N+1's tools (e.g. as the new top
event, or as a hint to `bind_module`), but ALL further queries within
iteration N+1 must re-derive their keywords from iteration N+1's own tool
invocations. The audit catches violations by checking `iteration_id` on
each keyword usage.

### Phase 4 (3gpp-rca-orchestrator finalize)

- Every keyword in every table cell of the final report traces to a
  `keyword_provenance_audit` entry
- Skill VALIDATES the audit per-iteration before writing the report
- Any keyword without provenance → v6 policy violation → halt with error

---

## Anti-Hallucination Hard Stops (preserved)

| Condition | Skill response |
|---|---|
| spec_query.py returns empty `phases` (Phase 3.1) | Fall back to `generate_hypotheses` and record `fallback_used` in state |
| code_search.py bind_module returns empty `modules` | Mark branch as `unbindable`; rely on spec-only evaluation |
| code_search.py expand_failure_modes returns empty | Fall back to spec_query.py expand_sub_causes |
| spec_query.py find_commanded_values returns empty | Record "no commanded values"; root_cause_class becomes ABSENCE or TIMER_EXPIRY |
| log_query.py cross-ref returns no ie_value_extractions | Mark as open item; do NOT fabricate value |
| Any tool returns exit code 2 (tool unavailable) | Halt iteration; write error to state file |

v6 NEW iteration-level halt:
| Condition | Skill response |
|---|---|
| current_iteration_id > meta.iteration_budget | Iteration controller forces `accept_terminal` or `abort` recommendation; user can still override but with explicit confirmation |

NEVER bypass these halts by inventing values.

---

## Keyword Chain Diagram (v6)

```
engineer description
       │
       ▼ 3gpp-scoping (audit: iteration_id=null)
scope_filter (with spec_lookup from spec_query.py lightweight_procedure)
       │
       ▼ 3gpp-event-timeline (audit: iteration_id=null)
top_event_candidates (signaling rows + expected_flow from spec_query.py)
       │
       ▼ Checkpoint A — user picks top_event
top_event (selected by user)
       │
       ▼ ITERATION 1 begins (audit: iteration_id=1)
3gpp-fta-build-tree
  hybrid_tree skeleton (spec_query.py skeleton OR fallback)
  hybrid_tree.branches[*].modules (code_search.py bind_module)
       │
       ▼ 3gpp-fta-evaluate-branches (audit: iteration_id=1)
Gate A: log_query.py phase3_gate_a → pivot-pruning decisions
Gate B: code_search.py expand_failure_modes → log_query.py phase3_gate_b
        → base_events
       │
       ▼ 3gpp-fta-cross-reference (audit: iteration_id=1)
spec_query.py find_commanded_values → commanded IE names
log_query.py cross_ref signaling → commanded value
code_search.py find_implementation → actual-value log keywords
log_query.py cross_ref trace → actual value
        → discrepancy detection
       │
       ▼ 3gpp-fta-root-cause (audit: iteration_id=1, no new tool calls)
iteration_root_cause
       │
       ▼ Checkpoint B — user picks dig_deeper / accept / abort
       │
       │  dig_deeper → ITERATION 2 begins (audit: iteration_id=2)
       │  (input_top_event derived from base event in iteration 1)
       │  ... loops back to 3gpp-fta-build-tree ...
       │
       │  accept_terminal → phase3_root_cause_chain synthesis (multi-iter)
       │
       ▼ 3gpp-rca-orchestrator finalize (audit: validate all iterations)
report assembly + keyword_provenance_audit validation
       │
       ▼ TERMINATE — NO fix generation
```

---

## Validation Checklist (run by orchestrator at Phase 4)

Before writing the final report, the orchestrator verifies:

- [ ] For every keyword in `phase3_root_cause_chain.causal_chain[*]`,
  find matching entry in `keyword_provenance_audit` with the correct
  `iteration_id`
- [ ] No keyword is used in iteration N's query if its provenance is
  from iteration M where M ≠ N (exception: top event derivation across
  the boundary, which is explicitly allowed)
- [ ] All `fta_iterations[i].pruned_branches` have explicit `evidence`
  from `gate_a_result`
- [ ] All `fta_iterations[i].base_events` have both `signaling` and
  `trace` evidence (or a documented reason for one being empty)
- [ ] If any iteration's `root_cause_class == "VALUE_DISCREPANCY"`,
  the corresponding entry in `cross_reference_findings` has matching
  `commanded_value` and `actual_value`
- [ ] `phase4_rca_report.termination_reason` is set
- [ ] NO fix recommendations, code patches, or remediation steps
  anywhere in the report or state file
- [ ] Audit entry count matches sum of (tool calls × output keywords)
  across all iterations

If any check fails → halt and write the failure reason to
`phase4_rca_report.termination_reason`.

---

## `ENGINEER_PROVIDED` Carve-Out (v6 NEW — seed_and_run mode only)

When a run is seeded via `3gpp-fta-seed-init` (`meta.mode ==
"seed_and_run"`), `fta_iterations[1].input_top_event` has `source:
"ENGINEER_PROVIDED"` instead of being derived from
`phase2_ecf.top_event`.

**The carve-out applies to exactly one keyword: the `event` string in
that one field.** It is exempt from the trace-to-tool-call requirement
because it was asserted directly by the engineer, not derived by any
pipeline phase.

**The carve-out does NOT extend to anything else:**
- Every keyword `3gpp-fta-build-tree`, `3gpp-fta-evaluate-branches`, and
  `3gpp-fta-cross-reference` derive FROM that top event (spec skeleton
  matches, code module bindings, Gate A/B log keywords, commanded/actual
  values) MUST still trace to a tool invocation in the same iteration, per
  the rules above. The top event being engineer-provided does not make its
  downstream consequences engineer-provided.
- Iteration 2 and beyond are entirely unaffected — if the engineer's
  seeded iteration 1 leads to `dig_deeper`, iteration 2's top event is
  derived from iteration 1's `base_events[]` exactly as in a normal run,
  and is audited exactly as in a normal run (no `ENGINEER_PROVIDED` tag).
- The Phase 4 validation checklist's rule "every keyword in the causal
  chain traces to `keyword_provenance_audit`" is unchanged EXCEPT that a
  lookup for the iteration-1 top event keyword may instead match an
  `engineer_inputs[]` entry (`input_id`, `assertion`, `at`) in place of a
  `keyword_provenance_audit` entry, and only for that one field.
