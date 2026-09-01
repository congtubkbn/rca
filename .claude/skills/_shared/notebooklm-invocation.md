# NotebookLM Invocation Contract

This documents what `rca-analyze` (issue #8) needs when consulting
NotebookLM for the resolution ladder's rungs 1 (3GPP spec) and 4 (vendor
documentation). It governs how this suite calls the general-purpose
`notebooklm` skill already present in this repository
(`.claude/skills/notebooklm/SKILL.md`) — that skill is a third-party,
general programmatic API for NotebookLM (create notebooks, add sources,
query, generate artifacts) and is not specific to this pipeline's
citation/tier discipline. This file is the discipline layer `rca-analyze`
applies on top of it; it does not replace or duplicate that skill's own
mechanics.

## What it is used for here

Two corpora, consulted at two different rungs (`resolution-ladder.md`):

- **3GPP spec notebook** (rung 1) — the normative procedure description:
  what messages/IEs/timers are involved in a procedure when it works.
- **Vendor documentation notebook** (rung 4) — Qualcomm/MTK chip-series
  detail beyond what the 3GPP spec states.

Which notebook to query for a given issue is a workspace configuration
concern (which notebook IDs exist, which chip series/vendor this issue's
`build`/`model` maps to) — out of scope for this ticket; when that mapping
is not resolvable, this rung is skipped and stated per
`resolution-ladder.md`, the same as a missing `source_checkout`.

## Invoking it

Query in the form of a specific, answerable question — never an
open-ended "what's wrong with this log":

```
"For <procedure/issue_type>, what messages/IEs/log literals indicate
<the specific condition being asked about>, per <spec/vendor doc>?"
```

## What counts as a usable answer

**A citation naming a specific document and section is required.** An
answer with no citation — however specific or confident it sounds — is
FORBIDDEN provenance per `keyword-provenance.md`, not SOFT, and must not
be used at all: not to generate a hypothesis, not to generate a query
keyword, nothing. This is the one hard gate this file adds on top of the
underlying `notebooklm` skill's own behavior, which does not itself
enforce a citation requirement.

A usable answer:

```json
{
  "question": "<as asked>",
  "answer": "<the substantive answer>",
  "citation": {"document": "<e.g. 3GPP TS 24.229>", "section": "<e.g. §5.1.6.8.4>"}
}
```

## What the calling skill must do with the result

1. Write the full returned answer to `runs/run-NN/raw/rca-analyze-q-<NN>.json`
   (same shared numbering as every other tool call this round makes, per
   `log-query-invocation.md`'s numbering rule).
2. Append one line to `evidence/tools.jsonl` per `tool-ledger-format.md`,
   with `tool: "notebooklm"`, `table: null`, `keywords_in: []` (this call
   introduces a claim rather than consuming a prior keyword),
   `result_ref` pointing at the file from step 1.
3. If the answer carries a citation: record the claim at `SPEC_INFERRED`
   with the citation attached — never higher, regardless of how the
   answer will be used next. See `keyword-provenance.md`'s "Promotion and
   verification" for what happens after (a keyword from this answer gets
   queried against the log/code; the underlying protocol claim itself
   stays `SPEC_INFERRED` unless independently confirmed).
4. If the answer carries no citation: discard it. Do not record it as
   `ASSUMED` or anything else — it was never usable, so there is nothing
   to carry forward except, optionally, an `open_notes` entry that the
   question was asked and returned nothing citable.

## When it is unavailable

If the underlying `notebooklm` skill fails to connect, has no notebook
configured for this issue's corpus, or the workspace mapping from
`build`/`model` to a notebook ID is not resolvable: append an `error`
ledger line and treat this rung as unavailable for the rest of the round,
per `resolution-ladder.md` — state it once, do not retry per hypothesis,
and never fabricate a citation to keep a round moving.
