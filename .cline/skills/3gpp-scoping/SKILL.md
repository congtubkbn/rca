---
name: 3gpp-scoping
description: >
  Phase 1 of the 3GPP UE RCA pipeline — IS/IS-NOT scoping. Build the scope_filter
  for a UE failure: procedure, RAT, layers, time window, condition, reproducibility,
  discriminator. Calls 3gpp-spec-retrieval (lightweight_procedure operation) for
  procedure metadata. Optionally calls 3gpp-log-queries (phase1, signaling table
  only) for a sanity check. STRICTLY PROHIBITED from accessing UE_Trace_log or
  code search. Does NOT attempt root cause. Use this skill when starting Phase 1
  of the pipeline, after the orchestrator has initialized the state file.
  Triggers: "scope this UE failure", "build IS/IS-NOT for this problem",
  "Phase 1 of 3GPP RCA".
---

# 3GPP Phase 1 — IS/IS-NOT Scoping

## Role

Define the failure boundary from the engineer's description. Produce a precise
`scope_filter` so downstream phases know WHERE to look. Does NOT attempt root
cause analysis — that's FTA's job.

## Hard constraints (table isolation)

1. Tool calls allowed:
   - `3gpp-spec-retrieval` (lightweight_procedure operation only)
   - `3gpp-log-queries` (phase1 tag, signaling table ONLY)
2. Tool calls FORBIDDEN:
   - Any UE_Trace_log query
   - Any code search
   - Any other spec retrieval operation (skeleton, find_commanded_values, etc.)

## Inputs

- `<workspace>/.rca/current_state_path.txt` → state file path
- Engineer description is in `state.meta.engineer_input`

## Output

Writes `phase1_scope_filter` block to state file. Fields:

```json
{
  "completed_at": "<ISO>",
  "procedure": "<3GPP procedure name>",
  "rat": "LTE | 5G NR | NR-NSA | WCDMA",
  "bands": ["..."],
  "layers": ["..."],
  "layers_excluded": ["..."],
  "condition": "<state/trigger condition>",
  "time_window": {"start_ms": 0, "end_ms": 0},
  "discriminator": "<biggest IS vs IS-NOT contrast>",
  "reproducibility": "always | intermittent ~X%",
  "ambiguities": ["..."],
  "spec_lookup": { /* from spec_query.py lightweight_procedure */ },
  "signaling_sanity_check": { /* optional, from log_query.py phase1 */ }
}
```

---

## Execution

### Step 1 — Extract raw facts from engineer description

Parse the description for:
- UE model / chipset / firmware version
- RAT, band, EARFCN/NR-ARFCN
- Network operator / PLMN
- Test scenario (Attach, TAU, Handover, etc.)
- Failure symptom
- Conditions at failure
- Reproducibility
- Environment

### Step 2 — Build IS/IS-NOT contrasts (reasoning only)

Four dimensions, both columns specific:

| Dimension | IS | IS NOT |
|---|---|---|
| WHAT | Procedure that fails | Similar procedures that work |
| WHERE | Layer / band / cell / PLMN | Layers / bands that don't fail |
| WHEN | Condition / state at failure | When it works fine |
| EXTENT | Frequency / severity | What the failure is NOT |

Pick the biggest gap → `discriminator`.

### Step 3 — Call 3gpp-spec-retrieval for procedure metadata

```
Use the 3gpp-spec-retrieval skill with:
  operation: lightweight_procedure
  procedure: <inferred from description>
  rat: <inferred from description>
  need: is_is_not
```

The shared skill executes:
```bash
python3 ${TOOL_DIR}/spec_query.py \
  --operation lightweight_procedure \
  --procedure "<procedure>" \
  --rat "<rat>" \
  --need is_is_not \
  --state-file "<state_path>" \
  --max-tokens 600
```

Result is written to `phase1_scope_filter.spec_lookup` in the state file.

Use the returned `primary_layers` to populate `scope_filter.layers`.
Use the returned `initiating_message` for the optional sanity check.

**Halt condition:** If spec_query returns empty (procedure unrecognized),
mark `scope_filter.ambiguities[]` with "Procedure name not recognized by spec
retrieval — confirm with engineer" and HALT pipeline.

### Step 4 — (Optional) Signaling sanity check

Trigger ONLY if:
- Engineer description doesn't unambiguously identify the procedure, OR
- Time window unclear and signaling can help bound it, OR
- Confirming procedure presence in capture would resolve scope

```
Use the 3gpp-log-queries skill with:
  phase_tag: phase1
  table: UE_3gpp_signaling_log
  keywords: [scope_filter.spec_lookup.initiating_message]
  time_window: {start_ms: 0, end_ms: 10000}
```

The shared skill executes log_query.py with `--phase-tag phase1`. Result is
written to `phase1_scope_filter.signaling_sanity_check`.

**Forbidden in Phase 1:**
- Querying UE_Trace_log
- Querying for content beyond procedure presence + count + timestamps

### Step 5 — Resolve ambiguities

List any remaining unclear items in `scope_filter.ambiguities[]`.

**Hard rule:** `ambiguities` MUST be empty before Phase 2 starts. If non-empty,
HALT and ask the engineer to clarify.

### Step 6 — Write scope_filter to state file

Atomic write with `completed_at` timestamp. Use the format in
`references/scoping-checklist.md` for the exact JSON shape.

---

## Anti-Hallucination

- `procedure` and `rat` may be inferred from engineer description (those are
  facts the engineer states).
- `layers`, `key_timers`, `initiating_message` come from `spec_query.py`
  output — NEVER from pre-trained memory.
- `signaling_sanity_check.event_count`, `first_ts`, `last_ts` come from
  `log_query.py` output — NEVER fabricated.

If a field cannot be filled from tool output, leave it `null` and add an
entry to `ambiguities[]` — do not invent.

---

## What this skill does NOT do

- ❌ Does NOT query `UE_Trace_log` (forbidden in Phase 1)
- ❌ Does NOT search source code
- ❌ Does NOT use static spec reference files (those don't exist in v5)
- ❌ Does NOT propose a root cause
- ❌ Does NOT build a fault tree
- ❌ Does NOT generate hypotheses

Output is `scope_filter`. Root cause discovery is FTA's job (later skills).
