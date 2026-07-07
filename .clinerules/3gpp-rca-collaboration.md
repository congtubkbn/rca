# 3GPP RCA Collaboration Rule (always-on) — v6

This rule is the **only always-on rule** for the 3GPP RCA pipeline. It
encodes invariants that apply across every skill in the catalog. Detailed
per-phase rules belong inside individual SKILL.md files.

---

## v6 Architecture Summary

v6 introduces **per-level iterative FTA with user gates**:

1. After Phase 2, the user confirms the Top Event (Checkpoint A)
2. Each FTA iteration runs Phases 3.1 → 3.5 producing an iteration-local
   root cause, then HALTS at Checkpoint B
3. At Checkpoint B the user chooses to dig deeper (start iteration N+1),
   accept terminal (proceed to final report), or abort
4. Phase 4 synthesizes a causal chain across all iterations

Iteration budget default: **5**. No fast mode — every iteration requires
user gate (D2 = drop fast mode).

---

## Core invariants (preserved from v3 → v4 → v5 → v6)

### 1. State file is the source of truth
- Single state file at `/tmp/rca_state_<UTC_ts>.json` (or platform equivalent)
- Path stored in `.rca/current_state_path.txt` in workspace root
- v6 adds `meta.current_phase` state machine for resume-from-halt support
- See `.cline/skills/_shared/state-file-schema.md` for the full schema

### 2. Table isolation (hard constraint, enforced at the tool layer)
- IS/IS-NOT (Phase 1) and ECF (Phase 2) MAY ONLY query `UE_3gpp_signaling_log`
- `UE_Trace_log` may ONLY be touched in FTA Gate B or cross-reference
- Python tool `log_query.py` enforces this; rejects mismatches at script entry
- Rule applies **per iteration** in v6 — every iteration's Gate A is
  signaling-only; every Gate B is trace-only

### 3. Anti-hallucination keyword discipline (now iteration-scoped)
- Every keyword used in any tool query MUST originate from a prior Python
  tool invocation in the same pipeline run
- v6: every audit entry includes `iteration_id` so provenance is scoped
- Python scripts auto-append to `keyword_provenance_audit`
- Cross-iteration keyword reuse is allowed ONLY for `input_top_event`
  derivation across iteration boundaries
- See `.cline/skills/_shared/keyword-provenance-rules.md`

### 4. Hard termination (NO fix generation)
- Pipeline terminates when user accepts a terminal iteration root cause
  AND `phase3_root_cause_chain` is synthesized, OR when user aborts
- Final RCA report contains: causal chain, evidence per iteration,
  rejected hypotheses, open items, user decision audit, keyword
  provenance audit
- The pipeline NEVER produces: fix recommendations, code patches, config
  values to change, test cases, engineering action items, or any "next
  steps" beyond suggesting additional log capture

### 5. Tool invocation pattern (Cline + no-MCP environment)
- All underlying tools are Python scripts under `<workspace>/3gpp-tools/`
  (path in `meta.tool_dir`)
- Skills shell out via `<execute_command>` to run `spec_query.py`,
  `code_search.py`, `log_query.py`
- Scripts write structured output to the state file directly; print
  compressed JSON summary to stdout
- See `.cline/skills/_shared/tool-invocation-templates.md`

### 6. v6 NEW: User gates are mandatory
- Checkpoint A (after Phase 2): user confirms Top Event from curated list
- Checkpoint B (after each FTA iteration): user picks dig_deeper / accept_terminal / abort
- Override of agent recommendation is allowed but requires explicit
  confirmation (D4) — both choices recorded in audit
- See `.cline/skills/_shared/checkpoint-presentation-formats.md`

### 7. v6 NEW: Iteration scoping
- Each FTA iteration has its own `fta_iterations[i]` entry with full tree,
  base events, cross-reference findings, and iteration_root_cause
- Iterations form a causal chain, not a single flat tree
- Final synthesis in `phase3_root_cause_chain` records which iteration
  produced the terminal root cause

---

## Skill catalog (12 skills) — v6

The orchestrator and pipeline phases:

| # | Skill | Phase | Purpose |
|---|---|---|---|
| 1 | `3gpp-rca-orchestrator` | 0 + 4 | Initialize state, run pipeline kickoff, finalize report |
| 2 | `3gpp-scoping` | 1 | IS/IS-NOT scope_filter, signaling sanity check (unchanged from v5) |
| 3 | `3gpp-event-timeline` | 2 | Build event timeline, produce top_event_candidates[] |
| 4 | `3gpp-top-event-confirmation` | Checkpoint A | Present candidates; capture user selection |
| 5 | `3gpp-fta-build-tree` | 3.1 (per iter) | Hybrid skeleton + code module binding |
| 6 | `3gpp-fta-evaluate-branches` | 3.2 + 3.3 (per iter) | Gate A pivot-pruning + dynamic expansion + Gate B |
| 7 | `3gpp-fta-cross-reference` | 3.4 (per iter) | Commanded-vs-actual value comparison |
| 8 | `3gpp-fta-root-cause` | 3.5 (per iter) | Synthesize iteration root cause |
| 9 | `3gpp-fta-iteration-controller` | Checkpoint B | Recommendation + user dig/accept/abort gate |

Shared retrieval skills (invoked by the phase skills, never trigger directly):

| # | Skill | Used by |
|---|---|---|
| 10 | `3gpp-spec-retrieval` | Phases 1, 2, 3.1, 3.2, 3.4 (unchanged from v5) |
| 11 | `3gpp-code-retrieval` | Phases 3.1, 3.3, 3.4 (unchanged from v5) |
| 12 | `3gpp-log-queries` | Phases 1 (optional), 2, 3.2, 3.3, 3.4 (unchanged from v5) |

Entry point: `/rca` workflow in `.clinerules/workflows/rca.md`.

---

## Workflow Control Flow

```
User: /rca <description>
  ↓
Workflow reads .rca/current_state_path.txt:
  - NO file → fresh start: orchestrator init → scoping → event-timeline
              → top-event-confirmation → HALT (Checkpoint A)
  - YES file → dispatch on meta.current_phase:
        phase2_pending_confirmation  → no-op, wait for user response
        phase2_confirmed             → start iteration 1
        iteration_N_running          → continue iteration N
        iteration_N_pending_decision → no-op, wait for user response
        phase4_finalizing            → run orchestrator finalize
        complete                     → display report
```

User types `/rca` again after each pause; workflow resumes from
`meta.current_phase`.

---

## What NOT to do

- ❌ Never write a fix or remediation step anywhere in the pipeline output
- ❌ Never query `UE_Trace_log` from a Phase 1 or Phase 2 skill
- ❌ Never invent log message strings, function names, or IE names
- ❌ Never read multiple state-file sections eagerly — slice-read only
- ❌ Never bypass a tool error by fabricating its expected output
- ❌ Never skip user gates — Checkpoint A and Checkpoint B are mandatory
  (no fast mode in v6)
- ❌ Never reuse iteration N's keywords in iteration M's queries (except
  top event derivation at iteration boundaries)
- ❌ Never proceed past a terminal iteration to invent "next steps"
