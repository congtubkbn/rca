---
name: rca-learn
description: >
  Write a case record for an accepted PLM-issue RCA conclusion — issue
  type, symptom, failure point, the queries and keywords that actually
  proved useful, the root cause, and any vendor/spec-documentation claim
  the log contradicted (with the document and chip series) — into
  `.rca/knowledge/cases/`, so a later run can be pointed at where to look
  without repeating a dead end. Also handles an engineer's separate,
  explicit `promote` action that drafts a reviewed playbook from one or
  more existing cases and, on `confirm playbook <id>`, checks it for
  subscriber identifiers or log excerpts before writing it to the one part
  of `.rca/` committed to git, `.rca/knowledge/playbooks/`. Use when an
  engineer wants to record, learn from, or close out an accepted
  conclusion (e.g. "learn from PLM-12345", "record this case"), or to
  promote a repeated pattern into a playbook (e.g. "promote a playbook
  from PLM-12345-run-01 and PLM-19090-run-02", "confirm playbook
  qc9205_ims_timeout", "discard that playbook draft"). Requires
  `issue.json.active_run` to be set with a confirmed `conclusion.json` —
  invoke `rca-conclude` and reply `accept` to its draft first if it is
  not; this skill refuses to run at all otherwise and states why. Reaching
  a conclusion, running further analysis, or generating hypotheses is
  `rca-analyze`/`rca-conclude`'s job, which this skill only reads — do not
  use this skill for that. Producing a Technical Report is `tr-creator`'s
  job, a separate, explicitly invoked skill this skill never calls — do
  not use this skill for that either. Do NOT confuse a
  `promote`/`confirm playbook` request with
  `scope.json.classification.matched_playbook` — that is a row id in
  `rca-scope`'s hand-maintained `references/known-issue-types.md`, a
  different concept this skill neither reads nor writes; only
  `rca-scope` touches it.
---

# rca-learn

Part of the PLM-issue pipeline (issue #5): `rca-intake → rca-scope →
rca-analyze ⟲ → rca-conclude → rca-learn`. This is the pipeline's fifth
and final step (issue #11), reached only after an engineer has replied
`accept` to `rca-conclude`'s standing draft. Its job is capture, not
investigation: it runs no new log, code, or NotebookLM query of its own —
it reads what `rca-scope`/`rca-analyze`/`rca-conclude` already wrote for
one specific run and turns it into a durable, reusable record.

Read `.claude/skills/_shared/run-bundle-layout.md` before changing
anything below — it is the authoritative schema for
`knowledge/cases/<case_id>.json` and `knowledge/playbooks/<playbook_id>.md`,
including which fields this skill may copy forward versus author itself.
Also read `_shared/evidence-tiers.md`'s **Tier immutability** rule — this
skill exists specifically not to violate it — and
`_shared/keyword-provenance.md`'s canonical term, "**Cases and playbooks
are hints, never evidence**"
(`_shared/keyword-provenance.md#cases-and-playbooks-are-hints-never-evidence`)
— the rule that governs how the case base this skill writes may later be
read back by `rca-analyze`. This skill makes no tool calls of any kind — it
does not call `log-query-invocation.md`, `code-graph-invocation.md`, or
`notebooklm-invocation.md` — and does not call `_shared/checkpoint-format.md`
either, since it presents no checkpoint of its own.

```yaml
contract:
  requires: [issue_id, active_run, confirmed_conclusion]
  optional: [run_id, promote]
  produces:
    - .rca/knowledge/cases/<case_id>.json
    - .rca/knowledge/.drafts/<playbook_id>.md (only via "Handling promote")
    - .rca/knowledge/playbooks/<playbook_id>.md (only via "Handling confirm playbook")
    - .rca/issues/<issue_id>/runs/run-NN/manifest.json (current_step, next_step, updated_at only)
  self_seedable: false
```

`confirmed_conclusion` means `runs/<active_run>/conclusion.json.confirmed
== true` — the record that an engineer already replied `accept` to
`rca-conclude`'s draft. `self_seedable: false` for the same reason as
`rca-conclude`: there is nothing an engineer can pass at invocation that
substitutes for that acceptance having already happened — the fix for a
missing one is to run `rca-conclude` and accept, not to pass more
arguments here.

The `promote`/`confirm playbook`/`discard playbook` invocation forms
(below, under "Handling promote") are a **separate action** from writing
a case record, with their own precondition — at least one existing
`knowledge/cases/<case_id>.json` to draft from — and need neither
`issue_id` nor `active_run` at all, since a case file already names the
issue and run it came from and a playbook may legitimately be drafted
across cases from different issues. They exist in this same skill because
they read the same `knowledge/` directory this skill owns, not because
they share a precondition with the default case-write behavior.

## What this delivers

Two things, reached by different invocations:

1. **A case record** (the default behavior, reached via `/rca`'s dispatch
   once `manifest.json.next_step == "rca-learn"`, or direct invocation):
   one `knowledge/cases/<case_id>.json` per accepted conclusion, capturing
   what the run actually found — never a re-derivation, never an upgrade
   of any tier already recorded.
2. **A promoted playbook** (an entirely separate, engineer-initiated
   action): reviewed Markdown prose drafted from one or more existing
   cases, written to the single part of `.rca/` that is committed to git,
   and only after an explicit confirmation step that checks it for
   customer data.

Both are asset-building, not analysis: per
`_shared/keyword-provenance.md`'s "**Cases and playbooks are hints, never
evidence**"
(`_shared/keyword-provenance.md#cases-and-playbooks-are-hints-never-evidence`),
a case or a playbook may only ever *suggest where to look* to a later
`rca-analyze` round, never itself evidence for a conclusion — and per
`_shared/evidence-tiers.md`'s **Tier immutability** rule, it never mutates
the tier a finding already carries. A case record read a year from now by
a different run still shows an `ASSUMED` finding as `ASSUMED`, not as
something reinforced by having been written down.

## Inputs

- `issue_id` (required for the default case-write behavior; not needed
  for `promote`/`confirm playbook`/`discard playbook`) — from invocation
  or `/rca`'s dispatch.
- `run_id` (optional, case-write behavior only) — which run to learn from.
  Must equal `issue.json.active_run` if supplied (see Step 1); there is no
  independent resolution the way `rca-scope`/`rca-analyze`/`rca-conclude`
  have, because this skill is not free to pick "the highest-numbered run"
  the way they are — only the accepted run may ever be learned from.
- `promote` (optional) — the engineer's playbook-drafting request, parsed
  from the invocation's own text: a `playbook_id` (a short slug) and
  either explicit `case_id`s or an `issue_type` to match across all
  existing cases, e.g. "promote qc9205_ims_timeout from
  PLM-12345-run-01, PLM-19090-run-02" or "promote generic_sms_cp_error
  for issue_type sms_failure". See "Handling promote" below.
- A standing draft's reply — `confirm playbook <playbook_id>` or `discard
  playbook <playbook_id>` — parsed the same way, addressed to a draft
  `promote` already produced.

## Steps (default: write a case record)

### 1. Resolve `issue_id` and the active run

1. If `issue_id` is missing, HALT: "Need a PLM issue ID to learn from.
   Which issue?" Do not guess one from conversation context. (This does
   not apply to `promote`/`confirm playbook`/`discard playbook` — see
   "Handling promote" below, which is reached before this step for those
   invocations.)
2. If `.rca/issues/<issue_id>/` does not exist, HALT: "No run bundle for
   `<issue_id>` — run `rca-intake` first."
3. Read `issue.json`. If `active_run` is `null`, HALT: "No accepted
   conclusion for `<issue_id>` yet — `active_run` is not set. `rca-learn`
   only ever writes a case for the run an engineer has explicitly accepted
   a conclusion for; run `rca-conclude` and reply `accept` to its draft
   first." This is the mechanical answer to "refuses to run when no run is
   active, stating why" — never proceed by guessing which run was meant.
4. If `run_id` was supplied and does not equal `active_run`: HALT: "Only
   the active run (`<active_run>`) may be written into the case base — run
   `<run_id>` is not the accepted conclusion for `<issue_id>`. If `<run_id>`
   should be the accepted one instead, run `rca-conclude` against it and
   accept its draft, which moves `active_run` there." Never write a case
   for a run other than `active_run`, regardless of what is asked for —
   this is the mechanical enforcement of "only the run named by
   `active_run` may be written to the case base."
5. `run_id = active_run` from here on.

### 2. Check the confirmed-conclusion precondition

Read `runs/<run_id>/manifest.json` and `runs/<run_id>/conclusion.json`.

- If `manifest.json` is missing: HALT: "Run `<run_id>` has no
  `manifest.json` — its bundle looks incomplete; check for a partial
  write." (Defensive — unreachable in practice, since `active_run` is only
  ever set by `rca-conclude` against a run that already has one.)
- If `manifest.json.status == "aborted"`: HALT: "Run `<run_id>` is marked
  aborted, yet `active_run` points at it — this should never happen
  (`rca-conclude` never sets `active_run` on an abort); check for a
  hand-edited bundle before proceeding." Never write a case for an
  aborted run under any circumstance.
- If `conclusion.json` does not exist, or `confirmed != true`: HALT: "Run
  `<run_id>` has no confirmed conclusion — `active_run` points at it, but
  `conclusion.json` is missing or still a draft. This should not happen
  outside a hand-edited bundle; re-run `rca-conclude`'s `accept` handling
  against this run." This is this skill's contract `requires` check for
  `confirmed_conclusion`.

### 3. Check whether this run's case already exists

`case_id = "<issue_id>-<run_id>"`. If
`knowledge/cases/<case_id>.json` already exists: this run has already
been learned from. Do not rewrite it — a case file, once written, is
immutable, the same discipline `conclusion.json` has from `confirmed:
true` onward (see `run-bundle-layout.md`). Report its existing content in
full (so the engineer sees what was recorded without opening the file
directly) and HALT. Do not proceed to Step 4.

### 4. Assemble the case record

Read only what's needed, never the whole bundle: `input/plm-snapshot.json`,
`input/log-pointers.json`, `runs/<run_id>/scope.json`,
`runs/<run_id>/conclusion.json`, every `runs/<run_id>/analysis/round-NN.json`
in round order, and `runs/<run_id>/evidence/tools.jsonl` (only the lines
referenced by the `ledger_ref`/`evidence_ref` pointers Step 4.3 below
actually needs — not read wholesale for keyword mining beyond that).

1. **`issue_type`, `symptom`** — `scope.json.classification.issue_type`;
   `symptom` = `input/plm-snapshot.json.title`, verbatim (a short,
   already-existing summary — this skill does not compose a new one).
2. **`failure_point`, `root_cause`, `causal_chain`** — copied verbatim,
   tier and `evidence_ref` intact, from `conclusion.json.problem`,
   `conclusion.json.root_cause`, and `conclusion.json.causal_chain`. Per
   `evidence-tiers.md`, this copy never upgrades anything — a
   `root_cause.tier` of `ASSUMED` in `conclusion.json` is written here as
   `ASSUMED`, not as anything stronger, regardless of how confidently the
   conclusion's prose reads.
3. **`useful_queries`, `meaningful_keywords`** — from every round's
   `hypotheses[].queries[]` entry with `outcome: "hit"`, keep only the
   ones whose finding actually reached `failure_point`,
   `causal_chain_additions`, or the hypothesis named in the accepted
   round's `checkpoint.recommendation` — a hit that only ever supported an
   `eliminated` hypothesis is not "useful" in this file's sense, even
   though it was still a real finding in this log. For each kept entry,
   look up its `ledger_ref` line in `evidence/tools.jsonl` and record
   `tool`, `table`, the `ledger_ref` itself, and a one-line `why_useful`
   naming which `failure_point`/`causal_chain`/accepted-hypothesis entry
   it produced. `meaningful_keywords` is the deduplicated union of every
   keyword named in those same ledger lines' `params`/`keywords_in`.
4. **`contradicted_docs`** — one entry per
   `runs/<run_id>/analysis/round-NN.json.contradicted_findings[]` entry
   across every round of this run, each with `chip_series` filled in from
   `input/log-pointers.json.build`/`.model` as recorded for this run (the
   build/model-to-chip-series mapping is a workspace concern per
   `notebooklm-invocation.md` — use whatever is on record, literally;
   never infer a chip series that isn't already stated there). If neither
   `build` nor `model` is set, `chip_series: "unknown"` — stated plainly,
   never guessed to fill the field. `document`, `section`, `claim`,
   `log_showed`, and `evidence_ref` are copied verbatim from the round's
   entry.
5. This skill authors no new analytical claim anywhere in this file —
   `symptom`, `why_useful` are excerpts or one-line restatements of text
   already written by an earlier skill or held in the PLM snapshot, never
   a fresh inference. There is accordingly no forbidden-pattern scan here
   the way `rca-conclude` has one: this skill introduces no prose that
   could contain a fix/patch/remediation suggestion, since it writes
   nothing beyond what upstream skills already scanned or held verbatim.

### 5. Write `knowledge/cases/<case_id>.json`

Create `.rca/knowledge/cases/` if it does not exist yet (first case ever
written in this workspace). Write the file per the schema in
`run-bundle-layout.md`, `written_at` = now. This file is never rewritten
after this — see Step 3.

### 6. Update `manifest.json` and report

Update `runs/<run_id>/manifest.json` in place: `current_step:
"rca-learn"`, `next_step: "complete"`, `updated_at` to now. Leave
`status` untouched (`"in_progress"` — there is no separate "done" status
value in this schema; `next_step: "complete"` is what marks a run as
having nothing further scheduled, distinct from `null`, which is reserved
for `status == "aborted"` — see `run-bundle-layout.md`'s note on this and
`.claude/commands/rca.md`'s dispatcher, which branches on `"complete"`
explicitly rather than treating it as `null`).

Report to the engineer: the case was written (`case_id`, path), a short
summary of what it captured (issue type, failure point, root cause, count
of useful queries/keywords, count of contradicted-doc findings if any),
and that this issue's pipeline has reached its end for this run — no
further step is scheduled, though a new run via `rca-intake` remains
available if this issue needs revisiting. Mention that a `promote`
request is available separately if this case (with others) looks like a
repeated pattern worth writing up as a playbook, but do not suggest one
unprompted or imply this skill will do so on its own initiative. HALT.

## Handling `promote`

Reached directly on any invocation whose text carries `promote`, `confirm
playbook`, or `discard playbook` — **before** Step 1 above, since none of
these need `issue_id`/`active_run` at all.

### `promote <playbook_id> from <case_id>[, case_id...]` / `promote <playbook_id> for issue_type <type>`

1. Parse `playbook_id` and either the explicit `case_id` list or the
   `issue_type` to match. If neither a case list nor an issue_type is
   present, HALT: "`promote` needs at least one existing case to draft
   from — name case_id(s) (e.g. `promote qc9205_ims_timeout from
   PLM-12345-run-01, PLM-19090-run-02`) or an issue_type to match across
   all recorded cases (e.g. `promote generic_sms_cp_error for issue_type
   sms_failure`)."
2. Resolve the source cases:
   - Explicit `case_id`s: read each `knowledge/cases/<case_id>.json`. If
     any named id does not exist, HALT naming exactly which one(s) are
     missing — never silently drop a case the engineer named.
   - `issue_type`: read every `knowledge/cases/*.json` and keep those
     whose `issue_type` matches. If none match, HALT: "No recorded cases
     for issue_type `<type>` yet — nothing to draft a playbook from."
3. Draft the playbook body (Markdown, per the schema in
   `run-bundle-layout.md`):
   - Title: a short, descriptive name for the pattern (not copied from
     any single case's `symptom` verbatim — a playbook generalizes across
     however many cases it draws from).
   - `Promoted: <now> — drafted from <case_id, case_id, ...>` — every
     source case named, so the provenance line alone lets a reader find
     the underlying data.
   - Body: the common `issue_type`(s), the shared shape of `failure_point`
     across the source cases, the shared shape of `root_cause`, and —
     stated with exactly the tiers the source cases themselves carry,
     never smoothed into uniform confidence — what a future engineer
     should check first. If any source case's `root_cause`/`failure_point`
     tier is `ASSUMED` or `CODE_UNAVAILABLE`, the draft says so plainly
     rather than presenting the pattern as more settled than its weakest
     source case. Every `contradicted_docs` entry shared by two or more
     source cases (same `document`, same `chip_series`) is written up
     explicitly — this is the accumulated "map of where vendor
     documentation cannot be trusted for a given series" issue #5 names as
     the suite's most valuable asset, and the whole reason this promotion
     path exists.
   - If only one source case was named: state this plainly in the draft
     ("drafted from a single observed instance; not yet a confirmed
     repeated pattern") rather than implying repetition that hasn't
     happened. This skill does not block promotion on a case count — that
     judgment belongs to the engineer requesting it — but it never
     misstates what "repeated" means either.
4. Write the draft to `.rca/knowledge/.drafts/<playbook_id>.md` (creating
   `.rca/knowledge/.drafts/` if needed) — git-ignored, like the rest of
   `.rca/`. If a draft already exists at this path, overwrite it (a draft,
   unlike a written case or a confirmed playbook, is exactly the mutable,
   not-yet-reviewed state).
5. Report the draft in full. State plainly: reply `confirm playbook
   <playbook_id>` to run the customer-data check and commit it to
   `knowledge/playbooks/<playbook_id>.md` (the one part of `.rca/`
   committed to git — writing it there does not itself run `git add`/`git
   commit`; that remains the engineer's own action), or `discard playbook
   <playbook_id>` to drop it without committing anything. HALT.

### `confirm playbook <playbook_id>`

1. If no draft exists at `.rca/knowledge/.drafts/<playbook_id>.md`, HALT:
   "No standing draft named `<playbook_id>` — run `promote` first."
2. If `knowledge/playbooks/<playbook_id>.md` already exists: HALT: "A
   playbook named `<playbook_id>` already exists — promoted playbooks are
   never overwritten from here. Pick a different id, or edit
   `knowledge/playbooks/<playbook_id>.md` directly; it is a plain,
   engineer-owned Markdown file once written, not a schema this skill
   guards after the fact."
3. **Run the customer-data check** against the draft's full content
   (below). If it finds anything: **do not write anything**. HALT, stating
   exactly which pattern matched and where in the draft, and that the
   draft remains standing at `.rca/knowledge/.drafts/<playbook_id>.md` for
   the engineer to edit and re-confirm — never auto-redacted or
   silently trimmed by this skill.
4. If clean: create `.rca/knowledge/playbooks/` if it does not exist yet,
   write the draft's content verbatim to
   `.rca/knowledge/playbooks/<playbook_id>.md`, and delete the file at
   `.rca/knowledge/.drafts/<playbook_id>.md` (its job is done — the
   reviewed copy now lives at the tracked path). Report: the playbook is
   written, its path is no longer excluded by `.gitignore`, and adding and
   committing it to git remains a separate, explicit action for the
   engineer to take — this skill never runs `git add`/`git commit` itself.
   HALT.

### `discard playbook <playbook_id>`

Delete `.rca/knowledge/.drafts/<playbook_id>.md` if it exists (a no-op,
reported as such, if it does not). Never touches
`knowledge/playbooks/<playbook_id>.md` even if a file of the same name
already exists there — discarding a draft can never remove an
already-confirmed playbook. Report the draft is discarded. HALT.

### The customer-data check

Applied to a playbook draft's full content before Step "confirm playbook"
above may write it anywhere git will track. Two layers, both required —
either alone is not enough:

**Mechanical patterns** (any one match blocks the write outright):
- A run of 10 or more consecutive digits anywhere outside the required
  provenance line's `case_id`s (catches an IMSI, IMEI, MSISDN, or ICCID
  copied in rather than described).
- An email-address-shaped string.
- A `PLM-<digits>` issue reference anywhere outside the provenance line —
  a playbook describes a pattern, not a pointer back to one customer's
  ticket; `case_id`s in "Promoted: ... drafted from ..." are the one
  named exception, since a case id identifies a case record, not a
  customer.
- A block of two or more lines that reproduces literal log-line shape
  (timestamped, pipe- or bracket-delimited fields) rather than a
  plain-English description of what happened — a playbook says what to
  check, it does not carry the log itself.

**Judgment read**: does anything else in the draft read like a
subscriber's phone number, a device serial, an account or subscriber
identifier, or a person's name carried in from the PLM issue? Flag and
refuse if unsure — a false positive costs a rephrase and a re-confirm; a
false negative commits customer data to git, which is exactly what
`.gitignore`'s carve-out exists to prevent for everything except this one
reviewed, engineer-confirmed path.

## What this skill does not do

- ❌ Never upgrades a tier when copying it into a case record, and never
  lets a later `rca-analyze` round upgrade one either by reading it back —
  per `_shared/evidence-tiers.md`'s **Tier immutability** rule and
  `_shared/keyword-provenance.md`'s "**Cases and playbooks are hints,
  never evidence**"
  (`_shared/keyword-provenance.md#cases-and-playbooks-are-hints-never-evidence`).
