---
name: rca-analyze
description: >
  Run one or more rounds of hypothesis-driven analysis on an existing,
  scoped PLM-issue RCA run — locate the failure point, generate and test
  competing hypotheses via log-query/code-graph/NotebookLM — then present
  a checkpoint and either halt or, under `manifest.json.autonomy`,
  continue automatically. Also handles an engineer's reply to a standing
  checkpoint (`dig <direction>`, `redirect <information>`, `accept`,
  `abort`), enforces the round budget, and records each (agent
  recommendation, engineer decision) pair. Writes `analysis/round-NN.json`
  and updates `manifest.json`. Use when an engineer wants to run,
  continue, or reply to a round of analysis on a run that already has a
  `scope.json` (e.g. "analyze PLM-12345", "dig into H2", "redirect: it's a
  Qualcomm 9205 build", "accept this", "abort this run"). Requires
  `scope.json` to exist — invoke `rca-scope` first if it does not. Do NOT
  use this for the older v6 3GPP fault-tree suite's FTA skills
  (`.cline/skills/3gpp-fta-*`) — unrelated pipeline, no PLM issue ID, no
  run bundle. Do NOT use this to classify an issue or narrow the
  window/tables/layers — that's `rca-scope`, which this skill only reads.
  Do NOT use this to actually reach a final root cause or reproduction
  scenario — that's `rca-conclude`; `accept` here only records the
  decision and names `rca-conclude` as next, it never invokes it.
---

# rca-analyze

Part of the PLM-issue pipeline (issue #5): `rca-intake → rca-scope →
rca-analyze ⟲ → rca-conclude → rca-learn`. This is the pipeline's third
step, and the one the parent spec's skill table marks "Runs as a loop" —
issue #8 built one round ending at a checkpoint; issue #9 adds the loop
around it (`dig <direction>` / `redirect <information>` / `accept` /
`abort`, the round budget, `manifest.json.autonomy`, and the four
never-bypassable gates). Both live in this one skill: there is no separate
loop-controller skill, because the loop's state (which round is current,
what was recommended, what the engineer decided) is exactly the state this
skill already owns.

Read `.claude/skills/_shared/run-bundle-layout.md` before changing
anything below (the authoritative schema for `analysis/round-NN.json` and
`manifest.json`, including `manifest.json.decisions[]`), and read these
before changing how this skill reasons or calls anything:
`_shared/resolution-ladder.md` (the order in which this skill tries to
resolve an open question), `_shared/keyword-provenance.md` (what a
finding from where may be used for, including how a `redirect`'s
`ENGINEER_PROVIDED` input fits in), `_shared/checkpoint-format.md` (the
presentation this skill's checkpoint step produces, including its
"How to respond" section), and the three invocation contracts this skill
calls into — `_shared/log-query-invocation.md`,
`_shared/code-graph-invocation.md`, `_shared/notebooklm-invocation.md`.

```yaml
contract:
  requires: [issue_id, existing_run, scope]
  optional: [run_id, verb, direction, redirect_info, override]
  produces:
    - .rca/issues/<issue_id>/runs/run-NN/analysis/round-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/evidence/tools.jsonl (appended)
    - .rca/issues/<issue_id>/runs/run-NN/raw/rca-analyze-q-NN.json
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, updated_at, current_round, standing_recommendation, decisions always; next_step, status only on accept/abort)
  self_seedable: false
```

`self_seedable: false` for the same reason as `rca-scope`: this skill
operates on a run bundle earlier skills already created. There is nothing
an engineer can pass at invocation that substitutes for a `scope.json`
having already been written — the fix for a missing one is to run
`rca-scope`, not to pass more arguments here.

## What this delivers

One or more rounds' worth of analysis: where in signalling or trace the
failure actually is, what competing explanations were tested against the
log (and, where available, code and documentation), what survived, and
what the round recommends investigating next — presented as a checkpoint.
Whether that checkpoint halts and waits, or the skill takes its own
recommendation and keeps going, depends on `manifest.json.autonomy` and
the four gates below; either way, every checkpoint reached is recorded as
a decision pair in `manifest.json.decisions[]`.

## Inputs

- `issue_id` (required, from invocation or `/rca`'s dispatch).
- `run_id` (optional) — which run to analyze. Defaults to `issue.json`'s
  `active_run` if set, else the highest-numbered entry in `issue.json.runs`
  — same resolution as `rca-scope`.
- `verb` (optional) — the engineer's reply to the run's standing
  checkpoint: `dig`, `redirect`, `accept`, or `abort`. Absent when this
  invocation is a fresh start (round 1) or a bare re-ask with no reply
  encoded (see Step 3). Parsed from the invocation's own text (e.g. "dig
  into H2", "redirect: it's a Qualcomm 9205 build", "accept", "abort —
  build is being retired") — never inferred from earlier turns of the
  conversation that aren't also present in this same invocation.
- `direction` (optional) — used with `dig`: a hypothesis ID or statement
  from the standing checkpoint's `candidate_directions`. Also accepted
  bare (no `verb`) as a direct-invocation shortcut with the same meaning,
  for engineers who already know exactly which hypothesis they want
  pursued.
- `redirect_info` (optional) — used with `redirect`: the engineer-supplied
  information text, verbatim.
- `override` (optional) — supplied only alongside `dig` at the round
  budget, together with a one-line rationale in the same text (e.g. "dig
  override H3 — this is a known-hard issue, need one more round; rationale:
  prior five rounds all pointed the same direction but none reached
  VERIFIED_LOG"). Absent otherwise. See Step 7's round-budget gate for
  exactly what this unlocks and what it does not.

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
5. If `manifest.json.status == "aborted"`: HALT: "Run `<run_id>` was
   aborted (`<manifest.json`'s most recent `decisions[]` entry with
   `verb: "abort"`, its `input`>). Start a new run with `rca-intake` to
   analyze this issue further — an aborted run is never resumed or
   reopened." This is a hard stop regardless of `verb` supplied — even
   `dig`/`redirect` on an aborted run does not resurrect it.

### 2. Check the scope precondition

Read `runs/run-NN/scope.json`. If it does not exist: HALT: "Run `<run_id>`
has no `scope.json` — run `rca-scope` first." This is this skill's
contract `requires` check for `scope` — never proceed with a guessed or
default window/tables/layers.

### 3. Resolve this invocation's verb against the standing checkpoint

`manifest.json.current_round` says how many rounds already exist (`0` for
a fresh run — go straight to Step 4 with `direction: null`,
`engineer_redirect: null`, skipping the rest of this step; any `verb`
supplied on a round-0 invocation is meaningless and is ignored with an
`open_notes` note on round 1 rather than an error). Otherwise, the round
numbered `manifest.json.current_round` is the standing checkpoint this
invocation is replying to; read its `checkpoint` section (already on disk
— never re-derived from conversation).

1. **`verb` is `"accept"`**: go to "Handling `accept`" below instead of
   Step 4. No new round is written.
2. **`verb` is `"abort"`**: go to "Handling `abort`" below instead of
   Step 4. No new round is written.
3. **`verb` is `"dig"`**: `direction` = the supplied direction (HALT if
   none supplied: "`dig` needs a direction — which candidate? [lists
   `checkpoint.candidate_directions` by id]"). `engineer_redirect = null`.
   If the standing round is at the round budget (Step 7's gate tripped on
   it), this `dig` is only honored when `override` is also supplied with a
   rationale — otherwise HALT restating the budget gate exactly as that
   round's checkpoint already stated it, and do not proceed to Step 4.
4. **`verb` is `"redirect"`**: HALT if `redirect_info` is empty: "`redirect`
   needs the information itself — what should the agent know?" Otherwise
   `engineer_redirect = {"text": redirect_info, "tier":
   "ENGINEER_PROVIDED", "recorded_at": <now>}`. `direction` = the standing
   round's own `checkpoint.recommendation.direction` — a redirect adds a
   premise to the same line of inquiry, it does not by itself pick a
   different candidate. This is deliberately **not** a literal in-place
   rewrite of the standing round: `run-bundle-layout.md`'s append-only
   discipline ("a round's file is never overwritten once written") applies
   to a `redirect` exactly as it does to every other reply, precisely so
   round N+1 stays provable against round N's actual recorded state rather
   than a version silently rewritten after the fact — "re-running the
   round" against new information means writing the *next* round with
   that information now in hand, not mutating the one already shown to
   the engineer.
5. **No `verb`, but `direction` supplied directly**: treat exactly as case
   3 above (a direct-invocation shortcut), except the round-budget gate
   still applies identically — a bare `direction` does not bypass it.
6. **No `verb`, no `direction`**: the engineer is asking to continue
   without stating how. `direction` = the standing round's own
   `checkpoint.recommendation.direction`; `engineer_redirect = null`. Note
   in the new round's `open_notes` that no explicit verb was supplied.

For cases 3, 5, and 6, before proceeding to Step 4: record this round's
decision pair now, onto `manifest.json.decisions[]` (append, never
rewrite an existing entry) — `round` = the standing round's number,
`agent_recommendation` = its `checkpoint.recommendation` verbatim,
`engineer_response = {"verb": <"dig" or the case-6 implicit "dig">,
"input": direction, "recorded_at": <now>}`, `override` = whether an
override applied (case 3's budget path only), `override_rationale` = the
rationale text when `override` is true, else `null`. Case 4 (`redirect`)
records the same shape with `verb: "redirect"` and `input: redirect_info`.
This happens once per standing round — if `manifest.json.decisions[]`
already has an entry for this exact round number (a second reply arriving
after the loop already advanced), do not append a duplicate; proceed using
the new reply's `direction`/`engineer_redirect` for the round about to be
written regardless, since the engineer is entitled to redirect again even
after an auto-continued round, but the audit trail keeps only the first
recorded response per round it replies to plus this new one tagged against
the round it actually produces.

### 4. Determine the round number and read prior rounds

1. `round_number = manifest.json.current_round + 1`.
2. If `round_number > manifest.json.round_budget` and no override was
   established in Step 3: this should be unreachable (Step 3's budget
   check and Step 7's gate both guard it), but if reached anyway, HALT:
   "Round budget (`<round_budget>`) already reached for run `<run_id>` —
   reply `accept`, `abort`, or `dig override <direction>` with a
   rationale." Never silently write a round past budget.
3. If `round_number > 1`: read every existing `analysis/round-<01..N-1>.json`
   in order — this is how `causal_chain_additions` accumulate into "the
   causal chain so far" (the checkpoint step). Read only these files' own
   written content, never conversation history — a round run in a
   brand-new session must produce the same result as one run immediately
   after its predecessor, given the same `direction`/`engineer_redirect`
   inputs Step 3 resolved.

### 5. Locate the failure point

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
     Step 6 and generates hypotheses at the broader scoped-window level
     instead of around a specific event; the checkpoint's evidence gaps
     states this plainly rather than presenting hypotheses as if they
     were anchored to something they are not. It **is**, however, a trip
     of Step 7's "ask the engineer" gate: an unlocated failure point means
     the ladder had to reach rung 5 for the round's very anchor, so this
     round's checkpoint always halts regardless of `autonomy`.

### 6. Generate and test hypotheses

1. **Generate.** Produce 2–4 competing hypotheses for why the failure
   point (or, if unlocated, the scoped window's failure) occurred. Source
   them, per the resolution ladder:
   - When `engineer_redirect` is set (this round is answering a
     `redirect`): read it first, before any tool call. It may directly
     supply a keyword, rule a hypothesis in or out as a premise, or state
     a fact strong enough to become a `causal_chain_additions` entry on
     its own (tier `ENGINEER_PROVIDED`, per `evidence-tiers.md`'s rule
     that such a premise "may override an agent inference... but a
     conclusion resting on one is always labelled" as such — the
     checkpoint's evidence gaps must name it explicitly). At least one
     hypothesis this round incorporates it.
   - When `direction` was supplied (from a `dig`, an implicit continue, or
     a redirect's inherited direction): at least one hypothesis narrows
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
   reader can judge the reasoning before it runs). If, for a given
   hypothesis, truly no viable query can be constructed at all — no
   keyword, no code-graph target, nothing to point a tool at — do not
   fabricate a query to keep the shape uniform: leave `testing_query` as
   the best statement of what's missing, `queries: []`, and set
   `untested_tier: "ASSUMED"` on that hypothesis. This is rare and is what
   Step 7's ASSUMED-finding gate checks for on the round's *recommended*
   direction specifically.
2. **Test.** Run each hypothesis's `testing_query` (skip this for a
   hypothesis Step 1 just marked `untested_tier: "ASSUMED"` — there is
   nothing to run), and append one entry to that hypothesis's `queries[]`
   for every attempt, hit or miss alike — this is the ledger reference the
   checkpoint uses to tell "surviving with evidence" apart from "surviving
   but untested":
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
   point itself, an `engineer_redirect` fact, or a `CONTRADICTED`
   vendor-doc claim) is appended to `causal_chain_additions` with its
   tier and evidence reference — this is what accumulates across rounds
   into "the causal chain so far".

### 7. Write `round-NN.json`, build the checkpoint, and evaluate the gates

1. Write `analysis/round-<NN>.json` per the schema in
   `run-bundle-layout.md`, zero-padded, at the number determined in Step
   4, including `direction`/`engineer_redirect` from Step 3. Never
   overwrite an existing round file, including this run's own prior
   rounds.
2. `forced_by_round_budget = (round_number == manifest.json.round_budget)`.
   When true, the recommendation below is forced to acceptance regardless
   of what survived — the round still runs and still reports what it
   found, but section 3 of the checkpoint states plainly that the budget
   is why acceptance is being recommended, and section 4 states what
   remains unproven.
3. Build `checkpoint` per `checkpoint-format.md`:
   - **Causal chain so far**: every `causal_chain_additions` entry from
     every round of this run so far, this round's included, each with its
     tier.
   - **Ranked candidate directions**: every `surviving` hypothesis,
     ranked by how directly it would extend the chain if confirmed, each
     with its predicted evidence and testing query restated for direct
     display. Empty when `forced_by_round_budget` and nothing survived —
     stated as such, not omitted.
   - **Recommendation**: `forced_by_round_budget` ? `{"direction": null,
     "reason": "round budget (<round_budget>) reached; recommending
     acceptance — see evidence gaps for what remains unproven"}` : the
     top-ranked surviving direction, or — if none survived, or the
     failure point itself could not be located — a plain statement of
     that and what information would unblock the round, never a
     direction picked merely to look decisive.
   - **Evidence gaps**: every `SPEC_INFERRED`/`ASSUMED`/`TESTER_REPORTED`
     finding this round rests on (including any `untested_tier:
     "ASSUMED"` hypothesis), every `ENGINEER_PROVIDED` premise this round
     relied on, every `CODE_UNAVAILABLE` branch, every `CONTRADICTED`
     finding named explicitly, and every ladder rung this round could not
     resolve (including "prior cases — not yet available").
4. **Evaluate the four never-bypassable gates**, in this order, against
   this round exactly as just written — this determines whether this
   round's checkpoint halts no matter what `autonomy` says:
   1. **Round budget** — `forced_by_round_budget == true`. Always halts.
      The only gate an explicit, rationale-carrying override (Step 3,
      case 3) can move past, and only for one more round at a time — the
      next round is itself subject to the same check against the same
      `round_budget` (which this skill never raises on its own; only an
      engineer editing `manifest.json.round_budget` directly changes it).
   2. **ASSUMED finding** — the round's `checkpoint.recommendation`
      names a direction whose hypothesis carries `untested_tier:
      "ASSUMED"`. Always halts. Not overridable.
   3. **Ladder reached "ask the engineer"** — `failure_point.located ==
      false` this round, or an `open_notes` entry this round states the
      recommended direction itself depends on a question no rung 1–4
      resolved. Always halts. Not overridable.
   4. **Final acceptance** — `forced_by_round_budget == true`, OR nothing
      survived this round and nothing remains to test (every hypothesis
      `eliminated`, no untested candidate left). Always halts — this
      skill never invokes `rca-conclude`, at any autonomy setting; it
      only ever recommends `accept` as the next reply. Not overridable
      (this is the same event as gate 1 when it's budget-driven, and a
      distinct one when the analysis simply converges early).
   Record which gate(s), if any, tripped — this drives Step 8.

5. **Update `manifest.json` for this round, unconditionally, before
   Step 8 decides anything**: `current_step: "rca-analyze"`,
   `current_round: <round_number>`, `standing_recommendation` = this
   round's `checkpoint.recommendation`, `updated_at` to now. Leave
   `decisions` exactly as Step 3 left it (a fresh round 1 with no prior
   checkpoint appended nothing there) — Step 8.2 appends to it separately,
   below, only when it auto-continues. Leave `next_step` and `status`
   untouched here — deciding whether the true next step is another round,
   `rca-conclude`, or something else happens on the *next* invocation of
   this skill (or is handled in "Handling `accept`"/"Handling `abort`").
   This write must happen for every round this invocation produces,
   including ones that immediately auto-continue — Step 4's
   `round_number = manifest.json.current_round + 1` on the *next* pass
   through this loop depends on `current_round` already reflecting the
   round just written, or the next round would recompute the same number
   and collide with "a round's file is never overwritten once written."

### 8. Decide: halt, or continue automatically

1. If any gate from Step 7.4 tripped, OR `manifest.json.autonomy ==
   "review_all"`: halt at this round's checkpoint (`manifest.json` is
   already current, per Step 7.5). Go to "Report to the engineer and
   HALT" below.
2. Otherwise (`autonomy` is `"auto_until_blocked"` or `"auto"`, and no
   gate tripped): do not wait for an engineer reply. Append a
   `manifest.json.decisions[]` entry for the round Step 7 just wrote —
   `round` = that round's number, `agent_recommendation` = its
   `checkpoint.recommendation`, `engineer_response = {"verb":
   "auto_continue", "input": checkpoint.recommendation.direction,
   "recorded_at": <now>}`, `override: false`, `override_rationale: null`
   — then set `direction = checkpoint.recommendation.direction`,
   `engineer_redirect = null`, and go back to Step 4 to write the next
   round within this same invocation (Step 7.5's update to `current_round`
   is what makes Step 4.1's `round_number` calculation land on the next
   number, not a repeat of this one).
   `"auto_until_blocked"` and `"auto"` differ only in framing, never in
   which gates apply — both are stopped by exactly the four gates above
   and nothing else; `"auto"` is the setting an engineer chooses expecting
   the loop to typically run all the way to the round budget on a routine
   issue, `"auto_until_blocked"` expecting it to typically stop sooner at
   whichever gate the issue actually hits. Say which framing is in effect
   in the final halted report (see below) so the engineer can tell the
   difference between "this stopped early because it hit something" and
   "this ran to budget as expected."

### Handling `accept`

Reached only from Step 3 when `verb == "accept"`; no new round is written.

1. Append a `manifest.json.decisions[]` entry for the standing round (or,
   if `current_round == 0`, a decision with `round: 0` and
   `agent_recommendation: null` — there is no round to have recommended
   anything yet, the engineer is simply declining to run one):
   `agent_recommendation` = the standing round's `checkpoint.recommendation`
   when one exists, `engineer_response = {"verb": "accept", "input": null,
   "recorded_at": <now>}`. `override`/`override_rationale` here simply
   record the fact when applicable — `override: true` (with whatever
   rationale text, if any, came with the reply, else `override_rationale:
   null`) when that round's recommendation was *not* itself an acceptance
   recommendation (the engineer is accepting earlier than the analysis
   itself suggested, or there was no round at all); `override: false`,
   `override_rationale: null` otherwise. Unlike the round-budget gate
   (Step 3, case 3), this is never itself a HALT condition — the spec's
   override/rationale requirement is specifically the round-budget gate's;
   `accept` is always available to the engineer and this entry only
   records that they used it early, it never blocks them for not
   explaining why.
2. Update `manifest.json`: `next_step: "rca-conclude"`, `current_step:
   "rca-analyze"`, `updated_at` to now. Leave `status` as `"in_progress"`
   — the run is not concluded, only handed off; `rca-conclude` (issue #10)
   is what actually reaches a conclusion.
3. Report: the decision is recorded, the next pipeline step is
   `rca-conclude` — do not imply it will run automatically; invoking it
   (directly, or via `/rca`'s dispatch) is a separate step this skill does
   not take itself. HALT.

### Handling `abort`

Reached only from Step 3 when `verb == "abort"`; no new round is written.

1. Append a `manifest.json.decisions[]` entry for the standing round (or,
   if `current_round == 0`, a decision with `round: 0`): `agent_recommendation`
   = the standing round's `checkpoint.recommendation` if one exists, else
   `null`; `engineer_response = {"verb": "abort", "input": <the reason
   text supplied with the abort reply, or "no reason given">,
   "recorded_at": <now>}`; `override: false`, `override_rationale: null`
   (aborting is never a gate to override, it is always available).
2. Update `manifest.json`: `status: "aborted"`, `next_step: null`,
   `current_step: "rca-analyze"`, `updated_at` to now. This is permanent —
   Step 1.5 refuses to resume an aborted run.
3. Report: the run is closed without a conclusion, and why (the reason
   just recorded). State that a new run via `rca-intake` is required to
   analyze this issue further. HALT.

### Report to the engineer and HALT

Render `checkpoint` in the five-section form `checkpoint-format.md`
specifies (sections 1–4 plus "How to respond") for whichever round
actually halted — the last one written, if `autonomy` auto-continued
through several within this invocation. When more than one round ran
automatically in this invocation, briefly list them in order (round
number, direction pursued, one-line outcome) before the final checkpoint,
so the engineer can see what happened without reading every
`round-NN.json` — but only the final round's full checkpoint sections
render in full. State plainly which gate (if any) caused the halt, or
that the round budget was reached, per Step 7.4/8.

## What this skill does not do

- ❌ Never writes or modifies `scope.json` — reads it only.
- ❌ Never eliminates a hypothesis from a keyword miss, a tool being
  unavailable, or a module being a lib — only from a positive,
  contradicting HARD finding.
- ❌ Never uses an uncited NotebookLM answer for anything — not a
  hypothesis, not a query keyword, nothing (`keyword-provenance.md`,
  `notebooklm-invocation.md`).
- ❌ Never presents a `SPEC_INFERRED`/`ASSUMED`/`ENGINEER_PROVIDED`
  finding with the same confidence as a `VERIFIED_LOG`/`CODE_BOUND` one in
  the checkpoint's causal chain or recommendation — that confusion is
  exactly what the evidence-gaps section exists to prevent.
- ❌ Never auto-continues past a tripped gate, at any `autonomy` setting —
  the four gates in Step 7.4 are not a suggestion, and only the round
  budget is overridable at all, and only with an explicit rationale.
- ❌ Never raises `round_budget` itself, never re-enables an aborted run,
  never sets `manifest.json.status` back out of `"aborted"`.
- ❌ Never invokes `rca-conclude` — an `accept` reply only records the
  decision and names it as the next step.
- ❌ No reaching a final root cause, causal-chain synthesis, or
  reproduction scenario — that is `rca-conclude`.
