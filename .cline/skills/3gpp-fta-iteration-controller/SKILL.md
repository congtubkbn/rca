---
name: 3gpp-fta-iteration-controller
description: >
  Checkpoint B handler — after each FTA iteration completes (Phase 3.5), compute
  termination signals, derive an agent recommendation (dig_deeper | accept_terminal
  | abort), present the iteration summary + recommendation to the user, capture
  the user's decision, and route the pipeline accordingly. On dig_deeper, set up
  the next iteration with the user-selected base event as input top event. On
  accept_terminal, synthesize phase3_root_cause_chain across all iterations. On
  abort, terminate with rejection. Uses no retrieval tools — pure synthesis and
  state file update. D4: user override of agent recommendation requires explicit
  confirmation prompt. Triggers: "Checkpoint B for iteration N", "iteration
  controller", "decide dig deeper or accept terminal", "synthesize causal chain".
---

# 3GPP FTA Iteration Controller — Checkpoint B (v6 NEW)

## Role

After `3gpp-fta-root-cause` writes the iteration-local root cause, this skill:
1. Computes termination signals
2. Derives an `agent_recommendation`
3. Presents Checkpoint B to the user
4. Captures the user's decision
5. Routes the pipeline (next iteration / terminal synthesis / abort)

This skill is invoked twice per Checkpoint B interaction:
1. **PRESENT mode** — after `3gpp-fta-root-cause` completes for iteration N.
   Computes signals, renders prompt, halts.
2. **RECORD mode** — after user responds via `/rca <option>`. Workflow
   re-invokes the skill; updates state and dispatches.

## Hard constraints

- NO tool calls (no spec/code/log)
- NO new keywords introduced
- NO modification of iteration_root_cause
- NO synthesis of root causes the iteration didn't produce
- ALL recommendation logic is mechanical over state file data

## Preconditions

- `meta.current_phase` is one of:
  - `"iteration_<N>_running"` (3gpp-fta-root-cause just finished) → enter PRESENT mode
  - `"iteration_<N>_pending_decision"` (user responding) → enter RECORD mode
- `fta_iterations[N-1].iteration_root_cause` is populated (note: array is 0-indexed,
  iteration_id is 1-indexed, so iteration_id=N is at fta_iterations[N-1])
- For RECORD mode: workflow has parsed user response and supplies user_action

---

## PRESENT mode (first invocation)

### Steps

1. Read state file slice: `fta_iterations[current_iteration_id - 1]`
   (call this `iter` below)
2. Compute termination signals (boolean flags) over `iter`:

```
termination_signals = {
  "spec_skeleton_returned_empty_and_code_only_no_failure_modes":
    iter.hybrid_tree.spec_skeleton_returned_empty == true
    AND len([fm for fm in expand_failure_mode results]) == 0,

  "single_branch_tree":
    len(iter.hybrid_tree.branches) == 1
    AND all(branch.children is empty for branch in iter.hybrid_tree.branches),

  "find_implementation_returned_same_file_as_prior_iteration":
    iter.iteration_id > 1
    AND iter.iteration_root_cause.implementation_location ==
        fta_iterations[iter.iteration_id - 2].iteration_root_cause.implementation_location,

  "no_commanded_value_ies_relevant":
    all(finding.commanded_ie_lookup.commanded_value_ies == []
        for finding in iter.cross_reference_findings),

  "iteration_budget_near_exhaustion":
    iter.iteration_id >= meta.iteration_budget - 1,

  "all_base_events_rejected":
    len(iter.base_events) == 0 AND len(iter.rejected) > 0,

  "iteration_open":
    len(iter.open_items) > 0 AND len(iter.base_events) == 0,
}
```

3. Apply recommendation logic (in order — first match wins):

```
if termination_signals.all_base_events_rejected:
  rec_action = "abort"
  rec_id = null
  rec_rationale = "All hypotheses rejected at Gate B; cannot proceed"

elif termination_signals.iteration_open:
  rec_action = "abort"
  rec_id = null
  rec_rationale = "Insufficient log coverage; capture more trace and re-run"

elif count(termination_signals where True) >= 2:
  rec_action = "accept_terminal"
  rec_id = null
  rec_rationale = "Reached implementation primitives (multiple termination signals); further drilling beyond automated RCA scope"

elif termination_signals.iteration_budget_near_exhaustion:
  rec_action = "accept_terminal"
  rec_id = null
  rec_rationale = "Approaching iteration budget; halt before runaway"

elif iter.iteration_root_cause.root_cause_class == "VALUE_DISCREPANCY":
  # Find the cause-side base event from base_event_chain
  cause_be = first base_event in iter.iteration_root_cause.base_event_chain
             where relationship starts with "cause_of_"
  if cause_be is null:
    cause_be = first base_event (single-event case)
  rec_action = "dig_deeper"
  rec_id = cause_be.id
  rec_rationale = "VALUE_DISCREPANCY found at " + cause_be.id +
                  "; dig deeper to find code-level mechanism"

elif iter.iteration_root_cause.root_cause_class == "MULTI_CAUSE":
  # Pick highest-confidence base event
  best_be = max(iter.base_events, key=lambda be: confidence_to_int(be.confidence))
  rec_action = "dig_deeper"
  rec_id = best_be.hypothesis_id
  rec_rationale = "Multiple base events confirmed; highest-confidence selected for further analysis"

elif iter.iteration_root_cause.root_cause_class == "ABSENCE":
  if iter.iteration_id == 1:
    only_be = iter.base_events[0]   # ABSENCE typically has one
    rec_action = "dig_deeper"
    rec_id = only_be.hypothesis_id
    rec_rationale = "ABSENCE at depth 1; dig deeper to find code mechanism"
  else:
    rec_action = "accept_terminal"
    rec_id = null
    rec_rationale = "ABSENCE at depth >= 2; iteration root cause is at code level"

elif iter.iteration_root_cause.root_cause_class == "TIMER_EXPIRY":
  if iter.iteration_root_cause.implementation_location is not null:
    rec_action = "accept_terminal"
    rec_id = null
    rec_rationale = "Timer expiry with identified code location; terminal"
  else:
    timer_be = iter.base_events[0]
    rec_action = "dig_deeper"
    rec_id = timer_be.hypothesis_id
    rec_rationale = "Timer expiry without code location; dig into layer below timer"

else:
  rec_action = "accept_terminal"
  rec_id = null
  rec_rationale = "Iteration root cause not classified for drilling; accepting as terminal"
```

4. Write `iter.agent_recommendation`:

```json
{
  "computed_at": "<ISO>",
  "action": "<rec_action>",
  "recommended_base_event_id": "<rec_id>",
  "rationale": "<rec_rationale>",
  "termination_signals_detected": [<list of signals that are true>]
}
```

5. Render the Checkpoint B prompt per the format in
   `_shared/checkpoint-presentation-formats.md` (Section "Checkpoint B")

6. Update `meta.current_phase = "iteration_<N>_pending_decision"`

7. HALT — return to workflow

---

## RECORD mode (second invocation, after user response)

### Inputs from workflow
- `user_action` — one of: `dig_deeper`, `accept_terminal`, `abort`,
  `confirm_override`, `cancel`, `unparseable`
- `user_selected_id` — for `dig_deeper`: the base event id the user picked
- `pending_override` — bool, true if user previously picked an option that
  differed from agent recommendation and is now confirming

### Steps

1. Read state file slice: `fta_iterations[current_iteration_id - 1]` (call `iter`)
2. Dispatch on `user_action`:

#### Action: `dig_deeper` (first time, before override confirmation)

```
if user_selected_id != iter.agent_recommendation.recommended_base_event_id
   OR iter.agent_recommendation.action == "accept_terminal":
  # This is an override. Emit override-confirmation prompt and HALT.

  Render: """
  OVERRIDE CONFIRMATION
  You requested:     dig deeper into <user_selected_id>
  Agent recommended: <iter.agent_recommendation.action> <recommended_id>
  Reason agent gave: <iter.agent_recommendation.rationale>

  Are you sure?
    confirm override
    cancel
  """

  # Record pending state so RECORD-mode-2nd-call knows
  iter.pending_override = {
    "user_selected_id": user_selected_id,
    "at": <ISO>
  }
  # Stay in iteration_<N>_pending_decision
  HALT

else:
  # User confirmed the agent's recommendation. Proceed to dig deeper.
  goto Action: confirm_override (below)
```

#### Action: `confirm_override` (or aligned dig_deeper)

The user has agreed to dig deeper into `selected_id`.

```
1. Look up the selected base event in iter.base_events:
   selected_be = find_by_hypothesis_id(iter.base_events, selected_id)
   if selected_be is null:
     return error "Base event <selected_id> not in iteration <N>"

2. Determine if this was an override:
   was_override = (
     selected_id != iter.agent_recommendation.recommended_base_event_id
     OR iter.agent_recommendation.action == "accept_terminal"
   )

3. Write iter.user_decision:
   {
     decided_at: <ISO>,
     action: "dig_deeper",
     selected_base_event_id: selected_id,
     selected_base_event_name: selected_be.name (from iter.hybrid_tree branches/children),
     overrode_recommendation: was_override,
     override_confirmation_received: was_override,
     rationale: ""
   }

4. Append to user_decisions[]:
   {
     checkpoint: "B-iteration-<N>",
     decided_at: <ISO>,
     action: "dig_deeper",
     selected_base_event_id: selected_id,
     selected_base_event_name: selected_be.name,
     agent_recommendation: iter.agent_recommendation.action + " " + (iter.agent_recommendation.recommended_base_event_id or ""),
     overrode_recommendation: was_override,
     rationale: ""
   }

5. Check iteration budget:
   if iter.iteration_id >= meta.iteration_budget:
     # User pushed past budget. Allow it but note in audit. The next
     # iteration's controller will recommend accept_terminal again.

6. Start iteration N+1:
   meta.current_iteration_id = iter.iteration_id + 1
   meta.current_phase = "iteration_<N+1>_running"

   fta_iterations.append({
     iteration_id: meta.current_iteration_id,
     parent_iteration_id: iter.iteration_id,
     parent_base_event_id: selected_id,
     started_at: <ISO>,
     completed_at: null,
     input_top_event: {
       event: selected_be.name,
       source: "fta_iterations[" + iter.iteration_id + "].base_events[" + selected_id + "]",
       spec_anchored: false   /* iterations >= 2 are usually not spec-anchored */
     },
     hybrid_tree: null, pruned_branches: [], base_events: [],
     rejected: [], open_items: [], cross_reference_findings: [],
     iteration_root_cause: null,
     agent_recommendation: null,
     user_decision: null
   })

7. Cross-iteration keyword carry-over audit:
   keyword_provenance_audit.append({
     keyword: selected_be.name,
     type: "iteration_top_event_carryover",
     iteration_id: meta.current_iteration_id,
     used_by: "Iteration " + meta.current_iteration_id + " input top event",
     source: "Iteration " + iter.iteration_id + " base event " + selected_id,
     cross_iteration_boundary: true,
     verified: true
   })

8. Atomic write.
```

After this, workflow dispatches iteration N+1 (build-tree → evaluate → cross-ref → root-cause → controller).

#### Action: `accept_terminal`

The user is accepting the current iteration's root cause as final.

```
1. Write iter.user_decision:
   {
     decided_at: <ISO>,
     action: "accept_terminal",
     selected_base_event_id: null,
     selected_base_event_name: null,
     overrode_recommendation: (iter.agent_recommendation.action != "accept_terminal"),
     override_confirmation_received: (iter.agent_recommendation.action != "accept_terminal"),
     rationale: ""
   }

2. If override: ensure override confirmation was received. If not, emit
   override prompt:
   """
   You requested:    accept terminal
   Agent recommended: dig deeper into <agent_recommended_id>

   Confirm override?
     confirm override
     cancel
   """
   HALT.

3. Append to user_decisions[]:
   {
     checkpoint: "B-iteration-<N>",
     action: "accept_terminal",
     ...
   }

4. Synthesize phase3_root_cause_chain:

   causal_chain = []
   for each iteration in fta_iterations (in order):
     entry = {
       iteration: iteration.iteration_id,
       top_event: iteration.input_top_event.event,
       selected_cause_id: iteration.user_decision.selected_base_event_id
                         if iteration.user_decision.action == "dig_deeper"
                         else null,
       selected_cause_name: ...,
       relationship: "iteration leading to next" if next iteration exists
                     else "terminal",
       iteration_root_cause_class: iteration.iteration_root_cause.root_cause_class
     }
     causal_chain.append(entry)

   phase3_root_cause_chain = {
     synthesized_at: <ISO>,
     iterations_traversed: [i.iteration_id for i in fta_iterations],
     terminal_iteration_id: current_iteration_id,
     termination_reason: "User accepted terminal at iteration <N>",
     causal_chain: causal_chain,
     final_root_cause: iter.iteration_root_cause,  /* copy */
     user_override_count: <will be computed by orchestrator finalize>,
     high_disagreement_run: <will be computed by orchestrator finalize>
   }

5. meta.current_phase = "phase4_finalizing"
6. Atomic write.
```

After this, workflow dispatches `3gpp-rca-orchestrator` finalize mode.

#### Action: `abort`

```
1. Write iter.user_decision:
   {
     decided_at: <ISO>,
     action: "abort",
     selected_base_event_id: null,
     ...
     overrode_recommendation: (iter.agent_recommendation.action != "abort"),
     ...
   }
2. Append to user_decisions[]
3. Write phase3_root_cause_chain with termination_reason="User aborted at iteration <N>",
   final_root_cause = iter.iteration_root_cause (best effort even though
   user rejected it)
4. Write phase4_rca_report = {
     finalized_at: <ISO>,
     iteration_count: <N>,
     report_path: null,
     termination_reason: "User aborted at iteration <N>"
   }
5. meta.current_phase = "complete"
6. meta.finished_at = <ISO>

No final report file. (Could optionally produce a rejection report
listing what was found and what was rejected — but minimal v6 doesn't.)
```

#### Action: `cancel` (after override prompt was emitted)

User backed out of override.
```
1. Clear iter.pending_override
2. Re-render Checkpoint B prompt (workflow will re-invoke PRESENT mode logic)
   Or simpler: just stay in iteration_<N>_pending_decision and let the
   user re-respond.
```

#### Action: `unparseable`

Re-render Checkpoint B prompt with parse-error note.

3. Atomic write to state file.

---

## Override audit (D4 enforcement)

Every user_decision records:
- `overrode_recommendation` (bool)
- `override_confirmation_received` (bool — must be true if overrode=true)

The orchestrator's Phase 4 finalize counts overrides and sets
`high_disagreement_run = true` if ≥ 50% of decisions were overrides.

---

## Anti-Hallucination

- All inputs come from state file slices (no model-memory)
- Recommendation is mechanical logic over signals
- Causal chain synthesis copies existing fields, does not invent relationships
- The "relationship" labels in causal_chain are limited to:
  "iteration leading to next" or "terminal"
- Final root cause is copied verbatim from the terminal iteration

---

## What this skill does NOT do (HARD)

- ❌ No retrieval tool calls
- ❌ No modification of iteration_root_cause
- ❌ No invention of base events
- ❌ No interpretation of root_cause_class beyond mechanical recommendation logic
- ❌ No fix recommendations
- ❌ No bypass of override confirmation

See `references/checkpoint-b-checklist.md` for the audit checklist and
`references/recommendation-logic.md` for the full recommendation decision tree.
