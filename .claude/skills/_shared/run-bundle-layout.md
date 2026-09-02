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
        conclusion.json     # problem, root cause, causal chain, reproduction scenario — owned by rca-conclude
        CONCLUSION.md       # written by rca-conclude for THIS run only, once it reaches a conclusion
      run-02/
        ...
  knowledge/
    cases/<case_id>.json   # written by rca-learn, one per accepted (active_run) conclusion
    .drafts/<playbook_id>.md  # git-ignored staging area for an unconfirmed playbook draft — rca-learn only
    playbooks/<playbook_id>.md  # promoted, reviewed; the only part of .rca/ committed to git
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
#9; see the "Per-Section Write Owners" table below). `rca-conclude` (issue
#10) synthesizes `conclusion.json` and `CONCLUSION.md` from what
`rca-scope`/`rca-analyze` already wrote — it runs no new query itself —
and, only once an engineer explicitly confirms the draft, sets
`issue.json.active_run` and advances `manifest.json.next_step` to
`"rca-learn"`. `rca-learn` (issue #11) writes exactly one
`knowledge/cases/<case_id>.json` per accepted conclusion — the run named
by `issue.json.active_run`, never any other — and, only on an explicit,
separate engineer `promote` action, a reviewed `knowledge/playbooks/<playbook_id>.md`.
See "`knowledge/cases/<case_id>.json`" and "`knowledge/playbooks/<playbook_id>.md`"
below for both schemas.

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

`title`/`description`/`comments` are refreshed (fully overwritten) on
every `rca-intake` invocation for this issue — they always reflect the
latest PLM fetch, per `plm-invocation.md`. `engineer_clarification` is
refreshed **per field**: a field supplied at this invocation overwrites
its prior value; a field not supplied carries forward from this issue's
previous run's snapshot unchanged (never reset to `null` just because this
invocation didn't restate it). Nothing here is rephrased or summarized by
the skill — `title`/`description`/`comments` are written verbatim from
PLM; `engineer_clarification` is written verbatim from whatever the
engineer supplied.

```json
{
  "fetched_at": "<ISO 8601>",
  "title": "<verbatim>",
  "description": "<verbatim>",
  "comments": [
    {"comment_id": "<verbatim>", "author": "<verbatim>", "timestamp": "<ISO 8601>", "text": "<verbatim>"}
  ],
  "engineer_clarification": {
    "title": {"text": "<verbatim>", "tier": "ENGINEER_PROVIDED"} ,
    "description": {"text": "<verbatim>", "tier": "ENGINEER_PROVIDED"},
    "comments": {"text": "<verbatim>", "tier": "ENGINEER_PROVIDED"}
  }
}
```

`title`/`description`/`comments` are the snapshotted PLM text itself, kept
so a later edit in PLM cannot silently change what a conclusion rested on
— none of the three is itself tagged with an evidence tier at intake time,
because none is (yet) a claim used in analysis (the same reasoning that
already applied to `description` before this file's `engineer_clarification`
addition). There is no separate reproduction-steps field — see
`plm-invocation.md`'s "What this capability does not provide" for why.

`engineer_clarification` is an engineer's optional, explicit correction or
clarification of `title`/`description`/`comments` — supplied only when the
tester's own account is unclear or technically imprecise, per
`rca-intake/SKILL.md`'s inputs. Each populated sub-field is tier
`ENGINEER_PROVIDED`, never `TESTER_REPORTED` — the system cannot verify
that an engineer's rewrite preserves the tester's original words. It is
written **alongside**, never in place of, the corresponding verbatim
field: `rca-scope`/`rca-analyze` should prefer a populated
`engineer_clarification` field over its raw counterpart when seeding
classification or hypotheses (it is closer to the technical truth), while
`rca-conclude`'s `tester_comparison` always reads the raw verbatim field —
comparing the log against what the engineer already corrected would defeat
the point of checking the tester's account against the log at all. An
unpopulated sub-field is `null`.

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
  engineer (or autonomy) has actually responded to — "a later decision to
  trust the agent more should rest on evidence rather than impression"
  (issue #9). Each entry:
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
  `override_rationale` — see that file). The round-budget gate re-applies
  at every round from `round_budget` onward, not just once: an override
  that got the run past round `round_budget` does not carry forward to
  round `round_budget + 1`'s own checkpoint — that round needs its own
  fresh `override: true` + `override_rationale` entry here too.
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
  "contradicted_findings": [
    {"document": "<citation.document, from the NotebookLM answer this contradicts>", "section": "<citation.section, or null>", "claim": "<what the document said>", "log_showed": "<what the log actually showed>", "tier": "CONTRADICTED", "evidence_ref": "<ledger line + raw/ pointer of the HARD finding that disagreed>"}
  ],
  "case_hints": [
    {"source": "case | playbook", "id": "<case_id or playbook_id>", "hint": "<one line: what it suggested — a direction, a keyword, a table>", "used_for": "<hypothesis id this seeded, \"failure_point\" if it seeded Step 5's failure-point location instead, or null if read but not used>"}
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
  `round >= manifest.json.round_budget` — every round from the budget
  onward, not only the one exactly at it — whose
  `checkpoint.recommendation` is therefore forced to recommend acceptance
  regardless of what survived — see `rca-analyze/SKILL.md`'s round-budget
  gate.
- `contradicted_findings` (issue #11) is the structured record of a
  vendor/spec-documentation claim (a rung 1/4 NotebookLM citation) that a
  HARD finding this round disproved — the same event `keyword-provenance.md`'s
  "Promotion and verification" describes as tagging the claim
  `CONTRADICTED`, given a durable, machine-readable home instead of only a
  free-text `open_notes` sentence, specifically so `rca-learn` can read it
  without parsing prose. Empty on every round that produced no such
  finding, which is the common case — this is not something a round is
  expected to manufacture. A round written before issue #11 landed simply
  has no `contradicted_findings` field at all, read as `[]`, the same
  backward-compatibility rule `decisions[]` uses above.
- `case_hints` (issue #11) records every `.rca/knowledge/cases/` or
  `knowledge/playbooks/` entry this round's hypothesis generation *or*
  failure-point location actually considered (resolution ladder rung 6,
  once `rca-learn` exists) — Step 5's failure-point fallback and Step 6's
  hypothesis generation both read this rung and both write here — never
  more than a one-line pointer to what it suggested. A case or playbook
  hint may seed a hypothesis's `statement`, contribute a candidate keyword
  to a `testing_query`, or contribute the keyword a failure-point locate
  query is narrowed to, exactly like a rung-1/4 SOFT source or a
  FORBIDDEN-origin guess can; it may never itself appear in
  `causal_chain_additions`, `failure_point`, or any hypothesis's `queries[]`
  — only the fresh query this round actually runs against *this* issue's
  own log/code can do that (see `keyword-provenance.md`'s "cases suggest,
  they never prove" note). Empty on every round that read no matching case
  or playbook, or that predates issue #11.
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

## `runs/run-NN/conclusion.json`

Written by `rca-conclude` (issue #10), reached only once
`manifest.json.next_step == "rca-conclude"` (set by `rca-analyze`'s
`accept` handling — see above). One file per run, written once and then
either confirmed in place or left as-is: **mutable only up to its first
write, immutable from `confirmed: true` onward** — a confirmed conclusion
is never rewritten; analyzing further means starting a new run via
`rca-intake`.

```json
{
  "drafted_at": "<ISO 8601, when this file was written>",
  "confirmed": false,
  "confirmed_at": null,
  "problem": {
    "located": true,
    "statement": "<the observable failure point, protocol level>",
    "tier": "VERIFIED_LOG | ENGINEER_PROVIDED | null",
    "evidence_ref": "<ledger ref / raw pointer this was copied from verbatim, or null>"
  },
  "root_cause": {
    "established": true,
    "statement": "<synthesized root-cause statement>",
    "tier": "<tier of the terminal causal_chain entry>",
    "evidence_ref": "<ledger ref / raw pointer>"
  },
  "causal_chain": [
    {"round": 1, "statement": "<link>", "tier": "<tier>", "evidence_ref": "<ledger ref / raw pointer>"}
  ],
  "reproduction_scenario": {
    "preconditions": [
      {"statement": "<protocol-level precondition>", "tier": "<tier>", "evidence_ref": "<... or null>"}
    ],
    "steps": [
      {"step": 1, "statement": "<protocol-level action/event>", "tier": "<tier>", "evidence_ref": "<... or null>"}
    ],
    "expected_failure": {"statement": "<what a tester would observe if it reproduces>", "tier": "<tier>", "evidence_ref": "<... or null>"},
    "tester_comparison": {
      "tester_reported_text": "<verbatim, from input/plm-snapshot.json.description — never engineer_clarification.description>",
      "matches": ["<scenario statement that aligns with the tester's account>"],
      "divergences": [
        {"tester_claim": "<what the tester's text said>", "scenario_says": "<what the scenario states instead>", "tier": "CONTRADICTED | <other tier>", "evidence_ref": "<... or null>"}
      ]
    }
  },
  "evidence_gaps": ["<every SPEC_INFERRED/ASSUMED/TESTER_REPORTED/CODE_UNAVAILABLE/CONTRADICTED item this conclusion rests on, restated plainly>"],
  "rests_on_weak_evidence": true,
  "weak_evidence_notice": "<explicit statement of which parts rest on ASSUMED or CODE_UNAVAILABLE links, stated prominently; null if none>"
}
```

- `problem`, `root_cause`, and every `causal_chain` entry's `tier`/
  `evidence_ref` are always copied verbatim from a round's
  `failure_point`/`causal_chain_additions` (or, when no analysis round ever
  ran, from `scope.json.failure_time`) — `rca-conclude` never runs a new
  log/code/NotebookLM query itself and never invents a reference; it only
  synthesizes across what `rca-scope`/`rca-analyze` already recorded. Per
  `evidence-tiers.md`, copying forward never upgrades a tier.
- `root_cause.established: false` and `causal_chain: []` are valid outcomes
  (an accepted run that produced no causal-chain findings, including the
  round-0 edge case) — stated plainly, never papered over with a fabricated
  cause.
- `reproduction_scenario.tester_comparison.divergences[].tier` is
  `"CONTRADICTED"` specifically when a HARD (`VERIFIED_LOG`/`CODE_BOUND`)
  finding positively disagrees with what the tester reported — not merely
  when the scenario adds detail the tester didn't mention. `evidence-tiers.md`
  names "the tester's own PLM account" as one of the sources `CONTRADICTED`
  can apply to for exactly this case — see that file's tier table and
  `rca-conclude`'s scope note.
- `rests_on_weak_evidence`/`weak_evidence_notice` are computed from whether
  `root_cause`, any `causal_chain` entry, or any `reproduction_scenario`
  precondition/step/`expected_failure` carries tier `ASSUMED` or
  `CODE_UNAVAILABLE` — this is what issue #10's "states this prominently
  rather than presenting uniform confidence" requirement checks.
- A forbidden-pattern scan (fixes, patches, configuration changes, test
  cases, next-step suggestions — see `rca-conclude/SKILL.md`) runs over
  every authored string in this file before it is written, with a named
  exception for verbatim-quoted external text (`tester_reported_text`) —
  the tester may use these words innocently in their own account.

## `knowledge/cases/<case_id>.json`

Written by `rca-learn` (issue #11), one file per accepted conclusion —
`case_id` is `<issue_id>-<run_id>` (e.g. `PLM-12345-run-01`), so a case
file's own name already states which run it came from. Written once, from
a run's already-confirmed `conclusion.json` and the `analysis/round-NN.json`
files it was built from; `rca-learn` runs no query of its own and invents
nothing. **Only the run named by `issue.json.active_run` at the moment
`rca-learn` runs may produce one** — an abandoned, aborted, or merely
superseded run never enters the case base, even if it once had its own
(unconfirmed, or since-superseded) conclusion.

```json
{
  "case_id": "PLM-12345-run-01",
  "issue_id": "PLM-12345",
  "run_id": "run-01",
  "written_at": "<ISO 8601>",
  "issue_type": "<scope.json.classification.issue_type for this run>",
  "symptom": "<input/plm-snapshot.json title, verbatim>",
  "failure_point": {"statement": "<conclusion.json.problem.statement>", "tier": "<tier, copied verbatim>", "evidence_ref": "<copied verbatim, or null>"},
  "root_cause": {"statement": "<conclusion.json.root_cause.statement>", "tier": "<tier, copied verbatim>", "evidence_ref": "<copied verbatim, or null>"},
  "causal_chain": ["<conclusion.json.causal_chain, copied verbatim, tiers and evidence_refs intact>"],
  "useful_queries": [
    {"tool": "log-query | code-search | notebooklm", "table": "<table, or null>", "ledger_ref": "<copied verbatim>", "why_useful": "<one line: which failure_point/causal_chain entry this hit produced>"}
  ],
  "meaningful_keywords": ["<every keyword named in a useful_queries[] entry's ledger line, deduplicated>"],
  "contradicted_docs": [
    {"document": "<citation.document>", "section": "<citation.section, or null>", "chip_series": "<derived from input/log-pointers.json.build/model at write time, or \"unknown\" if neither is set>", "claim": "<what the document said>", "log_showed": "<what the log actually showed>", "evidence_ref": "<copied verbatim>"}
  ]
}
```

- Every tier and `evidence_ref` in this file is copied **verbatim** from
  where `rca-conclude`/`rca-analyze` already recorded it — never
  re-derived, never upgraded. Per `evidence-tiers.md`'s "a tier never
  improves with the passage of time," a finding that was `ASSUMED` when
  `conclusion.json` recorded it is still `ASSUMED` here, and stays
  `ASSUMED` no matter how many later runs read this case back as a hint —
  see `keyword-provenance.md`'s "cases suggest, they never prove."
- `useful_queries` is drawn from every `hypotheses[].queries[]` entry
  across this run's rounds with `outcome: "hit"`, restricted to the ones
  whose finding actually reached `failure_point`, `causal_chain_additions`,
  or a hypothesis that survived to the accepted recommendation — a hit
  that fed an eliminated hypothesis is not "useful" in the sense this file
  means, even though it was still a demonstrated fact in this log.
  `meaningful_keywords` is the deduplicated union of every keyword named in
  those entries' `evidence/tools.jsonl` lines (`params`/`keywords_in`).
- `contradicted_docs` is drawn from every `analysis/round-NN.json.contradicted_findings[]`
  entry across this run's rounds, each with `chip_series` filled in at
  case-write time from this run's own `input/log-pointers.json` (a
  workspace-supplied `build`/`model`, per `notebooklm-invocation.md`'s note
  that the build/model-to-chip-series mapping is a workspace concern) —
  never guessed when neither field is set. This is the accumulating "map
  of where the vendor docs cannot be trusted for a given series" issue #5's
  spec names as the suite's most durable output.
- A case file, once written, is not rewritten — the same immutability
  `conclusion.json` has from `confirmed: true` onward, for the same reason:
  a further analysis of the same issue is a new run via `rca-intake`,
  which (if it too reaches an accepted conclusion) writes its own,
  differently-named `case_id`, never overwrites this one.
- `rca-learn` writes no field here from its own reasoning — `symptom`,
  `why_useful`, `claim`, `log_showed` are all short excerpts or copies of
  text `rca-scope`/`rca-analyze`/`rca-conclude` already wrote or the PLM
  snapshot already held, never a new analytical claim.

## `knowledge/playbooks/<playbook_id>.md`

Written by `rca-learn` (issue #11), only on a separate, explicit engineer
`promote` action — never automatically, and never as a side effect of
writing a case record. This is the **only** part of `.rca/` committed to
git (see `.gitignore`'s carve-out); everything else under `.rca/`,
`knowledge/cases/` included, stays local and git-ignored because it can
hold field logs, subscriber identifiers, and other NDA material.

Plain Markdown prose, not JSON — "prose a colleague can read and correct"
(issue #5) — with no fixed schema beyond a required title line and a
required provenance line naming which case(s) it was drafted from:

```markdown
# Playbook: <short title, e.g. "VoLTE call drop — Qualcomm 9205, IMS re-INVITE timeout">

Promoted: <ISO 8601> — drafted from <case_id, case_id, ...>

<engineer-reviewed prose: the pattern, the issue type(s) it applies to,
what to check first, and any chip-series-specific vendor-documentation
caveat this pattern has confirmed repeatedly>
```

A playbook is drafted first at `.rca/knowledge/.drafts/<playbook_id>.md` —
git-ignored, like the rest of `.rca/`, since a draft is exactly the
unreviewed state this file's own git-tracking is meant to never expose —
and moved into this path only once the engineer's `confirm playbook
<playbook_id>` reply passes the customer-data check (see
`rca-learn/SKILL.md`). `rca-learn` never runs `git add`/`git commit`
itself; writing to this path only makes the file one `.gitignore` no
longer excludes; adding and committing it remains the engineer's own,
separate action.

This is a **different concept** from `scope.json.classification.matched_playbook`,
which names a row in `rca-scope`'s hand-maintained
`references/known-issue-types.md` — see that file's own note. Promoting a
playbook here never adds a row there, and the two are read by different
skills for different purposes.

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
| `issue.json.active_run` | `rca-conclude` — sole writer; set only when the engineer confirms a draft conclusion (never by `rca-intake`, never speculatively) |
| `input/plm-snapshot.json` | `rca-intake` |
| `input/log-pointers.json` | `rca-intake` — sole writer; `rca-scope` narrows into its own `scope.json` rather than writing back into this file |
| `runs/run-NN/manifest.json` (create) | `rca-intake` |
| `runs/run-NN/manifest.json.current_step`, `.updated_at` | Every pipeline skill updates these on entry/exit |
| `runs/run-NN/manifest.json.next_step`, `.status` | `rca-intake` and `rca-scope` at their own steps; `rca-analyze` (issue #9) additionally sets `next_step: "rca-conclude"` on an `accept` reply and `next_step: null` / `status: "aborted"` on an `abort` reply; `rca-conclude` (issue #10) additionally sets `next_step: "rca-learn"` on its own `accept` reply and `status: "aborted"` / `next_step: null` on its own `abort` reply; `rca-learn` (issue #11) additionally sets `next_step: "complete"` once it writes this run's case record — never on any other verb, and never `status` back out of `"aborted"`. `next_step: null` therefore means exactly one thing (`status == "aborted"`); pipeline completion after `rca-learn` is the distinct `"complete"` value instead, precisely so a `null` never has to be disambiguated by which skill set it — see `.claude/commands/rca.md`'s dispatcher, which treats `next_step == "complete"` as its own case, not as `null` |
| `runs/run-NN/manifest.json.current_round`, `.standing_recommendation`, `.decisions` | `rca-analyze` — sole writer |
| `runs/run-NN/scope.json` (create + full overwrite on re-run) | `rca-scope` — sole writer |
| `runs/run-NN/analysis/round-NN.json` (create; never overwritten once written) | `rca-analyze` — sole writer, one file per round |
| `runs/run-NN/conclusion.json` (create once; `confirmed`/`confirmed_at` flipped in place on accept; otherwise immutable) | `rca-conclude` — sole writer |
| `runs/run-NN/CONCLUSION.md` | `rca-conclude` — sole writer, for this run only |
| `runs/run-NN/evidence/tools.jsonl` | Appended by whichever skill makes the call; never rewritten, only appended to |
| `runs/run-NN/raw/*` | Written by whichever skill makes the call; files are never overwritten, only added to (see `log-query-invocation.md`'s numbering rule) |
| `knowledge/cases/<case_id>.json` (create once; never rewritten) | `rca-learn` — sole writer, one file per accepted conclusion of the run named `active_run` |
| `knowledge/.drafts/<playbook_id>.md` (create/overwrite on `promote`; deleted on `confirm playbook`/`discard playbook`) | `rca-learn` — sole writer, the mutable pre-review staging copy of a playbook draft |
| `knowledge/playbooks/<playbook_id>.md` | `rca-learn` — sole writer, only on an explicit, separate engineer `promote` action |

Two skills writing one section is a defect regardless of whether it
currently misbehaves.

## Slice-read discipline

Skills read only the sections they need, not the whole bundle. `rca-intake`
never reads `runs/*` beyond listing directory names to pick the next run
number. A skill that needs a prior run's conclusion reads that run's
`conclusion.json` directly rather than walking the whole issue tree.
