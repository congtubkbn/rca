# Phase 3.1 Input/Output Specification — Hybrid Fault Tree Construction

**Skill:** `3gpp-fta-build-tree`  
**Scope:** Per-iteration FTA skeleton construction + code binding  
**Version:** v6  

---

## Input Contract

### Read-Only State Sections

Phase 3.1 reads ONLY these slices from the state file:

```json
{
  "meta": {
    "current_iteration_id": <N>,
    "tool_dir": "<path to 3gpp-tools/>",
    "db_tables": ["UE_3gpp_signaling_log", "UE_Trace_log"]
  },
  "phase1_scope_filter": {
    "procedure": "<procedure name>",
    "rat": "<RAT: 5G NR | LTE | ...>"
  },
  "fta_iterations": [
    {
      "iteration_id": <N>,
      "input_top_event": {
        "event": "<top event descriptor>",
        "source": "<phase2_ecf.top_event | base_event_from_iteration_N-1>",
        "spec_anchored": <true | false>
      }
    }
  ]
}
```

### Input Parameters from Workflow

- **`iteration_id`** (integer, 1+): Which iteration to construct. Workflow supplies this.
- **Implicit state confirmation:** `meta.current_phase == "iteration_<N>_running"` where N = iteration_id.

---

## Execution Steps with Query Shapes

### Step 1 — Read & Validate Inputs

**File:** State file at path from `.rca/current_state_path.txt`

```python
state = read_json(state_file_path)
iteration_id = state['meta']['current_iteration_id']
scope = state['phase1_scope_filter']
input_top_event = state['fta_iterations'][iteration_id - 1]['input_top_event']

# Validation
assert iteration_id > 0
assert 'procedure' in scope and 'rat' in scope
assert 'event' in input_top_event
```

**Determines:** Is this iteration spec-anchored?
- Iteration 1: `input_top_event.source == "phase2_ecf.top_event"` → spec applies
- Iteration ≥ 2: `input_top_event.source` references a base_event from prior iteration → spec may not apply

---

### Step 2a — Request Spec Skeleton

**When:** All iterations attempt skeleton first.

**Tool:** `spec_query.py --operation skeleton`

**Command template:**
```bash
python3 {tool_dir}/spec_query.py \
  --operation skeleton \
  --procedure "{scope.procedure}" \
  --rat "{scope.rat}" \
  --top-event "{input_top_event.event}" \
  --state-file "{state_file_path}" \
  --max-tokens 1500
```

**Example invocation (5G Handover, iteration 1):**
```bash
python3 /workspace/3gpp-tools/spec_query.py \
  --operation skeleton \
  --procedure "Intra-AMF 5G Handover" \
  --rat "5G NR" \
  --top-event "5G_HO_Execution_Failure" \
  --state-file /tmp/rca_state_20260816T120000Z.json \
  --max-tokens 1500
```

**Expected stdout (compressed JSON):**
```json
{
  "operation": "skeleton",
  "procedure": "Intra-AMF 5G Handover",
  "rat": "5G NR",
  "top_event": "5G_HO_Execution_Failure",
  "spec_refs": ["TS 23.502 §4.9.1", "TS 38.331 §5.5"],
  "gate_at_top": "OR",
  "phases": [
    {
      "id": "P1",
      "name": "RRC_Signaling_Phase",
      "spec_ref": "TS 38.331 §5.5.1",
      "mandatory_messages": [
        "RRCReconfiguration with reconfigurationWithSync"
      ],
      "protocol_layer": "RRC"
    },
    {
      "id": "P2",
      "name": "Target_Cell_Sync_Phase",
      "spec_ref": "TS 38.331 §5.5.3",
      "mandatory_messages": [
        "RACH preamble transmission",
        "Random Access Response"
      ],
      "protocol_layer": "PHY/MAC"
    }
  ]
}
```

**Exit codes:**
- `0` — success, phases[] may be empty (expected for iter ≥ 2)
- `1` — bad arguments (missing procedure/rat)
- `2` — tool unavailable (RAG down)
- `4` — empty result (no spec phases; proceed to fallback)

**State file side effect:** Writes to `fta_iterations[N-1].hybrid_tree.spec_skeleton_source`.

---

### Step 2b — Fallback: Generate Hypotheses (if skeleton empty)

**When:** `skeleton` returns `"phases": []` OR exit code 4.

**Tool:** `spec_query.py --operation generate_hypotheses`

**Command template:**
```bash
python3 {tool_dir}/spec_query.py \
  --operation generate_hypotheses \
  --event "{input_top_event.event}" \
  --procedure "{scope.procedure}" \
  --rat "{scope.rat}" \
  --state-file "{state_file_path}" \
  --max-tokens 2000
```

**Example invocation (iteration 2 fallback, "Preamble_Power_Error" base event):**
```bash
python3 /workspace/3gpp-tools/spec_query.py \
  --operation generate_hypotheses \
  --event "Preamble_Power_Error" \
  --procedure "Intra-AMF 5G Handover" \
  --rat "5G NR" \
  --state-file /tmp/rca_state_20260816T120000Z.json \
  --max-tokens 2000
```

**Expected stdout:**
```json
{
  "operation": "generate_hypotheses",
  "event": "Preamble_Power_Error",
  "procedure": "Intra-AMF 5G Handover",
  "rat": "5G NR",
  "hypotheses": [
    {
      "id": "H1",
      "name": "DSP Calculates Incorrect Transmit Power",
      "explanation": "The DSP module calculates preamble Tx power based on commanded target power and pathloss estimate; incorrect calculation or underflow handling results in invalid power transmission.",
      "spec_grounding": "TS 38.331 §6.3.2 defines preambleReceivedTargetPower IE; TS 38.321 §5.1.3 specifies UE Tx power control calculations."
    },
    {
      "id": "H2",
      "name": "Pathloss Measurement Anomaly",
      "explanation": "The pathloss measurement used in Tx power calculation is erroneous, leading to over/under-powered preambles.",
      "spec_grounding": "TS 38.331 §5.2.4 defines pathloss reference procedures."
    },
    {
      "id": "H3",
      "name": "Firmware Power Limit Clamp Triggered",
      "explanation": "UE firmware clamps Tx power to safety limits that are inconsistent with network requirements.",
      "spec_grounding": "TS 38.306 §4 defines max TX power per device category."
    }
  ]
}
```

**Exit codes:** Same as skeleton.

**State file side effect:** Writes to `fta_iterations[N-1].hybrid_tree` (no `spec_skeleton_source`; instead uses hypotheses array).

---

### Step 3 — Bind Code Modules to Each Phase/Hypothesis

**Tool:** `code_search.py --operation bind_module`

**For each phase/hypothesis from Step 2a or 2b:**

**Command template (standard phase):**
```bash
python3 {tool_dir}/code_search.py \
  --operation bind_module \
  --phase-name "{phase.name}" \
  --phase-ref "{phase.spec_ref}" \
  --scope-layer "{phase.protocol_layer}" \
  --state-file "{state_file_path}" \
  --max-tokens 800
```

**Example (binding RRC_Signaling_Phase):**
```bash
python3 /workspace/3gpp-tools/code_search.py \
  --operation bind_module \
  --phase-name "RRC_Signaling_Phase" \
  --phase-ref "TS 38.331 §5.5.1" \
  --scope-layer "RRC" \
  --state-file /tmp/rca_state_20260816T120000Z.json \
  --max-tokens 800
```

**Expected stdout:**
```json
{
  "operation": "bind_module",
  "phase_name": "RRC_Signaling_Phase",
  "phase_ref": "TS 38.331 §5.5.1",
  "scope_layer": "RRC",
  "modules": [
    {
      "file": "rrc_ho_handler.cpp",
      "primary_function": "handle_rrc_reconfig_with_sync",
      "relevance": "HIGH",
      "evidence": "Function processes RRCReconfiguration with reconfigurationWithSync IE; handles handover branch setup."
    },
    {
      "file": "rrc_config_validator.cpp",
      "primary_function": "validate_reconfig_ies",
      "relevance": "MEDIUM",
      "evidence": "Validates IE syntax before processing."
    }
  ]
}
```

**For fallback hypothesis (no spec_ref):**
```bash
python3 {tool_dir}/code_search.py \
  --operation bind_module \
  --phase-name "DSP Calculates Incorrect Transmit Power" \
  --scope-layer "PHY/DSP" \
  --state-file "{state_file_path}" \
  --max-tokens 800
```

**Exit codes:** Same as skeleton/spec_query.

**State file side effect:** Appends to `fta_iterations[N-1].hybrid_tree.branches[<phase_id>].modules[]`.

**Edge case — no modules found:** Valid result; `"modules": []` with optional `"note": "no binding found"`. Branch proceeds to Phase 3.2 evaluation anyway.

---

## Output Contract

### Write Section: `fta_iterations[iteration_id - 1].hybrid_tree`

All writes are atomic (single JSON update, not incremental appends).

**Full output shape:**
```json
{
  "iteration_id": <N>,
  "hybrid_tree": {
    "constructed_at": "<ISO 8601 timestamp>",
    "spec_skeleton_returned_empty": false | true,
    "fallback_used": null | "generate_hypotheses + code-only",
    "gate_at_top": "OR",
    
    "spec_skeleton_source": {
      "operation": "skeleton",
      "procedure": "<scope.procedure>",
      "rat": "<scope.rat>",
      "top_event": "<input.event>",
      "phases": [/* from Step 2a stdout */]
    },
    
    "branches": [
      {
        "id": "P1" | "H1",
        "name": "<phase/hypothesis name>",
        "spec_ref": "<TS XX.XXX §Y.Y>" | null,
        "mandatory_messages": ["msg1", "msg2"],
        "protocol_layer": "RRC" | "NAS" | "PHY" | "PHY/DSP" | "MAC/PHY",
        
        "modules": [
          {
            "file": "src/module.cpp",
            "primary_function": "func_name",
            "relevance": "HIGH" | "MEDIUM" | "LOW",
            "evidence": "..."
          }
        ],
        
        "gate_a_result": null,
        "status": "unevaluated",
        "children": []
      }
    ]
  }
}
```

### Detailed Field Semantics

| Field | Type | Source | Semantics |
|-------|------|--------|-----------|
| `constructed_at` | ISO 8601 | Phase 3.1 | Timestamp when tree was built |
| `spec_skeleton_returned_empty` | bool | Step 2a result | True if Phase 2a returned `phases: []` |
| `fallback_used` | null \| string | Step 2b | "generate_hypotheses + code-only" if fallback invoked |
| `gate_at_top` | "OR" | Hardcoded | Top-level gate type (always OR in v6) |
| `spec_skeleton_source` | object | Step 2a stdout | Full skeleton output from spec_query.py (omitted if fallback used) |
| `branches[].id` | "P1", "P2", ... \| "H1", "H2", ... | Skeleton/hypothesis | Phase ID (spec) or Hypothesis ID (fallback) |
| `branches[].name` | string | Skeleton/hypothesis | Phase/hypothesis human-readable name |
| `branches[].spec_ref` | string \| null | Skeleton only | TS reference; null for hypotheses |
| `branches[].mandatory_messages` | array | Skeleton/hypothesis | Expected signaling messages for this branch |
| `branches[].protocol_layer` | string | Skeleton only | RRC, NAS, PHY, etc. |
| `branches[].modules[]` | array | Step 3 | Code binding results (empty if no match) |
| `branches[].gate_a_result` | null | Initialize | Filled by Phase 3.2; always null here |
| `branches[].status` | "unevaluated" | Initialize | Phase 3.2 transitions to "pruned_normal", "failure_here", "rejected" |
| `branches[].children` | [] | Initialize | Sub-branches added by Phase 3.3; always empty here |

---

## Anti-Hallucination Rules

### Rule 1: All phase/hypothesis names from tools only

- ✓ Use `phase.name` directly from skeleton stdout
- ✓ Use `hypothesis.name` directly from hypotheses stdout
- ❌ Do NOT invent phase names (e.g., "speculated_phase_X")
- ❌ Do NOT combine/abbreviate tool output

### Rule 2: Spec refs verbatim

- ✓ Use `spec_ref` exactly as returned by spec_query.py
- ✓ Example: "TS 38.331 §5.5.1" (preserve section number)
- ❌ Do NOT normalize (e.g., "TS 38.331 v16.3.0 §5.5.1" → "TS 38.331 §5.5.1")
- ❌ Do NOT infer missing spec refs

### Rule 3: Module paths from code_search.py

- ✓ Use `file` path exactly as returned
- ✓ Use `primary_function` exactly as returned
- ❌ Do NOT map relative paths to absolute (tool owns the mapping)
- ❌ Do NOT abbreviate function names

### Rule 4: Empty results are valid

- ✓ If `bind_module` returns `modules: []`, record it as-is
- ✓ If `skeleton` returns `phases: []`, trigger fallback (do not invent phases)
- ❌ Do NOT pad empty arrays with hypothetical entries

### Rule 5: Iteration-scoped audit entries

- Every audit log entry in this phase tags `iteration_id`
- Example: `{"event": "skeleton_call", "iteration_id": 1, "timestamp": "...", "tool": "spec_query.py"}`
- This traces which iteration triggered which tool call

---

## Error Handling

### Exit codes and recovery

| Tool | Exit Code | Action | State Write |
|------|-----------|--------|-------------|
| spec_query.py skeleton | 0 | Proceed to Step 2b or 3 | `spec_skeleton_source` + continue |
| spec_query.py skeleton | 1 | **Fail** — bad args | None; halt |
| spec_query.py skeleton | 2 | **Warn & fallback** — tool unavailable | `spec_skeleton_source = null`, set `fallback_used` |
| spec_query.py skeleton | 4 | **Fallback** — no phases (expected iter ≥ 2) | Invoke fallback (Step 2b) |
| spec_query.py hypotheses | 0 | Proceed to Step 3 | Use hypothesis array as branches |
| spec_query.py hypotheses | 1, 2 | **Fail** — cannot fallback | Halt with error |
| code_search.py bind_module | 0 | Record modules (may be empty) | `branches[].modules[]` |
| code_search.py bind_module | 1, 2 | **Fail** — tool issue | Halt with error |
| code_search.py bind_module | 4 | No modules found | `modules: []` (valid, branch proceeds) |

### Logging invariants

- Log all tool invocations (tool name, operation, key parameters, exit code, timestamp)
- If `bind_module` returns empty, log reason if provided by tool (e.g., `"note": "no functions match phase scope"`)
- If fallback triggered, log the reason (empty skeleton)

---

## State Machine & Next Phase

**Phase 3.1 does NOT change `meta.current_phase`.**

Workflow (orchestrator) checks:
- `fta_iterations[N-1].hybrid_tree` exists and `branches[]` is non-empty → dispatch Phase 3.2
- Otherwise → error

**Invariant:** If Phase 3.1 completes, `hybrid_tree.branches` MUST have ≥1 entry (either from skeleton or fallback hypothesis).

---

## Checklist (see `.cline/skills/_shared/build-tree-checklist.md`)

- [ ] Read state file slice (meta, scope, iteration input)
- [ ] Invoke spec_query.py skeleton
- [ ] If empty, invoke generate_hypotheses fallback
- [ ] For each phase/hypothesis, invoke code_search.py bind_module
- [ ] Assemble hybrid_tree JSON with all branches initialized (status="unevaluated", gate_a_result=null, children=[])
- [ ] Write atomic update to state file
- [ ] Audit log all tool invocations + exit codes
- [ ] Verify no anti-hallucination rule violations
- [ ] Return (do NOT change current_phase)
