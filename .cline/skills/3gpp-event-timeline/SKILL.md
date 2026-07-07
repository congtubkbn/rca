---
name: 3gpp-event-timeline
description: >
  Phase 2 of the 3GPP UE RCA pipeline v6 — Event & Causal Factor analysis.
  Build the signaling event timeline, classify events, identify missing events
  vs spec-defined flow, and produce a curated list of TOP EVENT CANDIDATES
  (1-3 entries) ranked by confidence for the user to select at Checkpoint A.
  Calls 3gpp-spec-retrieval (lightweight_procedure, need=ecf) for expected flow.
  Calls 3gpp-log-queries (phase2, signaling table only) for the timeline.
  STRICTLY PROHIBITED from accessing UE_Trace_log or code search. Does NOT
  set phase2_ecf.top_event directly — only writes the candidates list; the
  user's selection at Checkpoint A finalizes which becomes the top event.
  Use this skill at Phase 2 after Phase 1 scope_filter is complete. Triggers:
  "build event timeline", "produce top event candidates", "Phase 2 of 3GPP RCA",
  "run ECF for v6".
---

# 3GPP Phase 2 — Event & Causal Factor (ECF) v6

## Role

Build the signaling timeline. Produce a curated list of **1 to 3 Top Event
candidates** for the user to select from at Checkpoint A. Does NOT set
`phase2_ecf.top_event` — that's set by `3gpp-top-event-confirmation` after
the user picks.

## What Changed in v6

| Aspect | v5 | v6 |
|---|---|---|
| Output | One `top_event` directly | `top_event_candidates[]` (1-3 entries) |
| User interaction | None (unless ambiguous halt) | Mandatory Checkpoint A after |
| Phase 2 termination | Sets `phase2_ecf.top_event` and proceeds | Sets candidates, halts pipeline |
| Re-running on refine | Not supported | Supported — workflow re-triggers Phase 2 |

## Hard constraints (table isolation, preserved from v5)

1. Tool calls allowed:
   - `3gpp-spec-retrieval` (lightweight_procedure operation, need=ecf only)
   - `3gpp-log-queries` (phase2 tag, signaling table ONLY)
2. Tool calls FORBIDDEN:
   - Any UE_Trace_log query (regardless of how sparse signaling is)
   - Any code search

## Preconditions

- `phase1_scope_filter` exists in state file
- `phase1_scope_filter.ambiguities` is empty
- `meta.current_phase` is one of: `"phase1"` (entry), `"phase2_running"` (re-run from refine)

## Outputs

Writes to state file:

```json
"phase2_ecf": {
  "completed_at": "<ISO>",

  /* Empty until 3gpp-top-event-confirmation runs */
  "top_event": null,

  "observable_symptoms": {
    "events": [...],
    "earliest_anomaly": ... | null,
    "missing_events": [...],
    "log_coverage": "rich | partial | sparse",
    "queried_tables": ["UE_3gpp_signaling_log"],
    "expected_flow_source": {...}
  },

  /* v6 NEW — populated by this skill */
  "top_event_candidates": [
    {
      "rank": 1,
      "is_primary": true,
      "event": "<event text>",
      "timestamp": "<ts>",
      "layer": "<layer>",
      "evidence": "<one-line evidence>",
      "confidence": "HIGH | MEDIUM | LOW",
      "rejection_reason": null
    },
    ...
  ],

  /* Empty until Checkpoint A — populated by 3gpp-top-event-confirmation */
  "user_confirmation": null
}
```

And updates:
```
meta.current_phase = "phase2_running"
```

(The next skill `3gpp-top-event-confirmation` will transition to
`phase2_pending_confirmation`.)

---

## Execution

### Step 1 — Read scope_filter slice
Read ONLY `phase1_scope_filter` from state file. Extract: procedure, rat,
layers, time_window, condition.

If `phase1_scope_filter.user_refinements` is non-empty (re-run from refine
path), incorporate the refinement text into the analysis context (e.g. by
narrowing the time window if the user specified one, or by adjusting
expected layers).

### Step 2 — Get expected message flow

```
Use the 3gpp-spec-retrieval skill with:
  operation: lightweight_procedure
  procedure: <scope_filter.procedure>
  rat: <scope_filter.rat>
  need: ecf
```

Returns structured `expected_flow[]` and writes to
`phase2_ecf.observable_symptoms.expected_flow_source`.

**Halt:** If empty, write halt error to state and ask engineer to clarify
procedure (this is rare — should have been caught in Phase 1).

### Step 3 — Retrieve signaling timeline

```
Use the 3gpp-log-queries skill with:
  phase_tag: phase2
  table: UE_3gpp_signaling_log
  keywords: [m.message for m in expected_flow]
  layers: scope_filter.layers
  time_window: scope_filter.time_window
```

Returns rows + `key_events` (≤5 compressed). Table isolation enforced at
script entry.

### Step 4 — Classify events
- `normal` — matches expected flow at expected time
- `anomaly` — first deviation from spec flow
- `consequence` — follows from earlier anomaly
- `symptom` — observable failure indicator (these become Top Event candidates)

### Step 5 — Identify missing events
For each `ref_msg` in `expected_flow` not present in retrieved rows:
```json
{
  "expected_message": "<ref_msg.message>",
  "expected_after": "<prior message in expected_flow>",
  "spec_ref": "<scope_filter.spec_lookup.spec_refs[0]>"
}
```

### Step 6 — **v6 CRITICAL: Build top_event_candidates[]**

Identify all `symptom`-classified events and any terminal/rejection-class
signaling messages (NAS rejects, RRC reestab rejects, T-timer expiries,
etc.) within the time window.

**Ranking algorithm:**

1. **Primary candidate (rank 1):** The LAST observable symptom in
   chronological order. This is the failure most likely to be the Top Event
   per 3GPP RCA methodology (work backward from terminal symptom).

2. **Alternative candidates (rank 2, optionally rank 3):** Earlier symptoms
   that are defensible as Top Events. A candidate is "defensible" if:
   - It is a distinct procedure outcome (not just a consequence of an
     earlier event), AND
   - It has its own signaling evidence (not just inferred), AND
   - It is at least MEDIUM-distinct from the primary (different layer,
     different cause code family, or different procedure phase)

   If only 1 or 2 candidates are defensible, output a list of size 1 or 2.
   NEVER pad to 3 with hallucinated alternatives.

**Confidence assignment:**
- HIGH — `log_coverage = rich` AND the event has explicit signaling
  evidence (e.g. a REJECT message with cause code, a T-timer expiry message)
- MEDIUM — `log_coverage = partial` OR event is inferred from message
  absence but with strong absence-of-RAR-style evidence
- LOW — `log_coverage = sparse` OR event is inferred from indirect signals

**Rejection reasons for non-primary candidates:**
- "Consequence of primary; not a distinct top event"
- "Earlier in chain but recovers; primary is the unrecovered failure"
- "Different layer but lower confidence; primary has stronger evidence"
- (Any other specific reason based on the rejected candidate's situation)

### Step 7 — Assess log coverage
```
coverage = retrieved_present_count / expected_flow_size
rich:    coverage ≥ 0.8
partial: 0.4 ≤ coverage < 0.8
sparse:  coverage < 0.4
```

### Step 8 — Single-candidate handling

If only one candidate is genuinely defensible (the common case for clean
captures), `top_event_candidates` has 1 entry. The Checkpoint A skill will
present it for confirmation — the user can still refine or reject. Do NOT
add fake alternatives to make the prompt look richer.

### Step 9 — Ambiguity handling

If `log_coverage == "sparse"` AND no candidate has HIGH confidence:
- Still produce candidates (with LOW confidence)
- Add an entry to scope_filter.ambiguities recommending more capture
- DO NOT halt here — Checkpoint A will let the user choose `refine` or
  `reject and restart`. The halt-with-AMBIGUOUS behavior from v5 is
  replaced by Checkpoint A's interactive options.

### Step 10 — Write state file
Atomic write of full `phase2_ecf` block:
- `top_event` = null (will be filled by Checkpoint A skill)
- `observable_symptoms` populated
- `top_event_candidates` populated (1-3 entries)
- `user_confirmation` = null

Set `meta.current_phase = "phase2_running"` (the workflow will then
trigger `3gpp-top-event-confirmation` which transitions to
`phase2_pending_confirmation`).

---

## Anti-Hallucination

- `expected_flow` comes from spec_query.py output — never invented
- Keep message names EXACTLY as Mode 5 returned them
- `top_event_candidates[i].event` text comes from actual signaling rows
- `top_event_candidates[i].evidence` is a one-line excerpt from actual rows
- `missing_events` derived from comparing retrieved rows to spec output
- NEVER invent timestamps, cause codes, message names, or pad the
  candidates list with hallucinated alternatives
- Rejection reasons for non-primary candidates must be derivable from the
  signaling data (e.g. "this REJECT came BEFORE this other REJECT, so
  the latter is later in time") — NOT speculative

---

## Anomaly heuristics (signaling only)

- **RRC:** Timer-expiry messages, unexpected state transitions
- **NAS:** REJECT with non-zero cause; unexpected EMM/5GMM state changes
- **Message gaps:** Expected message absent within procedure timer window
- **Out-of-order:** Reject before request; duplicate messages

PHY/MAC/RLC anomalies are NOT visible at the signaling layer — FTA Gate B
discovers those via trace logs, not this skill.

---

## What this skill does NOT do (HARD)

- ❌ Does NOT query UE_Trace_log under any condition
- ❌ Does NOT search source code
- ❌ Does NOT set `phase2_ecf.top_event` (the user does this via Checkpoint A)
- ❌ Does NOT pad `top_event_candidates` to size 3 with invented alternatives
- ❌ Does NOT propose root cause
- ❌ Does NOT build a fault tree
- ❌ Does NOT propose fixes
- ❌ Does NOT make the "final" call on which symptom is the Top Event

See `references/timeline-checklist.md` for the audit checklist.
