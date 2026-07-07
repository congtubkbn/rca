# Iteration Controller Recommendation Logic (v6)

This file documents the full recommendation decision tree the iteration
controller uses to derive `agent_recommendation` from iteration state.
Implementation must match this logic exactly — no inferences beyond what's
specified.

## Inputs

The controller has access to:
- `iter` = `fta_iterations[current_iteration_id - 1]` (the just-finished iteration)
- `meta.iteration_budget` (default 5)
- `fta_iterations[*]` (all prior iterations, for cross-iteration signals)

## Step 1: Compute termination signals

```python
def compute_signals(iter, all_iters, budget):
    signals = {}

    # Signal 1: Spec skeleton failed AND code expansion produced nothing
    signals["spec_skeleton_returned_empty_and_code_only_no_failure_modes"] = (
        iter.hybrid_tree.spec_skeleton_returned_empty == True
        and all(len(br.children) == 0 for br in iter.hybrid_tree.branches)
    )

    # Signal 2: Tree collapsed to one branch with no children
    signals["single_branch_tree"] = (
        len(iter.hybrid_tree.branches) == 1
        and all(len(br.children) == 0 for br in iter.hybrid_tree.branches)
    )

    # Signal 3: Code search converged on same file as prior iteration
    if iter.iteration_id > 1:
        prior = all_iters[iter.iteration_id - 2]
        cur_loc = iter.iteration_root_cause.implementation_location
        prior_loc = prior.iteration_root_cause.implementation_location
        signals["find_implementation_returned_same_file_as_prior_iteration"] = (
            cur_loc is not None and prior_loc is not None and cur_loc == prior_loc
        )
    else:
        signals["find_implementation_returned_same_file_as_prior_iteration"] = False

    # Signal 4: No commanded-value IEs at this depth
    signals["no_commanded_value_ies_relevant"] = all(
        len(f.commanded_ie_lookup.commanded_value_ies) == 0
        for f in iter.cross_reference_findings
    )

    # Signal 5: Iteration budget about to exhaust
    signals["iteration_budget_near_exhaustion"] = (
        iter.iteration_id >= budget - 1
    )

    # Signal 6: All hypotheses Gate B-rejected
    signals["all_base_events_rejected"] = (
        len(iter.base_events) == 0 and len(iter.rejected) > 0
    )

    # Signal 7: Iteration produced only open items (insufficient evidence)
    signals["iteration_open"] = (
        len(iter.open_items) > 0 and len(iter.base_events) == 0
    )

    return signals
```

## Step 2: Apply decision tree (first match wins)

```python
def derive_recommendation(iter, signals, all_iters):
    rc_class = iter.iteration_root_cause.root_cause_class

    # PRIORITY 1: Hard failure modes
    if signals["all_base_events_rejected"]:
        return Recommendation(
            action="abort",
            id=None,
            rationale="All hypotheses rejected at Gate B; cannot proceed",
        )

    if signals["iteration_open"]:
        return Recommendation(
            action="abort",
            id=None,
            rationale="Insufficient log coverage; capture more trace and re-run",
        )

    # PRIORITY 2: Convergence / budget signals
    signal_count = sum(1 for v in signals.values() if v)
    if signal_count >= 2:
        return Recommendation(
            action="accept_terminal",
            id=None,
            rationale="Reached implementation primitives ("
                     + str(signal_count) + " termination signals); further "
                     + "drilling beyond automated RCA scope",
        )

    if signals["iteration_budget_near_exhaustion"]:
        return Recommendation(
            action="accept_terminal",
            id=None,
            rationale="Approaching iteration budget; halt before runaway",
        )

    # PRIORITY 3: Class-driven logic
    if rc_class == "VALUE_DISCREPANCY":
        # Find the cause-side base event in the iteration's chain
        cause_be = find_cause_in_chain(iter.iteration_root_cause.base_event_chain)
        if cause_be is None:
            # Single base event with discrepancy
            cause_be = iter.base_events[0] if iter.base_events else None
        if cause_be is None:
            return Recommendation(action="accept_terminal", id=None,
                                  rationale="No base event to dig into")
        return Recommendation(
            action="dig_deeper",
            id=cause_be.id,
            rationale="VALUE_DISCREPANCY found at " + cause_be.id
                     + "; dig deeper to find code-level mechanism",
        )

    if rc_class == "MULTI_CAUSE":
        # Pick highest-confidence base event
        if not iter.base_events:
            return Recommendation(action="accept_terminal", id=None,
                                  rationale="MULTI_CAUSE with no base events; terminal")
        best_be = max(iter.base_events,
                      key=lambda be: confidence_value(be.confidence))
        return Recommendation(
            action="dig_deeper",
            id=best_be.hypothesis_id,
            rationale="Multiple base events confirmed; highest-confidence "
                     "(" + best_be.hypothesis_id + ") selected for further analysis",
        )

    if rc_class == "ABSENCE":
        if iter.iteration_id == 1 and iter.base_events:
            be = iter.base_events[0]
            return Recommendation(
                action="dig_deeper",
                id=be.hypothesis_id,
                rationale="ABSENCE at depth 1; dig deeper to find code mechanism",
            )
        return Recommendation(
            action="accept_terminal",
            id=None,
            rationale="ABSENCE at depth >= 2; iteration root cause is at code level",
        )

    if rc_class == "TIMER_EXPIRY":
        if iter.iteration_root_cause.implementation_location is not None:
            return Recommendation(
                action="accept_terminal",
                id=None,
                rationale="Timer expiry with identified code location; terminal",
            )
        if iter.base_events:
            be = iter.base_events[0]
            return Recommendation(
                action="dig_deeper",
                id=be.hypothesis_id,
                rationale="Timer expiry without code location; dig into layer below timer",
            )
        return Recommendation(action="accept_terminal", id=None,
                              rationale="Timer expiry with no base events; terminal")

    # PRIORITY 4: Default / unhandled classes
    return Recommendation(
        action="accept_terminal",
        id=None,
        rationale="Iteration root cause class '" + rc_class
                 + "' not classified for drilling; accepting as terminal",
    )
```

## Helpers

```python
def confidence_value(conf_str):
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(conf_str, 0)

def find_cause_in_chain(base_event_chain):
    """Find the base event labeled as cause_of_X in the chain."""
    for entry in base_event_chain:
        if entry.relationship.startswith("cause_of_"):
            return entry
    return None
```

## Examples (matching the v6 walk-through)

### Iteration 1: 5G HO with VALUE_DISCREPANCY
- `rc_class = "VALUE_DISCREPANCY"`
- Signals: budget_near_exhaustion=False (1/5), others all False
- `base_event_chain = [{id: "P2.1", relationship: "symptom"}, {id: "P2.2", relationship: "cause_of_P2.1"}]`
- cause_be = P2.2
- → Recommendation: `dig_deeper P2.2`, rationale="VALUE_DISCREPANCY found at P2.2..."

### Iteration 2: Drilling into Preamble_Power_Error, ABSENCE found
- `rc_class = "ABSENCE"`
- Signals: spec_skeleton_returned_empty_and_code_only_no_failure_modes=False
  (failure modes did exist via code), single_branch_tree=False (multiple Q hyps),
  find_implementation_returned_same_file=True (dsp_power_calc.c appears in both
  iter 1 and iter 2 implementation_location)
- signal_count = 1, not ≥2
- iteration_id = 2, budget_near_exhaustion = (2 >= 4) → False
- rc_class = ABSENCE, iteration_id != 1 → accept_terminal
- → Recommendation: `accept_terminal`, rationale="ABSENCE at depth >= 2..."

### Hypothetical: Iteration 3 (if user overrode and dug deeper)
- Suppose iter 3 also lands on dsp_power_calc.c with ABSENCE
- find_implementation_returned_same_file=True (now signal #1)
- single_branch_tree=True (very narrow scope) (signal #2)
- signal_count = 2 → accept_terminal regardless of class
- → Recommendation: `accept_terminal`, rationale="Reached implementation
  primitives (2 termination signals); further drilling beyond automated RCA scope"

## Important constraints

- This logic is mechanical. No fuzzy interpretation, no "use judgment" steps.
- If a case doesn't match any branch in the decision tree, default to
  `accept_terminal`. Never recommend `dig_deeper` without a clear base event id.
- The `recommended_base_event_id` MUST be a base event that exists in
  `iter.base_events`. If the logic above would suggest an id not in
  base_events, fall through to `accept_terminal` with explanation.
