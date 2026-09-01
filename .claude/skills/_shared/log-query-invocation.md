# Log-Query Invocation Contract

This documents what `rca-scope` (GitHub issue #7) and `rca-analyze`
(GitHub issue #8) need to call the log-query capability. The contract
itself (invocation shape, return shape, numbering/ledger discipline) is
identical for both callers — only *why* a query is issued differs, and
that lives in each skill's own `SKILL.md`, not here.

## What it is

The log-query capability is a DuckDB-backed retrieval tool over the two log
tables an issue's data was loaded into (their names live in
`input/log-pointers.json.tables`, per `run-bundle-layout.md`). Like the PLM
MCP connection `rca-intake` calls, it is a **workspace dependency, not part
of this repository** (issue #5, "capabilities already exist as separate
skills"; see also root `CLAUDE.md`'s treatment of the older v6 suite's
`3gpp-tools/*.py` for the same relationship). It is expected to already be
configured in the environment a skill runs in; no skill in this suite
attempts to configure or discover it. This suite's table-isolation posture
(none enforced; every call records which table it touched instead) is
`tool-ledger-format.md`'s `table` field — see that file rather than
duplicating it here.

## Invoking it

```
Call the log-query capability with:
  duckdb_path: <input/log-pointers.json.duckdb_path>
  table: <one entry from input/log-pointers.json.tables — one call per table>
  keywords: [<string>, ...]
  time_window: {start: <ISO 8601 or null>, end: <ISO 8601 or null>}
  max_results: <a bound the calling skill sets, e.g. 50>
```

- `duckdb_path` and the candidate `table` values come only from
  `input/log-pointers.json`, written by `rca-intake` — never guessed or
  defaulted to a workspace convention a skill hasn't actually checked. If
  `duckdb_path` is `null` or `tables` is empty, the capability cannot be
  called at all; this is a `rca-scope` contract precondition (see its
  `SKILL.md`), not something this file works around.
- `keywords` must each have a stated origin the calling skill can name (e.g.
  "from the `<issue_type>` playbook's failure-indicator list", "from the
  generic fallback list", "from an engineer-supplied classification hint").
  `rca-scope` is where this suite's query discipline starts (issue #7): a
  query is always allowed to run, but the skill must be able to say where
  each keyword came from when it records the call.
- `time_window` bounds the search. A skill with no candidate window yet
  (e.g. `rca-scope` determining the failure time from scratch) passes the
  full loaded range from `input/log-pointers.json.time_range` when known,
  or an unbounded window when that, too, is `null`.

## What it returns

A compressed summary — never the full row set:

```json
{
  "table": "UE_3gpp_signaling_log",
  "keywords_used": ["RRCConnectionRelease", "..."],
  "keywords_with_hits": ["RRCConnectionRelease"],
  "keywords_missed": ["..."],
  "matched_event_count": 3,
  "events": [
    {"timestamp": "<ISO 8601>", "layer": "RRC", "message": "RRCConnectionRelease", "snippet": "<short text>"}
  ]
}
```

A keyword with no hits teaches the calling skill nothing about the log —
per `evidence-tiers.md`'s "guessing may ask, never answer" rule, a miss may
not be used to claim the log *lacks* something, only that this particular
query did not find it.

## What the calling skill must do with the result

Unlike the older v6 suite's Python scripts, this capability does not write
into the run bundle itself — the calling skill does, immediately, so the
full result never lingers in context beyond the single turn it arrived in:

1. Write the full returned payload to
   `runs/run-NN/raw/<skill-name>-q-<NN>.json` (zero-padded, numbered by
   listing existing files matching that prefix and continuing past the
   highest index already present — never overwritten by a re-run, so a
   later invocation's queries stay distinguishable from an earlier one's).
2. Append one line to `runs/run-NN/evidence/tools.jsonl` per
   `tool-ledger-format.md`, with `tool: "log-query"`, `table` set to the
   table just queried, `keywords_in` set to the keyword list with its
   stated origin, and `result_ref` pointing at the file from step 1.
3. Carry forward into the run's own state file (e.g. `scope.json`) only the
   summary fields it actually needs — `matched_event_count`,
   `keywords_with_hits`, and the specific `events[]` entries that support a
   written claim, not the raw payload.

## `rca-analyze`'s use of this contract

`rca-analyze` issues two kinds of query beyond `rca-scope`'s single
time-anchor query:

- **Locate-the-failure-point queries** — narrower and more targeted than
  `rca-scope`'s time-anchor query, often around `scope.json.failure_time`
  when that is `VERIFIED_LOG`, or guided by a rung-1 NotebookLM answer's
  suggested keywords when it is not (`resolution-ladder.md`).
- **Hypothesis-testing queries** — one call per hypothesis's predicted
  evidence, `keywords` drawn from wherever the hypothesis's prediction
  came from (HARD, SOFT-with-citation, or a guess — see
  `keyword-provenance.md`) and `table` narrowed to whichever of
  `scope.json.tables_in_scope` the hypothesis actually concerns, not all
  of them by default.

Both kinds follow this file's contract exactly — same invocation shape,
same `raw/`/ledger writes, same "a keyword's stated origin" requirement.
`rca-analyze`'s `raw/` files share one numbering sequence across every
tool it calls in a round (log-query, code-graph, NotebookLM alike) — see
`code-graph-invocation.md` and `notebooklm-invocation.md`.

## When it is unavailable

If the capability is not configured or fails to connect: append an `error`
ledger line (same shape as a successful call, `status: "error"` and the
stated reason in `error`) and HALT — state which query could not run and
why, per `runs/run-NN/evidence/tools.jsonl`'s `status`/`error` fields. Never
fabricate query results to keep a skill moving.
