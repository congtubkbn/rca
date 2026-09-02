# Evidence Tiers

Every claim the PLM-issue pipeline (`rca-intake → rca-scope → rca-analyze
⟲ → rca-conclude → rca-learn`) records carries one of
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
| `CONTRADICTED` | A source (spec, vendor doc, a prior case, or the tester's own PLM account) claims it; a HARD finding (the log, or code) shows otherwise. |
| `CODE_UNAVAILABLE` | Not verifiable against code because the module ships as a lib. |

## Rules

- **Tier immutability: a tier never improves with the passage of time.**
  A finding carried forward from an earlier run is still whatever tier it
  was written at. Reaching `VERIFIED_LOG` requires verification against
  the log of the issue currently being analysed — never inherited from a
  prior run or a prior case record. This is the mechanism that stops an
  assumption from being laundered into a verified finding by repetition.
- **Guessing may ask, never answer.** A tier is assigned to what a source
  actually said or showed — never to what a query merely failed to
  contradict. A failed guess teaches nothing and gets no tier at all,
  positive or negative.
- **`TESTER_REPORTED` is a claim, not a fact.** It is recorded so the
  pipeline can reason about what was reported without anchoring on it as
  ground truth. It marks a claim traced to the PLM issue's own verbatim
  `title`/`description` text (which may itself contain the tester's
  reported reproduction steps and expected result — PLM has no separate
  field for these; see `plm-invocation.md`) — never to a query result, an
  agent inference, or `engineer_clarification` (that is always
  `ENGINEER_PROVIDED`, regardless of how closely it echoes the tester's
  words). `rca-scope` tags it onto an issue-type classification when the
  classification came from matching that PLM text, not from an engineer
  override; `rca-conclude` tags it the same way when comparing
  `plm-snapshot.json.description` against the log in
  `tester_comparison`. Any skill reading `input/plm-snapshot.json`'s
  verbatim fields may assign it, on the same basis: the claim traces to
  PLM's own words. `rca-intake` itself assigns no tier to these fields at
  fetch time — see the skill-by-skill tier assignments below.
- **`ENGINEER_PROVIDED` may override an agent inference when the engineer
  explicitly directs it**, but a conclusion resting on one is always
  labelled as resting on an engineer premise — never presented as if it
  were pipeline-verified.

## Skill-by-Skill Tier Assignments

`rca-intake` writes no `TESTER_REPORTED` itself — `title`/`description`/
`comments` are stored verbatim from PLM, untagged, the same way
`description` always was (not yet a claim used in analysis). It writes
`ENGINEER_PROVIDED` in two places: on `input/plm-snapshot.json.engineer_clarification`'s
populated fields (an engineer's explicit correction of an unclear or
technically imprecise PLM account — see `run-bundle-layout.md`), and on
anything the engineer asserts directly into `input/log-pointers.json` at
invocation time (e.g. a known build/model or source commit).

`rca-scope` writes `TESTER_REPORTED` (on an issue-type
classification matched from PLM text), `ENGINEER_PROVIDED` (on an
engineer-supplied failure time or classification hint), and `VERIFIED_LOG`
(on a failure time actually found by a log query).

`rca-analyze` writes
`VERIFIED_LOG` and `CODE_BOUND` (a hypothesis-testing query's hit),
`SPEC_INFERRED` (a cited NotebookLM answer, per rungs 1/4 of the
resolution ladder), `CODE_UNAVAILABLE` (a branch behind a lib module), and
`CONTRADICTED` (a HARD finding disproving a SOFT claim).
Its loop also uses two gate-triggering tiers: `ENGINEER_PROVIDED` on a `redirect <information>` reply's
injected text (recorded in `analysis/round-NN.json.engineer_redirect` —
see `run-bundle-layout.md`), and `ASSUMED` on a hypothesis that reached
the checkpoint with no query ever attempted against it at all
(`hypotheses[].untested_tier` in the same file) — a rare case, since
Step 6 of `rca-analyze/SKILL.md` always tries to construct a testing
query, but not always possible (no viable keyword, no applicable table).

`rca-conclude` writes no tier from a new query of its own — it
only copies `problem`/`root_cause`/`causal_chain`/
`reproduction_scenario` tiers forward verbatim from what
`rca-scope`/`rca-analyze` already recorded (per this file's "never
improves with time" rule), with one use specific to synthesis:
`CONTRADICTED` when the reproduction scenario it derives from the causal
chain disagrees with `input/plm-snapshot.json`'s verbatim `description`
text (never `engineer_clarification`) on a point a HARD finding actually
settles — the tester's account is checked against the log, not assumed
correct, so a mistaken account gets corrected here rather than carried into a report.
This is why the table above
names "the tester's own PLM account" alongside spec/vendor-doc/prior-case
as a source `CONTRADICTED` can apply to — `rca-conclude` is the first
skill to contradict that particular source.

`rca-learn`
writes no tier from a fresh query of its own either — like `rca-conclude`,
it only copies tiers forward, from `conclusion.json` and
`analysis/round-NN.json` into `knowledge/cases/<case_id>.json`, never
upgrading any of them. It is, however, the skill whose entire second
purpose is enforcing "a tier never improves with the passage of time" on
the read side too: a later `rca-analyze` round consulting a case
(resolution-ladder rung 6) sees the tier exactly as `rca-learn` wrote it,
never as something reinforced by having accumulated across cases — see
`keyword-provenance.md`'s "Cases and playbooks are hints, never evidence."

The keyword-provenance ladder (HARD / SOFT / FORBIDDEN — which *sources*
may support a conclusion) is a related but separate concept, documented in
`_shared/keyword-provenance.md`.
