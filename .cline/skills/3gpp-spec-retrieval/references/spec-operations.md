# Spec Operations Reference

Detailed parameter and return shapes for each `spec_query.py` operation. The
shared `3gpp-spec-retrieval` skill consults this when assembling commands.

## Operation: skeleton

### Required args
| Arg | Type | Example |
|---|---|---|
| `--procedure` | string | `"Intra-AMF 5G Handover"` |
| `--rat` | string | `"5G NR"` |
| `--top-event` | string | `"5G_HO_Execution_Failure"` |
| `--state-file` | path | `/tmp/rca_state_<ts>.json` |

### Optional args
| Arg | Default | Effect |
|---|---|---|
| `--max-tokens` | 1500 | Token budget for stdout output |

### Stdout shape
```json
{
  "operation": "skeleton",
  "procedure": "...",
  "spec_refs": ["..."],
  "gate_at_top": "OR" | "AND",
  "phases": [
    {"id": "P1", "name": "...", "spec_ref": "...",
     "mandatory_messages": ["..."], "direction_per_message": ["DL", "UL"],
     "protocol_layer": "RRC"}
  ]
}
```

### Side effects
Writes to state file:
- `phase3_hybrid_tree.spec_skeleton_source`
- Initial `phase3_hybrid_tree.branches[]` (without modules or children)

---

## Operation: lightweight_procedure

### Required args
| Arg | Type | Example |
|---|---|---|
| `--procedure` | string | `"LTE Initial Attach"` |
| `--rat` | string | `"LTE"` |
| `--need` | enum | `is_is_not` or `ecf` |
| `--state-file` | path | ... |

### Stdout shape (need=is_is_not)
```json
{
  "operation": "lightweight_procedure",
  "need": "is_is_not",
  "procedure": "...",
  "primary_layers": ["..."],
  "key_timers": [{"timer": "T3410", "duration_default": "15s", "on_expiry": "..."}],
  "initiating_message": "ATTACH REQUEST",
  "spec_refs": ["TS 24.301 §5.5.1"]
}
```

### Stdout shape (need=ecf)
```json
{
  "operation": "lightweight_procedure",
  "need": "ecf",
  "procedure": "...",
  "expected_flow": [
    {"order": 1, "message": "RRCConnectionRequest", "direction": "UL", "layer": "RRC"}
  ],
  "key_timers": [...],
  "spec_refs": [...]
}
```

### Side effects
- `--need is_is_not` → `phase1_scope_filter.spec_lookup`
- `--need ecf` → `phase2_ecf.observable_symptoms.expected_flow_source`

---

## Operation: extract_ies

### Required args
`--message`, `--procedure`, `--spec-ref`, `--hypothesis-id`, `--state-file`.

### Stdout shape
```json
{
  "operation": "extract_ies",
  "for_hypothesis_id": "P1",
  "message_definitions": [
    {"message_name": "RRCReconfiguration",
     "mandatory_ies": ["rrc-TransactionIdentifier", "..."],
     "optional_ies": ["measConfig", "..."],
     "direction": "DL"}
  ]
}
```

### Side effects
- `phase3_evaluations[<id>].spec_ie_extraction`

---

## Operation: find_commanded_values

### Required args
| Arg | Type | Notes |
|---|---|---|
| `--base-event-name` | string | e.g. `"Preamble_Power_Error"` |
| `--base-event-layer` | string | e.g. `"PHY"` |
| `--upstream-messages` | string list | space-separated, e.g. `"RRCReconfiguration"` |
| `--state-file` | path | |

### Stdout shape
```json
{
  "operation": "find_commanded_values",
  "base_event_name": "...",
  "commanded_value_ies": [
    {"ie_name": "preambleReceivedTargetPower",
     "message": "RRCReconfiguration",
     "meaning": "...",
     "spec_ref": "TS 38.331 §6.3.2",
     "ue_action": "Calculate Tx power = target - pathloss; apply to PRACH",
     "range_unit": "dBm, integer, -202..-60"}
  ]
}
```

If empty: `{"commanded_value_ies": [], "note": "..."}` — valid result.

### Side effects
- `phase3_cross_reference_findings[<id>].commanded_ie_lookup`

---

## Operation: generate_hypotheses (FALLBACK ONLY)

Used only when skeleton returns empty `phases[]`.

### Required args
`--event`, `--procedure`, `--rat`, `--state-file`.

### Stdout shape (v3 hypothesis list)
```json
{
  "operation": "generate_hypotheses",
  "hypotheses": [
    {"id": "H1", "cause": "...", "spec_ref": "...", "gate": "OR",
     "ie_names": [...], "message_names": [...], "expected_layer": "..."}
  ]
}
```

### Side effects
- `phase3_hypotheses` (v3 path, fallback location)

---

## Operation: expand_sub_causes (FALLBACK ONLY)

Used only when code expand_failure_modes returns empty `failure_modes[]`.

### Required args
`--parent-cause`, `--parent-spec-ref`, `--procedure`, `--state-file`.

### Stdout shape
```json
{
  "operation": "expand_sub_causes",
  "parent_hypothesis_id": "...",
  "sub_causes_exist": true | false,
  "sub_causes": [
    {"cause": "...", "spec_ref": "...", "gate": "AND" | "OR",
     "ie_names": [...], "message_names": [...], "expected_layer": "..."}
  ]
}
```

If `sub_causes_exist: false` → branch is a leaf (declare base event without
further expansion).

---

## Anti-hallucination contract (enforced by spec_query.py itself)

- Every output IE name preserves spec hyphenated notation verbatim
- Every output message name preserves spec ALL CAPS notation verbatim
- Spec refs are verbatim `TS XX.XXX §Y.Y` strings
- If spec RAG returns no spec_ref for an item → `spec_ref: null` (not invented)
- The script auto-appends each output keyword to `keyword_provenance_audit`
  with `source: "3gpp-spec-retrieval <operation>"`
