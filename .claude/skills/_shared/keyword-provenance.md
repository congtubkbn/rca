# Keyword Provenance — Source Ranking

This governs what a keyword or claim used by `rca-analyze` (issue #8, the
first skill in this suite that can assert anything toward a conclusion)
may be used *for*, based on where it came from. It is related to but
distinct from `evidence-tiers.md`: tiers describe how a **claim** is known;
this file ranks **sources** and states what each rank may support.

## Ranks

| Rank | Sources | May support |
|---|---|---|
| **HARD** | The log-query capability (DuckDB), the code-graph capability (tree-sitter) | A conclusion. What these return demonstrably exists in this issue's own data. |
| **SOFT** | NotebookLM, only when its answer carries a citation naming a specific document and section | A hypothesis, or the keywords for a query. Never a conclusion on its own — see "Promotion and verification" below. |
| **FORBIDDEN** | The model's pretrained knowledge — 3GPP terminology, message names, IE names, cause codes, or vendor-chip behavior recalled rather than looked up | Nothing that reaches a conclusion. See "Guessing may ask, never answer" — this is the one exception to "never", and it is narrow. |

A NotebookLM answer with no citation is treated as FORBIDDEN, not SOFT —
the citation is what makes it SOFT at all. Never relax this because an
answer sounds confident or specific.

## Guessing may ask, never answer

This is `evidence-tiers.md`'s rule, restated here because it is what makes
FORBIDDEN sources usable at all without becoming a laundering path:

A keyword may originate anywhere — HARD, SOFT, or the model's own
pretrained knowledge — and still be used to **construct a query**. What
happens next depends only on the query's result, never on where the
keyword came from:

- **Hit**: the keyword now demonstrably exists in this issue's log or
  code. It is promoted to HARD provenance from this point forward in this
  run, and the fact it revealed may be recorded at `VERIFIED_LOG` or
  `CODE_BOUND`. Its origin (including "guessed from general 3GPP
  knowledge, not from this issue's own prior evidence") is still recorded
  in the ledger's `keywords_in` — promotion changes what the finding may
  support, not the historical record of how the keyword was chosen.
- **Miss**: nothing was learned. The keyword is dropped from the analysis.
  No claim — positive or negative — may be drawn from the miss. The guess
  may simply have been wrong; a miss never means "this does not happen in
  this log", only "this specific string, at this specific query, was not
  found."

This is the mechanism that lets `rca-analyze` do what an experienced
engineer does when a module ships as a lib and there is nothing to trace
into: guess a plausible log literal from general knowledge, search for it,
and let the log — not the guess — decide whether the guess was right.

## Promotion and verification

A SOFT claim (a NotebookLM answer with citation) never supports a
conclusion by itself. It is promoted only by an independent HARD check:

- If the claim is about a **keyword's existence** (a message name, an IE,
  a log literal) — query for it. A hit promotes that specific fact to
  `VERIFIED_LOG`/`CODE_BOUND` per "guessing may ask, never answer" above.
  A miss leaves the claim at `SPEC_INFERRED`, unchanged.
- If the claim is about **protocol behavior or a requirement** (e.g. "the
  spec mandates X happens before Y", "this chip series logs Z on
  failure") — it stays `SPEC_INFERRED` unless a HARD source (a log
  sequence, a code path) actually confirms the behavior, not merely a
  keyword's presence.
- If a HARD query result **contradicts** a SOFT claim — the log shows the
  opposite of what the document said — record the claim at
  `CONTRADICTED`, per `evidence-tiers.md`. This is deliberately not
  treated as an error to route around; it is the pipeline's most valuable
  finding (issue #5, "where vendor documentation is wrong is the asset")
  and belongs in the round's `open_notes`, for `rca-learn` (issue #11,
  not yet built) to pick up once it exists.

## What this does not change

Table isolation is still not enforced (issue #5, "Explicit departures from
v6"; `tool-ledger-format.md`'s `table` field records what was queried, for
audit, not restriction). This file governs what a finding may be used
*for*, not which table or tool it is permitted to touch.

An engineer's `redirect <information>` reply (issue #9,
`checkpoint-format.md`) is a fourth, separate axis from the HARD/SOFT/
FORBIDDEN ranking above — it is not a *source* an agent chose, it is a
premise the engineer asserted directly, tagged `ENGINEER_PROVIDED` per
`evidence-tiers.md` regardless of how it gets used afterward. It may seed
a hypothesis or supply a query keyword exactly like a SOFT source can, and
per `evidence-tiers.md`'s `ENGINEER_PROVIDED` rule it may stand as a
premise on its own — but a conclusion resting on it must still say plainly
that it rests on an engineer premise, the same discipline as any other
non-HARD tier reaching the checkpoint's evidence gaps.
