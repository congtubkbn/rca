# Design: Seed FTA directly from an engineer-provided top event

Date: 2026-08-04
Status: Approved (design phase) — pending implementation plan

## Problem

The v6 RCA pipeline (`.clinerules/workflows/rca.md`) always runs Phase 1
(scoping) and Phase 2 (event timeline) before FTA can start, halting at
Checkpoint A for the engineer to confirm a top event. When an engineer has
already determined the top event through means outside the pipeline (manual
log review, a prior investigation, domain knowledge), this full sequence is
unnecessary overhead — there is currently no way to hand a top event
directly to FTA (Phase 3).

## Goals

- Let an engineer seed a new RCA state with a top event + scope window they
  already know, skipping Phase 1/Phase 2/Checkpoint A.
- From that seeded state, resume with the existing `/rca` command and have
  it run FTA iteration 1 exactly as it would after a normal Checkpoint A
  confirmation — no new iteration logic, no duplicated skill chain.
- Keep the engineer-provided premise honestly labeled and audited, per the
  pipeline's existing evidence-tier discipline (see
  `v6-coworker-interaction-model.md` §7) — never let it be laundered into a
  pipeline-verified fact.
- Touch as little of the existing, working pipeline as possible.

## Non-goals

- Not implementing the full co-worker interaction model
  (`v6-coworker-interaction-model.md`) — no generic skill contracts, no
  `resume <skill>` injection/supersession, no `standalone <skill>` mode.
  Only the single "seed top event → FTA" scenario (that doc's §5) is in
  scope.
- Not adding a new slash-command workflow. Invocation is via direct skill
  trigger (Cline's natural-language skill matching), not a `.clinerules/
  workflows/*.md` entry point. (Decided explicitly — see Rejected
  alternatives.)
- Not adding `validation_scope`/report labeling in Phase 4 finalize, or any
  other "supplementary information" file changes. Trimmed to the minimum
  set of files that something reads or enforces at runtime.

## Design

### Flow

```
Engineer triggers 3gpp-fta-seed-init skill directly (natural language,
matched via the skill's description/triggers — no slash command), providing:
  - top event description
  - scope window (time bound)

3gpp-fta-seed-init:
  1. Validate inputs.
     - Missing scope_window -> HALT, ask for it. Never infer a default.
  2. Check .rca/current_state_path.txt.
     - Points to a state whose current_phase != "complete" -> HALT, ask
       the engineer to confirm overwrite / archive the old run / cancel.
     - Otherwise -> proceed.
  3. Write a new minimal state file (see State shape below).
  4. Set .rca/current_state_path.txt to the new file.
  5. Tell the engineer: "State seeded. Run /rca to continue into FTA
     iteration 1."
  6. STOP. Does not itself invoke any FTA skill.

Engineer runs /rca (existing workflow, unmodified invocation):
  rca.md Step 0: .rca/current_state_path.txt exists -> RESUME
  rca.md Step 1B: current_phase == "phase2_confirmed_via_seed"
    -> matches NEW dispatch case (see rca.md changes below)
    -> runs the identical skill chain that Case `phase2_confirmed` runs:
       3gpp-fta-build-tree(iter=1)
       -> 3gpp-fta-evaluate-branches(iter=1)
       -> 3gpp-fta-cross-reference(iter=1)
       -> 3gpp-fta-root-cause(iter=1)
       -> 3gpp-fta-iteration-controller(iter=1)
       -> HALT Checkpoint B-1

From Checkpoint B-1 onward: identical to a normal full_workflow run. No
further changes anywhere.
```

### State shape written by `3gpp-fta-seed-init`

```json
{
  "meta": {
    "pipeline_version": "v6",
    "mode": "seed_and_run",
    "current_phase": "phase2_confirmed_via_seed",
    "current_iteration_id": 1,
    "iteration_budget": 5,
    "started_at": "<ISO 8601>",
    "engineer_input": "<verbatim top event description>",
    "db_tables": ["UE_3gpp_signaling_log", "UE_Trace_log"],
    "duckdb_path": "<path>",
    "tool_dir": "<path to 3gpp-tools/>"
  },
  "fta_iterations": [
    {
      "iteration_id": 1,
      "parent_iteration_id": null,
      "parent_base_event_id": null,
      "started_at": "<ISO>",
      "input_top_event": {
        "event": "<verbatim top event description>",
        "source": "ENGINEER_PROVIDED",
        "spec_anchored": false,
        "scope_window": { "start_ms": 0, "end_ms": 0 }
      }
    }
  ],
  "engineer_inputs": [
    {
      "at": "<ISO>",
      "input_id": "ei_1",
      "assertion": "<verbatim top event description>",
      "overrides": null
    }
  ],
  "user_decisions": [],
  "keyword_provenance_audit": []
}
```

`user_decisions: []` and `keyword_provenance_audit: []` are scaffolded empty (mirroring `3gpp-rca-orchestrator`'s normal Phase 0 init template) so downstream skills that append to them don't need to check for existence first.

`phase1_scope_filter` and `phase2_ecf` are absent — not written, not
faked. Downstream FTA skills (`3gpp-fta-build-tree` and later) do not read
those sections; verified against `3gpp-fta-build-tree/SKILL.md`
preconditions (only requires `iteration_id`, `fta_iterations[iteration_id
-1].input_top_event`, and the correct `current_phase`).

### Why `current_phase: "phase2_confirmed_via_seed"` and not reusing
`"phase2_confirmed"` verbatim

Reusing the existing value would let `rca.md` pick up the seeded state with
literally zero changes to that file. Rejected because it makes the state
file lie about what actually happened (Phase 1/2/Checkpoint A did not run)
— a future edit to Case `phase2_confirmed` that assumes `phase2_ecf.top_
event` exists would silently break seeded runs. A distinct phase value
costs one additive dispatch-table entry and keeps the state file honest
about its own history.

## Files touched

### New

| File | Purpose |
|---|---|
| `.cline/skills/3gpp-fta-seed-init/SKILL.md` | Validates input, checks for an in-progress run, writes the seeded state (all logic above) |

### Modified (additive only — no existing line changes)

| File | Change | Why mandatory |
|---|---|---|
| `.clinerules/workflows/rca.md` | Add one new Step 1B dispatch case, `phase2_confirmed_via_seed`, placed immediately before the existing `phase2_confirmed` case; body identical to that case's skill chain | Without it, `/rca` cannot resume a seeded state — the feature does not work end to end |
| `.cline/skills/_shared/keyword-provenance-rules.md` | Add one carve-out rule: when `fta_iterations[1].input_top_event.source == "ENGINEER_PROVIDED"`, the keyword in that `event` field is exempt from trace-to-tool-call. No other keyword (Gate A/B, iteration >= 2) is exempt. | `3gpp-log-queries/SKILL.md` reads this file at runtime (line 193-196) when Gate A/B construct log queries; without the carve-out the agent will self-block on the seeded keyword as a provenance violation |
| `.cline/skills/3gpp-rca-orchestrator/SKILL.md` | In Mode 2 (Finalize) Preconditions (lines 90-102): add a conditional — when `meta.mode == "seed_and_run"`, do not require `phase1_scope_filter`, `phase2_ecf.top_event_candidates[]`/`user_confirmation`, or a Checkpoint-A entry in `user_decisions[]` | **Correction from initial draft of this doc.** Finalize's existing preconditions hard-list these sections and HALT with "Pipeline incomplete: `<missing section>`" if absent (verified by reading `3gpp-rca-orchestrator/SKILL.md:90-102`). A seeded run never populates them — without this fix, every seeded run would build the full FTA tree, pass all iterations and Checkpoint B, then dead-end at Phase 4 finalize. This is a functional blocker, not the optional "reduced validation" labeling originally proposed under trade-off #2 below. |

### Explicitly not touched (verified not required at runtime)

- `_shared/state-file-schema.md` — no skill reads this file during execution (grep confirmed only `keyword-provenance-rules.md` is referenced at runtime, via `3gpp-log-queries`); it is a contract for humans editing skills, not consumed by the running pipeline.
- `_shared/rca-report-template.md` — `validation_scope` labeling (trade-off #2 below) is still an explicit scope cut; the template needs no change until that labeling is added.
- `CLAUDE.md` — guidance for Claude Code sessions on this repo, not read by the Cline pipeline runtime.
- `3gpp-fta-build-tree`, `evaluate-branches`, `cross-reference`, `root-cause`, `iteration-controller` — verified via grep across all four remaining skills for `phase1_scope_filter`/`phase2_ecf` references. Two soft, non-precondition references found (evaluate-branches uses `phase2_ecf.observable_symptoms.missing_events` only as an iteration-1 branch-priority heuristic; root-cause cites `phase1_scope_filter.discriminator` as one optional evidence-chain entry) — neither is a hard precondition, both degrade gracefully to absent. Explicit `## Preconditions` sections in all four skills confirmed to require only their own iteration slice + correct `current_phase`.

## Known trade-offs (accepted, not hidden)

1. **No deterministic slash-command entry.** Invocation depends on Cline's
   natural-language skill-trigger matching against `3gpp-fta-seed-init`'s
   `description`/triggers rather than a fixed `/rca-fta` command. Mitigated
   by writing a specific description with explicit trigger phrases and an
   explicit anti-trigger line ("do NOT use when no top event is
   determined yet"). Risk: a mis-phrased engineer request might not match
   and require rephrasing.
2. **No automatic "reduced validation" labeling in the final report.**
   Finalize is touched only enough to not hard-block on the missing
   Phase 1/2 sections (see file table above) — it does NOT add any
   `validation_scope` note or otherwise flag the iteration-1 top event as
   an unverified premise. A report produced from a seeded run reads
   identically to one from a fully-scoped run. A reader must separately
   know the run started via `3gpp-fta-seed-init` to know the iteration-1
   top event was `ENGINEER_PROVIDED`, not pipeline-confirmed. Accepted as
   an explicit scope cut for this iteration; can be added later as a
   small additive change to the same finalize mode block.
3. **Skill-chain duplication in `rca.md`.** The five-skill iteration-1
   chain now exists twice in `rca.md` (once under `phase2_confirmed`, once
   under `phase2_confirmed_via_seed`), byte-for-byte identical. If the
   chain ever changes (e.g. a new skill inserted), both cases must be
   updated together. Mitigated by a cross-reference comment in each case
   pointing at the other.

## Rejected alternatives

- **Separate `.clinerules/workflows/rca-fta.md` entry point.** Considered
  first; gives a deterministic `/rca-fta` slash command and keeps
  validation/precondition logic out of the skill. Rejected by explicit
  user decision in favor of a lighter footprint (one fewer file), accepting
  trade-off #1 above.
- **Reusing `current_phase: "phase2_confirmed"` verbatim (zero `rca.md`
  changes).** Rejected for honesty of the state file's own history — see
  "Why `phase2_confirmed_via_seed`" above.
- **`rca-fta.md` itself running the iteration-1 skill chain, then halting
  at Checkpoint B-1 directly** (an earlier iteration of this design).
  Rejected in favor of handing off to the existing `/rca` resume path,
  which needed no new orchestration code, only a state-file contract.
