# RCA Run Quality Rubric — 6 dimensions, scale 1–5

Used by LLM-judge (`eval_judge.py`) and human reviewers alike. Score each
dimension independently; every score requires a rationale citing specific
report content. The judge may use ONLY the final report and the eval record.

Anchors: 5 = flawless, 3 = usable with visible gaps, 1 = unusable/misleading.
Score 2 or below on any dimension routes the run to mandatory human review.

## 1. scope_quality
Is the Phase 1 scope filter precise and consistent with the engineer
description? Procedure/RAT/layers/time window coherent; IS/IS-NOT
discriminator meaningful; ambiguities surfaced rather than papered over.
- 5: tight scope, discriminator clearly separates failing vs working domain
- 3: scope correct but broad; discriminator generic
- 1: scope contradicts the description or omits stated constraints

## 2. top_event_quality
Are the Checkpoint A candidates well-ranked and evidence-backed? Rank-1
should be the failure's proximate observable, not a downstream consequence;
rejection reasons for alternatives must be substantive.
- 5: rank-1 clearly proximate, alternatives correctly rejected with reasons
- 3: rank-1 plausible but a listed alternative is arguably better
- 1: candidates are consequences/symptoms mislabeled as top events

## 3. tree_quality
Per iteration: is the hybrid FTA tree well-formed? Branches map to real
procedure phases; pruning decisions cite gate evidence; fallback (no spec
skeleton) acknowledged rather than hidden.
- 5: every branch spec- or code-anchored; pruning justified by gate results
- 3: tree correct but shallow, or one pruning weakly justified
- 1: branches invented without anchor, or pruning without stated evidence

## 4. evidence_rigor
Is every claim traceable? Log citations for observations, spec refs for
expected behavior, code locations for mechanisms. Provenance audit clean.
Confident-but-unsupported statements score LOW here.
- 5: every causal claim has a citation; provenance 100%
- 3: conclusions supported but some intermediate steps asserted bare
- 1: key claims unsupported, or provenance failures present

## 5. causal_chain_coherence
Does the iteration chain actually connect? Each link's "X caused Y" must be
backed by that iteration's cross-reference findings; no leaps between
iterations; terminal point genuinely terminal (implementation primitive),
not just where the budget ran out — unless explicitly stated as such.
- 5: unbroken, each link evidenced, terminal point justified
- 3: chain plausible; one link rests on correlation not shown mechanism
- 1: links contradict each other or skip levels without evidence

## 6. report_clarity
Can a modem engineer who did NOT run the pipeline act on this report?
Structure follows the template; the final root cause statement is specific
(class, location, mechanism); user decisions and overrides are visible.
- 5: self-contained, specific, decision audit clear
- 3: complete but requires state-file spelunking to follow one section
- 1: vague root cause ("timing issue somewhere"), missing sections

## Output format (judge)

```json
{"scores": [
  {"dimension": "scope_quality", "score": 4, "rationale": "..."},
  {"dimension": "top_event_quality", "score": 5, "rationale": "..."},
  {"dimension": "tree_quality", "score": 4, "rationale": "..."},
  {"dimension": "evidence_rigor", "score": 3, "rationale": "..."},
  {"dimension": "causal_chain_coherence", "score": 4, "rationale": "..."},
  {"dimension": "report_clarity", "score": 5, "rationale": "..."}
]}
```
