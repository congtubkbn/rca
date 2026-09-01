# Resolution Ladder

When `rca-analyze` (issue #8) needs to resolve an open question — where is
the failure point, why did a step fail, what does a candidate hypothesis
predict — it works down this ladder, degrading gracefully rather than
blocking:

```
spec (NotebookLM)  →  live log (DuckDB)  →  source (code graph, when not a lib)
   →  vendor documentation (NotebookLM)  →  ask the engineer  →  prior cases
```

Each rung is tried in order for a given question; a rung that resolves the
question stops the ladder for it. A rung that cannot resolve it (no
answer, no citation, no source available) is skipped and stated, never
silently omitted from the round's record.

## The rungs

1. **Spec (NotebookLM, 3GPP corpus)** — the normative baseline: what does
   the procedure look like when it works, what messages and IEs are
   involved. SOFT provenance, requires a citation (document + section).
   Used to generate hypotheses and candidate keywords — never to answer
   directly. See `keyword-provenance.md`.
2. **Live log (DuckDB, via the log-query capability)** — HARD provenance.
   The load-bearing rung: a claim only becomes `VERIFIED_LOG` here, and
   this is where a rung-1 or rung-4 claim gets checked. See
   `log-query-invocation.md`.
3. **Source (tree-sitter code graph), when the relevant module has
   source** — HARD provenance, `CODE_BOUND`. When the module ships as a
   lib, this rung reports `CODE_UNAVAILABLE` for that branch and the
   ladder continues at the next rung for whatever remains unresolved — a
   missing source tree caps depth, it does not stop the round.
4. **Vendor documentation (NotebookLM, Qualcomm/MTK corpus)** —
   chip-series-specific detail beyond what the 3GPP spec states. SOFT
   provenance, same citation requirement and same never-answers-directly
   rule as rung 1. Tried after the log and code rungs specifically because
   a vendor-doc claim is the one most likely to be wrong for a given chip
   series (issue #5) — checking the log and code first means there is
   already something concrete to check the document's claim against,
   rather than the other way around.
5. **Ask the engineer** — when no rung above resolves a question this
   round needs answered, the round does not fabricate an answer to keep
   moving. It states the open question plainly in the checkpoint's
   evidence gaps (see `checkpoint-format.md`). This rung is also, per
   issue #9, one of the four never-bypassable gates: when the round's
   *recommended* direction itself depends on a question this rung had to
   reach, `rca-analyze` always halts here regardless of
   `manifest.json.autonomy`. The engineer's answer, when it comes, is
   formalized as a `redirect <information>` reply, recorded at
   `ENGINEER_PROVIDED` and carried into the next round
   (`rca-analyze/SKILL.md`'s Step 3/6).
6. **Prior cases and playbooks** (`.rca/knowledge/cases/` and
   `.rca/knowledge/playbooks/`, written by `rca-learn`, issue #11) — a case
   or playbook whose `issue_type` matches this run's
   `scope.json.classification.issue_type` (or, once one exists, a
   playbook naming this generic category) is read for what it suggests: a
   candidate hypothesis statement, a keyword worth trying, a table worth
   looking in. It is a **hint that suggests where to look, never evidence
   for a conclusion** (issue #5, "cases suggest, they never prove") — a
   case hit contributes nothing to `causal_chain_additions`,
   `failure_point`, or a hypothesis's `queries[]` on its own; whatever it
   suggests still has to survive a fresh query against *this* issue's own
   log or code, exactly like a FORBIDDEN-origin guess can ask but never
   answer (see `keyword-provenance.md`). Every case/playbook this round
   actually reads is recorded in that round's `case_hints[]`
   (`run-bundle-layout.md`), stating what it suggested and, when used,
   which hypothesis it seeded — never silently absorbed into a hypothesis
   with no trace of where the idea came from. A finding read back from a
   case retains exactly the tier it was recorded at when the case was
   written; reading it again, or reading it from several cases at once,
   never promotes it (`evidence-tiers.md`'s "a tier never improves with
   the passage of time" applies here precisely because a case is the one
   thing designed to be read back repeatedly). No matching case or
   playbook is a normal, common outcome for this rung, stated as such —
   not an error, and not a reason to widen the search into cases from an
   unrelated `issue_type`.

## Why this order, not spec-then-fault-tree

The v6 suite (`.cline/skills/`) built a fault-tree skeleton from spec
before looking at any log data, and bound code at that point. This ladder
inverts that deliberately (issue #5, "Explicit departures from v6"):
hypotheses in `rca-analyze` are generated against an **observed** failure
point (rung 2, or a rung-1-guided query that hit), not derived from a
procedure diagram before anyone has looked at the log — spec-before-log is
exactly where an LLM invents most freely, and code-binding-as-precondition
is exactly where source is least likely to exist.
