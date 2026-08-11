---
name: 3gpp-fta-seed-init
description: >
  Seed a brand-new RCA state file directly from a top event the engineer
  already knows, skipping Phase 1 (scoping) and Phase 2 (event timeline +
  Checkpoint A). Writes a minimal state file and hands off to the existing
  /rca workflow, which resumes straight into FTA iteration 1. Use ONLY when
  the engineer explicitly states they already have a confirmed top event
  and wants to go directly to fault tree analysis. Do NOT use when no top
  event has been determined yet, when the engineer wants normal scoping/
  timeline analysis, or mid-pipeline (use the running /rca workflow
  instead). Triggers: "seed FTA with top event", "start FTA directly from
  this top event", "skip scoping, go straight to FTA", "create RCA state
  from a known top event", "bypass Checkpoint A with this top event".
---

# 3GPP FTA Seed-Init Skill — v6 (engineer-provided top event)

## Role

Create a new RCA state file from an engineer-supplied top event and scope
window, bypassing Phase 1/Phase 2/Checkpoint A entirely. Hands off to the
existing `/rca` workflow for everything from FTA iteration 1 onward — this
skill does NOT itself invoke any FTA skill.

## Hard constraints

- NO retrieval tool calls (no spec/code/log) — this skill only writes state.
- NO scoping or event-timeline logic — those sections are left absent, not
  approximated.
- NO inferred scope window — if the engineer does not supply one, HALT and
  ask. Never derive a default window from the top event's timestamp.
- NEVER invoke this skill if `.rca/current_state_path.txt` points at a
  state file whose `meta.current_phase != "complete"` without explicit
  engineer confirmation to overwrite.

## Inputs (from engineer, free text)

- `top_event_description` (required) — verbatim text describing the top
  event, e.g. "5G_HO_Execution_Failure — RRCReconfiguration with no
  following RAR at 14:02:12.50"
- `scope_window` (required) — a time bound as `{start_ms, end_ms}` or an
  equivalent timestamp range the engineer states in the request
- `procedure` (required) — 3GPP procedure name, e.g., "LTE RRC Connection Re-establishment"
- `rat` (required) — Radio Access Technology, e.g., "LTE"

If any is missing, do not proceed — see Step 1 below.

## Execution

### Step 1 — Validate inputs

- If `top_event_description` is missing or empty → HALT: "Need a top event
  description to seed FTA. What is the top event?"
- If `scope_window` is missing → HALT: "Need a time window (start/end) to
  bound Gate A log queries. What is the scope window?"
- If `procedure` or `rat` is missing → HALT: "Need procedure and rat to remain spec-anchored."

### Step 2 — Check for an in-progress run

1. Check whether `<workspace>/.rca/current_state_path.txt` exists.
2. If it exists, read the path and load `meta.current_phase` from that
   state file.
3. If `meta.current_phase != "complete"` → HALT: "An RCA run is already in
   progress (phase: `<current_phase>`, state file: `<path>`). Overwrite it,
   archive it, or cancel?" Wait for explicit engineer instruction before
   continuing.
4. If no file exists, or the existing one is `complete` → proceed.

### Step 3 — Generate Draft State File

1. Compute UTC timestamp: `TS=$(date -u +%Y%m%dT%H%M%SZ)`
2. Draft State file path: `<workspace>/.rca/draft_state_${TS}.json` (create `.rca/` directory if missing).
3. Write the draft state:

```json
{
  "meta": {
    "pipeline_version": "v6",
    "mode": "seed_and_run",
    "current_phase": "phase2_confirmed_via_seed",
    "current_iteration_id": 1,
    "iteration_budget": 5,
    "started_at": "<ISO from TS>",
    "finished_at": null,
    "engineer_input": "<verbatim top_event_description>",
    "db_tables": ["UE_3gpp_signaling_log", "UE_Trace_log"],
    "duckdb_path": "<resolved path>",
    "tool_dir": "<resolved path, default <workspace>/3gpp-tools/>"
  },
  "phase1_scope_filter": {
    "procedure": "<verbatim procedure>",
    "rat": "<verbatim rat>",
    "time_window": { "start_ms": <from scope_window>, "end_ms": <from scope_window> }
  },
  "fta_iterations": [
    {
      "iteration_id": 1,
      "parent_iteration_id": null,
      "parent_base_event_id": null,
      "started_at": "<ISO from TS>",
      "input_top_event": {
        "event": "<verbatim top_event_description>",
        "source": "ENGINEER_PROVIDED",
        "spec_anchored": true,
        "scope_window": { "start_ms": <from scope_window>, "end_ms": <from scope_window> }
      }
    }
  ],
  "engineer_inputs": [
    {
      "at": "<ISO from TS>",
      "input_id": "ei_1",
      "assertion": "<verbatim top_event_description>",
      "overrides": null
    }
  ],
  "user_decisions": [],
  "keyword_provenance_audit": []
}
```

Note: `phase2_ecf` is NOT written — absent, not faked. `phase1_scope_filter` IS written so downstream FTA skills remain spec-anchored.

### Step 4 — User Review & Edit

1. Print the generated JSON of the draft state to the chat.
2. Provide the absolute path to the draft state file to the engineer:
   > Draft state seeded at: `<draft_state_path>`. 
   > Please open this file in your IDE to review and edit it if necessary. 
   > Once you are done, reply "OK" or "Done" to finalize the state.
3. HALT and wait for the engineer's confirmation.

### Step 5 — Commit State & Hand off

1. After the engineer confirms, READ the draft state file back into memory.
2. Validate that it is a valid JSON file. If it fails parsing, tell the engineer:
   > Invalid JSON format. Please fix the syntax errors in the file and reply "OK" again. (HALT)
3. Ensure `spec_anchored` is still `true`. If not, warn the engineer but proceed if they insist.
4. Verify Python tool scripts exist (same check as orchestrator Phase 0):
   - `<tool_dir>/spec_query.py`
   - `<tool_dir>/code_search.py`
   - `<tool_dir>/log_query.py`
   - If any missing → HALT with "Tool dependency missing: `<name>`"
5. Write the validated draft state path to `<workspace>/.rca/current_state_path.txt`.
6. Tell the engineer:

> State finalized and locked (`<draft_state_path>`). Run `/rca` to continue into FTA
> iteration 1.

STOP. Do not invoke `3gpp-fta-build-tree` or any other FTA skill directly
— the `/rca` workflow's existing resume path (Step 1B, Case
`phase2_confirmed_via_seed`) owns that.

## What this skill does NOT do

- ❌ No retrieval calls (spec / code / log)
- ❌ No scope determination (that's `3gpp-scoping`, intentionally skipped)
- ❌ No timeline extraction (that's `3gpp-event-timeline`, intentionally skipped)
- ❌ No Checkpoint A presentation (intentionally skipped)
- ❌ No FTA work of any kind (that's `3gpp-fta-build-tree` onward, invoked
  by `/rca` on the next turn, not by this skill)
- ❌ No inferring a scope window when the engineer didn't supply one

## Anti-Hallucination

- `fta_iterations[0].input_top_event.event` is copied verbatim from the
  engineer's own words — never paraphrased, never embellished with details
  the engineer didn't state.
- `source: "ENGINEER_PROVIDED"` must never be changed to any other
  evidence tier by this or any other skill — see
  `_shared/keyword-provenance-rules.md` carve-out.
