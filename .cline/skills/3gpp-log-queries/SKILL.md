---
name: 3gpp-log-queries
description: >
  Shared utility skill for querying UE DuckDB log tables via log_query.py.
  Enforces strict table isolation at the script entry — Phase 1 and Phase 2
  may ONLY query UE_3gpp_signaling_log; UE_Trace_log may ONLY be touched in
  FTA Gate B (phase3_gate_b) or cross-reference (phase3_cross_ref). The script
  refuses mismatched phase_tag + table combinations. Supports return_ie_values
  flag for Phase 3.4 cross-reference value extraction. Use whenever a phase
  skill needs DB data — never call log_query.py directly. Triggers: "query
  UE_3gpp_signaling_log", "query UE_Trace_log", "run signaling sanity check",
  "run Gate A or Gate B query", "extract IE values for cross-reference".
---

# 3GPP Log Queries Shared Skill

## Role

Single point of entry for all DuckDB queries against UE_3gpp_signaling_log
and UE_Trace_log. Other skills delegate to this one.

## Critical: table isolation enforcement

The Python script `log_query.py` itself validates the `--phase-tag` + `--table`
combination at entry and refuses mismatches with exit code 3.

| `--phase-tag` | Allowed `--table` | Caller |
|---|---|---|
| `phase1` | UE_3gpp_signaling_log ONLY | `3gpp-scoping` |
| `phase2` | UE_3gpp_signaling_log ONLY | `3gpp-event-timeline` |
| `phase3_gate_a` | UE_3gpp_signaling_log ONLY | `3gpp-fta-evaluate-branches` (Gate A) |
| `phase3_gate_b` | UE_Trace_log ONLY | `3gpp-fta-evaluate-branches` (Gate B) |
| `phase3_cross_ref` | EITHER (caller specifies) | `3gpp-fta-cross-reference` |

Any other combination → script exits with:
```json
{"error": "Table isolation violation",
 "phase_tag": "phase1", "table": "UE_Trace_log",
 "policy": "v5 §table-isolation"}
```

The skill MUST verify exit code 0 before passing data back. If exit code 3,
report the policy violation to the caller — do not retry with a different table.

---

## Common command template

```
<execute_command>
python3 ${TOOL_DIR}/log_query.py \
  --phase-tag <tag> \
  --table <table> \
  --keywords "<kw1>" "<kw2>" ... \
  [--ie-names "<ie1>" "<ie2>" ...] \
  [--log-tags "<tag1>" "<tag2>" ...] \
  [--time-window-start-ms <int>] \
  [--time-window-end-ms <int>] \
  [--layers "<l1>" "<l2>" ...] \
  [--hypothesis-id "<id>"] \
  [--return-ie-values true] \
  --state-file "<state_path>" \
  --max-tokens 1500
</execute_command>
```

## Per-phase usage

### phase1 (sanity check)
```
--phase-tag phase1
--table UE_3gpp_signaling_log
--keywords "<scope_filter.spec_lookup.initiating_message>"
--time-window-start-ms 0 --time-window-end-ms 10000
```

### phase2 (timeline retrieval)
```
--phase-tag phase2
--table UE_3gpp_signaling_log
--keywords <all expected_flow[].message>
--time-window from scope_filter.time_window
--layers from scope_filter.layers
```

### phase3_gate_a (FTA Gate A)
```
--phase-tag phase3_gate_a
--table UE_3gpp_signaling_log
--keywords <branch.mandatory_messages>
--ie-names <from spec extract_ies output if available>
--hypothesis-id <branch.id>
```

### phase3_gate_b (FTA Gate B)
```
--phase-tag phase3_gate_b
--table UE_Trace_log
--keywords <failure_mode.log_keywords>  (literal log macro strings)
--log-tags <failure_mode.log_tags>
--hypothesis-id <failure_mode.id>
```

### phase3_cross_ref (cross-reference)
```
--phase-tag phase3_cross_ref
--table <UE_3gpp_signaling_log OR UE_Trace_log>
--keywords <containing message OR macro literal>
--ie-names <IE name from spec find_commanded_values>
--return-ie-values true
--hypothesis-id <base_event.id>
```

---

## Expected stdout shapes

### Standard (all phases)
```json
{
  "queried_table": "...",
  "tool_used": "query_UE_3gpp_signaling_log_only" | "query_UE_trace_log",
  "keywords_used": [...],
  "keywords_with_hits": [...],
  "keywords_missed": [...],
  "matched_event_count": <int>,
  "evidence_summary": "...",
  "key_events": [
    {"timestamp": "...", "layer": "...", "direction": "...",
     "message": "...", "kpis": {...}, "raw_excerpt": "..."}
  ]
}
```

### Cross-reference (with `--return-ie-values true`)
```json
{
  ... standard fields ...
  "ie_value_extractions": [
    {"ie_name": "preambleReceivedTargetPower",
     "value": "-110 dBm",
     "source_msg": "RRCReconfiguration",
     "timestamp": "14:02:11.00"}
  ]
}
```

For trace cross-ref:
```json
{
  "ie_value_extractions": [
    {"ie_name": "Tx Power",
     "value": "-10 dBm",
     "source_msg": "DSP_CALC trace",
     "timestamp": "14:02:11.50",
     "annotations": ["Underflow limit"]}
  ]
}
```

---

## State file writes per phase

| phase_tag | Section written |
|---|---|
| `phase1` | `phase1_scope_filter.signaling_sanity_check` |
| `phase2` | `phase2_ecf.observable_symptoms.events[]` |
| `phase3_gate_a` | `phase3_hybrid_tree.branches[<id>].gate_a_result` |
| `phase3_gate_b` | `phase3_hybrid_tree.branches[*].children[<id>].gate_b_result` |
| `phase3_cross_ref` (signaling) | `phase3_cross_reference_findings[<id>].commanded_value` |
| `phase3_cross_ref` (trace) | `phase3_cross_reference_findings[<id>].actual_value` |

---

## Error handling

| Exit code | Meaning | Action |
|---|---|---|
| 0 | Success — keywords found OR empty result | Return stdout JSON |
| 1 | Invalid args — bug in this skill | Halt with error |
| 2 | DB unavailable / table not found | Halt pipeline; report |
| 3 | Table isolation violation | Report and halt — do NOT retry |
| 4 | Empty result | Return empty JSON; caller decides |

### Keyword discipline (enforced by script)

The script REFUSES queries with empty `--keywords`. It also auto-appends each
input keyword to `keyword_provenance_audit` with a reference to which prior
tool invocation produced it — so the orchestrator can audit the full chain
at Phase 4 finalize.

If the skill cannot produce keywords (e.g. spec_query returned empty), the
caller must fall back per the per-phase rules (see
`_shared/keyword-provenance-rules.md`) — never invent keywords just to make
this skill succeed.

See `references/log-operations.md` for per-phase parameter details and
example SQL queries.
