---
name: 3gpp-top-event-confirmation
description: >
  Checkpoint A handler — present the user with the curated list of Top Event
  candidates produced by 3gpp-event-timeline (1-3 entries), capture the user's
  selection, and gate progression to FTA. Uses no retrieval tools — pure
  presentation and state file update. After receiving the user's response,
  writes phase2_ecf.top_event, user_confirmation, and a user_decisions[]
  entry; advances meta.current_phase to "phase2_confirmed". Triggers:
  "present top event candidates", "Checkpoint A", "confirm top event",
  "user selection for top event". Always invoked by the /rca workflow after
  3gpp-event-timeline completes.
---

# 3GPP Top Event Confirmation Skill — Checkpoint A (v6 NEW)

## Role

Implement the Checkpoint A user gate after Phase 2. Present 1-3 candidate
Top Events with evidence; capture the user's choice; update state file;
hand control back to the workflow.

This skill is invoked twice per Checkpoint A interaction:
1. **First invocation (PRESENT mode)** — after `3gpp-event-timeline`
   completes. Reads candidates, renders the checkpoint prompt, halts.
2. **Second invocation (RECORD mode)** — after user responds via
   `/rca <option>`. Workflow re-invokes the skill with the parsed user
   response; skill records the decision and updates state.

## Hard constraints

- NO tool calls (no spec/code/log)
- NO new keywords introduced
- NO interpretation of candidates beyond ranking by confidence
- NO override of user choice once received

## Preconditions

- `meta.current_phase` is one of:
  - `"phase2_running"` (just finished event-timeline) → enter PRESENT mode
  - `"phase2_pending_confirmation"` (user is responding) → enter RECORD mode
- `phase2_ecf.top_event_candidates[]` is populated (1-3 entries)
- `phase2_ecf.observable_symptoms` is populated

---

## PRESENT mode (first invocation)

### Steps

1. Read state file slices: `phase1_scope_filter`, `phase2_ecf.top_event_candidates`,
   `phase2_ecf.observable_symptoms.log_coverage`
2. Determine agent recommendation:
   - Default: confirm rank 1 (primary)
   - If primary confidence is LOW and any alternative is MEDIUM or HIGH,
     recommendation switches to that alternative (rare)
3. Render the Checkpoint A prompt per the format in
   `_shared/checkpoint-presentation-formats.md` (Section "Checkpoint A")
4. Update `meta.current_phase = "phase2_pending_confirmation"`
5. HALT — return to workflow which terminates the turn

The user will then type `/rca <option>`, the workflow parses it, and
re-invokes this skill in RECORD mode.

---

## RECORD mode (second invocation, after user response)

### Inputs from workflow
- `user_action` — one of: `confirm`, `use_alternative_2`, `use_alternative_3`,
  `refine`, `reject_and_restart`, `abort`
- `refinement_text` — present only if action is `refine`
- `selected_rank` — derived: 1 for confirm, 2 for use_alternative_2, etc.

### Steps

1. Read state file slice: `phase2_ecf.top_event_candidates[]`
2. Dispatch on `user_action`:

#### Action: `confirm` (rank 1)

```
phase2_ecf.top_event = (full record from top_event_candidates[0])
  — copy event, timestamp, layer, evidence into the canonical
    phase2_ecf.top_event structure (procedure inherited from scope)

phase2_ecf.user_confirmation = {
  confirmed_at: <ISO>,
  selected_rank: 1,
  overrode_recommendation: false,  /* agent recommended rank 1 */
  rationale: ""
}

user_decisions.append({
  checkpoint: "A",
  decided_at: <ISO>,
  action: "confirm_primary",
  selected_rank: 1,
  agent_recommendation: "confirm rank 1",
  overrode_recommendation: false,
  rationale: ""
})

meta.current_phase = "phase2_confirmed"
```

#### Action: `use_alternative_2` or `use_alternative_3`

```
selected = top_event_candidates[selected_rank - 1]

phase2_ecf.top_event = (full record from selected)

phase2_ecf.user_confirmation = {
  confirmed_at: <ISO>,
  selected_rank: <2 or 3>,
  overrode_recommendation: true,   /* agent recommended rank 1 */
  rationale: ""
}

user_decisions.append({
  checkpoint: "A",
  action: "use_alternative",
  selected_rank: <2 or 3>,
  agent_recommendation: "confirm rank 1",
  overrode_recommendation: true,
  ...
})

meta.current_phase = "phase2_confirmed"
```

Note: D4 says "override allowed with confirmation," but Checkpoint A
is a deliberate menu-pick, not an override of a specific
recommendation. The user explicitly picked rank 2 or 3 from the
displayed menu. No additional confirmation prompt is required at
Checkpoint A because there's no ambiguity about user intent — they
chose by rank number from the printed list.

#### Action: `refine: <text>`

The user wants to add information and re-run Phase 2.

```
1. Append the refinement text to phase1_scope_filter (e.g. update
   .condition or .ambiguities array, or add a new field
   .user_refinements[]). Concretely, write:
     phase1_scope_filter.user_refinements (append): {
       at: <ISO>,
       text: <refinement_text>
     }
2. Clear phase2_ecf and re-trigger 3gpp-event-timeline. The workflow
   detects this and re-runs the skill.
3. Set meta.current_phase = "phase2_running"
```

This skill does NOT directly re-run event-timeline; the workflow does
that on the next dispatch.

#### Action: `reject_and_restart`

```
1. Halt with prompt to user: "Please provide a fresh scope/description.
   The pipeline will restart Phase 1."
2. When user provides new info: clear phase1_scope_filter, phase2_ecf,
   and restart from 3gpp-scoping.
3. Set meta.current_phase = "phase1" (workflow will dispatch scoping again)
```

This is the rarest path. It indicates the original scope was wrong, not
just that the top event needs refinement.

#### Action: `abort`

```
phase4_rca_report = {
  finalized_at: <ISO>,
  iteration_count: 0,
  report_path: null,
  termination_reason: "User aborted at Checkpoint A"
}

meta.current_phase = "complete"
meta.finished_at = <ISO>
```

No final report generated. Pipeline terminates with rejection record.

#### Unparseable action

If the workflow could not parse the user's response, this skill is invoked
with `user_action = "unparseable"`. Re-render the Checkpoint A prompt with
a note: "Could not parse your response; please use one of the option
keywords listed below."

3. Atomic write to state file.

---

## Output

After RECORD mode completes, the workflow checks `meta.current_phase`:
- `phase2_confirmed` → workflow proceeds to start iteration 1
- `phase2_running` → workflow re-triggers event-timeline (refine path)
- `phase1` → workflow re-triggers scoping (reject and restart path)
- `complete` → workflow terminates with rejection (abort path)

---

## Anti-Hallucination

- Candidates come from `top_event_candidates[]` (produced by event-timeline)
- This skill MAY NOT invent additional candidates
- This skill MAY NOT modify candidate evidence or rejection_reasons
- Recommendation logic is mechanical (highest confidence, prefer primary
  unless explicitly weaker)

---

## What this skill does NOT do (HARD)

- ❌ No retrieval tool calls
- ❌ No new candidate generation
- ❌ No interpretation of evidence beyond confidence comparison
- ❌ No FTA work (next skill is 3gpp-fta-build-tree)
- ❌ No fix recommendations

See `references/checkpoint-a-checklist.md` for the audit checklist.
