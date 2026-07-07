# FTA Cross-Reference Checklist (Phase 3.4) — v6

## Preconditions
- [ ] `iteration_id` provided
- [ ] `fta_iterations[iteration_id - 1].base_events` exists (may be empty)
- [ ] `fta_iterations[iteration_id - 1].hybrid_tree` available for upstream lookup
- [ ] `meta.current_phase == "iteration_<N>_running"`

## Empty base_events case
- [ ] If `base_events` is empty: write empty `cross_reference_findings: []` and return

## For each confirmed base event

### Step 1 — find_commanded_values
- [ ] Collect upstream messages (from parent branch or iteration input_top_event for code-only iters)
- [ ] Invoke `3gpp-spec-retrieval find_commanded_values`
- [ ] If empty: write finding with empty list + note, move on
  (Phase 3.5 will classify as ABSENCE or TIMER_EXPIRY)

### Step 2 — Commanded value extraction
For each commanded IE:
- [ ] Invoke `3gpp-log-queries phase3_cross_ref` against signaling table with `return_ie_values=true`
- [ ] If empty: append to `open_items[]`, do NOT fabricate

### Step 3 — find_implementation
- [ ] Invoke `3gpp-code-retrieval find_implementation`
- [ ] If `found: false`: append to open items, do NOT fabricate

### Step 4 — Actual value extraction
- [ ] Invoke `3gpp-log-queries phase3_cross_ref` against trace table with `return_ie_values=true`
- [ ] Keywords from Step 3 output (literal log macros only)
- [ ] If empty: append to open items

### Step 5 — Compare and classify
- [ ] Compute delta (numeric or categorical)
- [ ] Apply significance threshold (dBm: |Δ|>3dB; timer: |Δ|>10%; bool/enum: any)
- [ ] If significant: `root_cause_class = "VALUE_DISCREPANCY"`
- [ ] If matches: `root_cause_class = null` (Phase 3.5 will set ABSENCE)
- [ ] Document threshold used

### Step 6 — Record implementation location
- [ ] `implementation_location` from Step 3 `implementation_files[0]`

### Step 7 — Append to state file
- [ ] New entry in `fta_iterations[iter-1].cross_reference_findings[]`
- [ ] `queried_at` timestamp set
- [ ] `interpretation` is a 1-2 sentence description using only populated values

## Iteration-specific
- [ ] All output written to `fta_iterations[iteration_id - 1].cross_reference_findings[]`
- [ ] All audit entries tagged with current `iteration_id`

## Hard NOT-do checks
- [ ] No values fabricated when tool extraction empty
- [ ] No Gate A or Gate B calls (cross_ref tag only)
- [ ] No `expand_failure_modes` calls
- [ ] No `skeleton` calls
- [ ] No root cause synthesis (Phase 3.5's job)
- [ ] No modifications to other iterations

## Final state-file write
- [ ] One `cross_reference_findings` entry per confirmed base event
  (even if commanded_value_ies was empty)
- [ ] All entries have base_event_id, queried_at, commanded_ie_lookup
- [ ] Discrepancy entries have commanded_value, actual_value, delta,
  root_cause_class, implementation_location, interpretation
- [ ] `meta.current_phase` NOT changed
- [ ] Atomic write completed
