---
name: 3gpp-fta-render-tree
description: >
  Visual renderer for the FTA hybrid tree — v6 companion capability, NOT a
  pipeline phase and not part of meta.current_phase. Reads
  fta_iterations[N].hybrid_tree (plus base_events, rejected, open_items,
  cross_reference_findings, iteration_root_cause, and phase_eval_log[] if
  present) and produces a self-contained HTML fault-tree diagram, following
  the exact status→visual mapping established in
  docs/architecture/2026-08-17-fta-phase-eval-suite-design.html ("Worked
  example" section — that file's VoLTE tree is the canonical reference
  rendering this skill reproduces for any real run). Read-only against the
  state file — writes only an output HTML file to disk. Auto-triggers right
  after 3gpp-fta-iteration-controller enters PRESENT mode for an iteration
  (Checkpoint B is halting anyway; the render gives the engineer a visual to
  decide dig/accept/abort by). Also invocable on demand at any point once
  Phase 3.1 has run. Triggers: "render FTA tree", "render fault tree",
  "visualize hybrid tree", "draw tree for iteration N", "show me the tree",
  "render the tree like the eval-suite design doc".
---

# 3GPP FTA Tree Renderer (v6, companion — not a pipeline phase)

## Role

Turn one iteration's `hybrid_tree` into an HTML fault-tree diagram, using
the exact visual language already established for this pipeline in
`docs/architecture/2026-08-17-fta-phase-eval-suite-design.html`. That file's
"Worked example — VoLTE call drop" section drew a tree by hand for an
illustrative run; this skill produces the same rendering, mechanically,
from a real `hybrid_tree` in the state file.

## What this is NOT

- Not a pipeline phase — does not read or write `meta.current_phase`.
- Not a gate — never blocks, never halts waiting on a decision.
- Not a state writer — the state file is untouched by this skill. The only
  output is a standalone HTML file on disk.
- Not a replacement for Checkpoint B's text prompt (`_shared/checkpoint-presentation-formats.md`)
  — the render is a visual companion the engineer opens alongside it, not a
  substitute for it.

## Hard constraints

1. Read-only against the state file. Zero writes to it, ever.
2. No `3gpp-spec-retrieval`, `3gpp-code-retrieval`, or `3gpp-log-queries`
   calls — this skill only transforms data already in the state file.
3. Never invents a branch, child, status, or value not present in the
   state file slice read in Step 1.
4. Reuses the status → visual mapping in §2 verbatim across runs — does
   not improvise new colors or treatments per invocation. If a status value
   appears that isn't in the mapping table, render it with the
   `unevaluated` treatment and note the unmapped status in the caption
   rather than guessing a color for it.
5. Rendering assumes the operating agent has a diagram-generation
   capability equivalent to the `diagram-design` skill (as used to produce
   the reference file above). If unavailable, fall back to Step 4b: emit
   the same status-mapped node list as a plain HTML nested list / table
   instead of SVG — never skip the render silently.

## Preconditions

- `iteration_id` provided; defaults to `meta.current_iteration_id`.
- `fta_iterations[iteration_id - 1].hybrid_tree` exists with at least
  `branches[]` populated (i.e. Phase 3.1 has run). Fine to render before
  Gate B expansion — branches without `children[]` yet just render as
  leaves with the `unevaluated` or in-progress treatment.

## Output

One HTML file on disk. Nothing written to the state file.

---

## Execution

### Step 1 — Read state slice

Read `fta_iterations[iteration_id - 1]`:
`input_top_event`, `hybrid_tree`, `base_events[]`, `rejected[]`,
`open_items[]`, `cross_reference_findings[]`, `iteration_root_cause`
(may be null if rendering mid-iteration, before Phase 3.5).

Also read `fta_iterations[iteration_id - 1].phase_eval_log[]` **if the
array exists** (populated by the `3gpp-fta-eval-*` skills, when built per
the eval-suite design) — used only for the `!` flag badge in §2. If the
field is absent, render with zero badges. Its absence is not evidence of
"all clean" — do not imply that in the caption.

### Step 2 — Map state to diagram nodes

**Root** = `input_top_event.event`; eyebrow text =
`"TOP EVENT · ITER " + iteration_id`; sublabel = `input_top_event.source`.

**Level 1** — one node per `hybrid_tree.branches[i]`, by `status`:

| `status` | Fill | Stroke | Sublabel |
|---|---|---|---|
| `unevaluated` | `ink@0.02` | `ink@0.20` dashed | `"pending"` |
| `open` | `ink@0.02` | `ink@0.20` dashed | `"open · " + brief reason` |
| `pruned_normal` | `ink@0.05` | `muted` solid | `"pruned · " + matched-row count if known` |
| `failure_here` / `absent`, no `children[]` yet | `paper` | `ink@0.30` solid | status text verbatim |
| `failure_here` / `absent`, `children[]` populated | `paper` | `ink@0.32` solid, width 1.2 | `"→ expand"` |
| `not_applicable` | `ink@0.02` | `ink@0.20` dashed | `"N/A (code-only)"` |
| anything else (unmapped) | `unevaluated` treatment | — | `status` value verbatim + note in caption |

**Level 2** — one node per `branches[i].children[j]`, only rendered when
`children[]` is non-empty, by set membership:

| Membership | Fill | Stroke | Sublabel |
|---|---|---|---|
| In `base_events[]` **and** named as the deepest cause in `iteration_root_cause.base_event_chain` | `accent-tint` | `accent` (coral) | delta from the matching `cross_reference_findings[]` entry if one exists, else `"confirmed"` |
| In `base_events[]`, not the terminal cause | `ink@0.05` | `muted` solid | `"confirmed"` |
| In `rejected[]` | `ink@0.015` | `ink@0.15` | `"rejected · no match"` |
| In `open_items[]` | `ink@0.02` | `ink@0.20` dashed | `"open"` |

**Coral rule (mandatory — mirrors diagram-design's Tree §Focal, exactly
one focal node per diagram):** accent goes on at most one node — the base
event `iteration_root_cause.base_event_chain` names as the deepest cause.
If `iteration_root_cause` is null (rendering before Phase 3.5 has run),
no node gets accent; all confirmed base events use the plain "confirmed"
muted treatment instead. Never guess which base event will end up being
the cause before Phase 3.5 says so.

**Eval-flag badge:** draw the amber `!` circle badge (as in the reference
file) on a node only when `phase_eval_log[]` contains an entry whose
`judgment_checks[]` names that branch/child id with `verdict: "concern"`
or worse, or a `mechanical_checks[]` entry with `result: "fail"` naming
it. Never draw a badge without a backing log entry.

### Step 3 — Handle overflow (breadth budget)

Tree diagrams cap legible breadth at 5 nodes per level. If
`branches[]` has more than 5:
- Keep the 5 highest-priority (same priority order Gate A itself already
  uses: branches matching `phase2_ecf.observable_symptoms.missing_events`
  first, then `failure_here` / `absent` / `open`, `pruned_normal` last).
- Collapse the remainder into one summary node labeled `"+N pruned"`
  (muted treatment, no individual detail).
- State the drop explicitly in the diagram caption — e.g. `"3 additional
  pruned_normal branches omitted, see state file for full list"`. Never
  truncate silently.

Apply the same rule independently to any branch whose `children[]` has
more than 5 entries.

### Step 4 — Render

**4a (preferred):** Produce the diagram using a `diagram-design`-equivalent
Tree-type generator: orthogonal elbow connectors (parent vertical drop →
sibling horizontal bus → child vertical drop), rounded 6px node corners,
Geist sans node names, Geist Mono sublabels, coral reserved for the one
focal node per §2, legend strip at the bottom matching the reference
file's legend (investigated / open / pruned / confirmed / rejected /
eval-flagged).

**4b (fallback, only if 4a's capability is unavailable):** Emit the same
node set — status, sublabel, badge — as a plain nested HTML list or table
instead of SVG. Never skip rendering outright just because the diagram
generator isn't available.

### Step 5 — Write output file

Write to `.rca/renders/iteration_<N>_tree_<UTC_ts>.html` in the target
workspace (create `.rca/renders/` if it doesn't exist yet). Report the
file path back to the engineer.

**Do not** write this path — or any pointer to it — into the state file.
`_shared/state-file-schema.md` owns no such field, and adding one would
require updating that schema doc plus every skill that touches
`fta_iterations[i]`. Out of scope for a read-only companion skill.

---

## Anti-Hallucination

- Every node's label, status, and sublabel value comes directly from the
  state file slice read in Step 1 — never inferred, rounded, or
  embellished beyond what's stored.
- The delta shown on the coral node comes only from a matching
  `cross_reference_findings[]` entry — if none exists, show `"confirmed"`,
  never a fabricated number.
- Eval-flag badges require a real `phase_eval_log[]` entry naming that
  exact branch/child id — absence of the array or a non-matching entry
  means zero badges on that node.
- Overflow collapsing (§3) must state the exact count omitted, never a
  vague "and more".

---

## What this skill does NOT do (HARD)

- ❌ Does NOT write to the state file, in any field
- ❌ Does NOT change `meta.current_phase`
- ❌ Does NOT gate, block, or stand in for Checkpoint B
- ❌ Does NOT call `3gpp-spec-retrieval`, `3gpp-code-retrieval`, or `3gpp-log-queries`
- ❌ Does NOT render iterations other than the one requested
- ❌ Does NOT invent colors or treatments outside the §2 mapping table
- ❌ Does NOT imply "all clean" when `phase_eval_log[]` is simply absent
