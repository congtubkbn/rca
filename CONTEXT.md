# RCA Pipeline

The domain vocabulary for the PLM-issue root-cause-analysis pipeline
(`rca-intake → rca-scope → rca-analyze ⟲ → rca-conclude → rca-learn`) —
see root `CLAUDE.md` for the pipeline's architecture.

## Language

**PLM snapshot**:
The verbatim `title`/`description`/`comments` text captured from PLM at
one `rca-intake` fetch, written to `input/plm-snapshot.json`. It is a
historical record, not live PLM state — a later edit in PLM does not
change what an already-created run rests on.
_Avoid_: PLM data, issue text

**Tester's account**:
The tester's own narrative in the PLM issue — `title` plus `description`
— including whatever reproduction steps and expected result the tester
wrote, since PLM keeps no field of its own for those. Treated as an
unverified claim (`TESTER_REPORTED`) until a downstream skill checks it
against the log or code.
_Avoid_: reproduction steps, ground truth, what actually happened

**Comment**:
One entry in a PLM issue's comment thread — contributed by an SWPL
analyst, another team, or the analysing engineer, not only the tester.
Recorded verbatim with its `comment_id`/`author`/`timestamp` and no
evidence tier at intake time; a later skill may use one as an unverified
hint, never as proof. Distinct from an **engineer clarification** below —
a comment is PLM's own historical record, never edited by this pipeline.
_Avoid_: note, remark

**Recommendation**:
The top-ranked surviving hypothesis `rca-analyze` names at a round's
checkpoint — the causal explanation the evidence currently supports best,
evidence-tiered and revisable across rounds as new rounds run. This is
`rca-analyze` **finding** a root cause candidate, not the pipeline
concluding one — an `accept` reply only hands the recommendation to
`rca-conclude`, which is what actually confirms it.
_Avoid_: root cause (when describing `rca-analyze`'s own output), finding,
verdict

**Conclusion**:
`rca-conclude`'s synthesized deliverable — the root cause, causal chain,
and reproduction scenario written to `conclusion.json`/`CONCLUSION.md` from
an accepted `rca-analyze` recommendation, checked against the tester's
account. The only point in the pipeline where "root cause" names a
finished, confirmed answer rather than a still-revisable recommendation.
_Avoid_: result, output, report

**Engineer clarification**:
An analysing engineer's explicit correction or clarification of the
tester's account or of a comment, supplied because the original PLM text
is unclear or technically imprecise. Recorded separately from — never in
place of — the PLM text it clarifies, tier `ENGINEER_PROVIDED`. Preferred
over the raw PLM text when `rca-scope`/`rca-analyze` seed a classification
or hypothesis, but never substituted for the raw text when `rca-conclude`
compares the tester's account against the log — the tester's own words
must survive that check unedited.
_Avoid_: correction, override, engineer note
