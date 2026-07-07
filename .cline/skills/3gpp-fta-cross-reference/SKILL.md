---
name: 3gpp-fta-cross-reference
description: >
  Phase 3.4 of the 3GPP UE RCA pipeline v6 — per-iteration cross-reference.
  Accepts iteration_id parameter. For each confirmed base event in
  fta_iterations[iteration_id - 1].base_events, identify network-COMMANDED
  IE values from upstream signaling and compare against the UE's ACTUAL
  applied values from trace logs. A discrepancy is the root cause class
  VALUE_DISCREPANCY. Calls 3gpp-spec-retrieval (find_commanded_values),
  3gpp-log-queries (cross_ref signaling for commanded, cross_ref trace for
  actual, both with return_ie_values), and 3gpp-code-retrieval
  (find_implementation for actual-value log macros). Writes findings to
  fta_iterations[iteration_id - 1].cross_reference_findings[]. Triggers:
  "cross-reference for iteration N", "find value discrepancies for iteration",
  "Phase 3.4 for iteration".
---

# 3GPP Phase 3.4 — Cross-Reference (v6, per iteration)

## Role

For each confirmed base event in the current iteration, compare commanded
value (signaling) vs actual value (trace). v4/v5 critical mechanism for
finding VALUE_DISCREPANCY root causes; preserved verbatim in v6 with
iteration scoping.

## v6 Change from v5

Accepts `iteration_id`. Reads `fta_iterations[iter-1].base_events` and
writes `fta_iterations[iter-1].cross_reference_findings[]`.

For iterations ≥ 2 (code-only fallback often), `find_commanded_values`
may return empty more often — that's fine, the finding records empty
commanded_value_ies and Phase 3.5 will classify as ABSENCE.

## Hard constraints

1. Tool calls allowed:
   - `3gpp-spec-retrieval` (find_commanded_values operation only)
   - `3gpp-log-queries` (phase3_cross_ref tag, EITHER table)
   - `3gpp-code-retrieval` (find_implementation operation)
2. Tool calls FORBIDDEN:
   - `3gpp-spec-retrieval skeleton / extract_ies / lightweight_procedure / generate_hypotheses`
   - `3gpp-code-retrieval bind_module / expand_failure_modes`
   - `3gpp-log-queries phase1/phase2/phase3_gate_a/phase3_gate_b`
3. All audit entries tagged with `iteration_id`

## Preconditions

- `iteration_id` provided
- `fta_iterations[iteration_id - 1].base_events` exists (may be empty if
  all rejected — in which case this skill does nothing and returns)
- `meta.current_phase == "iteration_<iteration_id>_running"`

## Output

Writes to `fta_iterations[iteration_id - 1].cross_reference_findings[]`,
one entry per confirmed base event:

```json
{
  "base_event_id": "P2.2",
  "queried_at": "<ISO>",
  "commanded_ie_lookup": {...},
  "commanded_value": {...} | null,
  "actual_value": {...} | null,
  "delta": "..." | null,
  "root_cause_class": "VALUE_DISCREPANCY" | null,
  "implementation_location": "..." | null,
  "interpretation": "..."
}
```

If no commanded-value IEs: entry with empty list + note; Phase 3.5
classifies as ABSENCE or TIMER_EXPIRY.

---

## Execution

If `base_events` is empty: nothing to do; write
`cross_reference_findings: []` and return.

Otherwise, for each entry in `base_events`:

### Step 1 — Identify commanded-value IEs
Collect upstream messages from parent branch's `mandatory_messages`.
For iterations ≥ 2 with code-only fallback, parent branch may not exist —
use the iteration's `input_top_event` context instead.

```
Use the 3gpp-spec-retrieval skill with:
  operation: find_commanded_values
  base_event_name: <base_event.description>
  base_event_layer: <base_event.layer>
  upstream_signaling_messages: <list>
```

If empty: record finding with `commanded_value_ies: []` + note; move on.

### Step 2 — For each commanded IE, extract commanded value (signaling)
```
Use the 3gpp-log-queries skill with:
  phase_tag: phase3_cross_ref
  table: UE_3gpp_signaling_log
  keywords: [<commanded_ie.message>]
  ie_names: [<commanded_ie.ie_name>]
  time_window: <scope_filter.time_window>
  return_ie_values: true
  hypothesis_id: <base_event.id>
```

If extraction empty: append to `open_items[]`, do NOT fabricate.

### Step 3 — Find actual-value log macros (code)
```
Use the 3gpp-code-retrieval skill with:
  operation: find_implementation
  hypothesis_cause: <description of expected UE action>
  spec_ie_names: [<commanded_ie.ie_name>]
  scope_procedure: <scope_filter.procedure>
  scope_layer: <base_event.layer>
```

If `found: false`: mark unverifiable, append to open items.

### Step 4 — Extract actual value from trace
```
Use the 3gpp-log-queries skill with:
  phase_tag: phase3_cross_ref
  table: UE_Trace_log
  keywords: <from Step 3 log_keywords>
  log_tags: <from Step 3 log_tags>
  time_window: <scope_filter.time_window>
  return_ie_values: true
  hypothesis_id: <base_event.id>
```

If empty: append to open items.

### Step 5 — Compare and classify

```
delta = compute_numeric_delta(commanded.value, actual.value)
       OR categorical_delta if non-numeric

if delta is significant (threshold per IE type):
  root_cause_class = "VALUE_DISCREPANCY"
else:
  root_cause_class = null  (Phase 3.5 will set ABSENCE)
```

**Significance:** dBm |Δ|>3dB; timer |Δ|>10%; boolean/enum any. Document threshold.

### Step 6 — Record implementation location
From Step 3 `implementation_files[0]`.

### Step 7 — Append to state file
Atomic write of new entry in `fta_iterations[iter-1].cross_reference_findings[]`.

---

## Anti-Hallucination

- Commanded IE names ONLY from `find_commanded_values` output
- Commanded values ONLY from log_query.py cross_ref signaling extractions
- Actual-value log keywords ONLY from `find_implementation` output
- Actual values ONLY from log_query.py cross_ref trace extractions
- Implementation file paths from code_search.py output
- All audit entries tagged with `iteration_id`
- NEVER fabricate values, deltas, or interpretations

---

## What this skill does NOT do (HARD)

- ❌ Does NOT determine the final root_cause_class (Phase 3.5's job)
- ❌ Does NOT generate fixes
- ❌ Does NOT call Gate A or Gate B operations (different phase tags)
- ❌ Does NOT fabricate values when extraction is empty
- ❌ Does NOT skip base events
- ❌ Does NOT touch other iterations' findings

See `references/cross-reference-checklist.md`.
