---
name: notebooklm-deep-dive
description: Iteratively mine one NotebookLM notebook across 10 fixed rounds where the notebook proposes each next query. Use when the user wants a deep, logged, multi-round Q&A dive into a NotebookLM notebook — e.g. mapping RCA v6 internals, or benchmarking NotebookLM answer quality. Every query/response is saved to output-notebooklm/<task>/ for later synthesis. Triggers: "deep dive notebooklm", "khai thác notebook", "đào sâu notebooklm", "map RCA v6 from notebook".
---

# NotebookLM Deep Dive

Run a fixed 10-round research loop against ONE NotebookLM notebook. Each round the
notebook answers in a strict template and proposes the single best next query; you
lightly guard that query and feed it to the next round. Everything is logged.

## Prerequisites
- The `notebooklm` skill must be authenticated (`python "C:/Users/Win 11/.claude/skills/notebooklm/scripts/run.py" auth_manager.py setup` if not).
- Default notebook (RCA v6): `f5e859be-eb94-43be-bc12-bf9453bf7099`.

## Inputs to collect from the user
- **Goal** (constant every round), e.g. "Map RCA v6: inputs, outputs, technical functions of each phase."
- **Seed question** (round 1), e.g. "What is Phase 0 of RCA v6 — its inputs, outputs, and technical functions?"
- **Notebook ID** (default the RCA v6 one).

## Procedure

Let `SCRIPTS = .claude/skills/notebooklm-deep-dive/scripts/loop.py`.

1. **Timestamp:** get `TS` from the shell: `date +%Y%m%d-%H%M%S`.
2. **Init:**
   `python "SCRIPTS" init --goal "<goal>" --seed "<seed>" --notebook-id "<id>" --timestamp "<TS>"`
   Record the printed `TASK_DIR`. Set `question = <seed>`.
3. **For round N = 1..10:**
   a. `python "SCRIPTS" ask --task-dir "TASK_DIR" --round N --question "<question>"`
      → read the JSON printed on stdout (fields: `answer, key_facts, sources, coverage, gaps, next_query, round`).
      - **Call failure:** if this command exits non-zero (NotebookLMError — e.g. auth dropped or timed out),
        STOP the whole run immediately. Do not run further rounds. Report to the user which round failed
        and why (the error message names the returncode and stdout/stderr tail).
      - **Template not honored:** if the printed JSON has BOTH `coverage` and `next_query` empty (NotebookLM
        ignored the output template), re-run this SAME round's `ask` ONCE, suffixing the question with a short
        format reminder: `" — Please answer using the exact template with all 6 fields: ANSWER, KEY_FACTS,
        SOURCES, COVERAGE, GAPS, BEST_NEXT_QUERY."` If the retry is still empty on both fields, record
        `coverage = NOT_FOUND` for the quality verdict and proceed to step b with whatever `next_query` you
        have (empty is fine — the light-guard in step b will derive a fallback).
   b. **Light-guard `next_query`** → produce `final_next` + `source`:
      - `next_query` empty → derive a query from `gaps` toward the goal; `source = claude-fallback`.
      - `next_query` duplicates any earlier round's question → rephrase to an unasked angle; `source = claude-dedup`.
      - `next_query` clearly off the goal → minimally re-aim at the goal; `source = claude-reaim`.
      - otherwise → `final_next = next_query`; `source = notebooklm`.
      (On round 10 you may set `final_next = ""` and `source = notebooklm` — it won't be used.)
   c. `python "SCRIPTS" trace --task-dir "TASK_DIR" --round N --query "<question>" --coverage "<coverage>" --next-query "<final_next>" --source "<source>"`
   d. Set `question = final_next` for the next round.
   Never stop early — run all 10 rounds even if `coverage` is FULL.
4. **Synthesize** `TASK_DIR/summary.md` yourself (use the Write tool):
   - **Findings toward the goal** — deduped `KEY_FACTS` across rounds.
   - **NotebookLM quality verdict** — COVERAGE distribution (# FULL / PARTIAL / NOT_FOUND from `trace.jsonl`), guard-edit counts by `source`, whether the query chain converged on the goal or wandered, and notable unanswered gaps.
5. Tell the user where the artifacts are (`TASK_DIR`) and give a 3-5 line recap.

## Notes
- Each `ask` opens a fresh, memory-less NotebookLM session; continuity rides entirely in the `[ALREADY ASKED]` block the script builds from `trace.jsonl`. This is expected.
- `ask` can take up to ~2 min/round (browser automation). 10 rounds ≈ up to 20 min.
- Do not edit `trace.jsonl` by hand — it is the machine-readable spine for later analysis (evaluation framework B).
