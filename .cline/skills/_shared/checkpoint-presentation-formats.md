# Checkpoint Presentation Formats — v6 NEW

This file specifies how the two user-facing checkpoints in v6 present
information to the engineer. Consistent formatting is critical for two
reasons:

1. **Anti-rubber-stamp.** The engineer must be able to see the evidence
   behind the agent's recommendation, not just the recommendation itself.
   Rich, structured presentation makes engaged review easier than blind
   acceptance.
2. **Override visibility.** When the engineer overrides the agent's
   recommendation, the override is recorded with rationale. The
   presentation format must make the agent's recommendation crisp enough
   that the engineer can articulate *why* they're overriding.

The two checkpoints use parallel structure: **Summary → Evidence → Options
→ Recommendation → Prompt.**

---

## Checkpoint A — Top Event Confirmation

Triggered at end of Phase 2 by `3gpp-top-event-confirmation` skill.

### Presentation template

```
═══════════════════════════════════════════════════════════════
CHECKPOINT A — TOP EVENT CONFIRMATION
═══════════════════════════════════════════════════════════════

Scope (Phase 1 summary):
  Procedure:        <scope_filter.procedure>
  RAT / Band:       <scope_filter.rat> / <scope_filter.bands>
  Reproducibility:  <scope_filter.reproducibility>
  Discriminator:    <scope_filter.discriminator>

Signaling coverage: <observable_symptoms.log_coverage>
Missing events:     <count from observable_symptoms.missing_events>

───────────────────────────────────────────────────────────────
TOP EVENT CANDIDATES
───────────────────────────────────────────────────────────────

[1] PRIMARY  (confidence: <HIGH | MEDIUM | LOW>)
    Event:      <event description>
    Timestamp:  <timestamp>
    Layer:      <layer>
    Evidence:   <one-sentence signaling evidence>

[2] ALTERNATIVE  (confidence: <LOW | MEDIUM>)
    Event:      <...>
    Timestamp:  <...>
    Evidence:   <...>
    Rejection reason (why agent did not pick this): <...>

[3] ALTERNATIVE  (confidence: <LOW>)
    Event:      <...>
    ...

(omit alternatives if no defensible alternatives exist; list will be
size 1 to 3)

───────────────────────────────────────────────────────────────
AGENT RECOMMENDATION:  Confirm [1] PRIMARY
   Rationale: <one-line rationale based on confidence + log_coverage>

───────────────────────────────────────────────────────────────
YOUR OPTIONS
───────────────────────────────────────────────────────────────

  confirm                  — accept the primary (recommended)
  use alternative N        — pick alternative [N] from the list above
  refine: <question/info>  — give the agent more info; Phase 2 re-runs
  reject and restart       — back to Phase 1 (rare; only if scope was wrong)
  abort                    — stop the RCA entirely

Please reply with one of the above options.
═══════════════════════════════════════════════════════════════
```

### How alternatives are generated (presentation rule)

The `3gpp-event-timeline` skill produces `top_event_candidates[]` with up to
**3 entries** (D3 = 3). Rule:

- `rank 1` = primary symptom (last observable failure in signaling)
- `rank 2-3` = next observable symptoms or rejected-but-defensible candidates,
  each with `rejection_reason`

If only one candidate is genuinely defensible, the list is size 1 and the
presentation simply omits the "ALTERNATIVE" sections — but the checkpoint
still happens. The engineer either confirms, refines, or aborts.

NEVER pad the candidate list with hallucinated alternatives to reach size 3.
Better to show 1 defensible candidate than 3 with two invented.

### User response parsing

| User reply contains... | Action |
|---|---|
| `confirm` or `1` or `accept` | Accept primary (rank 1) |
| `use alternative 2` or `alt 2` or `use 2` | Pick rank 2 |
| `use alternative 3` or `alt 3` or `use 3` | Pick rank 3 |
| `refine: <text>` or `refine <text>` | Re-run Phase 2 with appended user info |
| `reject and restart` or `restart` | Back to Phase 1 — ask engineer for new info first |
| `abort` or `stop` or `cancel` | Halt pipeline; mark `meta.current_phase = "complete"` with rejection |

Ambiguous responses → ask the engineer to repeat with a clearer phrase.

### State updates after Checkpoint A

```json
"phase2_ecf.top_event": <selected candidate's full record (event/timestamp/layer/etc.)>,
"phase2_ecf.user_confirmation": {
  "confirmed_at": "<ISO now>",
  "selected_rank": <1|2|3>,
  "overrode_recommendation": <true if selected_rank != 1>,
  "rationale": "<from user 'refine' or empty>"
},
"user_decisions[]": append {
  "checkpoint": "A",
  ...
},
"meta.current_phase": "phase2_confirmed"
```

---

## Checkpoint B — Iteration Decision (one per FTA iteration)

Triggered at end of each FTA iteration by `3gpp-fta-iteration-controller`.

### Presentation template

```
═══════════════════════════════════════════════════════════════
CHECKPOINT B — ITERATION <N> DECISION
═══════════════════════════════════════════════════════════════

Iteration <N> top event:  <iteration's input_top_event.event>
Iteration <N> result:

  Root cause class:  <VALUE_DISCREPANCY | ABSENCE | TIMER_EXPIRY | MULTI_CAUSE | OPEN | ALL_REJECTED>

  Failing phase:     <iteration_root_cause.failing_phase>
  Pruned phases:     <comma-separated list>

  Base events confirmed (Gate B):
    <id> <name> — <layer> — <one-line evidence>
    <id> <name> — <layer> — <one-line evidence>

  Cross-reference findings:
    <base_event_id>:
      Commanded:  <commanded_value if present>
      Actual:     <actual_value if present>
      Delta:      <delta if present>
      Class:      <VALUE_DISCREPANCY or N/A>

  Iteration root cause:
    <iteration_root_cause.description>
    Implementation: <implementation_location>
    Spec violation: <spec_violation>

  Causal chain so far (iterations 1..N):
    <iter 1 top event> ← <iter 1 selected cause>
                       ← <iter 2 selected cause>
                       ← <iter N current finding>

───────────────────────────────────────────────────────────────
AGENT RECOMMENDATION:  <dig_deeper P2.2 | accept_terminal | abort>
   Rationale: <2-line rationale based on iteration findings>
   Termination signals detected: <list, or "none">

───────────────────────────────────────────────────────────────
YOUR OPTIONS
───────────────────────────────────────────────────────────────

  dig deeper into <base_event_id>   — start iteration <N+1> with that
                                       base event as the new top event
  accept                            — accept this iteration's root cause
                                       as terminal; proceed to final report
  abort                             — stop the RCA entirely

  (Iteration budget: <N> of <iteration_budget> used)

If you choose to dig deeper into a base event the agent did NOT
recommend, you will be asked to confirm the override.

Please reply with one of the above options.
═══════════════════════════════════════════════════════════════
```

### How `agent_recommendation` is computed

`3gpp-fta-iteration-controller` evaluates termination signals after each
iteration:

| Signal | Detection |
|---|---|
| `spec_skeleton_returned_empty_and_code_only_no_failure_modes` | `hybrid_tree.spec_skeleton_returned_empty == true` AND `failure_modes[]` is empty |
| `single_branch_tree` | `hybrid_tree.branches` has exactly 1 entry AND no children added |
| `find_implementation_returned_same_file_as_prior_iteration` | Code search converged on same file across 2+ iterations |
| `no_commanded_value_ies_relevant` | Phase 3.4 found `commanded_value_ies: []` |
| `iteration_budget_near_exhaustion` | `current_iteration_id >= iteration_budget - 1` |
| `all_base_events_rejected` | `base_events[]` is empty AND `rejected[]` is not empty |
| `iteration_open` | `open_items[]` is non-empty AND `base_events[]` is empty |

Recommendation logic:

```
if all_base_events_rejected:
  recommend "abort"
  rationale = "All hypotheses rejected at Gate B; cannot proceed"

elif iteration_open:
  recommend "abort"
  rationale = "Insufficient log coverage; capture more trace and re-run"

elif >=2 termination signals fire:
  recommend "accept_terminal"
  rationale = "Reached implementation primitives; further drilling beyond automated RCA scope"

elif iteration_budget_near_exhaustion:
  recommend "accept_terminal"
  rationale = "Approaching iteration budget; halt before runaway"

elif iteration_root_cause.root_cause_class == "VALUE_DISCREPANCY":
  # Cross-ref found a cause→symptom relationship.
  # The "cause" side base event is the natural next top event.
  recommend "dig_deeper <cause_base_event_id>"
  rationale = "VALUE_DISCREPANCY found at <id>; dig deeper to find code-level mechanism"

elif iteration_root_cause.root_cause_class == "MULTI_CAUSE":
  # Multiple confirmed base events without clear cause/symptom.
  # Pick the deepest-confidence one.
  recommend "dig_deeper <highest_confidence_base_event_id>"
  rationale = "Multiple base events confirmed; deepest-confidence selected for further analysis"

elif iteration_root_cause.root_cause_class == "ABSENCE":
  # Single base event, no commanded value.
  # If at depth 1, dig into it; if at depth >=2, accept terminal.
  if current_iteration_id == 1:
    recommend "dig_deeper <only_base_event_id>"
  else:
    recommend "accept_terminal"

elif iteration_root_cause.root_cause_class == "TIMER_EXPIRY":
  # Timer expiry usually means dig into the layer below the timer.
  # If code mechanism is identified at this depth, accept terminal.
  if implementation_location is not null:
    recommend "accept_terminal"
  else:
    recommend "dig_deeper <timer_base_event_id>"

else:
  recommend "accept_terminal"
  rationale = "Iteration root cause not classified for drilling; accepting as terminal"
```

### User response parsing

| User reply | Action |
|---|---|
| `dig deeper into <id>` or `dig <id>` or `<id>` | Start iteration N+1 with that base event |
| `accept` or `accept terminal` or `terminate` | Synthesize `phase3_root_cause_chain`; proceed to Phase 4 |
| `abort` or `stop` or `cancel` | Halt pipeline with rejection report |

### Override confirmation (D4)

If the user picks a `dig_deeper` action targeting a base event different
from `agent_recommendation.recommended_base_event_id`, OR if the agent
recommended `accept_terminal` and the user picked `dig_deeper`, the
controller emits a confirmation prompt:

```
───────────────────────────────────────────────────────────────
OVERRIDE CONFIRMATION
───────────────────────────────────────────────────────────────

You requested:    dig deeper into <user-chosen base event>
Agent recommended: <agent's recommendation>

Reason agent gave: <agent_recommendation.rationale>

Are you sure you want to override? Type:
  confirm override     — proceed with your choice
  cancel               — reconsider; back to options

═══════════════════════════════════════════════════════════════
```

`user_decision.overrode_recommendation` is set true. The audit log
records both choices. Phase 4 report flags `high_disagreement_run = true`
if override rate ≥ 50% of all checkpoint decisions in the run.

### State updates after Checkpoint B

```json
"fta_iterations[<N>].user_decision": {
  "decided_at": "<ISO>",
  "action": "<dig_deeper | accept_terminal | abort>",
  "selected_base_event_id": "<id or null>",
  "selected_base_event_name": "<name or null>",
  "overrode_recommendation": <bool>,
  "override_confirmation_received": <bool>,
  "rationale": ""
},

"user_decisions[]": append entry,

# If dig_deeper:
"meta.current_iteration_id": <N+1>,
"meta.current_phase": "iteration_<N+1>_running",
"fta_iterations[<N+1>]": new entry with input_top_event derived from selected base event

# If accept_terminal:
"meta.current_phase": "phase4_finalizing",
"phase3_root_cause_chain": <synthesized from all iterations>

# If abort:
"meta.current_phase": "complete",
"phase4_rca_report.termination_reason": "User aborted at iteration <N>"
```

---

## Render Constraints

- Use plain ASCII tables and dividers (no Markdown header levels beyond
  what shows clearly in monospace). Cline's terminal/IDE display is fine
  for ASCII art.
- Total checkpoint presentation should fit in roughly 50–80 lines so the
  engineer can scan it without scrolling extensively.
- One-line evidence summaries; full evidence is in the state file.
- All option keywords are case-insensitive in parsing.

## What checkpoints do NOT include

- Raw log rows (those are in state file or DB)
- Full spec text (spec refs only)
- Full code snippets (file paths and function names only)
- Fix recommendations (NEVER, per v3-v6 hard termination invariant)
