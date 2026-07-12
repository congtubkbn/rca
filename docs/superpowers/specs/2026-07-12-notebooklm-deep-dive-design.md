# Design: `notebooklm-deep-dive` skill

**Date:** 2026-07-12
**Status:** Approved (brainstorming) — ready for implementation plan
**Author:** the.thoi + Claude

## Context

RCA v6 is a root-cause-analysis system for protocol issues (call drop, call fail,
emergency call, no service) on Samsung models using Qualcomm / LSI / MTK chipsets,
driven by UE logs. Its full code + design live in a Google NotebookLM notebook
(ID `f5e859be-eb94-43be-bc12-bf9453bf7099`), NOT in this repo.

The larger goal is a **two-part program**:

- **(A) Extraction mechanism** — a reusable deep-research loop over NotebookLM.
  *This spec.*
- **(B) RCA v6 evaluation framework** — dimensions + metrics (did RCA finish the
  analysis, %-contribution to the engineer, what it contributed, how to visualize,
  how to compare versions). *Deferred to a later spec; consumes (A)'s output.*

Sequencing decided: build (A) first, use it to map RCA v6 internals (inputs, outputs,
technical functions), THEN co-design (B).

Prior art in the environment: a general `deep-research` skill (web-oriented) and a
`notebooklm` skill (programmatic notebook query). (A) marries the loop idea of the
former with the notebook backend of the latter.

## Goal of (A)

Given a seed question + a goal, iteratively mine ONE NotebookLM notebook across a
**fixed 10 rounds**, where **NotebookLM itself proposes the next query each round**.
Log every query/response so the data can later be synthesized and so the exercise
doubles as a **benchmark of NotebookLM's output quality**.

Non-goals (explicitly out of scope, deferred to B): scoring RCA v6, %-contribution
metric, version comparison, visualization dashboards.

## Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| Loop control | NotebookLM returns a `BEST_NEXT_QUERY`; that becomes the next round's question | Tests NotebookLM's ability to steer its own deepening |
| Early exit | **None** — always run all 10 rounds | Goal is to observe NotebookLM quality across a full chain, not to stop when "done" |
| Next-query handling | **Light guard** — send verbatim, but if empty / duplicate of a prior query / clearly off-goal, Claude minimally fixes it and logs the edit | Keeps chain productive without fully losing the "pure NotebookLM" signal |
| Query language | **English (technical)** | Notebook sources are English/3GPP/chipset terminology; matches retrieval |
| Deliverables per round | structured input + structured output templates | User's request: define input + output templates, response then carries enough info |

## Input template (sent to NotebookLM each round)

```
[TASK GOAL]     {overall goal — constant every round}
[ROUND]         {n}/10
[QUESTION]      {round 1 = seed; rounds 2-10 = prev BEST_NEXT_QUERY (post-guard)}
[ALREADY ASKED] {bullet list of prior questions, to avoid repetition}

Answer ONLY from notebook sources. Cite every claim. Then fill the output
template below exactly, with every field present.
```

## Output template (NotebookLM must return this shape)

```
ANSWER:          {direct technical answer}
KEY_FACTS:       {bullets — inputs / outputs / functions / data structures}
SOURCES:         {source names + cited snippets}
COVERAGE:        {FULL | PARTIAL | NOT_FOUND}
GAPS:            {what the notebook could NOT answer}
BEST_NEXT_QUERY: {ONE single most valuable follow-up toward TASK GOAL}
```

`COVERAGE` + `GAPS` are the deliberate **NotebookLM quality signal** consumed by (B).

## Per-round flow

1. Render input template (goal + round# + question + already-asked).
2. Send to NotebookLM via the `notebooklm` skill's query/chat call (notebook ID = config).
3. Receive response; if it does not conform to the output template, re-ask once
   with a format reminder before recording.
4. Write `round-NN_query.md` and `round-NN_response.md`; append one line to `trace.jsonl`.
5. Extract `BEST_NEXT_QUERY` → **light guard**:
   - empty → Claude derives a gap-filling query from GAPS; log `next_query_source = "claude-fallback"`.
   - duplicate of a prior question → Claude rephrases to an unasked angle; log `next_query_source = "claude-dedup"`.
   - clearly off-goal → Claude minimally re-aims at TASK GOAL; log `next_query_source = "claude-reaim"`.
   - otherwise → verbatim; log `next_query_source = "notebooklm"`.
6. Repeat until round 10.

## Synthesis (after round 10)

Write `summary.md`:
- Consolidated findings toward the goal (deduped KEY_FACTS).
- **NotebookLM quality verdict:** COVERAGE distribution (# FULL / PARTIAL / NOT_FOUND),
  # of guard edits by type, did the query chain converge on the goal or wander,
  notable gaps that stayed unanswered.

## Artifact layout

```
output-notebooklm/
  <YYYYMMDD-HHMMSS>_<slug>/
    00-task.md          # goal, notebook ID, config (max_rounds, language), start time
    round-01_query.md
    round-01_response.md
    ...                 # through round-10
    trace.jsonl         # 1 line/round: {round, query, coverage, next_query, next_query_source, ts}
    summary.md
```

`trace.jsonl` is the machine-readable spine that (B) will consume for analysis/visualization.

## Configuration

| Key | Default | Notes |
|---|---|---|
| `notebook_id` | `f5e859be-eb94-43be-bc12-bf9453bf7099` | RCA v6 notebook |
| `max_rounds` | `10` | Fixed-length chain |
| `language` | `en` | Technical English queries |
| output root | `output-notebooklm/` (workspace) | one subfolder per task |

## Dependencies

- `notebooklm` skill — supplies the notebook query/chat call. **Implementation plan
  must confirm the exact invocation + how a text answer is returned** before building
  the loop.
- Runtime shell for the task timestamp (scripts cannot call the clock directly).

## Skill location

`e:\the.thoi\Project\rca-v6\.claude\skills\notebooklm-deep-dive\` — kept with the project.

## First real run (post-build validation)

Seed: `"What is Phase 0 of RCA v6 — its inputs, outputs, and technical functions?"`
Goal: `"Map RCA v6: inputs, outputs, and technical functions of each phase."`
Confirms the loop end-to-end and begins mapping v6 for (B).

## Open questions for the plan

1. Exact `notebooklm` skill call signature for a single Q&A against a notebook.
2. Whether the skill should be a shell/Python script the agent runs, or an
   agent-driven procedure with tool calls (affects how templates are rendered + logs written).
