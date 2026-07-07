# RCA State File Schema — v6

The state file is the single source of truth across the entire RCA pipeline.
v6 introduces **per-level iteration** and **user gate decisions**, so the
schema is more complex than v5.

## File Location

```
/tmp/rca_state_<UTC_timestamp>.json
```

On Windows: `%TEMP%\rca_state_<UTC_timestamp>.json`.
Path is stored in `.rca/current_state_path.txt` for downstream skills.

## Key Structural Changes from v5

| v5 | v6 |
|---|---|
| `phase3_hybrid_tree` (single tree) | `fta_iterations[]` (one tree per iteration) |
| `phase3_pruned_branches`, `phase3_base_events`, etc. | Inside each `fta_iterations[i].*` |
| `phase3_cross_reference_findings` (single set) | Inside each iteration |
| `phase3_root_cause` (single result) | `fta_iterations[i].iteration_root_cause` + `phase3_root_cause_chain` synthesis |
| `meta.current_phase` (implicit) | **Explicit** `current_phase` state machine |
| No user gates | `user_decisions[]` audit log |

## Phase State Machine

The orchestrator and workflow track progress through `meta.current_phase`:

```
phase0                          → init
phase1                          → scoping running
phase2_running                  → event timeline running
phase2_pending_confirmation     → HALT — Checkpoint A
phase2_confirmed                → ready to start iteration 1
iteration_N_running             → FTA iteration N in progress
iteration_N_pending_decision    → HALT — Checkpoint B for iteration N
phase4_finalizing               → orchestrator finalize running
complete                        → terminal
```

Skills always write the next state value before halting/returning so the
workflow knows what step to take next on the next `/rca` invocation.

---

## Full v6 Schema

```json
{
  "meta": {
    "pipeline_version": "v6",
    "current_phase": "phase0",
    "current_iteration_id": 0,
    "iteration_budget": 5,
    "started_at": "<ISO 8601>",
    "finished_at": null,
    "engineer_input": "<verbatim engineer description>",
    "db_tables": ["UE_3gpp_signaling_log", "UE_Trace_log"],
    "duckdb_path": "<path>",
    "tool_dir": "<path to 3gpp-tools/ Python scripts>"
  },

  "phase1_scope_filter": {
    /* unchanged from v5 */
    "completed_at": "<ISO>",
    "procedure": "...",
    "rat": "...",
    "bands": [...],
    "layers": [...],
    "layers_excluded": [...],
    "condition": "...",
    "time_window": {"start_ms": 0, "end_ms": 3000},
    "discriminator": "...",
    "reproducibility": "...",
    "ambiguities": [],
    "spec_lookup": {...},
    "signaling_sanity_check": {...}
  },

  "phase2_ecf": {
    "completed_at": "<ISO>",

    /* v5 fields unchanged */
    "top_event": {
      "procedure": "...",
      "layer": "...",
      "event": "<chosen top event after Checkpoint A>",
      "timestamp": "...",
      "cause_code": null,
      "description": "..."
    },
    "observable_symptoms": {...},

    /* v6 NEW */
    "top_event_candidates": [
      {
        "rank": 1,
        "is_primary": true,
        "event": "5G_HO_Execution_Failure (no target cell sync)",
        "timestamp": "14:02:12.50",
        "layer": "RRC",
        "evidence": "Last signaling: RRCReconfiguration with no following RAR",
        "confidence": "HIGH",
        "rejection_reason": null
      },
      {
        "rank": 2,
        "is_primary": false,
        "event": "RRC Connection Reestablishment Reject",
        "timestamp": "14:02:13.00",
        "layer": "RRC",
        "evidence": "Reestab attempt rejected after HO failure",
        "confidence": "LOW",
        "rejection_reason": "Consequence of primary; not a distinct top event"
      }
    ],

    /* v6 NEW — populated by 3gpp-top-event-confirmation after Checkpoint A */
    "user_confirmation": {
      "confirmed_at": "<ISO>",
      "selected_rank": 1,
      "overrode_recommendation": false,
      "rationale": ""
    }
  },

  /* v6 NEW — audit log of all user gate decisions */
  "user_decisions": [
    {
      "checkpoint": "A",
      "decided_at": "<ISO>",
      "action": "confirm_primary",
      "selected_rank": 1,
      "agent_recommendation": "confirm rank 1",
      "overrode_recommendation": false,
      "rationale": ""
    },
    {
      "checkpoint": "B-iteration-1",
      "decided_at": "<ISO>",
      "action": "dig_deeper",
      "selected_base_event_id": "P2.2",
      "selected_base_event_name": "Preamble_Power_Error",
      "agent_recommendation": "dig_deeper P2.2",
      "overrode_recommendation": false,
      "rationale": ""
    }
  ],

  /* v6 NEW — replaces flat phase3_* sections */
  "fta_iterations": [
    {
      "iteration_id": 1,
      "parent_iteration_id": null,
      "parent_base_event_id": null,
      "started_at": "<ISO>",
      "completed_at": "<ISO>",

      "input_top_event": {
        "event": "5G_HO_Execution_Failure",
        "source": "phase2_ecf.top_event",
        "spec_anchored": true
      },

      "hybrid_tree": {
        /* same shape as v5 phase3_hybrid_tree */
        "constructed_at": "<ISO>",
        "spec_skeleton_returned_empty": false,
        "fallback_used": null,
        "gate_at_top": "OR",
        "spec_skeleton_source": {...},
        "branches": [
          {
            "id": "P1",
            "name": "RRC_Signaling_Phase",
            "spec_ref": "TS 38.331 §5.5.1",
            "mandatory_messages": [...],
            "modules": [...],
            "gate_a_result": {...},
            "status": "pruned_normal",
            "children": []
          },
          {
            "id": "P2",
            "name": "Target_Cell_Sync_Phase",
            ...
            "status": "failure_here",
            "children": [
              {"id": "P2.1", "name": "RACH_Timeout", ...},
              {"id": "P2.2", "name": "Preamble_Power_Error", ...}
            ]
          }
        ]
      },

      "pruned_branches": [...],
      "base_events": [...],
      "rejected": [...],
      "open_items": [...],
      "cross_reference_findings": [...],

      "iteration_root_cause": {
        "deduced_at": "<ISO>",
        "iteration_id": 1,
        "input_top_event": "5G_HO_Execution_Failure",
        "failing_phase": "Target_Cell_Sync_Phase",
        "pruned_phases": ["RRC_Signaling_Phase"],
        "base_event_chain": [...],
        "root_cause_class": "VALUE_DISCREPANCY",
        "description": "...",
        "commanded_value": "...",
        "actual_value": "...",
        "implementation_location": "...",
        "spec_violation": "...",
        "evidence_chain": [...]
      },

      /* v6 NEW — what the iteration controller recommends */
      "agent_recommendation": {
        "computed_at": "<ISO>",
        "action": "dig_deeper | accept_terminal | abort",
        "recommended_base_event_id": "P2.2",
        "rationale": "P2.2 caused P2.1 per cross-reference; dig deeper to find code-level mechanism",
        "termination_signals_detected": []
      },

      /* v6 NEW — user's decision at Checkpoint B for this iteration */
      "user_decision": {
        "decided_at": "<ISO>",
        "action": "dig_deeper",
        "selected_base_event_id": "P2.2",
        "selected_base_event_name": "Preamble_Power_Error",
        "overrode_recommendation": false,
        "override_confirmation_received": false,
        "rationale": ""
      }
    },

    /* iteration 2 — drilling into P2.2 (Preamble_Power_Error) */
    {
      "iteration_id": 2,
      "parent_iteration_id": 1,
      "parent_base_event_id": "P2.2",
      "started_at": "<ISO>",
      "completed_at": "<ISO>",

      "input_top_event": {
        "event": "Preamble_Power_Error",
        "source": "fta_iterations[1].base_events[P2.2]",
        "spec_anchored": false
      },

      "hybrid_tree": {
        "spec_skeleton_returned_empty": true,  /* common at depth */
        "fallback_used": "generate_hypotheses + code-only",
        ...
      },
      ...

      "iteration_root_cause": {
        "iteration_id": 2,
        "root_cause_class": "ABSENCE",
        "description": "Missing bounds check in dsp_calc_preamble_tx_power...",
        ...
      },

      "agent_recommendation": {
        "action": "accept_terminal",
        "rationale": "Reached code-implementation primitive...",
        "termination_signals_detected": [
          "single_branch_tree",
          "find_implementation_returned_same_file_as_prior_iteration",
          "no_commanded_value_ies_relevant"
        ]
      },

      "user_decision": {
        "action": "accept_terminal",
        "overrode_recommendation": false,
        ...
      }
    }
  ],

  /* v6 NEW — synthesized from all iterations after user accepts terminal */
  "phase3_root_cause_chain": {
    "synthesized_at": "<ISO>",
    "iterations_traversed": [1, 2],
    "terminal_iteration_id": 2,
    "termination_reason": "User accepted terminal at iteration 2",
    "causal_chain": [
      {
        "iteration": 1,
        "top_event": "5G_HO_Execution_Failure",
        "selected_cause_id": "P2.2",
        "selected_cause_name": "Preamble_Power_Error",
        "relationship": "P2.2 caused P2.1 (RACH_Timeout) which caused top event",
        "iteration_root_cause_class": "VALUE_DISCREPANCY"
      },
      {
        "iteration": 2,
        "top_event": "Preamble_Power_Error",
        "selected_cause_id": "Q3",
        "selected_cause_name": "Missing_Bounds_Check",
        "relationship": "terminal",
        "iteration_root_cause_class": "ABSENCE"
      }
    ],
    "final_root_cause": {
      /* copy of terminal iteration's iteration_root_cause */
    },
    "high_disagreement_run": false,    /* true if user overrode recs ≥ 50% of decisions */
    "user_override_count": 0
  },

  "phase4_rca_report": {
    "finalized_at": "<ISO>",
    "iteration_count": 2,
    "report_path": "<path to RCA report markdown file>",
    "termination_reason": "User accepted terminal at iteration 2"
  },

  "keyword_provenance_audit": [
    /* iteration-scoped entries */
    {
      "keyword": "RRCReconfiguration",
      "type": "message_name",
      "iteration_id": 1,
      "used_by": "Phase 3 Gate A P1",
      "source": "3gpp-spec-retrieval skeleton operation",
      "verified": true
    },
    {
      "keyword": "dsp_calc_preamble_tx_power",
      "type": "function_name",
      "iteration_id": 2,
      "used_by": "Iteration 2 module binding",
      "source": "3gpp-code-retrieval find_implementation",
      "verified": true
    }
  ]
}
```

---

## Per-Section Write Owners (v6)

| Section | Written By |
|---|---|
| `meta` | `3gpp-rca-orchestrator` (Phase 0); `meta.current_phase` updated by every skill on entry/exit |
| `meta.current_phase` | Each skill writes the next-phase value on completion |
| `phase1_scope_filter` | `3gpp-scoping` (unchanged from v5) |
| `phase2_ecf.top_event` | Set by `3gpp-top-event-confirmation` after user chooses |
| `phase2_ecf.observable_symptoms` | `3gpp-event-timeline` |
| `phase2_ecf.top_event_candidates` | **`3gpp-event-timeline`** (v6 NEW — produces ranked list) |
| `phase2_ecf.user_confirmation` | **`3gpp-top-event-confirmation`** (v6 NEW) |
| `user_decisions[]` | Appended by `3gpp-top-event-confirmation` (A) and `3gpp-fta-iteration-controller` (B-N) |
| `fta_iterations[i].input_top_event` | `3gpp-rca-orchestrator` (for iter 1) or `3gpp-fta-iteration-controller` (for iter ≥2) when transitioning to next iteration |
| `fta_iterations[i].hybrid_tree` + `pruned_branches` + `base_events` etc. | `3gpp-fta-build-tree`, `3gpp-fta-evaluate-branches`, `3gpp-fta-cross-reference` (all iteration-aware) |
| `fta_iterations[i].iteration_root_cause` | `3gpp-fta-root-cause` (iteration-aware) |
| `fta_iterations[i].agent_recommendation` | **`3gpp-fta-iteration-controller`** (v6 NEW) |
| `fta_iterations[i].user_decision` | **`3gpp-fta-iteration-controller`** after user response |
| `phase3_root_cause_chain` | **`3gpp-fta-iteration-controller`** when user picks `accept_terminal` |
| `phase4_rca_report` | `3gpp-rca-orchestrator` (Phase 4 finalize) |
| `keyword_provenance_audit` | All retrieval skills (iteration-scoped) |

---

## Slice-Read Discipline (preserved from v5)

Skills MUST slice-read only the sections they need. The orchestrator never
loads the full state file except at Phase 4 finalize. Specifically:

- Phase 1 reads `meta.engineer_input` only
- Phase 2 reads `phase1_scope_filter` only
- Each FTA phase skill reads its own iteration's slice plus prior iteration roots if needed
- `phase3_root_cause_chain` synthesis at terminal needs all iteration root causes —
  but ONLY the `iteration_root_cause` blocks, not the full trees

---

## Concurrency

v6 is single-agent (one Cline task at a time, with user pauses between
phases). No concurrent-write protection needed. State file writes are atomic
(`.tmp` → `mv`).

## Migration from v5

v5 → v6 is NOT backwards compatible. A v5 state file cannot be resumed in
v6 directly. To re-run a v5 case on v6, start a new pipeline. (An optional
migration script could wrap a v5 `phase3_*` set into `fta_iterations[1]`
but this is not implemented in the baseline v6.)
