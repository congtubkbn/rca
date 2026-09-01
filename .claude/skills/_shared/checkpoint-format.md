# Checkpoint Presentation Format

`rca-analyze` (issues #8 and #9) ends every round here. This is the one
piece of the round the engineer actually reads; everything else in
`analysis/round-N.json` exists to make this checkpoint's claims traceable,
not to be read directly.

Issue #8 built one round ending at this checkpoint, always halting
regardless of `manifest.json.autonomy`. Issue #9 adds the loop around it:
a reply of `dig <direction>`, `redirect <information>`, `accept`, or
`abort` (section 5, below) drives what `rca-analyze` does next, and at
`autonomy: "auto"`/`"auto_until_blocked"` the skill may take that next
step itself instead of waiting for the engineer to type it — see
`rca-analyze/SKILL.md`'s loop-control steps for exactly when it does and
does not stop to wait. Four gates always stop it regardless of autonomy:
the round budget, a recommendation resting on an `ASSUMED` finding, the
resolution ladder reaching "ask the engineer" for something the
recommended direction depends on, and — always — final acceptance of a
root cause (`rca-analyze` never invokes `rca-conclude` itself; it reports
that `accept` is next and stops).

## Sections, in order

### 1. Causal chain so far

Every link established across this run's rounds so far (this round's own
findings plus anything carried from earlier rounds' `causal_chain`
entries), each stated with its evidence tier:

```
<link statement>  [<tier>, <ledger ref or raw/ pointer>]
```

An empty chain (round 1 found nothing conclusive yet) is stated as such,
not omitted.

### 2. Ranked candidate directions

Every surviving hypothesis this round produced, ranked by how directly it
would extend the causal chain if confirmed. Each entry states:

- The hypothesis itself.
- The evidence it would take to confirm or eliminate it (its predicted
  evidence — see `analysis/round-N.json`'s schema in
  `run-bundle-layout.md`).
- The specific query that would test it — table/tool and keywords, or the
  code-graph target — precise enough that the engineer can judge the
  reasoning before it runs, not just after.

### 3. Recommendation

One of the surviving directions, named, with a one-line reason it is
ranked first. If nothing survived (every hypothesis this round was
eliminated or the failure point itself could not be located), the
recommendation says so plainly and names what information would unblock
the round rather than picking a direction to appear decisive.

### 4. Evidence gaps

Every place this round's findings rest on something other than a HARD
source, stated explicitly rather than folded into the confident-sounding
prose above:

- Findings still at `SPEC_INFERRED`, `ASSUMED`, or `TESTER_REPORTED`.
- Branches marked `CODE_UNAVAILABLE` (module ships as a lib).
- Any `CONTRADICTED` finding (a source's claim the log disproved) —
  named explicitly, since this is the pipeline's most valuable kind of
  finding, not a failure to hide.
- Ladder rungs this round could not resolve (missing citation, no source,
  the "prior cases" rung not yet available because `rca-learn` does not
  exist) and what would need to be true to try them.

### 5. How to respond

Appended after section 4 whenever `rca-analyze` is actually halting here
(i.e. not the mid-loop status line an `autonomy: "auto"`/
`"auto_until_blocked"` round prints on its way to the next round
automatically — see below). States plainly:

- **`dig <direction>`** — start the next round narrowed onto one of
  section 2's candidate directions (by hypothesis id or its statement).
  Reads only `checkpoint.candidate_directions`, never conversation
  history, so the same direction typed in a fresh session produces the
  same next round as typed in a continuing one.
- **`redirect <information>`** — hand the agent something it could not
  have known: a fact about the device, network, or build. Recorded at
  tier `ENGINEER_PROVIDED` (`analysis/round-N.json.engineer_redirect`,
  never as ordinary chat) and folded into the next round's hypothesis
  generation.
- **`accept`** — this run's analysis is done; the next step is
  `rca-conclude`. Always halts, at every autonomy setting — `rca-analyze`
  records the decision and stops, it never invokes `rca-conclude` itself.
- **`abort`** — close this run without a conclusion. State why, even
  briefly; recorded verbatim.

At the round budget, this section says so explicitly and states that only
`accept`, `abort`, or an *explicit* override (stated as such, with a
one-line rationale) can move past it — the round budget is the only one
of the four gates an override can move past at all, and only for one more
round at a time. When this round's recommendation instead rests on an
`ASSUMED` finding, or the resolution ladder had to reach "ask the
engineer" for something the recommendation depends on, this section states
that plainly too, but there is no override for either — only `accept` or
`abort` move past them; digging further requires whatever would actually
resolve the gap (a query hit, an engineer's answer via `redirect`), not a
reply that just asserts past it. See `rca-analyze/SKILL.md`'s gate steps
(Step 7.4) for the exact wording each produces.

When `autonomy` is `"auto"` or `"auto_until_blocked"` and none of the four
gates above apply, `rca-analyze` does not print this section at all for
that round — it takes its own recommendation as if the engineer had typed
`dig <recommendation>`, records that in `manifest.json.decisions[]` as
`verb: "auto_continue"` (not a real engineer reply), and continues
straight into the next round within the same invocation. The final round
of such a run — whichever one trips a gate or reaches the round budget —
is the one that actually renders this section and halts.

## What this format does not do

It does not ask a question and wait inline mid-round — the round has
already ended by the time this is presented (`analysis/round-N.json` is
written first, in full, before the checkpoint built from it is shown).
Nothing in the checkpoint itself is mutable; an engineer's reply changes
what round `rca-analyze` writes *next*, never this one.

It never presents `SPEC_INFERRED` or `ASSUMED` findings with the same
confidence as `VERIFIED_LOG`/`CODE_BOUND` ones — tier labels are not
decoration, they are what section 4 exists to surface even when sections 1
and 3 read fluently.
