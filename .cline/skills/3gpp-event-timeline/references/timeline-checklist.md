# Event Timeline Checklist (Phase 2) — v6

## Preconditions
- [ ] State file exists; `phase1_scope_filter` populated and has empty `ambiguities`
- [ ] `meta.current_phase` is `"phase1"` or `"phase2_running"` (the latter is for refine re-runs)
- [ ] Read only the `phase1_scope_filter` slice

## Refine path handling
- [ ] If `phase1_scope_filter.user_refinements` is non-empty, incorporate
  refinement text into analysis context (narrowing time window or layers
  if the user specified)

## Get expected flow
- [ ] Invoke `3gpp-spec-retrieval` with `operation=lightweight_procedure`, `need=ecf`
- [ ] Verify `expected_flow[]` non-empty (halt if empty)
- [ ] Verify `expected_flow_source` written to state file

## Retrieve signaling timeline
- [ ] Invoke `3gpp-log-queries` with `phase_tag=phase2`, `table=UE_3gpp_signaling_log`
- [ ] Keywords are `expected_flow[].message` values
- [ ] Time window from `scope_filter.time_window`
- [ ] Layers from `scope_filter.layers`
- [ ] Verify tool exit code 0

## Classify events
- [ ] Each retrieved event labeled: normal / anomaly / consequence / symptom
- [ ] `earliest_anomaly` captured (or null if none)

## Identify missing events
- [ ] For each spec-defined message not in retrieved rows: append to `missing_events[]`

## v6 NEW: Build top_event_candidates[]
- [ ] Identify all symptom-class events in time order
- [ ] Rank 1 (primary): the LAST symptom in chronological order
- [ ] Rank 2-3 (alternatives): earlier symptoms that are defensible
  (distinct procedure outcome, distinct signaling evidence, different
  layer/cause/phase from primary)
- [ ] Each candidate has: rank, is_primary, event, timestamp, layer,
  evidence (one-line excerpt), confidence (HIGH/MEDIUM/LOW), rejection_reason
  (null for primary, specific reason for alternatives)
- [ ] List has 1, 2, or 3 entries — NEVER padded with invented alternatives
- [ ] Confidence assignment follows: HIGH (rich+explicit), MEDIUM (partial
  or strong absence), LOW (sparse or indirect)

## Assess log coverage
- [ ] `log_coverage` = rich | partial | sparse (per ratio)

## Ambiguity handling
- [ ] If sparse AND no HIGH-confidence candidate, still produce candidates
  (with LOW confidence); add note to ambiguities; do NOT halt
  (Checkpoint A handles user choice)

## Hard NOT-do checks
- [ ] No UE_Trace_log queries
- [ ] No code search invoked
- [ ] `phase2_ecf.top_event` left as `null` (Checkpoint A skill fills this)
- [ ] No fake alternatives added to candidates list
- [ ] No root cause proposed
- [ ] No hypotheses generated
- [ ] No fix recommendations

## Final state-file write
- [ ] `phase2_ecf.completed_at` set
- [ ] `phase2_ecf.top_event = null` (not yet selected)
- [ ] `observable_symptoms` fully populated
- [ ] `top_event_candidates` populated with 1-3 ranked entries
- [ ] `user_confirmation = null`
- [ ] `meta.current_phase` set to `"phase2_running"` (workflow will then
  trigger `3gpp-top-event-confirmation` which advances state)
- [ ] Atomic write completed
