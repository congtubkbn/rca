---
name: rca-conclude
description: >
  Synthesize an existing PLM-issue RCA run's accepted analysis into its
  three deliverables — the problem (observable failure point), the root
  cause with its causal chain, and a protocol-level reproduction scenario
  checked against the tester's reported steps — then present the draft and
  wait for the engineer to `accept` (which sets `issue.json.active_run`
  and hands off to `rca-learn`) or `abort` it. Writes `conclusion.json` and
  `CONCLUSION.md`. Use ONLY when an engineer wants to conclude, finalize,
  or confirm the root cause of a run whose analysis has already been
  accepted (e.g. "conclude PLM-12345", "what's the root cause here",
  "accept this conclusion", "draft the reproduction scenario"). Requires
  `manifest.json.next_step == "rca-conclude"` (set by `rca-analyze`'s own
  `accept` reply) or an existing `conclusion.json` on this run — invoke
  `rca-analyze` and reply `accept` to its checkpoint first if neither
  holds. Do NOT use this for the older, independent v6 3GPP fault-tree
  suite's `3gpp-fta-root-cause`/`3gpp-rca-orchestrator` skills
  (`.cline/skills/`) — that suite's Phase 3.5/Phase 4 write an entirely
  different `/tmp/rca_state_*.json` state file, have no PLM issue ID, and
  have no run-bundle concept at all. Do NOT use this to run further
  analysis, generate or test hypotheses, or locate a failure point — that
  is `rca-analyze`, which this skill only reads. Do NOT use this to
  produce a Technical Report — that is `tr-creator`, a separate,
  explicitly invoked skill this skill never calls. Do NOT use this to
  propose a fix, patch, configuration change, or test case — this skill
  mechanically refuses to write any of those, by design.
---

# rca-conclude

Part of the PLM-issue pipeline (issue #5): `rca-intake → rca-scope →
rca-analyze ⟲ → rca-conclude → rca-learn`. This is the pipeline's fourth
step (issue #10), reached only after an engineer has replied `accept` to
`rca-analyze`'s standing checkpoint. Its job is synthesis, not
investigation: it runs no new log, code, or NotebookLM query of its own —
it reads what `rca-scope` and `rca-analyze` already wrote and assembles it
into the three outputs issue #5's spec calls for, as data rather than
prose: the **problem**, the **root cause** with its **causal chain**, and
a **reproduction scenario**, each stated at protocol level with its own
evidence tier.

Read `.claude/skills/_shared/run-bundle-layout.md` before changing
anything below — it is the authoritative schema for `conclusion.json`,
including exactly which fields this skill may copy forward from
`scope.json`/`analysis/round-NN.json` versus author itself. Also read
`_shared/evidence-tiers.md` — specifically its `CONTRADICTED` tier
("never improves when copied forward" plus the fact that this skill is
the first to apply `CONTRADICTED` against the tester's own PLM account as
a source, not only spec/vendor-doc/prior-case). This skill does not call
`_shared/keyword-provenance.md`'s ranking mechanism at all — that file
governs promoting a SOFT (NotebookLM) claim during `rca-analyze`'s
rounds, a different, source-ranking concern this skill has no part in; nor
does it call `_shared/log-query-invocation.md`, `code-graph-invocation.md`,
or `notebooklm-invocation.md` — it makes no tool calls of any of those
kinds.

```yaml
contract:
  requires: [issue_id, existing_run, accepted_analysis]
  optional: [run_id, verb]
  produces:
    - .rca/issues/<issue_id>/runs/run-NN/conclusion.json
    - .rca/issues/<issue_id>/runs/run-NN/CONCLUSION.md
    - .rca/issues/<issue_id>/issue.json (active_run only, on this skill's own accept)
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, updated_at always; next_step, status only on this skill's own accept/abort)
  self_seedable: false
```

`accepted_analysis` means `manifest.json.next_step == "rca-conclude"` —
the record that an engineer already replied `accept` to `rca-analyze`'s
checkpoint (see that skill's "Handling `accept`"). `self_seedable: false`
for the same reason as `rca-scope`/`rca-analyze`: there is nothing an
engineer can pass at invocation that substitutes for that reply having
already happened — the fix for a missing one is to reply `accept` to
`rca-analyze`, not to pass more arguments here.

## What this delivers

A draft conclusion the engineer reviews and either confirms or discards —
never a conclusion this skill decides on its own to finalize. Confirming
is the one action in this whole suite that marks a run as *the* accepted
analysis for its issue (`issue.json.active_run`): the point past which a
Technical Report or a case record may be built from it. This skill never
produces either of those itself.

## Inputs

- `issue_id` (required, from invocation or `/rca`'s dispatch).
- `run_id` (optional) — which run to conclude. Defaults to `issue.json`'s
  `active_run` if set, else the highest-numbered entry in `issue.json.runs`
  — same resolution as `rca-scope`/`rca-analyze`.
- `verb` (optional) — the engineer's reply to a standing draft:
  `accept` or `abort`. Parsed from the invocation's own text (e.g.
  "accept", "abort — build is being retired"). Absent when this invocation
  is producing the first draft, or is a bare re-ask against a standing
  draft (see Step 3).

## Steps

### 1. Resolve `issue_id` and the target run

Same resolution `rca-scope`/`rca-analyze` use, restated here so this skill
needs no other `SKILL.md` in context to run correctly:

1. If `issue_id` is missing, HALT: "Need a PLM issue ID to conclude. Which
   issue?" Do not guess one from conversation context.
2. If `.rca/issues/<issue_id>/` does not exist, HALT: "No run bundle for
   `<issue_id>` — run `rca-intake` first." Never create one here.
3. Read `issue.json`. Resolve the target run: the supplied `run_id`, else
   `active_run` if set, else the highest-numbered entry in `runs`. If none
   resolves, HALT: "`<issue_id>` has no runs yet — run `rca-intake` first."
4. Read that run's `manifest.json`. If it is missing, HALT: "Run
   `<run_id>` has no `manifest.json` — its bundle looks incomplete;
   re-run `rca-intake` or check for a partial write."
5. If `manifest.json.status == "aborted"`: HALT: "Run `<run_id>` was
   aborted (`<manifest.json`'s most recent `decisions[]` entry with
   `verb: "abort"`, its `input`>). Start a new run with `rca-intake` to
   analyze this issue further." This is a hard stop regardless of `verb`
   supplied.

### 2. Check the accepted-analysis precondition

Read `runs/run-NN/conclusion.json` (it may not exist yet).

- If `conclusion.json` does not exist AND `manifest.json.next_step !=
  "rca-conclude"`: HALT: "Run `<run_id>` has not been accepted for
  conclusion yet (`next_step` is currently `<value>`) — reply `accept` to
  `rca-analyze`'s standing checkpoint first, or run `rca-analyze` to
  continue analysis." This is this skill's contract `requires` check for
  `accepted_analysis` — never proceed on a guessed or premature
  conclusion.
- If `conclusion.json` exists and `confirmed == true`: this run's
  conclusion is already final. HALT: "Run `<run_id>` already has a
  confirmed conclusion (confirmed at `<confirmed_at>`). To analyze this
  issue further, start a new run via `rca-intake` — a confirmed conclusion
  is never reopened or rewritten." Even a `verb` supplied here does not
  reopen it.
- Otherwise (no `conclusion.json` yet and `next_step == "rca-conclude"`,
  or `conclusion.json` exists with `confirmed: false`): proceed.

### 3. Resolve this invocation against the standing draft

- **No `conclusion.json` exists yet**: this is the first draft. Go to Step
  4 (Synthesize).
- **`conclusion.json` exists, `confirmed: false`**:
  1. `verb == "accept"`: go to "Handling `accept`" below instead of Step
     4.
  2. `verb == "abort"`: go to "Handling `abort`" below instead of Step 4.
  3. Otherwise (a bare re-ask with no `verb`): do not re-synthesize or
     touch `conclusion.json`/`CONCLUSION.md` — go straight to Step 8 and
     re-render the existing, already-written draft's report, exactly as
     first presented, as a reminder of what's pending confirmation. A
     draft is written once (Step 4–7) and never silently rewritten before
     confirmation; an engineer who wants a materially different draft
     replies `abort` and starts a new run via `rca-intake`, the same
     escape hatch every other gate in this suite uses when the answer
     isn't "continue as recommended."

### 4. Synthesize the draft

Read only what's needed, never the whole bundle:
`input/plm-snapshot.json`, `runs/run-NN/scope.json`, and every existing
`runs/run-NN/analysis/round-NN.json` in round order (empty if
`manifest.json.current_round == 0` — a legitimate case, see below).

1. **`problem`** — the observable failure point:
   - If any round has `failure_point.located: true`: use the **latest**
     such round's `failure_point` (the failure point does not move between
     rounds of a run, per `rca-analyze/SKILL.md`'s Step 5 — this is just
     reading the value already settled). `located: true`, `statement`
     derived from its `event` (timestamp, layer, message), `tier` and
     `evidence_ref` copied verbatim.
   - Else if no round exists or every round has `failure_point.located:
     false`, but `scope.json.failure_time.tier` is non-null: fall back to
     `scope.json.failure_time` — `located: true` (a time anchor, even
     without a located message exchange, is still an observed point in
     the log), `statement` states this is the scoped failure time rather
     than a located event, `tier`/`evidence_ref` copied verbatim from
     `scope.json.failure_time`.
   - Else: `located: false`, `statement` states plainly that no failure
     point was ever pinned in this run, `tier: null`, `evidence_ref:
     null`. Not a HALT — the draft still proceeds, with this stated
     prominently (see item 5, below).
2. **`causal_chain`** — concatenate every round's `causal_chain_additions`
   in round order, each entry tagged with its originating `round` number
   and its `tier`/`evidence_ref` copied verbatim. `[]` when no round ever
   produced one (including the round-0 accept edge case — `rca-analyze`'s
   "Handling `accept`" allows accepting before any round runs at all).
3. **`root_cause`**:
   - If `causal_chain` is non-empty: `established: true`, `statement`
     synthesizes one paragraph naming the terminal (last) entry as the
     root cause and how the chain before it leads there, `tier`/
     `evidence_ref` copied verbatim from that terminal entry — never
     upgraded past what it already was.
   - If `causal_chain` is empty: `established: false`, `statement` states
     plainly that this run's accepted analysis produced no causal-chain
     finding to conclude from, `tier: null`, `evidence_ref: null`. This is
     a legitimate, statable outcome (the v6 suite's closest analogue is
     `root_cause_class: OPEN`) — never fabricated to fill the field.
4. **`reproduction_scenario`** — built from `causal_chain`, `problem`, and
   `scope.json.window`/`classification`, at protocol level (message
   names, procedure steps, network/device conditions — not log-internal
   detail):
   - `preconditions[]`: the state the network/device must be in before the
     failure can occur (band, RAT, feature flags, prior procedure state) —
     each drawn from a specific `causal_chain`/`scope.json` entry with its
     tier and `evidence_ref` copied forward; a precondition with no such
     backing is tier `ASSUMED`, `evidence_ref: null`, and is named as such
     rather than silently blended in.
   - `steps[]`: the ordered sequence of actions/events (numbered) that
     leads to `problem`, again each tagged with the tier/`evidence_ref` of
     whatever `causal_chain`/`problem` entry it restates — a step this
     skill had to interpolate to make the sequence readable (e.g. an
     ordinary preceding procedure step nothing in the chain specifically
     evidenced) is tier `ASSUMED`.
   - `expected_failure`: what a tester attempting this scenario should
     observe if it reproduces — restates `problem`'s `statement`/`tier`/
     `evidence_ref`.
   - `tester_comparison`: `tester_reported_text` = verbatim
     `input/plm-snapshot.json.tester_reproduction_steps.text`. Compare it
     against `preconditions[]`/`steps[]`/`expected_failure`:
     - `matches[]`: scenario statements that agree with what the tester
       described.
     - `divergences[]`: everywhere the two disagree or the scenario adds
       something the tester didn't mention. Tag `tier: "CONTRADICTED"`
       specifically when a HARD (`VERIFIED_LOG`/`CODE_BOUND`) entry this
       scenario rests on positively disagrees with the tester's text (e.g.
       the tester says "happens every time" but the located failure point
       shows a specific, narrow precondition) — per `evidence-tiers.md`,
       this is the pipeline's most valuable kind of finding, named
       explicitly, never smoothed over to keep the tester's account
       looking right. A divergence that is merely additional detail (the
       scenario states a protocol-level precondition the tester's
       free-text account simply never mentioned, with nothing to
       contradict) is tagged with whatever tier that added detail itself
       carries, not `CONTRADICTED`.
5. **`evidence_gaps`** and the weak-evidence notice: collect, in one list,
   every `SPEC_INFERRED`/`ASSUMED`/`TESTER_REPORTED`/`CODE_UNAVAILABLE`/
   `CONTRADICTED` item `problem`/`root_cause`/`causal_chain`/
   `reproduction_scenario` rests on, stated plainly (mirroring
   `checkpoint-format.md`'s evidence-gaps section, applied here to the
   whole conclusion rather than one round). Set `rests_on_weak_evidence:
   true` and write `weak_evidence_notice` as one explicit sentence
   whenever anything in `root_cause`, any `causal_chain` entry, or any
   `reproduction_scenario` precondition/step/`expected_failure` carries
   tier `ASSUMED` or `CODE_UNAVAILABLE` — this is the mechanism behind
   issue #10's "states this prominently rather than presenting uniform
   confidence" requirement; it belongs at the top of both the draft's
   report (Step 6) and `CONCLUSION.md` (Step 7), never buried at the
   bottom. `rests_on_weak_evidence: false`, `weak_evidence_notice: null`
   when nothing qualifies.

### 5. Run the forbidden-pattern scan

Before writing anything: scan every **authored** string value assembled in
Step 4 (case-insensitive substring match) for: `"fix:"`, `"the fix is"`,
`"to fix this"`, `"suggested fix"`, `"proposed fix"`, `"patch:"`,
`"proposed patch"`, `"workaround"`, `"configuration change"`, `"config
change"`, `"config parameter should"`, `"test case"`, `"regression
test"`, `"verification procedure"`, `"recommend"`, `"recommendation:"`,
`"action item:"`, `"remediation:"`, `"next step:"`, `"should be
changed"`, `"should be modified"`, `"should be updated to"`.

**Exception**: matches inside verbatim-quoted external text —
`reproduction_scenario.tester_comparison.tester_reported_text` — are
allowed, since the tester may use these words innocently in their own
account (the same "matches inside `engineer_input` are allowed" carve-out
the older v6 suite uses, per
`.cline/skills/3gpp-rca-orchestrator/references/orchestrator-finalize-checklist.md`).
Every other field this skill itself authors — every `statement`,
`evidence_gaps` entry, `weak_evidence_notice`, `scenario_says` — is not
exempt.

If any forbidden pattern is found outside the exempted fields: **do not
write `conclusion.json` or `CONCLUSION.md`**. HALT: "Conclusion draft
blocked — contains a forbidden pattern (`<pattern>`, in `<field>`). This
pipeline terminates at a verified root cause; it does not propose fixes,
patches, configuration changes, test cases, or next steps. Rephrase and
retry." This is a mechanical gate, not a style suggestion — the same
discipline issue #5 states as "checked mechanically... not left to good
intentions," applied here instead of at a separate finalize phase since
this skill has no such phase of its own.

This scan governs the **written files** (`conclusion.json`,
`CONCLUSION.md`) only — this skill's own HALT/report text to the engineer
may still say things like "the next pipeline step is `rca-learn`," the
same pipeline-sequencing language every skill in this suite uses; that is
not a remediation suggestion.

### 6. Write `conclusion.json`

Create `runs/run-NN/conclusion.json` per the schema in
`run-bundle-layout.md`: `drafted_at: <now>`, `confirmed: false`,
`confirmed_at: null`, plus Step 4's fields. Written once — a standing
unconfirmed draft is never silently rewritten (Step 3, case 3); the only
later write to this file is "Handling `accept`" flipping `confirmed` to
`true` in place.

### 7. Write `CONCLUSION.md`

Render `conclusion.json`'s content as Markdown, in this order, at
`runs/run-NN/CONCLUSION.md`:

```
# RCA Conclusion — <issue_id> / <run_id>

Status: DRAFT — awaiting engineer confirmation

[If rests_on_weak_evidence: a prominent line, before any other content:
"⚠ This conclusion rests on unverified (ASSUMED) or code-unavailable
findings: <weak_evidence_notice>"]

## Problem
<problem.statement>  [<problem.tier>, <problem.evidence_ref>]

## Root Cause
<root_cause.statement>  [<root_cause.tier>, <root_cause.evidence_ref>]

## Causal Chain
1. (round <N>) <statement>  [<tier>, <evidence_ref>]
2. ...
(state "no causal-chain findings" if empty)

## Reproduction Scenario
### Preconditions
- <statement>  [<tier>, <evidence_ref>]
### Steps
1. <statement>  [<tier>, <evidence_ref>]
### Expected Failure
<expected_failure.statement>  [<tier>, <evidence_ref>]
### Compared to the Tester's Reported Steps
Tester reported: "<tester_reported_text>"
Matches: <matches[], or "none">
Divergences:
- <tester_claim> vs. <scenario_says>  [<tier>, <evidence_ref>]
(state "no divergences" if empty)

## Evidence Gaps
- <each evidence_gaps[] entry>
(state "none" if empty)

---
This conclusion ends here. It does not propose a fix, patch,
configuration change, test case, or next step. Downstream engineering
owns remediation. `tr-creator` remains a separate, explicitly invoked
skill for producing a Technical Report from an accepted conclusion.
```

On a confirmed conclusion (Step "Handling `accept`" below), the `Status`
line is rewritten to `Status: CONFIRMED at <confirmed_at>` and nothing
else in this rendering changes.

### 8. Update `manifest.json` and report

On a first draft (Steps 4–7 just ran): update `manifest.json` in place —
`current_step: "rca-conclude"`, `updated_at` to now. Leave
`next_step`/`status` untouched — still `"rca-conclude"` / `"in_progress"`,
pending confirmation. On a bare re-ask (Step 3, case 3), skip this
`manifest.json` update — nothing changed.

Report to the engineer: render `CONCLUSION.md`'s content in full (problem,
root cause, causal chain, reproduction scenario with tester comparison,
evidence gaps — the weak-evidence notice first and prominent, exactly as
Step 7 orders it, never softened). State plainly: reply `accept` to
confirm this conclusion (sets `issue.json.active_run` and hands off to
`rca-learn`), or `abort` to close this run without concluding. HALT.

**This step always halts, regardless of `manifest.json.autonomy`.** Unlike
`rca-analyze`, this skill has no auto-continuation path at any autonomy
setting — issue #10's "concluding is always gated on the engineer" is not
one gate among several, it is this skill's only mode. `autonomy: "auto"`
governs `rca-analyze`'s rounds; it has no effect here at all.

### Handling `accept`

Reached only from Step 3 case 1, on an existing unconfirmed draft.

1. Re-run Step 5's forbidden-pattern scan against the existing draft
   before doing anything else — belt-and-suspenders against a draft
   hand-edited on disk between being written and being accepted.
2. Set `conclusion.json.confirmed: true`, `confirmed_at: <now>`. This file
   is now immutable — Step 2's precondition check refuses any further
   invocation against this run.
3. Rewrite `CONCLUSION.md`'s `Status` line to `CONFIRMED at <confirmed_at>`
   (Step 7's rendering, otherwise unchanged).
4. Set `issue.json.active_run = <run_id>`. This is the only skill in the
   suite that ever writes this field.
5. Update `manifest.json`: `current_step: "rca-conclude"`, `next_step:
   "rca-learn"`, `updated_at` to now. Leave `status: "in_progress"` — the
   run is confirmed, not archived; `rca-learn` (issue #11) is what writes
   the case record from here.
6. Report: the conclusion is confirmed, `active_run` is set to `<run_id>`,
   and the next pipeline step is `rca-learn` — do not imply it will run
   automatically; invoking it (directly, or via `/rca`'s dispatch) is a
   separate step this skill does not take itself. State plainly that no
   Technical Report was produced and that `tr-creator` remains a separate,
   explicitly invoked skill. HALT.

### Handling `abort`

Reached only from Step 3 case 2, on an existing unconfirmed draft.

1. Leave `conclusion.json` exactly as it stands (`confirmed: false`,
   untouched) — the draft remains on disk as a record of what was
   proposed but not accepted; it is not deleted.
2. Update `manifest.json`: `status: "aborted"`, `next_step: null`,
   `current_step: "rca-conclude"`, `updated_at` to now. This is permanent
   — Step 1.5 refuses to resume an aborted run.
3. Do **not** set `issue.json.active_run`.
4. Report: this run is closed without a confirmed conclusion. State that a
   new run via `rca-intake` is required to analyze this issue further.
   HALT.

## What this skill does not do

- ❌ Never runs a new log-query, code-graph, or NotebookLM call — every
  tier and evidence reference in `conclusion.json` is copied forward from
  `scope.json`/`analysis/round-NN.json`, never freshly derived.
- ❌ Never writes to `analysis/round-NN.json` or `manifest.json.decisions`
  — those stay `rca-analyze`'s alone.
- ❌ Never sets `issue.json.active_run` without an explicit `accept` reply
  to the draft this skill itself presented — not on synthesis, not under
  any `autonomy` setting.
- ❌ Never rewrites a `conclusion.json` once `confirmed: true` — a further
  analysis of the same issue is a new run via `rca-intake`, never a
  reopened conclusion.
- ❌ Never writes a fix, patch, configuration change, test case, or
  next-step suggestion into `conclusion.json` or `CONCLUSION.md` — Step 5's
  scan blocks the write mechanically if one appears.
- ❌ Never produces a Technical Report — that is `tr-creator`, a separate,
  explicitly invoked skill this skill never calls.
- ❌ Never presents an `ASSUMED`/`CODE_UNAVAILABLE`-resting conclusion with
  the same confidence as one resting on `VERIFIED_LOG`/`CODE_BOUND` —
  `rests_on_weak_evidence`/`weak_evidence_notice` exist specifically to
  surface this, first, in both the draft report and `CONCLUSION.md`.
- ❌ Never presents the tester's reported reproduction steps as ground
  truth — the scenario is checked against them, and a genuine,
  HARD-evidenced disagreement is recorded at `CONTRADICTED`, not smoothed
  into agreement.
- ❌ No chaining into `rca-learn` — halts after a confirmed `accept` and
  states that it is the next pipeline step, but never invokes it itself;
  running it (directly, or via `/rca`'s dispatch) is a separate step.
