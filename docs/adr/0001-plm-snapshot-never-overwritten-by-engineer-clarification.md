# PLM snapshot and engineer clarification are stored side by side, never merged

`rca-intake` lets an engineer supply `engineer_clarification` for
`title`/`description`/`comments`, because a tester's PLM account can be
unclear or technically imprecise. We decided this clarification is always
written **alongside** the verbatim PLM snapshot in
`input/plm-snapshot.json`, never in place of it — even though a single
merged field would be simpler to read and would still let
`rca-scope`/`rca-analyze` seed off the engineer's corrected framing.

We rejected merging because `rca-conclude`'s `tester_comparison` step
depends on the tester's **original, unedited** words to detect cases where
the log disproves what the tester reported (tagged `CONTRADICTED`). If an
engineer's correction silently replaced the tester's account before that
comparison ran, the pipeline would compare the log against the engineer's
own opinion instead of the tester's — destroying the one mechanism this
suite has for catching a tester's mistaken account. Keeping both, with the
clarification tiered `ENGINEER_PROVIDED` and consumed preferentially by
earlier stages but never by `rca-conclude`'s comparison, preserves that
mechanism at the cost of a slightly larger schema.
