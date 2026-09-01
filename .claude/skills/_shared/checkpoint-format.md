# Checkpoint Presentation Format

`rca-analyze` (issue #8) ends every round here, then halts. This is the
one piece of the round the engineer actually reads; everything else in
`analysis/round-N.json` exists to make this checkpoint's claims traceable,
not to be read directly.

Issue #8 builds one round ending at this checkpoint. Issue #9 (not yet
built) adds the loop around it — `dig <direction>` / `redirect
<information>` / `accept` / `abort`, the round budget, and
`meta.autonomy` — none of that exists yet; a round built by this ticket
halts here unconditionally, regardless of what `manifest.json.autonomy`
says.

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

## What this format does not do

It does not ask a question and wait inline — the round has already ended
by the time this is presented (`analysis/round-N.json` is written first).
An engineer's answer becomes the next round's input once issue #9 exists;
until then, an open question here is a statement, not a live prompt.

It never presents `SPEC_INFERRED` or `ASSUMED` findings with the same
confidence as `VERIFIED_LOG`/`CODE_BOUND` ones — tier labels are not
decoration, they are what section 4 exists to surface even when sections 1
and 3 read fluently.
