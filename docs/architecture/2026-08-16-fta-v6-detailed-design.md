# FTA v6 Architecture & Flow — Detailed Design

**Date:** 2026-08-16  
**Version:** v6  
**Status:** Reference Documentation

---

## 1. FTA Pipeline Overview (per iteration)

Fault Tree Analysis runs as iterative loops. Each iteration processes one top event and produces a root cause, then halts at Checkpoint B for user decision.

```
Iteration N starts
    ↓
Phase 3.1: Build Hybrid Tree (spec skeleton + code binding)
    ↓
Phase 3.2: Gate A Evaluation (Signaling log query + Pivot-Prune)
    ↓
Phase 3.3: Dynamic Expansion (Expand failure modes + Gate B trace)
    ↓
Phase 3.4: Cross-Reference (Commanded vs Actual values)
    ↓
Phase 3.5: Root Cause Synthesis (Aggregate evidence)
    ↓
Checkpoint B: User Decision Gate
    ├─ accept_terminal → Phase 4 (Finalize)
    ├─ dig_deeper → Iteration N+1
    └─ abort → Phase 4 (Finalize)
```

**Key point:** Each iteration is self-contained. When user selects "dig_deeper", iteration N+1 begins with its own tree, base_event from iteration N as its input_top_event, and the same 5-phase sequence.

---

## 2. Phase 3.1: Build Hybrid Fault Tree

**Purpose:** Construct initial tree skeleton. Tree contains ONLY top-level phases, no children yet — children added in Phase 3.3 when a branch survives Gate A.

### Data Flow

```
INPUT: top_event, procedure, RAT, time_window

TOOL CALLS:
├─ spec_query.py --operation skeleton
│  → Extract spec phases from procedure (3GPP spec)
│  → Result: ["RRC Reconfiguration", "Cell selection", ...]
│
└─ code_search.py --operation bind_module (per phase)
   → Find UE code modules implementing each phase
   → Result: [file.c, function names, ...]

OUTPUT: hybrid_tree
├─ branches[] with status="unevaluated"
├─ modules[] per branch
├─ gate_a_result=null
└─ children=[]
```

### Execution Steps

1. **Read input:** Retrieve `input_top_event`, `procedure`, `rat` from state file iteration slice.

2. **Get spec skeleton:** Call `spec_query.py --operation skeleton` to fetch standardized phases from 3GPP spec for the procedure.

3. **Empty check (expected for iter ≥ 2):** If skeleton returns `phases: []`, invoke fallback:
   - `spec_query.py --operation generate_hypotheses`
   - Treat outputs as top-level hypotheses.

4. **Bind modules:** For each phase/hypothesis, call `code_search.py --operation bind_module` to find UE source files implementing that phase.

5. **Assemble & write:** Build `hybrid_tree.branches[]` with each phase/hypothesis as a top-level branch. All branches start:
   - `status="unevaluated"`
   - `gate_a_result=null`
   - `children=[]`

### Data Structure: Spec Skeleton

```json
{
  "phases": [
    {
      "phase_id": "P1",
      "name": "RRC Reconfiguration",
      "spec_ref": "TS 36.331 §5.3.5",
      "protocol_layer": "RRC",
      "mandatory_messages": ["RRCReconfiguration", "RAR"]
    }
  ]
}
```

### Data Structure: Code Binding

```json
{
  "phase_id": "P1",
  "modules": [
    {
      "file": "src/rrc_handler.c",
      "functions": ["rrc_reconfig_start", "rrc_send_req"]
    }
  ]
}
```

---

## 3. Phase 3.2 + 3.3: Evaluate & Expand Branches

**Purpose:** Walk each top-level branch through two evaluation gates. Gate A (signaling) classifies; Gate B (trace) verifies failure modes.

### Gate A & B Decision Flow

```
For each branch in hybrid_tree (status='unevaluated'):

GATE A: Query UE_3gpp_signaling_log
    ├─ normal_passage (no errors)
    │  → status = 'pruned_normal'
    │  → Add to pruned_branches[]
    │  → SKIP Gate B
    │
    ├─ failure_here (error/reject found)
    │  → status = 'failure_here'
    │  → Proceed to expansion & Gate B
    │
    ├─ absent (messages missing)
    │  → status = 'absent'
    │  → Proceed to expansion & Gate B
    │
    └─ unclear (ambiguous)
       → status = 'open'
       → Add to open_items[]
       → SKIP Gate B

EXPAND (for non-pruned branches):
    ├─ code_search.py --operation expand_failure_modes
    │  → Extract log keywords from code macros
    │  → Create children[] nodes
    │
    └─ Fallback: spec_query.py --operation expand_sub_causes
       (if code expansion empty)

GATE B: Query UE_Trace_log (per failure_mode)
    ├─ matched
    │  → status = 'base_event_confirmed'
    │  → Add to base_events[]
    │
    ├─ no match
    │  → status = 'rejected'
    │  → Add to rejected[]
    │
    └─ unclear
       → status = 'open'
       → Add to open_items[]
```

### Phase 3.2: Gate A (Signaling Evaluation)

Query signaling log for `mandatory_messages` defined on the branch. Interpret result:

| Query Result | Branch Status | Action |
|---|---|---|
| Messages clean, no errors | `pruned_normal` | Prune. Add to `pruned_branches[]`. Skip Gate B. |
| Messages + failure indicators | `failure_here` | Confirm failure. Proceed to expansion. |
| Messages absent | `absent` | Proceed to expansion. Gate B may find evidence. |
| Unclear / partial match | `open` | Add to `open_items[]`. Skip Gate B. |
| Iteration ≥ 2, code-only (no signaling) | `not_applicable` | Skip Gate A, go directly to expansion. |

**Early-exit condition:** If ALL branches pruned at Gate A → all phases normal, no failure found. Iteration halts with `"all_phases_normal_failure_not_in_skeleton"`. Iteration controller recommends `abort` or `accept_terminal`.

### Phase 3.3: Dynamic Expansion & Gate B

For branches that survived Gate A (failure_here, absent, or N/A):

1. **Expand failure modes:** Call `code_search.py --operation expand_failure_modes`. Extract literal log keywords from code log macros.

2. **Create children:** For each failure mode, create a child node under the branch. Assign IDs: `P1.1`, `P1.2`, etc.

3. **Gate B query:** For each failure mode, query `UE_Trace_log` using its log keywords.

4. **Interpret Gate B:**
   - Matched → `base_event_confirmed` → add to `base_events[]`
   - No match → `rejected` → add to `rejected[]`
   - Unclear → `open` → add to `open_items[]`

**Anti-laziness:** Evaluate ALL failure modes in an expanded branch, even if one is confirmed. No early exit.

### Data Structure: Code Expansion Result

```json
{
  "module": "src/rrc_handler.c",
  "failure_modes": [
    {
      "mode_id": "FM1",
      "name": "Timer_Expired",
      "log_keywords": ["TIMER_EXPIRED", "timeout_rrc"],
      "log_tags": ["RRC", "timing"],
      "line_range": [234, 256]
    }
  ]
}
```

### Table Isolation (Hard Rule)

- **Gate A ONLY queries** `UE_3gpp_signaling_log`
- **Gate B ONLY queries** `UE_Trace_log`
- Policy enforced at `log_query.py` layer (rejects mismatches)

---

## 4. Phase 3.4: Cross-Reference

**Purpose:** Compare commanded values (from signaling) vs actual behavior (from trace).

```
INPUT: base_events[] (confirmed failure modes from Gate B)

log_query.py --operation phase3_cross_ref
  ├─ Query UE_Trace_log
  └─ Compare: commanded values vs actual

OUTPUT: cross_reference_findings[]
├─ "RRC commanded X but UE executed Y"
├─ "Timer expired, commanded action not taken"
└─ ...
```

---

## 5. Phase 3.5: Root Cause Synthesis

**Purpose:** Aggregate all evidence from phases 1-4 into a single iteration root cause.

```json
{
  "iteration_root_cause": {
    "primary_cause": "...",
    "causal_chain": [...],
    "evidence": [
      { "type": "gate_a", "finding": "...", "source": "log query 123" },
      { "type": "gate_b", "finding": "..." },
      { "type": "cross_ref", "finding": "..." }
    ],
    "rejected_hypotheses": [...],
    "confidence": "HIGH/MEDIUM/LOW"
  }
}
```

---

## 6. Iteration Chaining

Iterations form a causal chain. Each iteration's base_events become the next iteration's top events.

```
Phase 2: Top Event
    ↓
5G_HO_Execution_Failure

Iteration 1
├─ input_top_event: 5G_HO_Execution_Failure
├─ Phase 3.1→3.5
└─ base_events[]
   ├─ P1.1 Preamble_Power_Error
   ├─ P2.2 RRC_Timer_Expire
   └─ P3.1 Invalid_Cell_Select

Checkpoint B-1: User selects "dig P2.2"
    ↓
Iteration 2
├─ input_top_event: RRC_Timer_Expire
├─ parent_base_event_id: P2.2
├─ Phase 3.1→3.5
└─ base_events[]
   ├─ P1.1 Timer_Config_Invalid
   └─ P2.1 Expired_Before_Reset

Checkpoint B-2: User selects "accept_terminal"
    ↓
Phase 4: Finalize
├─ Synthesize causal_chain across all iterations
└─ Generate final report
```

### State Structure per Iteration

```json
{
  "fta_iterations": [
    {
      "iteration_id": 2,
      "parent_iteration_id": 1,
      "parent_base_event_id": "P2.2",
      
      "input_top_event": {
        "event": "RRC_Timer_Expire",
        "source": "DERIVED_FROM_PRIOR_ITERATION",
        "spec_anchored": true
      },
      
      "hybrid_tree": { ... },
      "base_events": [ ... ],
      "pruned_branches": [ ... ],
      "rejected": [ ... ],
      "open_items": [ ... ],
      
      "cross_reference_findings": [ ... ],
      "iteration_root_cause": { ... }
    }
  ]
}
```

### Iteration Budget

- Default budget: 5 iterations (configurable in `meta.iteration_budget`)
- When approaching budget: iteration controller recommends `accept_terminal`
- User may still override and dig deeper; both recommendation and override recorded in audit

---

## 7. State File Structure

The state file is the **single source of truth**. Skills read/write only their iteration slice.

```
fta_state.json (per run)
├─ meta (pipeline metadata)
│  ├─ pipeline_version: "v6"
│  ├─ current_phase (state machine)
│  ├─ current_iteration_id
│  ├─ iteration_budget
│  └─ ...
│
├─ phase1_scope_filter (scope window, procedure, rat)
├─ phase2_ecf (top event candidates, user confirmation)
│
├─ fta_iterations[] (per-iteration data)
│  ├─ fta_iterations[0] (iteration 1)
│  ├─ fta_iterations[1] (iteration 2)
│  └─ ...
│
├─ user_decisions[] (audit log: Checkpoint A/B decisions)
└─ keyword_provenance_audit[] (all tool invocations)
```

### Phase State Machine

State machine tracks where in the pipeline we are. Skills read `current_phase`, do their work, write the next phase value:

| Phase Value | Meaning | Next Step |
|---|---|---|
| `phase0` | Initializing | → orchestrator Phase 0 |
| `phase1` | Scoping in progress | → 3gpp-scoping |
| `phase2_running` | Event timeline running | → 3gpp-event-timeline |
| `phase2_pending_confirmation` | Halted at Checkpoint A | → User confirms top event |
| `phase2_confirmed` | Ready for FTA iteration 1 | → Phase 3.1 (Build Tree) |
| `phase2_confirmed_via_seed` | Seeded state (engineer-provided) | → Phase 3.1 (Build Tree) |
| `iteration_N_running` | FTA iteration N in progress | → Phases 3.2, 3.3, 3.4, 3.5 |
| `iteration_N_pending_decision` | Halted at Checkpoint B-N | → User: dig/accept/abort |
| `phase4_finalizing` | Synthesizing final report | → orchestrator Phase 4 |
| `complete` | Done | — |

---

## 8. Data Sources & Tool Invocation Pattern

Skills never query data directly. They invoke Python tools under `3gpp-tools/` which write results to the state file and print a JSON summary to stdout.

### Tool Execution Pattern

```
Skill reads input from state file
    ↓
Execute shell command: python3 <tool>.py --args...
    ↓
Tool writes structured output to state file (fta_iterations[N].xxx)
    ↓
Tool prints compressed JSON summary to stdout
    ↓
Skill reads stdout JSON to verify success
    ↓
Skill continues or halts based on exit code
```

### The Three Python Tools

#### spec_query.py

```
Operations:
  • skeleton — Get phases of procedure
  • extract_ies — Get IE definitions
  • generate_hypotheses — Fallback when spec empty
  • expand_sub_causes — Fallback for sub-branches
  • find_commanded_values — Phase 3.4

Input: procedure, rat, top_event, etc.
Output: phases[], IE names, hypotheses, commanded values
```

#### code_search.py

```
Operations:
  • bind_module — Find files/functions implementing phase
  • expand_failure_modes — Extract log keywords from code
  • expand_sub_causes — Fallback for sub-branches
  • find_implementation — Phase 3.4

Input: phase_name, file path, etc.
Output: module bindings, log keywords, code references
```

#### log_query.py

```
Operations:
  • phase3_gate_a — Query UE_3gpp_signaling_log
  • phase3_gate_b — Query UE_Trace_log
  • phase3_cross_ref — Commanded vs actual comparison
  • phase1, phase2 — Scoping & timeline queries

Input: table, keywords, time_window, etc.
Output: matched events, timestamps, summaries

TABLE ISOLATION (enforced at tool entry):
  • phase1/phase2/phase3_gate_a → UE_3gpp_signaling_log ONLY
  • phase3_gate_b/phase3_cross_ref → UE_Trace_log ONLY
  • Mismatches → exit code 3 (policy violation)
```

### Exit Code Semantics

| Exit Code | Meaning | Skill Action |
|---|---|---|
| `0` | Success | Continue normal flow |
| `1` | Bad arguments / missing input | Halt, error message |
| `2` | Tool unavailable | Halt, tool missing |
| `3` | Policy violation (e.g., table isolation) | Halt, policy error |
| `4` | Empty result (no matches) | Continue, interpret as empty |

### Keyword Provenance

**Rule:** Every keyword (message name, IE name, log string, function name) used in any query must originate from a prior tool invocation in the same iteration.

- `keyword_provenance_audit[]` records all sources
- Checked at runtime by `log_query.py`
- Cross-iteration reuse allowed ONLY for deriving next iteration's top event from prior iteration's base event

---

## Key Architectural Principles

1. **Iteration-based:** FTA runs as a loop of iterations, not one flat tree. Each iteration has its own tree, base events, and root cause.

2. **User gates (mandatory):** Checkpoint B after each iteration. User chooses dig_deeper, accept_terminal, or abort. No fast mode.

3. **State file is truth:** All data flows through one JSON file at `/tmp/rca_state_*.json` (or Windows equivalent). Path cached at `.rca/current_state_path.txt`. No skill holds state in memory.

4. **Tool-driven:** Skills invoke Python tools under `3gpp-tools/`, never query data directly. Tools write to state file; skills read stdout.

5. **Table isolation:** Signaling log (Phase 3.2) vs. Trace log (Phase 3.3) segregated by policy. Enforced at tool layer.

6. **No hallucination:** Every keyword must trace back to tool output. Keyword provenance audit enforced.

7. **No fix generation:** Pipeline produces root cause + evidence chain. Never fixes, patches, configs, test cases, or "next steps" beyond log capture suggestions.

---

## Skills & Responsibilities

| Phase | Skill | Input | Output |
|-------|-------|-------|--------|
| 3.1 | `3gpp-fta-build-tree` | top_event, procedure, RAT | hybrid_tree skeleton + modules |
| 3.2+3.3 | `3gpp-fta-evaluate-branches` | hybrid_tree | branches status, children, base_events[] |
| 3.4 | `3gpp-fta-cross-reference` | base_events[] | cross_ref_findings[] |
| 3.5 | `3gpp-fta-root-cause` | all above | iteration_root_cause |
| Checkpoint B | `3gpp-fta-iteration-controller` | iteration_root_cause | user decision: dig/accept/abort |

---

## References

- `.cline/skills/_shared/state-file-schema.md` — Full JSON schema
- `.cline/skills/_shared/tool-invocation-templates.md` — Exact CLI shapes
- `.cline/skills/_shared/keyword-provenance-rules.md` — Anti-hallucination rules
- `.clinerules/3gpp-rca-collaboration.md` — Core invariants
