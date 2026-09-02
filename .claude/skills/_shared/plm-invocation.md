# PLM Invocation Contract

This documents what `rca-intake` (issue #6) needs to call the PLM MCP
connection. Like the log-query capability (`log-query-invocation.md`), the
code-graph capability, and NotebookLM, it is a **workspace dependency, not
part of this repository**: it is expected to already be configured in the
environment a skill runs in, and no skill in this suite attempts to
configure or discover it (see root `CLAUDE.md`).

## What it is

Three semantic operations over a PLM issue, keyed by `issue_id`:
`fetch_title | fetch_description | fetch_comments`. The exact underlying
MCP tool names are **deliberately not fixed by this contract** — which
registered tool actually answers `fetch_comments` in a given workspace is
resolved by the calling skill at the moment it runs, the same way
`log-query-invocation.md` never names the DuckDB capability's real function
signature. This is what lets `rca-intake` be written before the concrete
PLM MCP tool names are known: the contract states *intent*, never a
binding.

## Invoking it

```
Call the PLM MCP capability's <operation> for:
  operation: fetch_title | fetch_description | fetch_comments
  issue_id:  <e.g. "PLM-12345">
```

- `fetch_title` / `fetch_description` are **required** — without them a run
  bundle has nothing worth opening at all.
- `fetch_comments` is **optional** — supplementary hint material only; its
  absence degrades the run, it does not invalidate it.

## What each operation returns

- `fetch_title` → `{"title": "<verbatim>"}`
- `fetch_description` → `{"description": "<verbatim>"}` — this text carries
  the tester's account of the issue **and** whatever reproduction
  steps/expected result the tester wrote, undivided. There is no separate
  "reproduction steps" field in the underlying PLM system — see "What this
  capability does not provide" below.
- `fetch_comments` → `{"comments": [{"comment_id": "<id>", "author":
  "<name/id, verbatim>", "timestamp": "<ISO 8601>", "text": "<verbatim>"}, ...]}`
  — every comment on the issue, unbounded (this contract sets no
  pagination or `max_results`; issue volume in this domain does not
  warrant one). Comments in this system come from SWPL analysts, other
  teams, or the analysing engineer, not only the tester — the API returns
  no role/team field, so none is recorded; `author` is stored exactly as
  returned, with no inferred role.

## What the calling skill must do with the result

1. Write `title`/`description` verbatim into `input/plm-snapshot.json` —
   never rephrased, summarized, or corrected (see `rca-intake/SKILL.md`'s
   "no rephrasing" rule).
2. Write `comments` verbatim, one entry per comment, preserving
   `comment_id`/`author`/`timestamp` exactly as returned.
3. Append one line **per operation actually called** to `evidence/tools.jsonl`
   (`tool: "plm-mcp"`, `operation` one of the three above), per
   `tool-ledger-format.md` — including on failure, before halting
   (`fetch_title`/`fetch_description`) or before continuing degraded
   (`fetch_comments`).

## What this capability does not provide

- **No discrete "tester reproduction steps" field.** The tester's
  route/repro/expected-result text, when present, is embedded inside
  whatever `fetch_description` returns. `rca-intake` does not parse or
  extract it — PLM descriptions are not guaranteed to follow any fixed
  template, and slicing one out would require judgment this skill is not
  permitted to exercise (rephrasing is analysis; this skill does none).
- **No "info" operation** (model, SW version, incident location, etc.) is
  used by this suite at all — that data does not bear on locating a root
  cause and is out of scope for this contract. An engineer who wants
  build/model recorded supplies it directly via `rca-intake`'s existing
  `build`/`model` invocation inputs into `input/log-pointers.json` (see
  `run-bundle-layout.md`) — never sourced from PLM automatically.
- **No `role`/`team` field on a comment** — the underlying API does not
  provide one.

## When it is unavailable

- **`fetch_title` or `fetch_description` fails or is not configured**:
  append an `error` ledger line and HALT — never fabricate a title or
  description to keep going.
- **`fetch_comments` fails while the other two succeed**: append an
  `error` ledger line for that operation only, continue with
  `comments: []`, and state the gap plainly in `rca-intake`'s final report
  to the engineer — this is a routine, expected degradation, not a HALT
  condition.
- **`issue_id` is unknown to PLM** (any operation returns not-found): HALT
  — "PLM has no issue `<issue_id>`." Never invent a title, description, or
  comment list to fill the gap.
