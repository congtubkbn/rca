# Final RCA Report Template — v6

> **v6 boundary:** This report contains the verified root cause and the
> causal chain of FTA iterations that led to it. Fix recommendations,
> code changes, and remediation steps are intentionally out of scope.
> Fix design is a separate engineering activity.

The orchestrator (`3gpp-rca-orchestrator`) writes this report to the path
recorded in `phase4_rca_report.report_path` after Phase 4 termination.

---

# 3GPP UE Root Cause Analysis Report

**Pipeline version:** v6
**State file:** `<path>`
**Started:** `<ISO>`  **Finished:** `<ISO>`
**Iterations traversed:** `<N>`
**Termination reason:** `<from phase4_rca_report.termination_reason>`

---

## 1. Problem Scope (Phase 1)

**Procedure:** [scope_filter.procedure]
**RAT / Band:** [scope_filter.rat] / [scope_filter.bands]
**Failure condition:** [scope_filter.condition]
**Reproducibility:** [scope_filter.reproducibility]
**Discriminator:** [scope_filter.discriminator]

### Spec metadata (dynamic retrieval via spec_query.py)
- Primary layers: [scope_filter.spec_lookup.primary_layers]
- Key timers: [scope_filter.spec_lookup.key_timers]
- Initiating message: [scope_filter.spec_lookup.initiating_message]
- Spec refs: [scope_filter.spec_lookup.spec_refs]

| Dimension | IS | IS NOT |
|---|---|---|
| WHAT | | |
| WHERE | | |
| WHEN | | |
| EXTENT | | |

---

## 2. Top Event (Phase 2)

### Candidates considered (v6 NEW)

| Rank | Event | Confidence | Selected? | Rejection reason |
|---|---|---|---|---|
| 1 | [top_event_candidates[0].event] | [confidence] | [✓ or ] | [rejection_reason or —] |
| 2 | [...] | [...] | [...] | [...] |
| 3 | [...] | [...] | [...] | [...] |

### Selected Top Event

**Top Event:** [phase2_ecf.top_event.event]
**Layer:** [phase2_ecf.top_event.layer]
**Timestamp:** [phase2_ecf.top_event.timestamp]
**Cause code (if any):** [phase2_ecf.top_event.cause_code]
**Log coverage (signaling table):** [observable_symptoms.log_coverage]
**User override at Checkpoint A:** [user_confirmation.overrode_recommendation]

### Signaling timeline observed
```
[from observable_symptoms.events]
```

### Missing events (spec-predicted, absent from signaling)
| Expected Message | Expected After | Spec Ref |
|---|---|---|
| | | |

---

## 3. FTA Iterations (Phase 3 — v6 per-level)

### 3.0 Iteration Overview

| Iter | Input Top Event | Spec-anchored? | Root Cause Class | User Decision |
|---|---|---|---|---|
| 1 | [iter1.input_top_event.event] | [iter1.input_top_event.spec_anchored] | [iter1.iteration_root_cause.root_cause_class] | [iter1.user_decision.action] |
| 2 | [iter2.input_top_event.event] | [iter2.input_top_event.spec_anchored] | [iter2.iteration_root_cause.root_cause_class] | [iter2.user_decision.action] |
| ... | | | | |

User override count: [user_override_count] of [count of checkpoint decisions]
High-disagreement run: [high_disagreement_run]

---

### 3.N Iteration <N> Detail (one section per iteration)

**Input Top Event:** [iteration.input_top_event.event]
**Spec-anchored:** [iteration.input_top_event.spec_anchored]
**Fallback used:** [iteration.hybrid_tree.fallback_used or "none"]

#### Hybrid Fault Tree

```
[ASCII tree from iteration.hybrid_tree]

Legend:
  ❌  Input Top Event   💡  Hypothesis / Phase
  ✅  Confirmed normal (signaling matched cleanly)
  🎯  Failure location (Gate A confirmed failure here)
  ✂️  PRUNED (pivot-pruning — confirmed normal)
  ⚠️  Base Event (Gate B confirmed)
  ❌  REJECTED (Gate B absent)   ❓  OPEN
  🔍  Cross-reference performed   📍  Implementation location
```

#### Pruned branches (pivot-pruning record)

| ID | Phase Name | Pruned Reason | Evidence |
|---|---|---|---|
| | | normal_passage | |

#### Verified Base Events (Gate B confirmed)

| Branch | Failure Mode | Layer | Spec Ref | Confidence | Gate B Evidence |
|---|---|---|---|---|---|
| | | | | | |

#### Cross-Reference Findings (Phase 3.4)

For each confirmed base event the orchestrator compared commanded values
(signaling) against actual values (trace). Discrepancies = value-discrepancy
root cause class.

##### Cross-Reference — [base_event_id]

| Field | Value |
|---|---|
| Commanded IE | [...commanded_ie] |
| Commanded value | [...commanded_value.value] |
| Commanded source | [signaling: ...] |
| Actual value | [...actual_value.value] |
| Actual source | [trace: ...] |
| Delta | [...delta] |
| Root cause class | **[...root_cause_class]** |
| Implementation location | [...implementation_location] |
| Interpretation | [...interpretation] |

If no commanded-value IEs found → "No value-carrying IE relevant; class
falls to ABSENCE or TIMER_EXPIRY."

#### Iteration Root Cause

**Root cause class:** [iteration.iteration_root_cause.root_cause_class]

**Root cause statement (iteration-local):**
[iteration.iteration_root_cause.description]

**Specifics:**
- Failing phase: [iteration.iteration_root_cause.failing_phase]
- Pruned phases (normal): [iteration.iteration_root_cause.pruned_phases]
- Base event chain: [iteration.iteration_root_cause.base_event_chain]
- Commanded value: [iteration.iteration_root_cause.commanded_value]
- Actual value: [iteration.iteration_root_cause.actual_value]
- Implementation location: [iteration.iteration_root_cause.implementation_location]
- Spec violation: [iteration.iteration_root_cause.spec_violation]

**Evidence chain (within iteration):**
1. [iteration.iteration_root_cause.evidence_chain[0]]
2. [iteration.iteration_root_cause.evidence_chain[1]]
3. ...

#### Agent Recommendation vs User Decision

| Field | Value |
|---|---|
| Agent recommended | [iteration.agent_recommendation.action] |
| Agent rationale | [iteration.agent_recommendation.rationale] |
| Termination signals detected | [iteration.agent_recommendation.termination_signals_detected] |
| User decided | [iteration.user_decision.action] |
| User selected base event | [iteration.user_decision.selected_base_event_name] |
| User overrode agent? | [iteration.user_decision.overrode_recommendation] |
| Override confirmation received | [iteration.user_decision.override_confirmation_received] |

#### Rejected Hypotheses (this iteration)

| Branch | Hypothesis | Gate A | Gate B | Rejection Evidence |
|---|---|---|---|---|
| | | | | |

#### Open Items (this iteration)

| Branch | Hypothesis | Reason both gates unclear | Suggested Capture |
|---|---|---|---|
| | | | Enable [layer/tag] trace, re-capture |

---

## 4. Causal Chain (v6 NEW — synthesized across iterations)

The pipeline progressed through [N] iterations of FTA. Each iteration
identified a root cause that became the top event of the next iteration,
forming a causal chain from the original Top Event down to the terminal
root cause.

```
ITERATION 1:  Top Event = [iter1.input_top_event.event]
              → cause: [iter1.iteration_root_cause.root_cause_class] at
                [iter1.user_decision.selected_base_event_id]
                ([iter1.user_decision.selected_base_event_name])
              → user chose: dig deeper

ITERATION 2:  Top Event = [iter2.input_top_event.event]
              → cause: [iter2.iteration_root_cause.root_cause_class]
              → user chose: [iter2.user_decision.action]

... (one block per iteration)

TERMINAL (iteration [N]):
              → [final_root_cause summary]

FINAL CAUSAL CHAIN:
  [iter1 top event] ← [iter1 cause] ← [iter2 cause] ← ... ← [terminal cause]
```

### Final Root Cause

**Root cause class:** [phase3_root_cause_chain.final_root_cause.root_cause_class]
**Implementation location:** [phase3_root_cause_chain.final_root_cause.implementation_location]
**Spec violation:** [phase3_root_cause_chain.final_root_cause.spec_violation]

**Statement:**
[phase3_root_cause_chain.final_root_cause.description]

**Evidence chain (full, across iterations):**
1. (Iter 1 scope) [phase1_scope_filter.discriminator]
2. (Iter 1 Phase 2) Missing events: [observable_symptoms.missing_events]
3. (Iter 1 Phase 3.2) Pruned: [iter1.pruned_branches[*].evidence]
4. (Iter 1 Phase 3.3) Base event evidence: [iter1.base_events[*].evidence]
5. (Iter 1 Phase 3.4) Cross-ref: [iter1.cross_reference_findings[*]]
6. (Iter 2 Phase 3.1) Fallback hypothesis: [iter2.hybrid_tree...]
7. ... continues across iterations ...
N. (Iter [N] terminal) [final_root_cause.evidence_chain[-1]]

---

## 5. Keyword Provenance Audit (iteration-scoped)

Every keyword traces to a Python tool invocation in a specific iteration.

| Iter | Keyword | Type | Phase / Gate | Source Tool | Operation | Verified |
|---|---|---|---|---|---|---|
| null | RRCReconfiguration | message_name | Phase 2 | spec_query.py | lightweight_procedure | ✅ |
| 1 | RRCReconfiguration | message_name | Iter 1 Gate A P1 | spec_query.py | skeleton | ✅ |
| 1 | rrc_ho_handler.cpp | module_binding | Iter 1 P1 | code_search.py | bind_module | ✅ |
| 1 | preambleReceivedTargetPower | commanded_ie | Iter 1 cross-ref | spec_query.py | find_commanded_values | ✅ |
| 2 | dsp_calc_preamble_tx_power | function_name | Iter 2 P1 | code_search.py | find_implementation | ✅ |

**Audit rule:** Any keyword used but NOT in this table = v6 policy violation.
**Iteration boundary rule:** A keyword used in iteration N's query must have
provenance with `iteration_id = N` (or `null` for pre-FTA phases, with
explicit cross-iteration carry-over for top events).

---

## 6. User Decision Audit

| Checkpoint | Action | Selected | Agent recommended | Overrode? | Rationale |
|---|---|---|---|---|---|
| A | [user_decisions[0].action] | [...selected_rank] | [...agent_recommendation] | [...overrode_recommendation] | [...rationale] |
| B-1 | [user_decisions[1].action] | [...selected_base_event_name] | [...agent_recommendation] | [...] | [...] |
| B-2 | [...] | [...] | [...] | [...] | [...] |

User override count: [phase3_root_cause_chain.user_override_count]
High-disagreement run: [phase3_root_cause_chain.high_disagreement_run]

If `high_disagreement_run == true`: this run had significant user
disagreement with agent recommendations. Recommend manual review of the
causal chain and re-validation of the final root cause.

---

## 7. Pipeline Metadata

| Field | Value |
|---|---|
| Pipeline version | v6 |
| State file | [path] |
| Started / Finished | [meta.started_at] / [meta.finished_at] |
| Iterations traversed | [count of fta_iterations] |
| Iteration budget | [meta.iteration_budget] |
| User decisions | [count of user_decisions] |
| User overrides | [user_override_count] |
| Termination reason | [phase4_rca_report.termination_reason] |
| Final root cause class | [final_root_cause.root_cause_class] |

---

## 8. Termination Notice

This report ends here. Per v6 architecture, the pipeline does NOT produce:
- Fix recommendations
- Code patches or proposed code changes
- Configuration parameter values to adjust
- Test cases or verification procedures
- Engineering action items

Verified root cause (with full causal chain across iterations and
cross-reference evidence where applicable) is the complete deliverable.
Downstream engineering processes own fix design, implementation, and
validation.
