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
   evidence gaps (see `checkpoint-format.md`). Issue #8 (this ticket) ends
   every round at that checkpoint regardless; issue #9 (not yet built)
   formalizes the engineer's answer as a `redirect` carrying
   `ENGINEER_PROVIDED` evidence into the next round.
6. **Prior cases** (`.rca/knowledge/cases/`, written by `rca-learn`) — not
   yet available; that skill is issue #11, not built. A round that would
   have consulted this rung states so instead of skipping it silently
   (the same pattern `/rca` uses for a `next_step` naming a skill that
   does not exist yet). Once built, a case is a **hint that suggests where
   to look, never evidence for a conclusion** (issue #5, "cases suggest,
   they never prove") — this file is updated when issue #11 lands, but
   that constraint is already fixed by the parent spec and won't change.

## Why this order, not spec-then-fault-tree

The v6 suite (`.cline/skills/`) built a fault-tree skeleton from spec
before looking at any log data, and bound code at that point. This ladder
inverts that deliberately (issue #5, "Explicit departures from v6"):
hypotheses in `rca-analyze` are generated against an **observed** failure
point (rung 2, or a rung-1-guided query that hit), not derived from a
procedure diagram before anyone has looked at the log — spec-before-log is
exactly where an LLM invents most freely, and code-binding-as-precondition
is exactly where source is least likely to exist.
