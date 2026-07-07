# Code Operations Reference

Detailed parameter and return shapes for each `code_search.py` operation.

## Operation: bind_module

### Required args
| Arg | Type | Example |
|---|---|---|
| `--phase-name` | string | `"RRC_Signaling_Phase"` |
| `--phase-ref` | string | `"TS 38.331 §5.5.1"` |
| `--scope-layer` | string | `"RRC"` |
| `--state-file` | path | ... |

### Optional
| Arg | Default | Effect |
|---|---|---|
| `--max-tokens` | 800 | Token budget |
| `--max-modules` | 3 | Max modules to return |

### Stdout shape
```json
{
  "operation": "bind_module",
  "phase_name": "RRC_Signaling_Phase",
  "modules": [
    {"file": "rrc_ho_handler.cpp",
     "primary_function": "handle_rrc_reconfig_with_sync",
     "relevance": "HIGH" | "MEDIUM",
     "evidence": "snippet contained spec_ref comment and message handler"}
  ]
}
```

### Search strategy (inside the Python script)
1. `"<phase_name> handler <scope_layer> UE implementation"`
2. `"<phase_name keyword nouns> processing <scope_layer>"`
3. `"<spec_ref>"` (search for code mentioning the section number — codebases
   often comment with §refs)

Stop at first relevant set.

### Side effects
- `phase3_hybrid_tree.branches[<id>].modules`

If no module relevant: `modules: []` + `note: "no binding found"`. Valid result.

---

## Operation: expand_failure_modes

### Required args
| Arg | Type | Example |
|---|---|---|
| `--module` | string | `"phy_sync_task.c"` |
| `--phase-context` | string | `"Target_Cell_Sync_Phase"` |
| `--state-file` | path | |

### Stdout shape
```json
{
  "operation": "expand_failure_modes",
  "module": "...",
  "failure_modes": [
    {"id_suffix": "1",
     "name": "RACH_Timeout",
     "detection_code": "preamble retransmission counter compared to max",
     "log_keywords": ["RACH attempt", "max preamble trans reached"],
     "log_tags": ["THREAD_PHY"],
     "function_signature": "phy_sync_rach_send(...)",
     "layer": "PHY"},
    {"id_suffix": "2",
     "name": "Preamble_Power_Error",
     "detection_code": "Tx power validation underflow",
     "log_keywords": ["Tx Power clamped", "Underflow limit"],
     "log_tags": ["DSP_CALC"],
     "function_signature": "dsp_calc_preamble_tx_power(...)",
     "layer": "PHY/DSP"}
  ]
}
```

### Search strategy
1. `"<module> error handling failure paths"`
2. `"<module> timeout retry max limit reached"`
3. `"<module> validation reject invalid"`

Goal: surface error-handling blocks and the log macros within them.

### Symbol extraction rules (strict)
- Each `failure_modes[i]` = a distinct error-handling block in the code
- `log_keywords` ONLY from literal strings in these macros:
  ```
  MSG_HIGH("...")              → arg 1
  NAS_MSG_HIGH("...")          → arg 1
  LOG_MSG(code, "...")         → arg 2
  QCRIL_LOG_DEBUG("...")       → arg 1
  RRC_LOG_MSG(level, "...")    → arg 2
  SYS_ERR("...")               → arg 1
  DS_MSG_HIGH_1("...")         → arg 1
  printf("[TAG] ...")          → full string
  fprintf(stderr, "...")       → arg 2
  syslog(level, "...")         → arg 2
  ```
- `log_tags` from tag identifiers in macros or string prefixes (e.g.
  `"THREAD_PHY"`, `[DSP_CALC]`)
- `detection_code` is a ≤80-char paraphrase of WHAT THE CODE CHECKS (not what
  the spec says)
- `function_signature` from actual function signature in snippet

### Side effects
- `phase3_hybrid_tree.branches[<id>].children[]`

If no failure modes detectable: `failure_modes: []` + `note: "..."`.
Caller falls back to `3gpp-spec-retrieval expand_sub_causes`.

---

## Operation: find_implementation

### Required args
| Arg | Type | Example |
|---|---|---|
| `--hypothesis-cause` | string | `"DSP calculates and applies transmit power"` |
| `--spec-ie-names` | string list | space-separated, e.g. `"preambleReceivedTargetPower"` |
| `--scope-procedure` | string | `"Intra-AMF 5G Handover"` |
| `--scope-layer` | string | `"PHY"` |
| `--state-file` | path | |

### Stdout shape
```json
{
  "operation": "find_implementation",
  "found": true | false,
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "log_keywords": ["Tx Power clamped", "Underflow limit"],
  "log_tags": ["DSP_CALC"],
  "function_names": ["dsp_calc_preamble_tx_power"],
  "implementation_files": ["dsp_power_calc.c"],
  "evidence_summary": "Function applies tx power; logs clamped value on underflow"
}
```

### Search strategy
1. `"<hypothesis_cause> <scope_procedure> <scope_layer> UE implementation"`
2. `"<spec_ie_names[0]> handler <scope_layer> C"`

Max 3 queries. Stop at first relevant snippet.

### Side effects
- `phase3_cross_reference_findings[<id>].actual_value_lookup`

`found = false` when no relevant snippet — caller marks open item.

---

## Anti-hallucination contract (enforced by code_search.py)

- File paths come from `semantic_code_search` result metadata only
- Function names from snippet function signatures only
- `log_keywords` from literal macro strings only (per the macro list above)
- `log_tags` from literal tag identifiers in macro calls only
- `state_values` from enum/define constants in snippets only
- `found = false` when no relevant snippet — never LOW as confirmation
- No naming-convention inferences — if symbol isn't in snippet, it doesn't exist
- Script auto-appends each output keyword to `keyword_provenance_audit` with
  `source: "3gpp-code-retrieval <operation>"`
