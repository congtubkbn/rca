---
name: rca-analyze
description: >
  Run one round of analysis on an existing, scoped PLM-issue RCA run:
  locate the failure point in signalling or trace, generate competing
  hypotheses with their predicted evidence and testing query, run those
  queries via log-query/code-graph/NotebookLM to eliminate or support
  them, then present a checkpoint (causal chain, ranked directions,
  recommendation, evidence gaps) and HALT. Writes `analysis/round-NN.json`
  under an existing, scoped run. Use ONLY when an engineer wants to run,
  or re-run, one round of hypothesis-driven analysis on a PLM-issue run
  that already has a `scope.json` (e.g. "analyze PLM-12345", "run a round
  on this run", "what's the failure point here"). Requires `scope.json`
  to already exist — invoke `rca-scope` first if it does not. Do NOT use
  this for the older v6 3GPP fault-tree suite's FTA skills
  (`.cline/skills/3gpp-fta-*`) — unrelated pipeline, no PLM issue ID, no
  run bundle; that suite builds its tree from spec before reading any
  log, this skill does the reverse. Do NOT use this to classify an issue
  or narrow the window/tables/layers — that's `rca-scope`, which this
  skill only reads, never writes. Do NOT use this to reach a final root
  cause or reproduction scenario, or to accept/close a run — that's
  `rca-conclude`, not built yet. Do NOT use this to handle a `dig` /
  `redirect` / `abort` reply, enforce the round budget, or act on
  `manifest.json.autonomy` — this skill always halts at its checkpoint
  unconditionally; that loop is issue #9, not yet built.
---

# rca-analyze

Part of the PLM-issue pipeline (issue #5): `rca-intake → rca-scope →
rca-analyze ⟲ → rca-conclude → rca-learn`. This is the pipeline's third
step, and this ticket (issue #8) builds one round of it — the analytical
engine and its checkpoint. The multi-round loop around it (`dig
<direction>` / `redirect <information>` / `abort`, the round budget,
`manifest.json.autonomy`, the four never-bypassable gates) is issue #9,
not yet built; this skill always halts at its checkpoint regardless.

Read `.claude/skills/_shared/run-bundle-layout.md` before changing
anything below (the authoritative schema for `analysis/round-NN.json`),
and read these before changing how this skill reasons or calls anything:
`_shared/resolution-ladder.md` (the order in which this skill tries to
resolve an open question), `_shared/keyword-provenance.md` (what a
finding from where may be used for), `_shared/checkpoint-format.md` (the
presentation this skill's Step 6 produces), and the three invocation
contracts this skill calls into — `_shared/log-query-invocation.md`,
`_shared/code-graph-invocation.md`, `_shared/notebooklm-invocation.md`.

```yaml
contract:
  requires: [issue_id, existing_run, scope]
  optional: [run_id, direction]
  produces:
    - .rca/issues/<issue_id>/runs/run-NN/analysis/round-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/evidence/tools.jsonl (appended)
    - .rca/issues/<issue_id>/runs/run-NN/raw/rca-analyze-q-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, updated_at, current_round, standing_recommendation only)
  self_seedable: false
```

`self_seedable: false` for the same reason as `rca-scope`: this skill
operates on a run bundle earlier skills already created. There is nothing
an engineer can pass at invocation that substitutes for a `scope.json`
having already been written — the fix for a missing one is to run
`rca-scope`, not to pass more arguments here.

## What this delivers

One round's worth of analysis: where in signalling or trace the failure
actually is, what competing explanations were tested against the log
(and, where available, code and documentation), what survived, and what
the round recommends investigating next — presented as a checkpoint, then
halted.

## Inputs

- `issue_id` (required, from invocation or `/rca`'s dispatch).
- `run_id` (optional) — which run to analyze. Defaults to `issue.json`'s
  `active_run` if set, else the highest-numbered entry in `issue.json.runs`
  — same resolution as `rca-scope`.
- `direction` (optional) — a candidate direction to pursue this round,
  naming a hypothesis ID or its statement from a prior round's
  `checkpoint.candidate_directions`. Absent for round 1, since there is no
  prior checkpoint to name a direction from. This ticket accepts the
  input and records it in `round-NN.json.direction`; the verb parsing that
  produces it from an engineer's `dig <direction>` reply is issue #9's.

## Steps

### 1. Resolve `issue_id` and the target run

Same resolution `rca-scope` uses, restated here so this skill needs no
other `SKILL.md` in context to run correctly:

1. If `issue_id` is missing, HALT: "Need a PLM issue ID to analyze. Which
   issue?" Do not guess one from conversation context.
2. If `.rca/issues/<issue_id>/` does not exist, HALT: "No run bundle for
   `<issue_id>` — run `rca-intake` first." Never create one here.
3. Read `issue.json`. Resolve the target run: the supplied `run_id`, else
   `active_run` if set, else the highest-numbered entry in `runs`. If none
   resolves, HALT: "`<issue_id>` has no runs yet — run `rca-intake`
   first."
4. Read that run's `manifest.json`. If it is missing, HALT: "Run
   `<run_id>` has no `manifest.json` — its bundle looks incomplete;
   re-run `rca-intake` or check for a partial write."

### 2. Check the scope precondition

Read `runs/run-NN/scope.json`. If it does not exist: HALT: "Run `<run_id>`
has no `scope.json` — run `rca-scope` first." This is this skill's
contract `requires` check for `scope` — never proceed with a guessed or
default window/tables/layers.

### 3. Determine the round number and read prior rounds

1. `round_number = manifest.json.current_round + 1`.
2. If `round_number > 1`: read every existing `analysis/round-<01..N-1>.json`
   in order — this is how `causal_chain_additions` accumulate into "the
   causal chain so far" (Step 6). Read only these files' own written
   content, never conversation history — a round run in a brand-new
   session must produce the same result as one run immediately after its
   predecessor.
3. If `direction` was supplied but `round_number == 1` (no prior round to
   have named it): treat it as if it were absent and note this
   inconsistency in `open_notes` rather than failing — the round still
   runs, just without a direction to narrow around.

### 4. Locate the failure point

Skip this step (reuse the prior round's `failure_point` unchanged) if a
prior round already has `failure_point.located: true` — the failure point
does not move between rounds of the same run.

Otherwise:

1. If `scope.json.failure_time.origin == "log"` (i.e. `tier ==
   "VERIFIED_LOG"`): that event **is** the failure point. Read the event
   detail from the `raw/` file `scope.json.failure_time.evidence_ref`
   already points at — no new tool call, no new ledger line for this;
   record it in `failure_point` with the same `evidence_ref`.
2. Otherwise (`scope.json.failure_time.origin` is `"engineer"` without
   independent log corroboration, or `"undetermined"`): work rung 1 of
   the resolution ladder — ask NotebookLM (per
   `notebooklm-invocation.md`) what messages/IEs signal failure for
   `scope.json.classification.issue_type`'s procedure (or, if `generic`,
   ask about the broader category implied by the PLM description). Take
   any keywords a cited answer suggests, plus — when
   `scope.json.classification.matched_playbook` is non-null — that same
   row's `failure_indicator_keywords` from
   `.claude/skills/rca-scope/references/known-issue-types.md` (the list
   `rca-scope` itself already tried; `scope.json` does not carry a copy of
   it, only the `matched_playbook` id needed to look the row back up), and
   issue one locate query (rung 2, per
   `log-query-invocation.md`) across `scope.json.tables_in_scope` within
   `scope.json.window`.
   - Hit: record `failure_point.located: true`, the event, `tier:
     "VERIFIED_LOG"`, and the ledger/raw reference.
   - Miss: `failure_point.located: false`, `event: null`, `tier: null`.
     Add an `open_notes` entry stating the failure point could not be
     pinned this round. This is **not** a HALT — the round continues to
     Step 5 and generates hypotheses at the broader scoped-window level
     instead of around a specific event; the checkpoint's evidence gaps
     (Step 6) states this plainly rather than presenting hypotheses as if
     they were anchored to something they are not.

### 5. Generate and test hypotheses

1. **Generate.** Produce 2–4 competing hypotheses for why the failure
   point (or, if unlocated, the scoped window's failure) occurred. Source
   them, per the resolution ladder:
   - When `direction` was supplied: at least one hypothesis narrows
     directly on it.
   - Rung 1/4 (NotebookLM, spec then vendor documentation): ask what
     typically causes this failure signature for this procedure/chip
     series; each cited answer may seed one hypothesis, recorded with its
     citation.
   - A guess (FORBIDDEN-origin keyword, permitted only to ask per
     `keyword-provenance.md`) may seed a hypothesis when the ladder above
     produced nothing usable — state plainly in the hypothesis that its
     origin is a guess, not a citation.
   - Rung 6 (prior cases): not yet available (`rca-learn` is issue #11).
     State this once in `open_notes` rather than silently skipping it if
     this round would otherwise have consulted it.
   For each hypothesis, state its `predicted_evidence` (what a query
   would show if it were true) and its `testing_query` (precise enough —
   table + keywords, or a code-graph target — that the checkpoint's
   reader can judge the reasoning before it runs).
2. **Test.** Run each hypothesis's `testing_query`, and append one entry
   to that hypothesis's `queries[]` for every attempt, hit or miss alike
   — this is the ledger reference the checkpoint uses to tell "surviving
   with evidence" apart from "surviving but untested":
   - **`log-query`** (per `log-query-invocation.md`, narrowed to the
     table(s) that hypothesis actually concerns): a hit appends
     `{ledger_ref, outcome: "hit", tier: "VERIFIED_LOG"}` and keeps the
     hypothesis `surviving`. A miss appends `{ledger_ref, outcome: "miss",
     tier: null}` and keeps it `surviving` too — per
     `keyword-provenance.md`, a miss never eliminates anything on its
     own.
   - **`code-search`** (per `code-graph-invocation.md`): `resolved: true`
     appends a `queries[]` entry at `tier: "CODE_BOUND"`. `is_lib: true`
     records the branch this hypothesis depends on as `CODE_UNAVAILABLE`
     in `open_notes` (still appended to `queries[]`, `tier: null`) and
     leaves the hypothesis `surviving` at whatever tier its other
     evidence supports — the round continues, it does not stall on a lib
     module.
   - **`notebooklm`** (per `notebooklm-invocation.md`): never decides
     elimination by itself — its answer appends a `queries[]` entry at
     `tier: "SPEC_INFERRED"` (with citation) and supports the hypothesis
     only until independently checked against log or code per that
     file's "Promotion and verification".
3. **Eliminate.** A hypothesis moves to `eliminated` only when a HARD
   finding (from `log-query` or `code-search`) is **positively
   incompatible** with it — e.g. a trace entry showing the UE never
   received a frame the hypothesis assumes it processed, or a code path
   the trace shows was taken that the hypothesis's premise rules out.
   Record that finding's ledger reference in `eliminated_by`. Never
   eliminate a hypothesis from a keyword miss alone, and never eliminate
   more than one hypothesis from a single finding unless that finding
   genuinely contradicts each of them individually — state each
   contradiction on its own terms rather than treating "one thing was
   found" as ruling out everything else at once.
4. **Extend the causal chain.** Any finding strong enough to stand on its
   own regardless of which hypothesis it came from (e.g. the failure
   point itself, or a `CONTRADICTED` vendor-doc claim) is appended to
   `causal_chain_additions` with its tier and evidence reference — this
   is what accumulates across rounds into "the causal chain so far".

### 6. Write `round-NN.json` and the checkpoint

1. Write `analysis/round-<NN>.json` per the schema in
   `run-bundle-layout.md`, zero-padded, at the number determined in Step
   3. Never overwrite an existing round file, including this run's own
   prior rounds.
2. Build `checkpoint` per `checkpoint-format.md`:
   - **Causal chain so far**: every `causal_chain_additions` entry from
     every round of this run so far, this round's included, each with its
     tier.
   - **Ranked candidate directions**: every `surviving` hypothesis,
     ranked by how directly it would extend the chain if confirmed, each
     with its predicted evidence and testing query restated for direct
     display.
   - **Recommendation**: the top-ranked surviving direction, or — if none
     survived, or the failure point itself could not be located — a
     plain statement of that and what information would unblock the
     round, never a direction picked merely to look decisive.
   - **Evidence gaps**: every `SPEC_INFERRED`/`ASSUMED`/`TESTER_REPORTED`
     finding this round rests on, every `CODE_UNAVAILABLE` branch, every
     `CONTRADICTED` finding named explicitly, and every ladder rung this
     round could not resolve (including "prior cases — not yet
     available").

### 7. Update `manifest.json`

Update in place: `current_step: "rca-analyze"`, `current_round:
<round_number>`, `standing_recommendation` = this round's
`checkpoint.recommendation`, `updated_at` to now. Leave `next_step` and
`status` untouched — deciding what the true next step is (another round,
`rca-conclude`, something else) based on the engineer's response to this
checkpoint is issue #9's loop's decision to make, not this skill's; this
skill only reports what it found.

### 8. Report to the engineer and HALT

Render `checkpoint` in the four-section form `checkpoint-format.md`
specifies. State plainly that this round has ended and that continuing
(`dig`, `redirect`, `accept`, `abort`) is issue #9's mechanism, not yet
built in this suite — do not imply the next round will run automatically,
and do not act on `manifest.json.autonomy` regardless of its value.

## What this skill does not do

- ❌ Never writes or modifies `scope.json` — reads it only.
- ❌ Never eliminates a hypothesis from a keyword miss, a tool being
  unavailable, or a module being a lib — only from a positive,
  contradicting HARD finding.
- ❌ Never uses an uncited NotebookLM answer for anything — not a
  hypothesis, not a query keyword, nothing (`keyword-provenance.md`,
  `notebooklm-invocation.md`).
- ❌ Never presents a `SPEC_INFERRED`/`ASSUMED` finding with the same
  confidence as a `VERIFIED_LOG`/`CODE_BOUND` one in the checkpoint's
  causal chain or recommendation — that confusion is exactly what the
  evidence-gaps section exists to prevent.
- ❌ No `dig`/`redirect`/`abort` handling, no round-budget enforcement, no
  `manifest.json.autonomy` behavior, no reaching a final root cause or
  reproduction scenario — issues #9 and #10 respectively, not yet built.
- ❌ No chaining into another round or into `rca-conclude` — halts after
  Step 8 unconditionally.
