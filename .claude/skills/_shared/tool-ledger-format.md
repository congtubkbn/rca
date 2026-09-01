# Tool-Call Ledger Format — `evidence/tools.jsonl`

Every call any skill in this suite makes to an external retrieval system —
the PLM MCP connection, the DuckDB log-query skill, the tree-sitter code
graph, NotebookLM — appends exactly one line to
`.rca/issues/<issue_id>/runs/run-NN/evidence/tools.jsonl`. The ledger is
append-only and per-run: it is how any keyword or claim in that run's
conclusion can be traced back to the call that produced it (issue #5,
"nothing is auditable" is the problem this solves). Raw tool output never
enters it, and never enters the agent's context either — it is written to
`raw/` and only a summary plus a pointer is kept.

## Line format

One JSON object per line, no wrapping array:

```json
{"ts": "<ISO 8601>", "run": "run-01", "skill": "rca-intake", "tool": "plm-mcp", "operation": "fetch_issue", "params": {"issue_id": "PLM-12345"}, "keywords_in": [], "table": null, "result_ref": "input/plm-snapshot.json", "status": "ok", "error": null}
```

| Field | Meaning |
|---|---|
| `ts` | UTC ISO 8601 timestamp of the call. |
| `run` | The run this call belongs to (`run-01`, `run-02`, …). |
| `skill` | The skill that made the call (e.g. `rca-intake`). |
| `tool` | Which external system was called: `plm-mcp`, `log-query`, `code-search`, `notebooklm`. |
| `operation` | The specific operation requested of that tool. |
| `params` | The exact parameters passed — enough to reproduce the call. |
| `keywords_in` | Keywords this call *consumed* that must themselves already have provenance (empty for a call, like intake's, that introduces keywords rather than consuming them). |
| `table` | The DuckDB table queried, when `tool` is `log-query`; `null` otherwise. Recorded for audit — this suite does not enforce table isolation the way v6 did (issue #5, "Explicit departures from v6"). |
| `result_ref` | Where the full result was written (a path under `input/`, `raw/`, or a state-file section) — never the raw payload itself. |
| `status` | `"ok"` or `"error"`. |
| `error` | The stated reason when `status` is `"error"`; `null` otherwise. A failed call is still logged — a missing PLM connection or an unknown issue ID is itself an auditable event, not a reason to skip the ledger. |

## What `rca-intake` writes here

Exactly one line per run, for its single PLM MCP call: the issue fetch
that produced title, description, and tester reproduction steps. On
failure (PLM unavailable, unknown issue ID) it still writes the line, with
`status: "error"` and the stated reason in `error`, before halting.
