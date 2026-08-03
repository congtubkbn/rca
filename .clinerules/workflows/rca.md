# /rca — 3GPP UE Root Cause Analysis Pipeline (v6, dispatcher model)

This workflow is the single entry point for the 3GPP UE RCA pipeline.
Unlike v5 (which ran linearly start-to-finish), v6 is a **dispatcher**:
it checks the current phase in the state file and runs the next step,
halting at user gates and resuming when the user types `/rca` again.

Invoke with `/rca` followed by either:
- A new engineer description (starts fresh pipeline), OR
- A user response to a pending checkpoint (e.g. `/rca confirm`, `/rca dig deeper into P2.2`)

---

## Inputs expected

For fresh start:
1. Engineer description of the UE failure (free-form text)
2. DuckDB database path (or confirmation that one is loaded)
3. Optional: 3gpp-tools/ directory path if non-default

For checkpoint response:
- One of the option keywords listed in the relevant checkpoint
  (see `_shared/checkpoint-presentation-formats.md`)

If a required input is missing, the workflow halts and asks for it.

---

## Workflow steps (dispatcher)

<explicit_instructions>

### Step 0 — Read current state

1. Check if `<workspace>/.rca/current_state_path.txt` exists.
   - If NO → this is a FRESH START. Treat the rest of the `/rca` arguments
     as the engineer description. Go to Step 1A.
   - If YES → read the path; load `meta.current_phase` from the state file.
     This is a RESUME. Go to Step 1B.

### Step 1A — Fresh start

1. Validate environment:
   - `<workspace>/3gpp-tools/spec_query.py`, `code_search.py`,
     `log_query.py` exist (via `<execute_command>ls 3gpp-tools/`)
   - DuckDB tables `UE_3gpp_signaling_log` and `UE_Trace_log` accessible
   - If any check fails → STOP, report missing dependency
2. Trigger orchestrator init:
   ```
   Use the 3gpp-rca-orchestrator skill in init mode with the engineer
   description below. Initialize state file and write path to
   .rca/current_state_path.txt.

   Engineer description: <user input>
   ```
3. Trigger Phase 1 (scoping):
   ```
   Use the 3gpp-scoping skill. State file path is at
   .rca/current_state_path.txt.
   ```
4. Trigger Phase 2 (event timeline):
   ```
   Use the 3gpp-event-timeline skill. State file path is at
   .rca/current_state_path.txt.
   ```
5. Trigger Checkpoint A:
   ```
   Use the 3gpp-top-event-confirmation skill. State file path is at
   .rca/current_state_path.txt.
   ```
   This skill presents the candidates and HALTS the workflow.
6. STOP. User will type `/rca <response>` after reviewing the prompt.

### Step 1B — Resume from state file

Dispatch on `meta.current_phase`:

#### Case: `phase2_pending_confirmation`
The user is responding to Checkpoint A. Parse `/rca <response>`:

| User response | Action |
|---|---|
| `confirm` / `1` / `accept` | Trigger `3gpp-top-event-confirmation` with `selection=1`. Skill writes user_confirmation, sets phase to `phase2_confirmed`. Then proceed to Case `phase2_confirmed` below in the same turn. |
| `use alternative 2` / `alt 2` | Trigger skill with `selection=2`. |
| `use alternative 3` / `alt 3` | Trigger skill with `selection=3`. |
| `refine: <text>` | Trigger `3gpp-event-timeline` again with the additional info appended to scope; loops back to Checkpoint A. |
| `reject and restart` / `restart` | Ask user for new scope info; then re-trigger Phase 1 and Phase 2. |
| `abort` / `stop` | Mark `meta.current_phase = "complete"` with rejection; STOP. |
| (unparseable) | Ask user to repeat with a clearer option keyword. |

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

#### Case: `iteration_<N>_pending_decision`
The user is responding to Checkpoint B for iteration N. Parse `/rca <response>`:

| User response | Action |
|---|---|
| `dig deeper into <id>` / `dig <id>` / `<id>` | Trigger `3gpp-fta-iteration-controller` with `user_action=dig_deeper` and `selected_id=<id>`. If selected id ≠ agent's recommendation, emit override-confirmation prompt and HALT (user must reply `confirm override` to proceed). |
| `accept` / `accept terminal` / `terminate` | Trigger controller with `user_action=accept_terminal`. Skill synthesizes `phase3_root_cause_chain`, sets phase to `phase4_finalizing`. Then proceed to Case `phase4_finalizing` in the same turn. |
| `abort` / `stop` | Trigger controller with `user_action=abort`. Sets phase to `complete` with rejection report; STOP. |
| `confirm override` | Proceed with the previously-attempted override. Controller starts iteration N+1 with the user-selected base event. |
| `cancel` (after override prompt) | Return to Checkpoint B options. |
| (unparseable) | Ask user to repeat. |

After dig_deeper:
- `meta.current_iteration_id = N+1`
- `meta.current_phase = "iteration_<N+1>_running"`
- Iteration N+1's `input_top_event` derived from the selected base event
- Run `3gpp-fta-build-tree` with iteration_id=N+1 → ... → `3gpp-fta-iteration-controller` with iteration_id=N+1 → HALTS at Checkpoint B-(N+1)
- STOP.

#### Case: `iteration_<N>_running`
Pipeline was interrupted mid-iteration. Re-run from `3gpp-fta-build-tree`
with iteration_id=N. Idempotent — skills check what's already in
`fta_iterations[N]` before redoing work.

#### Case: `phase4_finalizing`
Run orchestrator finalize:
```
Use the 3gpp-rca-orchestrator skill in finalize mode. State file path is
at .rca/current_state_path.txt.
```
Orchestrator validates provenance, assembles report, writes
`phase4_rca_report`. Sets phase to `complete`.

#### Case: `complete`
Display the report path:
```
RCA pipeline terminated.
Report path: <phase4_rca_report.report_path>
Causal chain depth: <iterations_traversed>
Termination reason: <termination_reason>
```

Then run the evaluation extract step (spec FR-8/IN-1 — automatic, runs for
aborted runs too, so quality telemetry has total coverage):
```
<execute_command>python evaluation/scripts/eval_extract.py <state_file_path></execute_command>
```
If `evaluation/scripts/` is absent on this machine, note it and continue —
extraction failure never blocks or alters the RCA result.

Do NOT continue. Do NOT offer fixes.

If the user asks for fixes after this, respond:
> The v6 RCA pipeline terminates at verified root cause per the
> architecture termination policy. Fix design is a separate engineering
> activity owned by downstream processes. The root cause and causal chain
> in the report provide the inputs needed for that separate work.

</explicit_instructions>

---

## Halting conditions

| Halt reason | Trigger | Resume action |
|---|---|---|
| Missing tool scripts | Step 0 validation | Fix tooling; restart `/rca` |
| Missing engineer description | Step 1A | User provides description in `/rca` retry |
| DB tables unavailable | Step 0 validation | Fix DB; restart `/rca` |
| Scope ambiguities non-empty | Phase 1 halt | User clarifies; `/rca` resumes from `phase1` |
| Checkpoint A halt | Phase 2 → top-event-confirmation | User chooses option; `/rca <response>` |
| Checkpoint B-N halt | After iteration N | User chooses option; `/rca <response>` |
| Override-confirmation halt | User picked non-recommended option | `/rca confirm override` or `/rca cancel` |
| Iteration budget reached | controller forces `accept_terminal` or `abort` rec | User responds; can still override |
| Tool exit code 2 (unavailable) | Any tool invocation | Fix tooling; restart from current iteration |
| Provenance audit failure at Phase 4 | finalize validation | Halt; report which keyword failed; manual fix |

---

## Notes on running this workflow

- Workflow tokens are consumed only when invoked (Cline workflows are
  lazy-loaded). Each `/rca` invocation costs the workflow file's tokens
  once.
- State file is preserved after termination for audit purposes; only
  delete manually when the run is fully complete.
- Re-running `/rca` after a `complete` state will display the report again
  unless `.rca/current_state_path.txt` is deleted first.
- To start a fresh RCA while preserving the prior one: delete
  `.rca/current_state_path.txt` (the prior state file at
  `/tmp/rca_state_<ts>.json` is preserved).

## Iteration budget

Default: 5. After iteration 5 completes, controller forces
`accept_terminal` as the recommendation. User can still override with
`dig deeper`, but the override confirmation prompt will note that the
budget is exhausted. After iteration ~10, the controller may halt
unconditionally to prevent runaway.
