# Phase 0 Init Checklist — v6

Run through this list when invoked in init mode. ALL items must be satisfied
before returning the state file path to the workflow.

## Inputs
- [ ] Engineer description received (non-empty string)
- [ ] DuckDB path identified (from user input or default workspace location)
- [ ] Tool directory identified (from user input or `<workspace>/3gpp-tools/`)
- [ ] Iteration budget set (default 5; user may override)

## Tool dependencies
- [ ] `<tool_dir>/spec_query.py` exists and is executable
- [ ] `<tool_dir>/code_search.py` exists and is executable
- [ ] `<tool_dir>/log_query.py` exists and is executable
- [ ] Python 3 available on PATH

## DB dependencies
- [ ] DuckDB tables `UE_3gpp_signaling_log` and `UE_Trace_log` are queryable

## State file creation
- [ ] Compute UTC timestamp
- [ ] Create `/tmp/rca_state_<TS>.json` (or platform equivalent)
- [ ] Write meta block with all fields including v6-specific:
  - `pipeline_version: "v6"`
  - `current_phase: "phase0"`
  - `current_iteration_id: 0`
  - `iteration_budget: 5`
- [ ] Initialize empty arrays: `user_decisions: []`, `fta_iterations: []`,
  `keyword_provenance_audit: []`
- [ ] Use atomic write (`.tmp` → `mv`)
- [ ] Verify file is valid JSON after write

## Workspace bookkeeping
- [ ] Create `<workspace>/.rca/` directory if missing
- [ ] Write state file absolute path to `<workspace>/.rca/current_state_path.txt`
- [ ] Verify path file readable

## State machine transition
- [ ] Update `meta.current_phase` from `"phase0"` to `"phase1"`
  (the workflow expects this transition so it can dispatch to `3gpp-scoping`)

## Return
- [ ] Return the state file path to the caller
- [ ] Confirm to user: "RCA pipeline v6 initialized. State file: <path>"

## Halt conditions
- Any missing tool script → halt
- DuckDB unreachable → halt
- Cannot write `/tmp/` or workspace → halt
- Engineer description empty → halt and ask user
