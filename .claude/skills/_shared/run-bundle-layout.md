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
        analysis/
          round-01.json      # one round's findings + checkpoint — owned by rca-analyze, one file per round, never overwritten
          round-02.json
          ...
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
log queries. `rca-analyze` (issues #8 and #9) adds one
`analysis/round-NN.json` per round it runs, appending further ledger
lines and `raw/` files for its own log-query, code-graph, and NotebookLM
calls, and updates `manifest.json`'s `current_round`/
`standing_recommendation`/`decisions[]` fields every round — plus, when a
checkpoint's reply is `accept` or `abort`, `next_step`/`status` too (issue
#9; see the "Per-Section Write Owners" table below). Everything else in
the tree above (`conclusion.json`, `CONCLUSION.md`, `knowledge/`) is
written by skills that do not exist yet and is shown here only so this
file does not need to be restructured when they arrive.

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
  "standing_recommendation": null,
  "decisions": []
}
```

- `label` records the engineer's intent for this run (issue #5, story 6) —
  e.g. "first pass" or "re-run with corrected build". `rca-intake` asks
  for it or defaults to something inert like `"run <N>"`; it is never
  inferred from PLM content.
- `autonomy` (`review_all | auto_until_blocked | auto`) and `round_budget`
  are global run settings established at creation time with the defaults
  above, editable directly in this file by the engineer at any time
  (issue #9 adds no separate input for changing them — this file already
  is the configuration surface, so nothing else needs to exist). `status`
  is `"in_progress"` for the whole life of a run except `"aborted"`, set
  by `rca-analyze` (issue #9) the moment an `abort` is recorded — no other
  skill sets `status`, and nothing sets it back once aborted. `rca-analyze`
  (issues #8/#9) updates `current_round`, `standing_recommendation`, and
  `decisions` on every round it writes, and additionally `next_step` (to
  `"rca-conclude"` on `accept`, to `null` on `abort`) and `status` (to
  `"aborted"` on `abort`) — see `rca-analyze/SKILL.md`'s loop-handling
  steps and the "Per-Section Write Owners" table below.
- `decisions` is an append-only audit log, one entry per checkpoint an
  engineer (or autonomy) has actually responded to — mirroring the older
  v6 suite's own `user_decisions[]` (`.cline/skills/_shared/state-file-schema.md`)
  for the same reason: "a later decision to trust the agent more should
  rest on evidence rather than impression" (issue #9). Each entry:
  ```json
  {
    "round": 1,
    "agent_recommendation": {"direction": "H1", "reason": "<one line, from that round's checkpoint.recommendation>"},
    "engineer_response": {"verb": "dig | redirect | accept | abort | auto_continue", "input": "<direction, redirect text, abort reason, or null>", "recorded_at": "<ISO 8601>"},
    "override": false,
    "override_rationale": "<required when override is true; null otherwise>"
  }
  ```
  `verb: "auto_continue"` marks a round `rca-analyze` advanced on its own
  under `autonomy: "auto"`/`"auto_until_blocked"` rather than a reply an
  engineer actually typed — see `rca-analyze/SKILL.md`'s loop-control
  step. `override: true` records the one case a reply is honored past a
  gate that would otherwise have blocked it (only the round-budget gate is
  overridable at all, and only with an explicit override phrase carrying
  `override_rationale` — see that file).
- `input_snapshot_fetched_at` pins *this run* to the PLM snapshot it was
  created from, even though `input/plm-snapshot.json` itself is refreshed
  by later intake re-runs on the same issue.
- `rca-intake` creates this file with `decisions: []`; no prior ticket's
  `manifest.json` shape changes retroactively — a run created before issue
  #9 landed simply has no `decisions` entries yet until `rca-analyze`
  starts appending to it.

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

## `runs/run-NN/analysis/round-NN.json`

Written by `rca-analyze` (issues #8 and #9), one file per round,
zero-padded to two digits (`round-01.json`, `round-02.json`, …). **A
round's file is never overwritten once written** — the same append-only
discipline as `runs/run-NN` itself, and for the same reason: round N+1
must be provable against round N's actual recorded state, not a version
silently rewritten after the fact. This is why the (agent recommendation,
engineer decision) pair issue #9 adds is **not** a field on this file —
it cannot be known until after the round is written and the checkpoint
has been shown, so it lives in `manifest.json.decisions[]` instead (see
above), leaving every round file exactly as fixed as it always was.

```json
{
  "round": 1,
  "started_at": "<ISO 8601>",
  "completed_at": "<ISO 8601>",
  "direction": "<the candidate direction this round pursued, from the prior round's checkpoint — null for round 1>",
  "engineer_redirect": {"text": "<verbatim, from a redirect reply that produced this round>", "tier": "ENGINEER_PROVIDED", "recorded_at": "<ISO 8601>"},
  "forced_by_round_budget": false,
  "failure_point": {
    "located": true,
    "event": {"timestamp": "<ISO 8601>", "table": "<table>", "layer": "<layer>", "message": "<message/summary>"},
    "tier": "VERIFIED_LOG",
    "evidence_ref": "<ledger line + raw/ file pointer>"
  },
  "hypotheses": [
    {
      "id": "H1",
      "statement": "<the candidate explanation>",
      "predicted_evidence": "<what a query would show if this were true>",
      "testing_query": {"tool": "log-query | code-search | notebooklm", "target": "<table+keywords, or module/symbol>"},
      "status": "surviving | eliminated",
      "queries": [
        {"ledger_ref": "<ledger line + raw/ pointer>", "outcome": "hit | miss", "tier": "<tier the hit was recorded at, when outcome is hit; null on a miss>"}
      ],
      "eliminated_by": "<the ledger ref of the contradicting HARD finding, when status is eliminated; null otherwise>",
      "untested_tier": "<'ASSUMED', only when this hypothesis reached the checkpoint with queries: [] because no viable query could be constructed at all — see rca-analyze/SKILL.md's Step 6; null otherwise>"
    }
  ],
  "causal_chain_additions": [
    {"statement": "<a link this round established>", "tier": "<tier>", "evidence_ref": "<ledger line + raw/ pointer>"}
  ],
  "open_notes": ["<ladder rungs skipped and why, CONTRADICTED findings, anything unresolved>"],
  "checkpoint": {
    "causal_chain": ["<every link so far, this run, restated for direct display — see checkpoint-format.md>"],
    "candidate_directions": [
      {"hypothesis_id": "H1", "rank": 1, "testing_query_summary": "<one line>"}
    ],
    "recommendation": {"direction": "<hypothesis id, or null if nothing survived>", "reason": "<one line>"},
    "evidence_gaps": ["<restated from open_notes plus anything from hypotheses' non-HARD or miss-only queries>"]
  }
}
```

- `failure_point.located: false` (with `event: null`, `tier: null`) is a
  valid, expected outcome — see `rca-analyze/SKILL.md`'s Step 5. It is
  never papered over with a fabricated event.
- `hypotheses[].status` is only ever `"surviving"` or `"eliminated"` —
  see `keyword-provenance.md`: a hypothesis is eliminated only by a
  positive, contradicting HARD finding (`eliminated_by` set), never by a
  guessed keyword's miss. `queries[]` records **every** testing query run
  against a hypothesis, hit or miss alike — this is what lets the
  checkpoint distinguish "surviving with supporting evidence" from
  "surviving but untested" (a miss recorded here, per
  `keyword-provenance.md`'s "guessing may ask, never answer", never
  eliminates the hypothesis on its own). `queries[]` is empty only when no
  test has been attempted at all — the one case `untested_tier: "ASSUMED"`
  applies (issue #9's "conclusion resting on an ASSUMED finding" gate
  checks exactly this field on the round's recommended direction).
- `engineer_redirect` (issue #9) is non-null only on a round produced by a
  `redirect <information>` reply — see `rca-analyze/SKILL.md`'s handling
  of that verb. It is read, not re-derived, by Step 6's hypothesis
  generation on the round it appears in; it is never copied forward into a
  later round's own `engineer_redirect` field (a later round that still
  needs it reads this round's file directly, the same slice-read
  discipline as `causal_chain_additions`).
- `forced_by_round_budget: true` (issue #9) marks a round written at
  `round == manifest.json.round_budget`, whose `checkpoint.recommendation`
  is therefore forced to recommend acceptance regardless of what survived
  — see `rca-analyze/SKILL.md`'s round-budget gate.
- `checkpoint` is the structured source `rca-analyze` renders into the
  prose format `checkpoint-format.md` specifies when reporting to the
  engineer — the file holds the data, that document holds the
  presentation rules.
- Issue #8 built the single round this schema always produced one of;
  issue #9 adds the loop that chains rounds together — a later invocation
  reading a prior round's `checkpoint.recommendation` (via `dig`) or
  injecting new evidence (via `redirect`) to set `direction` /
  `engineer_redirect` on the next round it writes. Round 1 of any run
  still has `direction: null` and `engineer_redirect: null` — there is no
  prior checkpoint to have produced either.

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
| `runs/run-NN/manifest.json.current_step`, `.updated_at` | Every pipeline skill updates these on entry/exit |
| `runs/run-NN/manifest.json.next_step`, `.status` | `rca-intake` and `rca-scope` at their own steps; `rca-analyze` (issue #9) additionally sets `next_step: "rca-conclude"` on an `accept` reply and `next_step: null` / `status: "aborted"` on an `abort` reply — never on any other verb, and never `status` back out of `"aborted"` |
| `runs/run-NN/manifest.json.current_round`, `.standing_recommendation`, `.decisions` | `rca-analyze` — sole writer |
| `runs/run-NN/scope.json` (create + full overwrite on re-run) | `rca-scope` — sole writer |
| `runs/run-NN/analysis/round-NN.json` (create; never overwritten once written) | `rca-analyze` — sole writer, one file per round |
| `runs/run-NN/evidence/tools.jsonl` | Appended by whichever skill makes the call; never rewritten, only appended to |
| `runs/run-NN/raw/*` | Written by whichever skill makes the call; files are never overwritten, only added to (see `log-query-invocation.md`'s numbering rule) |
| `conclusion.json`, `CONCLUSION.md`, `knowledge/cases/`, `knowledge/playbooks/` | Not yet built — owned by `rca-conclude`, `rca-learn` respectively, per issue #5's ownership table |

Two skills writing one section is a defect regardless of whether it
currently misbehaves — the same rule the v6 suite states for its own
schema.

## Slice-read discipline

Skills read only the sections they need, not the whole bundle. `rca-intake`
never reads `runs/*` beyond listing directory names to pick the next run
number. A skill that needs a prior run's conclusion reads that run's
`conclusion.json` directly rather than walking the whole issue tree.
