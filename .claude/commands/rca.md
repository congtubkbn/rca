---
description: Run whichever single next step is due for a PLM-issue RCA run, then halt.
argument-hint: [PLM-issue-id | (blank to resume)]
---

# /rca — PLM-issue pipeline dispatcher

This is the entry point for the PLM-issue pipeline (`rca-intake →
rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`, GitHub issue #5).
It is a **dispatcher, not a script**: it reads the run bundle on disk
(`.claude/skills/_shared/run-bundle-layout.md`), runs exactly one next
step, and halts. It never chains steps in one invocation, and never
guesses what step comes next from conversation context — always re-derive
it from `manifest.json.next_step`.

This command is independent of `.clinerules/workflows/rca.md`, which
remains the older v6 3GPP fault-tree suite's Cline dispatcher, unchanged
by this suite (see root `CLAUDE.md`). The two share the `/rca` name by
coincidence of each suite choosing the obvious one; they read and write
entirely different files and never interact.

Invoking any skill in this suite directly (e.g. asking for `rca-intake`
by name) always works and always wins over this dispatcher — it is never
required to go through `/rca`.

Arguments: `$ARGUMENTS`

## Steps

<explicit_instructions>

### Step 1 — Is this a fresh start or a resume?

1. If `$ARGUMENTS` names a PLM issue ID (e.g. `PLM-12345`) AND
   `.rca/issues/<that_id>/` does **not** exist on disk: this is a fresh
   start. Go to Step 2A.
2. If `$ARGUMENTS` names a PLM issue ID AND `.rca/issues/<that_id>/`
   **does** exist: this is a resume for that specific issue. Go to Step 2B.
3. If `$ARGUMENTS` is blank: this command cannot know which issue to
   resume without being told, and must not guess from conversation
   history or by picking "the most recent" `.rca/issues/*` directory
   silently. HALT and ask: "Which PLM issue? (`/rca PLM-12345`)"

### Step 2A — Fresh start

Invoke the `rca-intake` skill with `issue_id` set to the given ID, passing
along any other inputs the engineer already stated in this conversation
(`label`, `duckdb_path`, `tables`, `time_range`, `build`, `model`,
`source_checkout` — see `.claude/skills/rca-intake/SKILL.md`'s Inputs
section). Let `rca-intake` run to completion and report; do not invoke
anything else afterward. HALT.

### Step 2B — Resume

1. Read `.rca/issues/<issue_id>/issue.json`.
2. Determine the target run: `active_run` if set, otherwise the
   highest-numbered entry in `runs`.
3. Read that run's `runs/<run_id>/manifest.json`.
4. Read `manifest.json.next_step`.
   - If `next_step` is `"rca-intake"` (an engineer explicitly asked to
     re-intake this issue with new information): invoke `rca-intake`
     exactly as in Step 2A, with this issue's ID. HALT.
   - If `next_step` names any other skill in this suite
     (`rca-scope`, `rca-analyze`, `rca-conclude`, `rca-learn`) and that
     skill exists in `.claude/skills/`: invoke it, pointing it at
     `runs/<run_id>/`. HALT.
   - If `next_step` names a skill that does **not** exist in
     `.claude/skills/` yet: state plainly which step is next and that it
     is not implemented in this suite yet (link the tracking issue if
     known, e.g. "next step is `rca-scope`, tracked as a sub-issue of
     GitHub issue #5, not yet built"). Do **not** attempt to improvise
     that step's behavior, and do not fall back to the older v6 suite.
     HALT.

</explicit_instructions>
