---
name: 3gpp-code-retrieval
description: >
  Shared utility skill for UE C/C++ source code retrieval via code_search.py.
  Wraps three code operations used across FTA phases: bind_module (Phase 3.1 —
  bind source files to spec phases), expand_failure_modes (Phase 3.3 — find
  failure paths in a bound module with literal log macro strings), and
  find_implementation (Phase 3.4 — find log macros reporting actual values for
  cross-reference). Each invocation calls code_search.py with --state-file so
  the script writes structured results directly to the state file. CRITICAL:
  all log_keywords returned are literal strings extracted from log macros
  (MSG_HIGH, SYS_ERR, etc.) — NEVER inferred. Use whenever a phase skill needs
  code data — never call code_search.py directly. Triggers: "call code
  semantic search", "bind module to phase", "expand failure modes", "find
  implementation for IE", "extract log macro literals".
---

# 3GPP Code Retrieval Shared Skill

## Role

Single point of entry for all UE codebase semantic searches. Other skills
delegate to this one rather than calling `code_search.py` directly.

## Supported operations

| Operation | Used by | Purpose |
|---|---|---|
| `bind_module` | `3gpp-fta-build-tree` | Find source files implementing a spec phase |
| `expand_failure_modes` | `3gpp-fta-evaluate-branches` | Find failure paths + log macros in a module |
| `find_implementation` | `3gpp-fta-cross-reference` | Find log macros reporting actual values |

## Critical: log macro literal extraction

All `log_keywords` returned by this skill are LITERAL STRINGS from these
exact log macros:

```
MSG_HIGH("...", ...)              → arg 1
NAS_MSG_HIGH("...", ...)          → arg 1
LOG_MSG(code, "...", ...)         → arg 2
QCRIL_LOG_DEBUG("...", ...)       → arg 1
RRC_LOG_MSG(level, "...", ...)    → arg 2
SYS_ERR("...", ...)               → arg 1
DS_MSG_HIGH_1("...", val)         → arg 1
printf("[TAG] ...\n", ...)        → full string
fprintf(stderr, "...", ...)       → arg 2
syslog(level, "...", ...)         → arg 2
```

The Python script extracts these literals from snippets returned by
`semantic_code_search`. NO inference. NO guessing what a log line "probably says."

---

## Execution templates

### Operation: bind_module

Caller args: `phase_name`, `phase_ref`, `scope_layer`.

```
<execute_command>
python3 ${TOOL_DIR}/code_search.py \
  --operation bind_module \
  --phase-name "<phase_name>" \
  --phase-ref "<phase_ref>" \
  --scope-layer "<scope_layer>" \
  --state-file "<state_path>" \
  --max-tokens 800
</execute_command>
```

Expected stdout:
```json
{
  "operation": "bind_module",
  "phase_name": "...",
  "modules": [
    {"file": "rrc_ho_handler.cpp",
     "primary_function": "handle_rrc_reconfig_with_sync",
     "relevance": "HIGH" | "MEDIUM",
     "evidence": "..."}
  ]
}
```

State file write: `phase3_hybrid_tree.branches[<id>].modules`

If `modules` empty: valid result; caller marks branch as `unbindable`.

### Operation: expand_failure_modes

Caller args: `module`, `phase_context`.

```
<execute_command>
python3 ${TOOL_DIR}/code_search.py \
  --operation expand_failure_modes \
  --module "<module>" \
  --phase-context "<phase_context>" \
  --state-file "<state_path>" \
  --max-tokens 1500
</execute_command>
```

Expected stdout:
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
     "layer": "PHY"}
  ]
}
```

State file write: `phase3_hybrid_tree.branches[<id>].children[]`

If `failure_modes` empty: caller falls back to `3gpp-spec-retrieval expand_sub_causes`.

### Operation: find_implementation

Caller args: `hypothesis_cause`, `spec_ie_names`, `scope_procedure`, `scope_layer`.

```
<execute_command>
python3 ${TOOL_DIR}/code_search.py \
  --operation find_implementation \
  --hypothesis-cause "<cause>" \
  --spec-ie-names "<ie1>" "<ie2>" \
  --scope-procedure "<procedure>" \
  --scope-layer "<layer>" \
  --state-file "<state_path>" \
  --max-tokens 1500
</execute_command>
```

Expected stdout:
```json
{
  "operation": "find_implementation",
  "found": true | false,
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "log_keywords": ["Tx Power clamped", "Underflow limit"],
  "log_tags": ["DSP_CALC"],
  "function_names": ["dsp_calc_preamble_tx_power"],
  "implementation_files": ["dsp_power_calc.c"],
  "evidence_summary": "..."
}
```

State file write: `phase3_cross_reference_findings[<id>].actual_value_lookup`

If `found: false`: caller marks as unverifiable; cross-reference open item.

---

## Error handling

| Exit code | Action |
|---|---|
| 0 | Success — return stdout JSON |
| 1 | Invalid args — bug in this skill; report and halt |
| 2 | Tool unavailable (code search backend down) — halt pipeline |
| 3 | Policy violation — should not happen for code; report and halt |
| 4 | Empty result — return empty JSON; caller decides fallback |

---

## Anti-Hallucination (enforced by code_search.py)

- File paths come from `semantic_code_search` result metadata only — NEVER
  from "what file name sounds right for this phase"
- Function names from snippet function signatures only
- `log_keywords` from literal log macro strings only (per the macro list above)
- `log_tags` from literal tag identifiers in macro calls only
- `state_values` from enum/define constants in snippets only
- `found = false` when no relevant snippet — never LOW as confirmation

This skill is a thin wrapper. The Python script is the authority on extraction
rules; this skill must not modify any returned values before returning.

See `references/code-operations.md` for per-operation parameter details.
