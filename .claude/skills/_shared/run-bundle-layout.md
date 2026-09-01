# Run Bundle Layout & State Schema

This is the contract every skill in the PLM-issue pipeline (`rca-intake →
rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`, GitHub issue #5)
reads and writes against. There is no orchestrator and no in-memory state:
the run bundle on disk under `.rca/` is the single source of truth, and a
skill that discovers something but fails to write it here has genuinely
lost it. Read this file before changing what any skill writes, and update
it in the same change if a skill's write shape changes.

`.rca/` is git-ignored from the first commit (see `.gitignore`) — field
logs, subscriber identifiers, and NDA material must never reach a remote.

This `.rca/` directory is a sibling of, and does not collide with, the
older v6 suite's own use of `.rca/current_state_path.txt` (see
`.cline/skills/_shared/state-file-schema.md`) — the two suites are
independent and this document does not describe that file.

## Directory layout

```
.rca/
  issues/<issue_id>/
    issue.json              # PLM metadata, active_run pointer — owned by rca-intake
    input/                  # pointers and snapshots, never copied log data
      plm-snapshot.json     # verbatim PLM text as read at the most recent intake
      log-pointers.json     # DuckDB path, tables, time range, build/model, source checkout + commit id
    runs/
      run-01/
        manifest.json       # status, current/next step, autonomy, round budget — created by rca-intake
        scope.json          # issue classification, failure time, window/tables/layers — owned by rca-scope
        evidence/
          tools.jsonl       # append-only tool-call ledger (see tool-ledger-format.md)
        raw/                # raw tool output; never enters any skill's context
        CONCLUSION.md       # written by rca-conclude for THIS run only, once it reaches a conclusion
      run-02/
        ...
  knowledge/
    cases/                  # written by rca-learn when a run is accepted
    playbooks/              # promoted, reviewed; the only part of .rca/ meant to be shared
```

`rca-intake` creates `issue.json`, `input/`, and a run's `manifest.json`
and `evidence/tools.jsonl`. `rca-scope` (issue #7) adds `scope.json` to an
existing run and appends further ledger lines and `raw/` files for its own
log queries. Everything else in the tree above (`analysis/round-N.json`,
`conclusion.json`, `CONCLUSION.md`, `knowledge/`) is written by skills that
do not exist yet and is shown here only so this file does not need to be
restructured when they arrive.

## `issue.json`

```json
{
  "issue_id": "PLM-12345",
  "created_at": "<ISO 8601, first intake>",
  "plm": {
    "title": "<verbatim, latest fetch>",
    "url": "<PLM issue URL, if the MCP connection provides one>"
  },
  "active_run": null,
  "runs": ["run-01"]
}
```

- `active_run` names the run that may feed a Technical Report or be
  written into the case base (issue #5). It is set only when an engineer
  accepts a conclusion — a step owned by `rca-conclude`/`rca-learn`, not
  `rca-intake`. It stays `null` through everything this ticket builds.
- `runs` is an append-only list of run IDs that exist for this issue, in
  creation order. `rca-intake` appends to it; nothing removes from it.
- `title`/`url` are refreshed on every intake re-run — they are
  convenience metadata, not evidence. The per-run evidentiary snapshot
  that a conclusion may actually rest on lives in `input/plm-snapshot.json`
  and is pinned per run via `manifest.json.input_snapshot_fetched_at`
  (below) — a later PLM edit changes `issue.json.plm.title` but cannot
  silently change what an already-created run was based on.

## `input/plm-snapshot.json`

Refreshed (fully overwritten) on every `rca-intake` invocation for this
issue — it always reflects the latest fetch. Written verbatim; nothing in
it is rephrased or summarized by the skill.

```json
{
  "fetched_at": "<ISO 8601>",
  "title": "<verbatim>",
  "description": "<verbatim>",
  "tester_reproduction_steps": {
    "text": "<verbatim>",
    "tier": "TESTER_REPORTED"
  }
}
```

`description` is the snapshotted PLM text itself, kept so a later edit in
PLM cannot silently change what a conclusion rested on — it is not itself
tagged with an evidence tier because it is not (yet) a claim used in
analysis. `tester_reproduction_steps` is: it is the tester's claim about
what reproduces the failure, recorded as a claim (`TESTER_REPORTED`), not
as fact.

## `input/log-pointers.json`

Pointers only — never copied log rows, since the log already lives in
DuckDB.

```json
{
  "duckdb_path": "<path, or null if not yet known>",
  "tables": ["<table name>", "..."],
  "time_range": {"start": "<ISO 8601 or null>", "end": "<ISO 8601 or null>"},
  "build": "<build id, or null>",
  "model": "<device model, or null>",
  "source_checkout": {"path": "<path or null>", "commit_id": "<commit id or null>"}
}
```

`time_range` here is the extent of the loaded log (what data exists at
all), supplied by the engineer or a workspace config at intake time — it
is a different concept from the *narrowed failure window* that
`rca-scope` derives later into its own `scope.json`, and the two must not
be conflated. Any field the engineer does not supply at intake time is
written as `null`, not guessed — `rca-scope` or the engineer fills it in
later.

## `runs/run-NN/manifest.json`

Created by `rca-intake` with these fields; later skills update the
bookkeeping fields marked below as they run (see "Per-Section Write
Owners").

```json
{
  "run_id": "run-01",
  "issue_id": "PLM-12345",
  "label": "<free text, engineer-supplied or a generated default>",
  "status": "in_progress",
  "current_step": "rca-intake",
  "next_step": "rca-scope",
  "created_at": "<ISO 8601>",
  "updated_at": "<ISO 8601>",
  "input_snapshot_fetched_at": "<copied from input/plm-snapshot.json.fetched_at at run creation>",
  "autonomy": "review_all",
  "round_budget": 5,
  "current_round": 0,
  "standing_recommendation": null
}
```

- `label` records the engineer's intent for this run (issue #5, story 6) —
  e.g. "first pass" or "re-run with corrected build". `rca-intake` asks
  for it or defaults to something inert like `"run <N>"`; it is never
  inferred from PLM content.
- `autonomy` and `round_budget` are global run settings established at
  creation time with the defaults above; `rca-analyze`'s checkpoint logic
  (not built yet) is what actually acts on them.
- `input_snapshot_fetched_at` pins *this run* to the PLM snapshot it was
  created from, even though `input/plm-snapshot.json` itself is refreshed
  by later intake re-runs on the same issue.

## `scope.json`

Written by `rca-scope` (issue #7). Fully overwritten on every invocation —
re-running `rca-scope` on an existing run **replaces** the scope, it never
appends to or merges with a prior scope, and it never re-reads
`input/plm-snapshot.json`'s source (PLM) — only the already-fetched file on
disk.

```json
{
  "completed_at": "<ISO 8601>",
  "classification": {
    "issue_type": "<e.g. volte_call_drop | sms_failure | no_service | emergency_call | generic>",
    "matched_playbook": "<playbook id from rca-scope's references/known-issue-types.md, or null>",
    "evidence": [
      {"source": "plm-snapshot.title|plm-snapshot.description|classification_hint", "detail": "<what indicated this>"}
    ],
    "tier": "TESTER_REPORTED | ENGINEER_PROVIDED | null"
  },
  "reduced_tier": false,
  "reduced_tier_reason": "<why, when true; null otherwise>",
  "failure_time": {
    "value": "<ISO 8601, or null if undetermined>",
    "origin": "engineer | log | undetermined",
    "tier": "ENGINEER_PROVIDED | VERIFIED_LOG | null",
    "evidence_ref": "<ledger line + raw/ file pointer, when origin is \"log\"; null otherwise>"
  },
  "window": {
    "start": "<ISO 8601>",
    "end": "<ISO 8601>",
    "basis": "<how this window was derived>"
  },
  "tables_in_scope": ["<table name>", "..."],
  "layers": ["<protocol layer>", "..."],
  "open_notes": ["<anything unresolved — e.g. failure time undetermined, generic classification>"]
}
```

- `classification.tier` is `TESTER_REPORTED` when the match came from PLM
  title/description text (the tester's own words), `ENGINEER_PROVIDED` when
  an explicit `classification_hint` overrode it, and `null` when
  `issue_type` is `generic` (nothing is being claimed).
- `reduced_tier: true` means classification matched no playbook and
  `rca-scope` proceeded generically — `tables_in_scope`/`layers` were not
  narrowed by a playbook, and per issue #5's classification rule, findings
  any later skill produces under this scope should be treated at a reduced
  tier as a result. `rca-scope` states this plainly rather than forcing the
  issue into the nearest-looking category.
- `failure_time.tier` is `ENGINEER_PROVIDED` when supplied at invocation,
  `VERIFIED_LOG` only once a log query actually hit a keyword and produced
  a timestamp, and `null`/`origin: "undetermined"` when neither happened —
  per `evidence-tiers.md`'s "guessing may ask, never answer" rule, a query
  that misses does not get to claim a failure time either way.
- `tables_in_scope` narrows (never widens) `input/log-pointers.json.tables`
  — the full extent of what is loaded — to what this run's analysis should
  query. `layers` is the corresponding set of protocol/application layers
  (e.g. `RRC`, `NAS`, `IMS/SIP`, `PHY`) relevant to the classified (or
  generic) issue type.

## Run numbering

Runs are numbered `run-01`, `run-02`, … in creation order, zero-padded to
two digits. `rca-intake` determines the next number by listing
`runs/` and taking one past the highest existing number (`run-01` if
none exist). **Re-running `rca-intake` on an existing issue always opens a
new run — it never overwrites an existing run's `manifest.json` or
anything under that run's directory.** `input/` and `issue.json` *are*
refreshed on a re-run (see above); only the numbered run directories are
append-only.

## Per-Section Write Owners

| Section / file | Written by |
|---|---|
| `issue.json` (create + refresh) | `rca-intake` |
| `input/plm-snapshot.json` | `rca-intake` |
| `input/log-pointers.json` | `rca-intake` — sole writer; `rca-scope` narrows into its own `scope.json` rather than writing back into this file |
| `runs/run-NN/manifest.json` (create) | `rca-intake` |
| `runs/run-NN/manifest.json.current_step`, `.next_step`, `.status`, `.updated_at` | Each pipeline skill updates these on entry/exit — `rca-intake` and `rca-scope` both exercise this now; `.current_round`/`.standing_recommendation` remain forward-declared for `rca-analyze`'s checkpoint logic, not yet built |
| `runs/run-NN/scope.json` (create + full overwrite on re-run) | `rca-scope` — sole writer |
| `runs/run-NN/evidence/tools.jsonl` | Appended by whichever skill makes the call; never rewritten, only appended to |
| `runs/run-NN/raw/*` | Written by whichever skill makes the call; files are never overwritten, only added to (see `log-query-invocation.md`'s numbering rule) |
| `analysis/round-N.json`, `conclusion.json`, `CONCLUSION.md`, `knowledge/cases/`, `knowledge/playbooks/` | Not yet built — owned by `rca-analyze`, `rca-conclude`, `rca-learn` respectively, per issue #5's ownership table |

Two skills writing one section is a defect regardless of whether it
currently misbehaves — the same rule the v6 suite states for its own
schema.

## Slice-read discipline

Skills read only the sections they need, not the whole bundle. `rca-intake`
never reads `runs/*` beyond listing directory names to pick the next run
number. A skill that needs a prior run's conclusion reads that run's
`conclusion.json` directly rather than walking the whole issue tree.
