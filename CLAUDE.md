# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Not a software project with a build/test/lint cycle — there is no source code, no
package manifest, no compiler. This repo **is** the specification/config for an
agentic pipeline: a suite of Markdown "skills" for **Claude Code** that drives
root-cause analysis on PLM issues — the product lifecycle management tracker
engineers file device-failure reports in. Editing this repo means editing
`SKILL.md` files and shared reference docs in prose/YAML-frontmatter/JSON-schema
form — there is nothing to `npm install`, build, or unit-test.

Two dependencies referenced throughout the skills are **not present in this
repo** and must not be hunted for locally — both are workspace dependencies,
expected to already be configured in the environment a skill runs in:
- The **PLM MCP connection** `rca-intake` calls to fetch an issue's title,
  description, and tester reproduction steps.
- A **DuckDB-backed log-query capability** and a **tree-sitter code-graph
  capability** that `rca-scope`/`rca-analyze` call — see
  `.claude/skills/_shared/log-query-invocation.md` and
  `code-graph-invocation.md` for the exact call shape.

## Repository layout

```
.claude/
  commands/rca.md              # /rca — dispatcher: runs whichever single next step is due, then halts
  skills/
    rca-intake/                # fetch a PLM issue, open (or add a run to) its .rca/issues/<issue_id>/ bundle
    rca-scope/                 # classify the issue, settle a failure time, narrow window/tables/layers → scope.json
    rca-analyze/                # hypothesis-driven analysis, round by round, with the dig/redirect/accept/abort loop
    rca-conclude/               # synthesize the accepted analysis into conclusion.json + CONCLUSION.md
    rca-learn/                  # write a knowledge/cases/ record; separate engineer-gated playbook promotion
    _shared/                    # cross-skill contracts, read these before editing any skill
      run-bundle-layout.md            # the .rca/issues/ directory layout and per-section write owners — READ FIRST
      contract-block-format.md        # the `contract:` block every skill declares
      evidence-tiers.md               # the eight evidence tiers
      tool-ledger-format.md           # the evidence/tools.jsonl line format
      log-query-invocation.md         # how rca-scope/rca-analyze call the log-query capability
      code-graph-invocation.md        # how rca-analyze calls the code-graph capability
      notebooklm-invocation.md        # how rca-analyze calls NotebookLM, plus this suite's citation requirement
      keyword-provenance.md           # HARD/SOFT/FORBIDDEN source ranking; "guessing may ask, never answer"
      resolution-ladder.md            # the order rca-analyze tries to resolve an open question
      checkpoint-format.md            # the presentation rca-analyze ends every round with
docs/agents/
  issue-tracker.md              # issues tracked on GitHub (congtubkbn/rca), via `gh`
  triage-labels.md               # the five canonical triage labels
  domain.md                      # how skills should consume this repo's CONTEXT.md / ADRs
```

When editing a skill, the shared files in `.claude/skills/_shared/` are the
contract every skill must honor — read the relevant one(s) before changing a
skill's behavior, since changing e.g. the run-bundle layout in one skill
without updating `_shared/run-bundle-layout.md` (and every other skill that
reads/writes that section) will break the pipeline.

## Architecture

### Pipeline shape: a per-run bundle on disk, no orchestrator

`rca-intake → rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`, each
skill owning one section of a run bundle under `.rca/issues/<issue_id>/`,
each independently invocable. There is **no orchestrator skill** — `/rca`
(`.claude/commands/rca.md`) only dispatches the single next step, by reading
`manifest.json.next_step`, and halts. It never chains steps in one
invocation and never guesses what step comes next from conversation
context. Invoking any skill in the suite directly (e.g. asking for
`rca-scope` by name) always works and always wins over the dispatcher — it
is never required to go through `/rca`.

```
/rca PLM-12345                               (fresh start)
  → rca-intake: fetch PLM issue, open .rca/issues/PLM-12345/runs/run-01/
/rca                                          (resume)
  → rca-scope: classify issue, settle failure time, narrow window/tables/layers → scope.json
/rca                                          (resume)
  → rca-analyze round 1: locate failure point, generate/test hypotheses → checkpoint
/rca dig into H2                              (engineer replies to checkpoint)
  → rca-analyze round 2: same loop, seeded from round 1's checkpoint
/rca accept                                   (engineer accepts the analysis)
  → rca-conclude: synthesize conclusion.json + CONCLUSION.md → draft presented
/rca accept                                   (engineer confirms the conclusion)
  → sets issue.json.active_run, hands off to rca-learn
  → rca-learn: writes knowledge/cases/<case_id>.json
```

A separate, explicit `promote` action (handled by `rca-learn`) drafts and,
after a customer-data check, commits reviewed prose to
`.rca/knowledge/playbooks/` — the one part of `.rca/` tracked in git.

### The run bundle is the single source of truth

Every skill reads and writes files under one run bundle,
`.rca/issues/<issue_id>/runs/<run_id>/` (full schema in
`_shared/run-bundle-layout.md`). No skill holds state in conversation memory
alone — if it's not written to disk, it doesn't count. Skills **slice-read**
only the sections/files they need (e.g. a skill that needs a prior run's
conclusion reads that run's `conclusion.json` directly, never the whole
issue tree). `.rca/` is git-ignored from the first commit — field logs,
subscriber identifiers, and NDA material must never reach a remote; the sole
carve-out is `.rca/knowledge/playbooks/`, promoted and reviewed before it is
ever committed.

### Hard invariants

1. **Keyword provenance**: every keyword used in a query must trace back to
   a prior tool call or verbatim engineer/PLM/case-hint input — never from
   the model's pretrained knowledge. See `_shared/keyword-provenance.md`'s
   HARD/SOFT/FORBIDDEN ranking and its "guessing may ask, never answer"
   rule — a query that misses does not get to claim a finding either way.
2. **Evidence tiers never improve with time**: a finding copied forward
   into a later file (a conclusion, a case record) keeps the tier it was
   first recorded at — see `_shared/evidence-tiers.md`.
3. **Hard termination, no fix generation**: the pipeline's deliverable is a
   verified root cause, causal chain, and reproduction scenario — never a
   fix, patch, config change, test case, or "next step". `rca-conclude` runs
   a forbidden-pattern string scan over every authored string before
   writing `conclusion.json`, with a named exception for verbatim-quoted
   external (tester/PLM) text.
4. **Engineer gates are mandatory and never bypassed on their own**: every
   `rca-analyze` round ends at a checkpoint; advancing past the round budget
   requires an explicit override with a recorded rationale;
   `rca-conclude`'s draft is confirmed only by an explicit engineer
   `accept`; `rca-learn`'s playbook promotion is a separate, explicit
   `promote`/`confirm playbook` action. `manifest.json.autonomy`
   (`review_all | auto_until_blocked | auto`) controls how much
   `rca-analyze` continues on its own between checkpoints, never whether a
   gate exists at all.
5. **Round budget** defaults to 5 (`manifest.json.round_budget`); a round
   written at the budget is forced to recommend acceptance, though the
   engineer can still override with a stated rationale.

### Append-only, immutable-once-written files

`analysis/round-NN.json` files are never overwritten once written — round
N+1 must be provable against round N's actual recorded state. `conclusion.json`
is mutable only up to `confirmed: true`, after which it is immutable —
analyzing further means starting a new run via `rca-intake`, never rewriting
an existing run. `knowledge/cases/<case_id>.json` is written once and never
rewritten, for the same reason. See `_shared/run-bundle-layout.md`'s
"Per-Section Write Owners" table for the full write-ownership map.

## Working in this repo

- There is no build, lint, or test command — validate changes by reading them
  against `_shared/run-bundle-layout.md` (the run-bundle shape), the
  invariants above, and consistency with sibling skills that read/write the
  same files (see the "Per-Section Write Owners" table in
  `_shared/run-bundle-layout.md`).
- Frontmatter `description:` in each `SKILL.md` is what Claude Code's skill
  triggering matches against — keep it specific about when the skill fires
  and when it must NOT (each skill lists explicit anti-triggers, mostly
  pointing engineers at the correct pipeline skill for a given ask).

## Agent skills

### Issue tracker

Issues tracked on GitHub (congtubkbn/rca), via `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five canonical labels (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.
