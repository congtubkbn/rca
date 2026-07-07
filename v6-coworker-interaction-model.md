# RCA Agent as Co-Worker — Interaction Model Design (v6 baseline)

Target: make the RCA agent a CO-WORKER, not a rigid full-workflow
executor. After a full run, an engineer can inject information and
re-trigger individual skills (e.g. FTA) for deeper/corrected analysis;
or provide a top event directly to start FTA; or use any individual
skill standalone without the full workflow.

Baseline: the v6 skill suite (`3gpp-skills-v6`) — orchestrator + scoping,
event-timeline, top-event-confirmation, FTA (build-tree,
evaluate-branches, cross-reference, root-cause, iteration-controller),
pre-signaling, wrapper skills (spec/code/log retrieval), state-file
schema.

---

## 1. The core reframe: orchestrator-driven → engineer-driven

Today the orchestrator OWNS the flow and drives phases in sequence;
skills are subordinate steps. The co-worker model INVERTS ownership:

- The ENGINEER owns the flow.
- Skills become independently-invocable tools that run from whatever
  partial state the engineer supplies.
- The orchestrator becomes a LIBRARIAN, not a boss: it validates a
  skill's preconditions and routes, but does not force the sequence.
- Full-workflow mode is ONE way to drive the skills (the convenience
  path), not the only way.

Everything below is built so that a skill behaves identically whether
its inputs came from an upstream phase or from the engineer directly.

---

## 2. The shared mechanism: per-skill state contracts

Each skill declares a contract so it can run without the orchestrator
having pre-populated state:

```yaml
# in each skill's SKILL.md frontmatter or a contract block
contract:
  requires:        # must be present (in state) or supplied to run
    - <state path or named input>
  optional:        # enriches if present
    - <state path>
  produces:        # what this skill writes
    - <state path>
  self_seedable: true|false   # can engineer supply `requires` directly?
```

Example — FTA build-tree:
```yaml
contract:
  requires: [ top_event, scope_window ]
  optional: [ phase2_ecf.events, phase1_scope_filter ]
  produces: [ fta_iterations[].hybrid_tree ]
  self_seedable: true
```

With contracts, all three target scenarios are the same operation —
"run skill S from a state that satisfies S.requires" — differing only in
HOW `requires` got satisfied (upstream phase vs engineer input).

---

## 3. Invocation modes (entry points)

Add explicit modes the engineer selects:

| Mode | Meaning | Flow |
|---|---|---|
| `full_workflow` | orchestrator drives everything (current v6 behavior) | scope → … → finalize |
| `seed_and_run <skill>` | engineer seeds minimal state, runs a skill + its natural downstream | e.g. seed top_event → FTA onward |
| `resume <skill>` | re-enter a skill on an EXISTING state with new engineer info | re-run FTA branch with correction |
| `standalone <skill>` | run ONE skill, return output to engineer, no continuation | e.g. cross-reference on given base events |

`full_workflow` is unchanged for backward compatibility. The other three
are the co-worker capabilities.

---

## 4. Scenario 1 — Post-RCA deeper / corrected analysis

"Your root cause is wrong/incomplete. Here's additional info. Re-run FTA
on this branch."

Needs three things:

### 4a. Re-entry on existing state with injected data
`resume <skill>` loads the existing state, applies the engineer's
injected facts, and re-runs the target skill. The injected facts are
written as a distinct evidence source (§7 tier).

### 4b. Supersession of downstream results
Re-running a skill makes downstream results STALE. The design must not
let old and new coexist silently:
- The re-run creates a new iteration/version of the affected section.
- Downstream sections produced before the re-run are marked
  `superseded_by: <new_run_id>` and excluded from the final report.
- The audit trail records an `engineer_triggered_rerun` event:
  who, when, what was injected, which skill, what was superseded.

### 4c. Reuse the existing iteration machinery
The v6 FTA iteration-controller already supports `dig_deeper` and
`force_full_analysis`. Engineer-triggered re-runs are a GENERALIZATION:
like `dig_deeper`, but able to target a SPECIFIC skill and inject data,
not just spawn a deeper full iteration. Extend the controller rather
than build new.

---

## 5. Scenario 2 — Direct top event → start FTA

Engineer provides the top event directly, skipping scope/timeline/
confirmation.

### 5a. State seeding
`seed_and_run fta-build-tree` constructs a MINIMAL valid state from
engineer input:
```json
{
  "meta": { "mode": "seed_and_run", "entry_skill": "fta-build-tree" },
  "top_event": {
    "description": "<engineer-provided>",
    "source": "ENGINEER_PROVIDED",
    "scope_window": { "start": "...", "end": "..." }
  }
}
```
The normally-upstream sections (`phase1_scope_filter`, `phase2_ecf`,
`user_confirmation`) are ABSENT. FTA must run from this minimal seed.

### 5b. Skills must check, not assume
build-tree currently may assume `phase2_ecf.events` exists. Under the
contract, it treats `phase2_ecf` as OPTIONAL: present → use it to enrich
the tree; absent → build from the top_event + spec/code retrieval alone.
This is the key code change: replace assumptions with contract checks.

### 5c. Scope fallback
If the engineer gives a top event but no scope window, the skill either
asks for one (it's `requires`) or derives a default from the top event's
timestamp ± a window. Never silently proceed without scope — Gate
queries need a time bound.

---

## 6. Scenario 3 — Standalone skill use

Engineer runs one skill (e.g. cross-reference on some base events, or
event-timeline on a window) with no workflow.

### 6a. Contract is the whole story
`standalone <skill>` runs iff the engineer supplies `requires`. Output
goes back to the engineer directly; no downstream is triggered.

### 6b. Reduced validation mode
The full workflow's Phase 4 validates CROSS-PHASE consistency. A
standalone run has no upstream/downstream to check against. So add a
`reduced_validation` mode that:
- validates what it CAN (verbatim provenance of this skill's own
  outputs, template-registry compliance, tier labeling)
- explicitly FLAGS what it cannot validate ("no cross-phase consistency
  check — standalone run")
- never silently claims full validation passed

### 6c. Output framing
A standalone skill returns its result tagged "standalone — not part of a
validated full RCA," so the engineer doesn't mistake a single-skill
output for a complete, cross-validated root cause.

---

## 7. The engineer-provided evidence tier (the connective tissue)

Engineer input is a NEW evidence source, and it's peculiar: high-trust
in one sense (a domain expert asserted it), unverified in another (not
traced to a log/spec/graph the way pipeline evidence is). It needs its
own tier.

```
ENGINEER_PROVIDED  — asserted by the engineer; authoritative as a
                     PREMISE, but not pipeline-verified
```

Rules:
- Recorded with provenance: who, when, the verbatim assertion, and what
  it overrides.
- It may OVERRIDE agent inferences when the engineer explicitly directs
  (the human is the senior partner). Example: engineer asserts the top
  event, overriding agent scoping.
- But it is still AUDITED and LABELED. A conclusion resting on an
  engineer premise is labeled "rests on ENGINEER_PROVIDED premise: X,"
  never laundered into VERIFIED.
- Phase 4 must DISTINGUISH "engineer-asserted premise" from "agent-
  derived + verified." Both are legitimate; conflating them is not.

This is the same tiered-honesty discipline as the rest of the system:
the agent faithfully analyzes an engineer-provided premise WITHOUT
pretending the premise itself was verified. If the engineer asserts a
wrong top event, the agent analyzes the wrong thing — correctly and
honestly labeled — which is acceptable co-worker behavior (not a
hallucination; an analysis of a stated premise).

---

## 8. The orchestrator as librarian (dispatcher)

Reframe the orchestrator into a lightweight dispatcher:

```
on engineer invocation (mode, skill, provided_inputs):
  1. load state (or create minimal seed)
  2. apply provided_inputs as ENGINEER_PROVIDED entries
  3. check skill.contract.requires against state
       missing & self_seedable → ask engineer / accept args
       missing & not seedable  → report what's needed, stop
  4. run the skill
  5. on completion:
       full_workflow / seed_and_run → OFFER (not force) next step
       resume     → apply supersession (§4b)
       standalone → return output + reduced_validation note, stop
```

This preserves full-workflow convenience while enabling standalone and
seeded use through ONE routing path.

---

## 9. State schema changes

Additive, backward-compatible:

```json
"meta": {
  "mode": "full_workflow | seed_and_run | resume | standalone",
  "entry_skill": "<skill name> | null",
  "engineer_inputs": [
    {"at": "<ISO>", "skill": "...", "assertion": "<verbatim>",
     "overrides": "<state path> | null", "input_id": "ei_<seq>"}
  ]
}
```
- Sections become OPTIONAL (a seeded state has gaps) — the schema must
  tolerate absent upstream sections.
- Add `superseded_by` to supersedable sections (§4b).
- Add `ENGINEER_PROVIDED` to the evidence-tier enum.
- Add `validation_scope: "full | reduced"` to the Phase 4 report.

---

## 10. Per-skill changes summary

| Skill | Change |
|---|---|
| orchestrator | becomes dispatcher (§8); keeps full_workflow path |
| all phase skills | declare `contract` (§2); replace upstream-assumptions with contract checks |
| fta-build-tree | run from a seeded top_event when phase2 absent (§5b) |
| iteration-controller | generalize dig_deeper → engineer-targeted re-run + injection (§4c) |
| cross-reference, event-timeline, etc. | support `standalone` + `reduced_validation` (§6) |
| finalize (Phase 4) | validate by `validation_scope`; distinguish ENGINEER_PROVIDED from verified (§7) |

---

## 11. Honest tensions

1. **Engineer override vs anti-hallucination.** A wrong engineer premise
   makes the agent analyze the wrong thing. Acceptable ONLY because it's
   labeled as an engineer premise, not agent-verified fact. The
   discipline holds: the agent never PRETENDS the premise was verified.
2. **Standalone loses cross-phase validation.** A single-skill output is
   genuinely weaker than a full validated RCA. `reduced_validation` +
   output framing prevent mistaking one for the other.
3. **Partial state integrity.** A seeded state is valid-but-incomplete.
   Skills must CHECK (contract) rather than ASSUME. This is the largest
   code change and the main risk: an unconverted skill that still
   assumes upstream population will break on a seeded state.
4. **Supersession complexity.** Re-runs create versioned state. Without
   disciplined `superseded_by` marking, stale results could leak into a
   report. Phase 4 must exclude superseded sections.

---

## 12. Recommended build order

1. **Contracts first** (§2) — declare requires/optional/produces for
   every skill. No behavior change yet; pure declaration. This is the
   foundation everything else needs.
2. **Skill assumption-audit** (§5b, §11.3) — find and fix every place a
   skill ASSUMES upstream population; replace with contract checks. The
   real work.
3. **Dispatcher** (§8) + invocation modes (§3).
4. **ENGINEER_PROVIDED tier** (§7) + schema changes (§9).
5. **Supersession** (§4b) + iteration-controller generalization (§4c).
6. **reduced_validation** (§6b) in finalize.

Steps 1–2 are most of the value: once skills run from a declared
contract instead of assumed upstream state, standalone and seeded use
are largely unlocked. Steps 3–6 make it safe, auditable, and honest.

---

## 13. The one principle

A skill must behave IDENTICALLY whether its inputs came from an upstream
phase or from the engineer — and the engineer's inputs must be honestly
tiered as premises, not laundered into verified facts. Get those two
right and the agent becomes a true co-worker: it follows the engineer's
lead, runs any piece on demand, and stays honest about what it has and
hasn't verified.

---

## NOTE ON BASELINE ALIGNMENT

This design was written from the known v6 architecture (orchestrator +
the phase/FTA/wrapper skills + state-file schema). The specific v6 file
contents in `3gpp-skills-v6` were not re-read when writing this (folder
enumeration wasn't available). Before implementation, align §10's
per-skill changes against the actual SKILL.md files — especially each
skill's current assumptions about upstream state, which §2/§5b/§11.3
depend on.
