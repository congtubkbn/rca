# Tool Invocation Templates — v5 (Python scripts via execute_command)

Cline in this environment has no MCP. All retrieval tools are invoked as
**Python script calls** via `<execute_command>`. This file is the contract
between every skill and the underlying tools.

## Tool Directory Convention

All Python tool scripts live under a directory referenced by `meta.tool_dir`
in the state file. Default: `<workspace>/3gpp-tools/`.

```
3gpp-tools/
├── spec_query.py        # 3GPP spec GraphRAG
├── code_search.py       # UE codebase semantic search
└── log_query.py         # DuckDB query helper (both tables)
```

Each script accepts a `--state-file <path>` argument and appends its output
to the relevant section of that JSON file. This way the script writes the
state file directly; the skill only needs to verify success.

Scripts also print a **compressed JSON summary to stdout** for the skill to
read with `read_file` / display. Raw spec/code/log data is never returned to
stdout — only the structured symbols the orchestrator needs.

---

## 1. Spec Retrieval (`spec_query.py`)

All Phase 1, Phase 2, and FTA spec lookups go through `spec_query.py`.
Operation selected by `--operation` flag.

### Operation: `skeleton` (FTA Phase 3.1)

```bash
python3 3gpp-tools/spec_query.py \
  --operation skeleton \
  --procedure "Intra-AMF 5G Handover" \
  --rat "5G NR" \
  --top-event "5G_HO_Execution_Failure" \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 1500
```

**Returns (stdout, compressed JSON, ≤1500 tokens):**
```json
{
  "operation": "skeleton",
  "procedure": "Intra-AMF 5G Handover",
  "spec_refs": ["TS 23.502 §4.9.1", "TS 38.331 §5.5"],
  "gate_at_top": "OR",
  "phases": [
    {"id": "P1", "name": "RRC_Signaling_Phase",
     "spec_ref": "TS 38.331 §5.5.1",
     "mandatory_messages": ["RRCReconfiguration with reconfigurationWithSync"],
     "protocol_layer": "RRC"}
  ]
}
```

**Writes to state file:** `phase3_hybrid_tree.spec_skeleton_source` and the
initial `phase3_hybrid_tree.branches[]` entries (without children).

---

### Operation: `lightweight_procedure` (Phase 1 & Phase 2)

```bash
python3 3gpp-tools/spec_query.py \
  --operation lightweight_procedure \
  --procedure "LTE Initial Attach" \
  --rat "LTE" \
  --need is_is_not | ecf \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 600
```

**Returns (stdout, ≤600 tokens):**
For `--need is_is_not`:
```json
{
  "operation": "lightweight_procedure",
  "need": "is_is_not",
  "procedure": "LTE Initial Attach",
  "primary_layers": ["NAS", "RRC", "MAC", "PHY"],
  "key_timers": [{"timer": "T3410", "duration_default": "15s",
                  "on_expiry": "Attach failure"}],
  "initiating_message": "ATTACH REQUEST",
  "spec_refs": ["TS 24.301 §5.5.1"]
}
```

For `--need ecf`:
```json
{
  "operation": "lightweight_procedure",
  "need": "ecf",
  "procedure": "LTE Initial Attach",
  "expected_flow": [
    {"order": 1, "message": "RRCConnectionRequest", "direction": "UL", "layer": "RRC"},
    {"order": 2, "message": "RRCConnectionSetup", "direction": "DL", "layer": "RRC"},
    {"order": 3, "message": "ATTACH REQUEST", "direction": "UL", "layer": "NAS"}
  ],
  "key_timers": [{"timer": "T3410", "duration_default": "15s", "on_expiry": "..."}],
  "spec_refs": ["TS 24.301 §5.5.1.2"]
}
```

**Writes to state file:** `phase1_scope_filter.spec_lookup` or
`phase2_ecf.observable_symptoms.expected_flow_source` depending on `--need`.

---

### Operation: `extract_ies` (FTA Gate A, optional refinement)

```bash
python3 3gpp-tools/spec_query.py \
  --operation extract_ies \
  --message "RRCReconfiguration" \
  --procedure "Intra-AMF 5G Handover" \
  --spec-ref "TS 38.331 §5.5.1" \
  --hypothesis-id P1 \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 800
```

**Returns:**
```json
{
  "operation": "extract_ies",
  "for_hypothesis_id": "P1",
  "message_definitions": [
    {"message_name": "RRCReconfiguration",
     "mandatory_ies": ["rrc-TransactionIdentifier", "reconfigurationWithSync"],
     "optional_ies": ["measConfig", "...etc"],
     "direction": "DL"}
  ]
}
```

**Writes to state file:** `phase3_evaluations[<hypothesis_id>].spec_ie_extraction`.

---

### Operation: `find_commanded_values` (FTA Phase 3.4 — v4 critical)

```bash
python3 3gpp-tools/spec_query.py \
  --operation find_commanded_values \
  --base-event-name "Preamble_Power_Error" \
  --base-event-layer "PHY" \
  --upstream-messages "RRCReconfiguration" \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 1000
```

**Returns:**
```json
{
  "operation": "find_commanded_values",
  "base_event_name": "Preamble_Power_Error",
  "commanded_value_ies": [
    {"ie_name": "preambleReceivedTargetPower",
     "message": "RRCReconfiguration",
     "meaning": "Network target receive power UE must transmit at",
     "spec_ref": "TS 38.331 §6.3.2, TS 38.321 §5.1.3",
     "ue_action": "Calculate Tx power = target - pathloss; apply to PRACH",
     "range_unit": "dBm, integer, -202..-60"}
  ]
}
```

**Writes to state file:** `phase3_cross_reference_findings[<id>].commanded_ie_lookup`.

If no relevant commanded values: `{"commanded_value_ies": [], "note": "..."}` —
valid result; orchestrator records and proceeds without value discrepancy.

---

### Operation: `generate_hypotheses` (FTA fallback when skeleton unavailable)

```bash
python3 3gpp-tools/spec_query.py \
  --operation generate_hypotheses \
  --event "Attach Failure cause #11" \
  --procedure "LTE Initial Attach" \
  --rat "LTE" \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 2000
```

Used only when `skeleton` returns no standardized procedure phases (i.e.,
the failure isn't on a standardized 3GPP procedure). Returns hypothesis list
identical to v3 Mode 1.

---

### Operation: `expand_sub_causes` (FTA fallback when code expansion empty)

```bash
python3 3gpp-tools/spec_query.py \
  --operation expand_sub_causes \
  --parent-cause "RRC connection failure" \
  --parent-spec-ref "TS 38.331 §5.3.3" \
  --procedure "5G Registration" \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 1500
```

Used when `code_search.py --operation expand_failure_modes` returns empty —
i.e., the code module has no explicit failure modes but spec defines them.

---

## 2. Code Retrieval (`code_search.py`)

All FTA code lookups go through `code_search.py`. Operation selected by
`--operation` flag.

### Operation: `bind_module` (FTA Phase 3.1)

```bash
python3 3gpp-tools/code_search.py \
  --operation bind_module \
  --phase-name "RRC_Signaling_Phase" \
  --phase-ref "TS 38.331 §5.5.1" \
  --scope-layer "RRC" \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 800
```

**Returns:**
```json
{
  "operation": "bind_module",
  "phase_name": "RRC_Signaling_Phase",
  "modules": [
    {"file": "rrc_ho_handler.cpp",
     "primary_function": "handle_rrc_reconfig_with_sync",
     "relevance": "HIGH",
     "evidence": "function processes RRCReconfiguration with reconfigurationWithSync IE"}
  ]
}
```

**Writes to state file:** `phase3_hybrid_tree.branches[<id>].modules`.

If no relevant module found: `{"modules": [], "note": "no binding found"}`.

---

### Operation: `expand_failure_modes` (FTA Phase 3.3)

```bash
python3 3gpp-tools/code_search.py \
  --operation expand_failure_modes \
  --module "phy_sync_task.c" \
  --phase-context "Target_Cell_Sync_Phase" \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 1500
```

**Returns:**
```json
{
  "operation": "expand_failure_modes",
  "module": "phy_sync_task.c",
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
     "detection_code": "Tx power calculation underflow check",
     "log_keywords": ["Tx Power clamped", "Underflow limit"],
     "log_tags": ["DSP_CALC"],
     "function_signature": "dsp_calc_preamble_tx_power(...)",
     "layer": "PHY/DSP"}
  ]
}
```

**Writes to state file:** `phase3_hybrid_tree.branches[<id>].children[]`.

**CRITICAL — log keyword extraction (literals only):**
The script MUST extract `log_keywords` from these macros only — never infer:
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

---

### Operation: `find_implementation` (FTA Phase 3.4 cross-reference)

Used during cross-reference Step 4.2 (b) to find log macros reporting the
*actual* value of a commanded IE. Equivalent to v3/v4 "Mode A".

```bash
python3 3gpp-tools/code_search.py \
  --operation find_implementation \
  --hypothesis-cause "DSP calculates and applies transmit power" \
  --spec-ie-names "preambleReceivedTargetPower" \
  --scope-procedure "Intra-AMF 5G Handover" \
  --scope-layer "PHY" \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 1500
```

**Returns:**
```json
{
  "operation": "find_implementation",
  "found": true,
  "confidence": "HIGH",
  "log_keywords": ["Tx Power clamped", "Underflow limit"],
  "log_tags": ["DSP_CALC"],
  "function_names": ["dsp_calc_preamble_tx_power"],
  "implementation_files": ["dsp_power_calc.c"],
  "evidence_summary": "Function applies tx power; logs clamped value on underflow"
}
```

**Writes to state file:** `phase3_cross_reference_findings[<id>].actual_value_lookup`.

---

## 3. Log Queries (`log_query.py`)

All DuckDB queries go through `log_query.py` with strict table isolation
enforced by the `--phase-tag` flag.

### Phase-Tag Validation (HARD STOP at script entry)

```
phase_tag = phase1, phase2          → ONLY UE_3gpp_signaling_log
phase_tag = phase3_gate_a           → ONLY UE_3gpp_signaling_log
phase_tag = phase3_gate_b           → ONLY UE_Trace_log
phase_tag = phase3_cross_ref        → EITHER table (FTA-only)
```

Mismatch → script exits with non-zero status and JSON error:
```json
{"error": "Table isolation violation",
 "phase_tag": "phase1", "table": "UE_Trace_log",
 "policy": "v5 §table-isolation"}
```

### Universal command shape

```bash
python3 3gpp-tools/log_query.py \
  --phase-tag <phase1|phase2|phase3_gate_a|phase3_gate_b|phase3_cross_ref> \
  --table <UE_3gpp_signaling_log|UE_Trace_log> \
  --keywords "kw1" "kw2" \
  --ie-names "ie1" "ie2" \
  --log-tags "tag1" "tag2" \
  --time-window-start-ms 0 \
  --time-window-end-ms 3000 \
  --layers "RRC" "NAS" \
  --hypothesis-id "P2.2" \
  --return-ie-values true \
  --state-file /tmp/rca_state_<ts>.json \
  --max-tokens 1500
```

Optional flags: `--ie-names`, `--log-tags`, `--time-window-*`, `--layers`,
`--hypothesis-id`, `--return-ie-values`.

### Returns (standard, all phases)

```json
{
  "queried_table": "UE_3gpp_signaling_log",
  "tool_used": "query_UE_3gpp_signaling_log_only",
  "keywords_used": ["RRCReconfiguration"],
  "keywords_with_hits": ["RRCReconfiguration"],
  "keywords_missed": [],
  "matched_event_count": 1,
  "evidence_summary": "RRCReconfiguration received at 14:02:11.00 with reconfigurationWithSync",
  "key_events": [
    {"timestamp": "14:02:11.00", "layer": "RRC", "direction": "DL",
     "message": "RRCReconfiguration",
     "kpis": {"reconfigurationWithSync": true}}
  ]
}
```

### Returns (cross-ref with `--return-ie-values true`, v4 critical)

```json
{
  ...standard fields...
  "ie_value_extractions": [
    {"ie_name": "preambleReceivedTargetPower",
     "value": "-110 dBm",
     "source_msg": "RRCReconfiguration",
     "timestamp": "14:02:11.00"}
  ]
}
```

For trace cross-ref queries:
```json
{
  "ie_value_extractions": [
    {"ie_name": "Tx Power", "value": "-10 dBm",
     "source_msg": "DSP_CALC trace",
     "timestamp": "14:02:11.50",
     "annotations": ["Underflow limit"]}
  ]
}
```

**Writes to state file:** depends on `--phase-tag` (see state schema for owners).

### Underlying tool dispatch

| `--phase-tag` | `--table` | Underlying tool called |
|---|---|---|
| phase1 / phase2 | UE_3gpp_signaling_log | `query_UE_3gpp_signaling_log_only(...)` |
| phase3_gate_a | UE_3gpp_signaling_log | `query_UE_3gpp_signaling_log_only(...)` |
| phase3_gate_b | UE_Trace_log | `query_UE_trace_log(...)` |
| phase3_cross_ref | (either, per `--table`) | (corresponding tool) |

---

## Error Handling

All three Python scripts share these conventions:

| Exit code | Meaning |
|---|---|
| 0 | Success — output is valid JSON on stdout, state file updated |
| 1 | Missing/invalid arguments — error on stderr, no state file changes |
| 2 | Tool unavailable (RAG/DB connection error) — JSON error on stdout |
| 3 | Policy violation (e.g. table isolation) — JSON error on stdout, no state file changes |
| 4 | Empty result — JSON with empty arrays on stdout, state file updated with empty entry |

Skills always check the exit code via `$?` and the JSON `error` field
before proceeding to the next step.

---

## Keyword Provenance (auto-appended)

Every tool script appends a `keyword_provenance_audit` entry to the state
file for each non-trivial output keyword (message names, IE names, log
literals, file paths). The skill doesn't need to do this manually — the
script handles it.

This guarantees every keyword used in any downstream query traces to a
specific tool invocation timestamp, satisfying the v3/v4/v5 anti-hallucination
contract automatically.
