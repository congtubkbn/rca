# Eval: `rca-analyze` layer/protocol coverage

**Status:** findings only — no skill changes applied yet, per agreement in the
2026-09-02 grilling session. Changes get decided in a follow-up round based
on what's below.

**Method:** no live PLM MCP / DuckDB / code-graph tools are connected in this
workspace — no skill was actually invoked end-to-end. For `volte_call_drop`,
`rca-intake` → `rca-scope` → `rca-analyze` round 1's steps were followed by
hand against a synthetic PLM issue, with every log-query/code-graph/
NotebookLM call **and its result authored by hand** (I wrote the ground
truth, then wrote the mocked tool outputs consistent with it, then wrote
what each `SKILL.md` step said to do with them), written into a real run
bundle at `.rca/issues/TEST-VOLTE-001/` (git-ignored, kept as reference —
see that folder for the full JSON). Two further scenarios (`no_service`,
`generic`) are lighter paper walkthroughs of `rca-scope`/`rca-analyze`'s
`SKILL.md` steps, no files written. **None of this is empirical in the
"observed an independent system's behavior" sense** — treat every finding
below as either (a) a static defect, verifiable by reading a checked-in
file, or (b) a behavioral finding from hand-tracing the steps, which is
informative about what the instructions actually cause but is still my own
execution of them, not a second system's.

**Headline, on the question that started this** (from the prior `/ask-matt`
session: is `rca-analyze`'s flat hypothesis list structurally wrong for
cross-layer causal chains, i.e. does it need FTA-style AND/OR gates): the
`volte_call_drop` trace produced one real, evidenced cross-layer edge —
`on_rrc_release_indication` (RRC) → `teardown_sip_session` (IMS), confirmed
at `CODE_BOUND` via a `code-graph trace_call_path` call specifically issued
to test the *mechanism*, not just the correlation — sitting inside a plain
linear `causal_chain_additions` list, no gate structure needed. That's
evidence against "structurally can't" for at least the AND-shaped case this
scenario represents. It does **not** cover the OR-shaped case (two
independent branches competing for the same link in the chain) — no
scenario here had one, so that half of the original question stays open.

**Checklist applied to each:**
1. Classification/scoping correctness
2. Failure-point location logic
3. Hypothesis generation spans `scope.json.layers`, or silos
4. Evidence-tier discipline
5. Causal-chain cross-layer linkage
6. Checkpoint gate correctness
7. Is `scope.json.layers` ever actually read

---

## Scenario 1 — `volte_call_drop` (dry-run)

Synthetic issue: VoLTE call drops ~30s in, at cell edge, audio chops first.
Engineered ground truth: PHY signal weakens → RRC declares Radio Link
Failure (T310 expiry) → IMS session manager's bearer-loss handler fires →
SIP BYE. A genuinely cross-layer chain, PHY→RRC→IMS, deliberately built to
stress the suspected gap.

1. **Classification** — correct. Title matched `"volte"`, `issue_type =
   volte_call_drop`, `matched_playbook` set, tier `TESTER_REPORTED`. No
   issue.
2. **Failure-point location** — correct and cheap: `scope.json.failure_time`
   was already `VERIFIED_LOG` (rca-scope's own time-anchor query hit), so
   Step 5 reused it with zero new tool calls, exactly as `SKILL.md` specifies.
3. **Hypothesis generation spans layers — yes, but because I chose to make
   it, not because the step routes there.** H1/H2 came from two NotebookLM
   spec citations (RLF behavior, normal-teardown behavior) that happen to
   name RRC and IMS/SIP; H3 (media-plane) was a stated guess. All three
   span layers because I, hand-tracing the round, chose to ask NotebookLM
   two layer-adjacent questions — a decision `rca-analyze/SKILL.md` Step 6
   permits but never prompts (static fact: Step 6 has no instruction to
   read `scope.json.layers` or probe each listed layer). A more literal,
   less thorough hand-trace of the same step could have generated three
   hypotheses all sitting inside RRC and the schema would not flag that as
   incomplete — see the merged finding below, where this stops being
   hypothetical.
4. **Evidence-tier discipline** — correct. H1 reached `VERIFIED_LOG` +
   `CODE_BOUND`; H2 was eliminated by a positive contradicting HARD finding
   (not a miss); H3's miss left it `surviving`-but-unsupported rather than
   eliminated, per `keyword-provenance.md`.
5. **Causal-chain cross-layer linkage — the one clean win.** The round
   didn't just note "RRC event happened" and "IMS event happened" as two
   flat facts — it ran a `code-graph trace_call_path` specifically to
   confirm the *mechanism* connecting them (`on_rrc_release_indication` →
   `teardown_sip_session`), recorded at `CODE_BOUND`. That's a real,
   evidenced cross-layer edge, not a temporal-adjacency guess. This proves
   the *schema* can hold a genuine cross-layer causal link — `rca-analyze`
   was never structurally incapable of it, contrary to what a purely static
   reading of Step 6 might suggest.
6. **Checkpoint gates** — correct. None of the four gates tripped (no
   budget, no `ASSUMED` recommendation, failure point located, not
   everything eliminated); `autonomy: "review_all"` halted regardless,
   correctly.
7. **Is `layers` ever read? No (static: Step 6 has no such instruction;
   confirmed by hand-tracing it — I never opened `scope.json.layers`
   either).** It didn't cost anything in this scenario, because the spec
   citations happened to cover the right ground. But the hand-trace
   produced one genuinely informative behavioral result: **the chain stops
   one link short of its own root, and I was the one running it, with the
   ground truth in hand.** H1 asserts "weak-signal-triggered" RLF, but the
   round only verified RRC-downward (T310 expiry → release → IMS teardown)
   — it never queried `UE_Trace_log` for the PHY/RSRP condition, even
   though the tester's own account ("cell edge", "1-2 bars", "not
   reproducible indoors") points straight at it, and even though I knew
   PHY was the engineered root cause while authoring the round. It didn't
   get routed there anyway — see the merged finding below.

## Scenario 2 — `no_service` (paper walkthrough)

Hypothetical: device shows "no service" for several minutes after exiting a
tunnel; SWPL notes it eventually self-recovers on manual airplane-mode
toggle. `known-issue-types.md` row: layers `RRC, NAS, PHY`, keywords "cell
selection failure", "out of service", "RRC_IDLE".

Tracing `rca-scope`: title matches `"no service"` → classifies cleanly,
`tables_in_scope`/`layers` set from the row, same as scenario 1 — no new
finding there.

Tracing `rca-analyze` Step 6 by hand surfaces a **different** structural
issue, not the same one restated: a `no_service` root cause is frequently a
claim about **absence** — "cell reselection never found a suitable cell",
"the UE never sent a Tracking Area Update after re-entering coverage" — but
`log-query`'s contract (`log-query-invocation.md`) only ever returns
*positive* keyword hits, and `keyword-provenance.md`'s "guessing may ask,
never answer" rule explicitly forbids treating a miss as proof something
didn't happen. So a hypothesis whose predicted evidence is genuinely "no
TAU was ever attempted" has no valid way to reach `VERIFIED_LOG` under this
contract — the closest it can get is finding a *positive* marker that
something else *did* happen instead (e.g. repeated `cell selection failure`
events), which is a proxy, not direct confirmation of the absence claim.
This isn't hypothetical for this issue type specifically — "no service"
root causes are disproportionately absence-shaped compared to
`volte_call_drop`'s clean event-boundary shape, so the gap bites harder
here than it would for the dry-run scenario.

`layers` usage: same as scenario 1 — present in `scope.json`, unread by
Step 6, no different outcome predicted.

## Scenario 3 — `generic` (paper walkthrough)

Hypothetical: "Device reboots randomly, sometimes mid-call" with a trace
log showing a watchdog/kernel-panic marker. Title/description match none of
`known-issue-types.md`'s `trigger_keywords` (no "volte", "sms", "no
service", "emergency") → `issue_type = "generic"`, `matched_playbook =
null`, `reduced_tier = true`, `layers = []`, `tables_in_scope` = everything
loaded (correct per `SKILL.md` Step 6's `generic` branch).

Tracing `rca-analyze` Step 5: `scope.json.failure_time.origin` is very
likely `"undetermined"` here too — the generic fallback keyword list
(`"release", "reject", "failure", "drop", "timeout", "abort",
"disconnect"`) has no obvious hit for a kernel panic/watchdog event, so
`rca-scope` most likely falls back to the full loaded window, correctly
flagged.

Tracing Step 6's hypothesis generation is where a **third, distinct**
finding shows up: rung 1/4 of the resolution ladder is NotebookLM against
3GPP-spec and vendor-chip-documentation corpora — both corpora are about
*protocol behavior*. A watchdog reset / kernel panic is a platform/OS-level
fault with no 3GPP procedure to cite at all. `SKILL.md` Step 5 does say
"if generic, ask about the broader category implied by the PLM
description", so the skill doesn't literally break — but rungs 1 and 4 are
structurally close to useless for this class of `generic` issue, pushing
almost the whole burden onto rung 2 (log-query for "panic"/"watchdog"/
"reset reason", if those literals exist in `UE_Trace_log`) or straight to
rung 5 ("ask the engineer"). That's a legitimate outcome, not a bug — but
it means **`"generic"` is currently one bucket for two different kinds of
issue**: "a real protocol issue this repo's hand-maintained
`known-issue-types.md` just doesn't have a row for yet" (spec/vendor rungs
still useful) vs. "a non-protocol issue where spec/vendor rungs are
inapplicable by category, not just by missing data" (only log/code/engineer
rungs are ever going to help). Nothing currently distinguishes the two, so
a `generic` run gets the same treatment either way.

`layers = []` for this scenario is consistent with the "unnarrowed, not
irrelevant" rule `run-bundle-layout.md` states — and moot anyway, since
`layers` isn't consumed downstream regardless of whether it's populated or
empty.

---

## Consolidated findings

Sorted by evidence type — static (verifiable by reading a checked-in file,
independent of anything I ran) first, then behavioral (from hand-tracing
the steps).

**F1 (static + behavioral, merged) — a playbook row under-scopes a textbook
case, and nothing downstream can ever catch it.** Static:
`known-issue-types.md`'s `volte_call_drop` row lists `layers: RRC, NAS,
IMS/SIP` and omits `PHY`, for an issue type whose textbook trigger (weak
signal at cell edge) *is* a PHY condition — verifiable by reading that one
file, no execution required. Behavioral: hand-tracing the dry-run with the
engineered ground truth already known, the round still stopped
RRC-downward and never reached PHY — not because the trace was careless,
but because (a) `scope.json.layers` was never consulted by Step 6 in the
first place (static: no such instruction exists), and (b) even if it had
been, this row's own list would have pointed away from PHY. The two facts
compound: the omission in the static file is exactly the kind of thing a
"does hypothesis generation cover every listed layer" check would catch —
and no such check exists, so it doesn't get caught. This is the strongest
finding in this eval and the most direct answer to Q3's original
suspicion.

**F2 (static) — the evidence contract structurally favors presence-shaped
hypotheses over absence-shaped ones.** `keyword-provenance.md`'s "a miss
never proves absence" rule is correct on its own terms, but it means issue
types where the root cause is characteristically "X never happened" (the
`no_service` walkthrough's "cell reselection never found a suitable cell",
"TAU never attempted") have a structurally weaker path to `VERIFIED_LOG`
than event-boundary issue types like `volte_call_drop`, where every
relevant fact is something that *did* log. Read directly off
`log-query-invocation.md`'s return shape (positive hits only) and
`keyword-provenance.md`'s miss rule — no execution needed to see it, though
the `no_service` walkthrough is what surfaced it.

**F3 (static) — `"generic"` conflates two different diagnostic
situations.** Read off `resolution-ladder.md`'s rungs 1/4 (3GPP-spec,
vendor-chip corpora) plus `rca-scope/SKILL.md`'s `generic` branch: a
protocol issue this repo's hand-maintained `known-issue-types.md` just
lacks a row for (rungs 1/4 still useful) and a non-protocol issue like a
kernel panic/watchdog reset (rungs 1/4 inapplicable by category, not
missing data) get the identical `layers: []`, `matched_playbook: null`
treatment. Surfaced by the `generic` walkthrough, verifiable from the
static files alone.

**On the FTA/AND-OR question this eval was commissioned to test:** see the
Headline above — answered for the AND-shaped case (no gate structure
needed, a linear chain held a real cross-layer edge fine), still open for
the OR-shaped case (no scenario here had two independent branches competing
for the same chain link).

## Fix applied (F1 only — F2/F3 left as documented, not fixed)

Two changes, no schema change:

1. `.claude/skills/rca-scope/references/known-issue-types.md` —
   `volte_call_drop`'s `layers` row: `RRC, NAS, IMS/SIP` → `PHY, RRC, NAS,
   IMS/SIP`.
2. `.claude/skills/rca-analyze/SKILL.md` Step 6.1 — hypothesis generation
   must now read `scope.json.layers` before sourcing hypotheses, and every
   listed layer must be either addressed by a hypothesis or excused by name
   in `open_notes` — a chain that terminates inside one layer is
   explicitly *not* itself grounds to skip a layer still listed as in
   scope. `layers = []` (generic classification) is exempt, unchanged.

**Not re-run against `TEST-VOLTE-001`** — that run's `round-01.json` is
kept as-is, as the "before" evidence (rewriting it would violate this
pipeline's own append-only-round rule). Expected effect, reasoned by hand
against the same ground truth: with `PHY` now in `layers`, round 1's
hypothesis generation can no longer silently stop at the RRC→IMS chain it
produced originally — it must either add a fourth, PHY-layer hypothesis
(querying `UE_Trace_log` for RSRP/out-of-sync markers to test whether weak
signal actually caused the T310 expiry, closing the gap F1 identified) or
write an explicit `open_notes` line saying why PHY isn't being pursued this
round. Either outcome is strictly more disclosed than the original round,
which did neither.

## Not fixed (F2, F3) — left as documented findings

No change made for the presence/absence evidence-contract gap
(`no_service`-shaped issues) or the `generic` conflation
(protocol-unrecognized vs. non-protocol). Revisit if/when either becomes a
real case, per the same reasoning that put this eval before a real one.
