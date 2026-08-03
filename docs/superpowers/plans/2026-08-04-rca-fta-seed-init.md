# RCA FTA Seed-Init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an engineer seed a new RCA state directly with a known top event + scope window, skip Phase 1/2/Checkpoint A, and resume via the existing `/rca` command straight into FTA iteration 1.

**Architecture:** One new skill (`3gpp-fta-seed-init`) validates input and writes a minimal state file with `current_phase: "phase2_confirmed_via_seed"`. Three existing files get small additive edits so the rest of the pipeline (dispatcher, keyword-provenance rule, Phase 4 finalize) accepts and correctly resumes that seeded state without any change to their existing behavior for normal runs.

**Tech Stack:** N/A — this repository has no build/test/lint tooling (per `CLAUDE.md`). All "files" are Markdown skill/workflow specs consumed by Cline's agent runtime. Verification per task is Read/Grep-based: confirm exact content landed at the right location and that no pre-existing line was altered.

## Global Constraints

- Spec source of truth: `docs/superpowers/specs/2026-08-04-rca-fta-seed-design.md` — every requirement below traces to it.
- All edits to existing files must be strictly additive — no existing line changed or removed (verified by diff review in each task).
- New skill's `description` frontmatter must include explicit trigger phrases and an explicit anti-trigger line (no slash-command entry point was chosen — see spec's Rejected alternatives).
- `phase1_scope_filter` and `phase2_ecf` must never be written by the seed path — they stay absent, not faked.
- Evidence tier `ENGINEER_PROVIDED` is exempted from keyword-provenance trace-back ONLY for `fta_iterations[1].input_top_event.event` — no other keyword, ever.

---

### Task 1: Create `3gpp-fta-seed-init` skill

**Files:**
- Create: `.cline/skills/3gpp-fta-seed-init/SKILL.md`

**Interfaces:**
- Produces: a state file (path written to `.rca/current_state_path.txt`) with `meta.mode == "seed_and_run"`, `meta.current_phase == "phase2_confirmed_via_seed"`, `meta.current_iteration_id == 1`, and `fta_iterations[0].input_top_event.source == "ENGINEER_PROVIDED"` — this exact shape is what Task 3's new `rca.md` dispatch case and Task 4's orchestrator finalize conditional both key off of.

- [ ] **Step 1: Write the skill file**

```markdown
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

If either is missing, do not proceed — see Step 1 below.

## Execution

### Step 1 — Validate inputs

- If `top_event_description` is missing or empty → HALT: "Need a top event
  description to seed FTA. What is the top event?"
- If `scope_window` is missing → HALT: "Need a time window (start/end) to
  bound Gate A log queries. What is the scope window?"

### Step 2 — Check for an in-progress run

1. Check whether `<workspace>/.rca/current_state_path.txt` exists.
2. If it exists, read the path and load `meta.current_phase` from that
   state file.
3. If `meta.current_phase != "complete"` → HALT: "An RCA run is already in
   progress (phase: `<current_phase>`, state file: `<path>`). Overwrite it,
   archive it, or cancel?" Wait for explicit engineer instruction before
   continuing.
4. If no file exists, or the existing one is `complete` → proceed.

### Step 3 — Write the seed state file

1. Compute UTC timestamp: `TS=$(date -u +%Y%m%dT%H%M%SZ)`
2. State file path: `/tmp/rca_state_${TS}.json` (or
   `%TEMP%\rca_state_${TS}.json` on Windows) — same convention as
   `3gpp-rca-orchestrator` Phase 0 init.
3. Write:

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
  "fta_iterations": [
    {
      "iteration_id": 1,
      "parent_iteration_id": null,
      "parent_base_event_id": null,
      "started_at": "<ISO from TS>",
      "input_top_event": {
        "event": "<verbatim top_event_description>",
        "source": "ENGINEER_PROVIDED",
        "spec_anchored": false,
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

Note: `phase1_scope_filter` and `phase2_ecf` are NOT written — absent, not
faked.

4. Verify Python tool scripts exist (same check as orchestrator Phase 0):
   - `<tool_dir>/spec_query.py`
   - `<tool_dir>/code_search.py`
   - `<tool_dir>/log_query.py`
   - If any missing → HALT with "Tool dependency missing: `<name>`"
5. Write `<STATE>` path to `<workspace>/.rca/current_state_path.txt`
   (create `.rca/` directory if missing). Atomic write (`.tmp` → move).

### Step 4 — Hand off

Tell the engineer:

> State seeded (`<STATE path>`). Run `/rca` to continue into FTA
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
```

- [ ] **Step 2: Verify the file was created at the right path with the right frontmatter**

Run: search for the skill name and check the file is well-formed YAML frontmatter + Markdown body.
Expected: `.cline/skills/3gpp-fta-seed-init/SKILL.md` exists, starts with `---`, has `name: 3gpp-fta-seed-init`, ends frontmatter with a second `---`, and includes an explicit anti-trigger sentence ("Do NOT use when...").

- [ ] **Step 3: Commit**

```bash
git add .cline/skills/3gpp-fta-seed-init/SKILL.md
git commit -m "feat: add 3gpp-fta-seed-init skill for engineer-provided top events"
```

---

### Task 2: Add `ENGINEER_PROVIDED` carve-out to keyword provenance rules

**Files:**
- Modify: `.cline/skills/_shared/keyword-provenance-rules.md` (append a new section; no existing line changed)

**Interfaces:**
- Consumes: nothing new — this is a rules document read by `3gpp-log-queries/SKILL.md` at runtime (confirmed via grep, lines 193-196) and by the FTA skills that construct Gate A/B queries in iteration 1.
- Produces: the exception that `3gpp-fta-evaluate-branches` (Gate A/B, iteration 1) relies on to use `fta_iterations[1].input_top_event.event` as a query keyword without triggering a self-imposed provenance halt, when that event's `source == "ENGINEER_PROVIDED"`.

- [ ] **Step 1: Read current end-of-file content to find the exact insertion point**

The file currently ends (line 236) with:
```
If any check fails → halt and write the failure reason to
`phase4_rca_report.termination_reason`.
```

- [ ] **Step 2: Append a new section immediately after that closing paragraph**

```markdown

---

## `ENGINEER_PROVIDED` Carve-Out (v6 NEW — seed_and_run mode only)

When a run is seeded via `3gpp-fta-seed-init` (`meta.mode ==
"seed_and_run"`), `fta_iterations[1].input_top_event` has `source:
"ENGINEER_PROVIDED"` instead of being derived from
`phase2_ecf.top_event`.

**The carve-out applies to exactly one keyword: the `event` string in
that one field.** It is exempt from the trace-to-tool-call requirement
because it was asserted directly by the engineer, not derived by any
pipeline phase.

**The carve-out does NOT extend to anything else:**
- Every keyword `3gpp-fta-build-tree`, `3gpp-fta-evaluate-branches`, and
  `3gpp-fta-cross-reference` derive FROM that top event (spec skeleton
  matches, code module bindings, Gate A/B log keywords, commanded/actual
  values) MUST still trace to a tool invocation in the same iteration, per
  the rules above. The top event being engineer-provided does not make its
  downstream consequences engineer-provided.
- Iteration 2 and beyond are entirely unaffected — if the engineer's
  seeded iteration 1 leads to `dig_deeper`, iteration 2's top event is
  derived from iteration 1's `base_events[]` exactly as in a normal run,
  and is audited exactly as in a normal run (no `ENGINEER_PROVIDED` tag).
- The Phase 4 validation checklist's rule "every keyword in the causal
  chain traces to `keyword_provenance_audit`" is unchanged EXCEPT that a
  lookup for the iteration-1 top event keyword may instead match an
  `engineer_inputs[]` entry (`input_id`, `assertion`, `at`) in place of a
  `keyword_provenance_audit` entry, and only for that one field.
```

- [ ] **Step 3: Verify the append landed correctly and nothing above it changed**

Run: `git diff .cline/skills/_shared/keyword-provenance-rules.md`
Expected: diff shows only added lines (`+`), all after the file's prior last line; zero removed/changed lines (no `-` except possibly a trailing-newline artifact).

- [ ] **Step 4: Commit**

```bash
git add .cline/skills/_shared/keyword-provenance-rules.md
git commit -m "docs: add ENGINEER_PROVIDED keyword-provenance carve-out for seeded FTA runs"
```

---

### Task 3: Add `phase2_confirmed_via_seed` dispatch case to `/rca`

**Files:**
- Modify: `.clinerules/workflows/rca.md` (insert new case; no existing line changed)

**Interfaces:**
- Consumes: `meta.current_phase == "phase2_confirmed_via_seed"` as written by Task 1's skill.
- Produces: the same skill-chain invocation sequence that Case `phase2_confirmed` already produces (`3gpp-fta-build-tree` → `3gpp-fta-evaluate-branches` → `3gpp-fta-cross-reference` → `3gpp-fta-root-cause` → `3gpp-fta-iteration-controller`, HALT at Checkpoint B-1) — Task 4 and the unmodified downstream skills consume iteration 1's output exactly as they would from a normal run.

- [ ] **Step 1: Locate the exact insertion point**

Existing content at lines 91-105 of `.clinerules/workflows/rca.md`:
```
#### Case: `phase2_confirmed`
Top event is locked in. Start iteration 1:
```
meta.current_iteration_id = 1
meta.current_phase = "iteration_1_running"
Use the 3gpp-fta-build-tree skill with iteration_id=1.
   State file path is at .rca/current_state_path.txt.
```
Then in sequence:
- `3gpp-fta-evaluate-branches` with iteration_id=1
- `3gpp-fta-cross-reference` with iteration_id=1
- `3gpp-fta-root-cause` with iteration_id=1
- `3gpp-fta-iteration-controller` with iteration_id=1 → HALTS at Checkpoint B-1

STOP. User will type `/rca <response>`.
```

- [ ] **Step 2: Insert a new case immediately before it**

```markdown
#### Case: `phase2_confirmed_via_seed`
Top event was provided directly by the engineer via `3gpp-fta-seed-init`
(`meta.mode == "seed_and_run"`), bypassing Phase 1/2/Checkpoint A. Start
iteration 1 — identical handling to Case `phase2_confirmed` below, except
`fta_iterations[1].input_top_event.source == "ENGINEER_PROVIDED"` instead
of derived from `phase2_ecf.top_event`:
```
meta.current_iteration_id = 1
meta.current_phase = "iteration_1_running"
Use the 3gpp-fta-build-tree skill with iteration_id=1.
   State file path is at .rca/current_state_path.txt.
```
Then in sequence — same chain as Case `phase2_confirmed` (keep both in
sync if this chain ever changes):
- `3gpp-fta-evaluate-branches` with iteration_id=1
- `3gpp-fta-cross-reference` with iteration_id=1
- `3gpp-fta-root-cause` with iteration_id=1
- `3gpp-fta-iteration-controller` with iteration_id=1 → HALTS at Checkpoint B-1

STOP. User will type `/rca <response>`.

#### Case: `phase2_confirmed`
Top event is locked in. Start iteration 1:
```
meta.current_iteration_id = 1
meta.current_phase = "iteration_1_running"
Use the 3gpp-fta-build-tree skill with iteration_id=1.
   State file path is at .rca/current_state_path.txt.
```
Then in sequence — same chain as Case `phase2_confirmed_via_seed` (keep
both in sync if this chain ever changes):
- `3gpp-fta-evaluate-branches` with iteration_id=1
- `3gpp-fta-cross-reference` with iteration_id=1
- `3gpp-fta-root-cause` with iteration_id=1
- `3gpp-fta-iteration-controller` with iteration_id=1 → HALTS at Checkpoint B-1

STOP. User will type `/rca <response>`.
```

- [ ] **Step 3: Verify only an insertion happened**

Run: `git diff .clinerules/workflows/rca.md`
Expected: diff shows only added lines (`+`) forming the new case block plus
two added cross-reference sentences ("keep both in sync...") inside each
case; the original `phase2_confirmed` case's five bullet lines and STOP
sentence appear unchanged (no `-` lines other than possible blank-line
reflow).

- [ ] **Step 4: Commit**

```bash
git add .clinerules/workflows/rca.md
git commit -m "feat: dispatch seeded FTA runs (phase2_confirmed_via_seed) to iteration 1"
```

---

### Task 4: Exempt seeded runs from Phase 4 finalize's Phase 1/2 preconditions

**Files:**
- Modify: `.cline/skills/3gpp-rca-orchestrator/SKILL.md` (edit the Mode 2 Preconditions section, lines 90-102; additive conditional, no removal of the normal-run requirement)

**Interfaces:**
- Consumes: `meta.mode` (written by Task 1's skill; absent/undefined for normal `full_workflow` runs, which must keep requiring every section listed today).
- Produces: finalize proceeds past the precondition check for a seeded run instead of halting with "Pipeline incomplete: phase1_scope_filter".

- [ ] **Step 1: Locate exact current text**

Current lines 90-102 of `.cline/skills/3gpp-rca-orchestrator/SKILL.md`:
```
### Preconditions

- `<workspace>/.rca/current_state_path.txt` exists with valid state file path
- `meta.current_phase == "phase4_finalizing"` (set by iteration controller after user accepted terminal)
- State file contains at minimum:
  - `meta` (Phase 0)
  - `phase1_scope_filter` (Phase 1)
  - `phase2_ecf` with `top_event_candidates[]` and `user_confirmation` (Phase 2 + Checkpoint A)
  - `user_decisions[]` (at least Checkpoint A entry)
  - `fta_iterations[]` (at least iteration 1)
  - `phase3_root_cause_chain` (set by iteration controller)

If any precondition missing → HALT with "Pipeline incomplete: <missing section>"
```

- [ ] **Step 2: Replace with the conditional version**

```markdown
### Preconditions

- `<workspace>/.rca/current_state_path.txt` exists with valid state file path
- `meta.current_phase == "phase4_finalizing"` (set by iteration controller after user accepted terminal)
- State file contains at minimum:
  - `meta` (Phase 0)
  - `fta_iterations[]` (at least iteration 1)
  - `phase3_root_cause_chain` (set by iteration controller)
  - If `meta.mode != "seed_and_run"` (normal `full_workflow` run), additionally:
    - `phase1_scope_filter` (Phase 1)
    - `phase2_ecf` with `top_event_candidates[]` and `user_confirmation` (Phase 2 + Checkpoint A)
    - `user_decisions[]` with at least one Checkpoint A entry
  - If `meta.mode == "seed_and_run"` (seeded via `3gpp-fta-seed-init`):
    - `phase1_scope_filter` and `phase2_ecf` are expected to be absent — do
      NOT treat their absence as a missing-section failure
    - `user_decisions[]` is expected to have no Checkpoint A entry — only
      Checkpoint B entries are required

If any precondition missing → HALT with "Pipeline incomplete: <missing section>"
```

- [ ] **Step 3: Verify the normal-run path is unchanged and the seeded-run path is now covered**

Run: `git diff .cline/skills/3gpp-rca-orchestrator/SKILL.md`
Expected: diff shows the four bullet lines under "State file contains at
minimum" reorganized under two new conditional sub-lists; the substantive
requirement text for a normal run (`phase1_scope_filter`, `phase2_ecf`
shape, Checkpoint A entry) is present verbatim inside the `mode !=
"seed_and_run"` branch — i.e. nothing was deleted, only made conditional
and one new branch added.

- [ ] **Step 4: Commit**

```bash
git add .cline/skills/3gpp-rca-orchestrator/SKILL.md
git commit -m "fix: don't require Phase 1/2 sections at finalize for seed_and_run runs"
```

---

### Task 5: Cross-check the full flow against the spec, end to end

**Files:** none created/modified — verification only.

- [ ] **Step 1: Re-read the four changed/created files together**

Confirm, by reading:
1. `3gpp-fta-seed-init/SKILL.md` writes `current_phase: "phase2_confirmed_via_seed"` — matches the exact string Task 3's new `rca.md` case matches on.
2. `rca.md`'s new case sets `current_phase = "iteration_1_running"` before invoking `3gpp-fta-build-tree` — matches that skill's precondition (`meta.current_phase == "iteration_<iteration_id>_running"`).
3. `keyword-provenance-rules.md`'s carve-out references `source == "ENGINEER_PROVIDED"` — matches the exact field/value Task 1's skill writes.
4. `3gpp-rca-orchestrator/SKILL.md`'s finalize conditional checks `meta.mode == "seed_and_run"` — matches the exact field/value Task 1's skill writes.

- [ ] **Step 2: Confirm no normal-run file or behavior changed**

Run: `git diff main -- .clinerules/workflows/rca.md .cline/skills/_shared/keyword-provenance-rules.md .cline/skills/3gpp-rca-orchestrator/SKILL.md`
Expected: every changed hunk is additive (only `+` lines, or lines moved into a conditional branch with their original text preserved verbatim) — no normal `full_workflow` run's behavior is altered.

- [ ] **Step 3: Final commit if any cross-check fixes were needed, otherwise done**

```bash
git status
```
Expected: working tree clean (all 4 tasks already committed individually).
