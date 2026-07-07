# Scoping Checklist (Phase 1)

## Read state file
- [ ] Read `<workspace>/.rca/current_state_path.txt` → STATE_PATH
- [ ] Read `STATE_PATH` → extract `meta.engineer_input`, `meta.tool_dir`

## Extract from engineer description
- [ ] UE model / chipset / firmware (note in ambiguities if missing)
- [ ] RAT identified ("LTE", "5G NR", "NR-NSA", "WCDMA")
- [ ] Band(s) identified
- [ ] Procedure identified (e.g. "Intra-AMF 5G Handover", "LTE Initial Attach")
- [ ] Failure symptom captured (e.g. "drops to No Service", "Attach Reject #11")
- [ ] Reproducibility classified ("always" or "intermittent ~X%")
- [ ] Time window estimate (or default to first 10s after trigger)

## IS/IS-NOT reasoning
- [ ] WHAT column filled (failing procedure)
- [ ] WHAT NOT column filled (similar procedures that work)
- [ ] WHERE column filled
- [ ] WHERE NOT column filled
- [ ] WHEN column filled
- [ ] WHEN NOT column filled
- [ ] EXTENT column filled
- [ ] EXTENT NOT column filled
- [ ] Discriminator identified (biggest gap)

## Spec retrieval (lightweight_procedure, need=is_is_not)
- [ ] Invoked 3gpp-spec-retrieval skill
- [ ] Spec query returned non-empty (else halt with ambiguity)
- [ ] `phase1_scope_filter.spec_lookup` populated by tool
- [ ] `primary_layers` copied to `scope_filter.layers`

## Optional signaling sanity check
- [ ] Determined whether sanity check is needed (per Step 4 trigger conditions)
- [ ] If yes: invoked 3gpp-log-queries skill with phase_tag=phase1
- [ ] If yes: `phase1_scope_filter.signaling_sanity_check` populated

## Ambiguity resolution
- [ ] All ambiguities listed in `scope_filter.ambiguities[]`
- [ ] If non-empty: HALT and ask engineer

## Final state-file write
- [ ] `phase1_scope_filter.completed_at` set
- [ ] All required fields present (procedure, rat, layers, layers_excluded,
  condition, time_window, discriminator, reproducibility, ambiguities)
- [ ] Atomic write completed
- [ ] Verified state file still valid JSON after write

## Hard NOT-do checks
- [ ] No `UE_Trace_log` queries issued
- [ ] No code search invoked
- [ ] No root cause proposed
- [ ] No fault tree built
- [ ] No hypotheses generated
- [ ] No fix recommendations
