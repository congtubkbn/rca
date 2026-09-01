# Evidence Tiers

Every claim the PLM-issue pipeline (`rca-intake → rca-scope → rca-analyze
⟲ → rca-conclude → rca-learn`, GitHub issue #5) records carries one of
these eight tiers, stating how the claim is known. A tier is not a
formality — it is what lets a later reader (or a later run) tell a
measured fact from an assumption without re-deriving it.

| Tier | Meaning |
|---|---|
| `VERIFIED_LOG` | Observed directly in the log of the run currently being analysed. |
| `CODE_BOUND` | Bound to source, for the build that produced this log. |
| `SPEC_INFERRED` | Inferred from a 3GPP spec or vendor document; not yet seen in the log. |
| `TESTER_REPORTED` | Stated by the tester in the PLM issue; unverified. |
| `ENGINEER_PROVIDED` | Asserted by the analysing engineer; authoritative as a premise, not pipeline-verified. |
| `ASSUMED` | Assumed by the agent; no evidence. |
| `CONTRADICTED` | A source (spec, vendor doc, or a prior case) claims it; the log shows otherwise. |
| `CODE_UNAVAILABLE` | Not verifiable against code because the module ships as a lib. |

## Rules

- **A tier never improves with the passage of time.** A finding carried
  forward from an earlier run is still whatever tier it was written at.
  Reaching `VERIFIED_LOG` requires verification against the log of the
  issue currently being analysed — never inherited from a prior run or a
  prior case record. This is the mechanism that stops an assumption from
  being laundered into a verified finding by repetition (see the parent
  spec's "evidence laundering" note, issue #5).
- **Guessing may ask, never answer.** A tier is assigned to what a source
  actually said or showed — never to what a query merely failed to
  contradict. A failed guess teaches nothing and gets no tier at all,
  positive or negative.
- **`TESTER_REPORTED` is a claim, not a fact.** It is recorded so the
  pipeline can reason about what was reported without anchoring on it as
  ground truth. `rca-intake` is the only skill that writes this tier — it
  tags the PLM issue's tester-reported reproduction steps as they are
  fetched, before any verification has had a chance to happen.
- **`ENGINEER_PROVIDED` may override an agent inference when the engineer
  explicitly directs it**, but a conclusion resting on one is always
  labelled as resting on an engineer premise — never presented as if it
  were pipeline-verified.

## Scope note for this ticket (issue #6)

`rca-intake` only ever writes `TESTER_REPORTED` (on the tester's
reproduction steps) and, when the engineer supplies input at invocation
time, `ENGINEER_PROVIDED` (on anything they assert directly, e.g. a known
build/model or source commit). The other six tiers belong to skills that
scope, analyse, and conclude — `rca-scope`, `rca-analyze`, `rca-conclude`
— which do not exist yet. This file documents the whole vocabulary now,
because the tier an existing skill writes must stay meaningful once the
rest of the suite is built; it does not imply those skills' behavior.

The keyword-provenance ladder (HARD / SOFT / FORBIDDEN — which *sources*
may support a conclusion) is a related but separate concept, owned by
whichever ticket introduces `rca-analyze`. It is not documented here.
