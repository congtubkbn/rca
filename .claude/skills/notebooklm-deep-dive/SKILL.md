---
name: notebooklm-deep-dive
description: Iteratively mine one NotebookLM notebook across 10 fixed rounds. NotebookLM answers each question in grounded prose; Claude structures the answer and picks the next question toward the goal. Use when the user wants a deep, logged, multi-round Q&A dive into a NotebookLM notebook — e.g. mapping RCA v6 internals, or benchmarking NotebookLM answer quality. Every query/response is saved to output-notebooklm/<task>/ for later synthesis. Triggers: "deep dive notebooklm", "khai thác notebook", "đào sâu notebooklm", "map RCA v6 from notebook".
---

# NotebookLM Deep Dive

Run a fixed 10-round research loop against ONE NotebookLM notebook. Each round the
notebook returns a grounded prose answer (it will NOT self-format or propose a next
query in cold automated sessions — verified). So **you** (Claude) do the structuring:
read each answer, judge how well the notebook covered the question, extract the key
facts, and choose the next question toward the goal. Everything is logged.

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
      → stdout is JSON `{"round": N, "answer": "<raw prose answer from the notebook>"}`.
      Keep `question` in a variable — you pass it verbatim to `trace` in step c.
      - **Call failure:** if this command exits non-zero (NotebookLMError — e.g. auth dropped or timed out),
        STOP the whole run immediately. Do not run further rounds. Report which round failed and why
        (the error message names the returncode and stdout/stderr tail).
      - **Empty answer:** if `answer` is blank or clearly a non-answer ("I don't have information…"),
        treat this round's `coverage` as `NOT_FOUND` in step b.
   b. **Structure the answer** (this is your judgment, from the `answer` text):
      - `coverage` ∈ {`FULL`, `PARTIAL`, `NOT_FOUND`} — how completely the notebook answered THIS question.
      - Note the `key_facts` (inputs / outputs / functions / data structures) and any `gaps` — you carry
        these into the final synthesis; they are not passed to the script.
      - `next_query` — the single most valuable next question toward the GOAL. Prefer filling a gap the
        answer exposed. It must NOT duplicate any earlier round's question (the notebook is memory-less;
        the `[ALREADY ASKED]` block the script builds from `trace.jsonl` reminds it, but you must still
        pick a genuinely new angle). On round 10, `next_query` may be empty.
   c. `python "SCRIPTS" trace --task-dir "TASK_DIR" --round N --query "<question>" --coverage "<coverage>" --next-query "<next_query>" --source "claude"`
      (Quote the `--question`/`--next-query` values carefully — they can contain punctuation.)
   d. Set `question = <next_query>` for the next round.
   Never stop early — run all 10 rounds even if `coverage` is FULL.
4. **Synthesize** `TASK_DIR/summary.md` yourself (use the Write tool):
   - **Findings toward the goal** — deduped key facts across all rounds (read the `round-NN_response.md` files).
   - **NotebookLM quality verdict** — COVERAGE distribution (# FULL / PARTIAL / NOT_FOUND from `trace.jsonl`),
     whether the question chain converged on the goal or wandered, and notable unanswered gaps. This is the
     answer-quality benchmark for NotebookLM on this notebook.
5. Tell the user where the artifacts are (`TASK_DIR`) and give a 3-5 line recap.

## Notes
- **Why Claude structures, not NotebookLM:** cold automated NotebookLM sessions return excellent grounded
  prose but ignore strict output-templating and won't propose their own next query. So the script sends a
  plain context+question prompt and captures the raw answer; the 6 structured fields and the next question
  are your job. This benchmarks NotebookLM's *answer* quality (its strength), which is what feeds framework B.
- Each `ask` opens a fresh, memory-less NotebookLM session; continuity rides in the `[ALREADY ASKED]` block
  the script builds from `trace.jsonl`. Expected.
- `ask` can take up to ~2 min/round (browser automation). 10 rounds ≈ up to 20 min.
- `trace.jsonl` schema per line: `{round, query, coverage, next_query, next_query_source, ts}` (`--source`
  fills `next_query_source`; use `"claude"`). Do not edit it by hand — it is the machine-readable spine for
  the evaluation framework (part B).
