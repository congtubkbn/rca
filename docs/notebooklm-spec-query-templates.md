# NotebookLM Spec Query Templates

Human-usable prompt templates for querying 3GPP spec sources loaded in
NotebookLM, mirroring the input/output contract of `spec_query.py` operations
defined in
[`.cline/skills/3gpp-spec-retrieval/references/spec-operations.md`](../.cline/skills/3gpp-spec-retrieval/references/spec-operations.md).

Use these when doing a manual spec lookup outside the pipeline (e.g.
sanity-checking what `spec_query.py` should return, or exploring a spec
before running the actual pipeline) — NOT a replacement for the pipeline's
own tool calls, which write directly to the state file.

## Master template

Swap `{{OPERATION}}` and the other placeholders per query; don't change the
requirements block.

```
OPERATION: {{OPERATION}}
TOP EVENT / SUBJECT: "{{TOP_EVENT}}"
PROCEDURE: "{{PROCEDURE}}"
RAT: {{RAT}}
{{EXTRA_PARAMS}}

Using the 3GPP specs in this notebook, {{TASK_INSTRUCTION}}.

For each result item, give me:
{{OUTPUT_FIELDS}}

Requirements:
- Every spec reference, IE name, and message name must come directly from the source documents — do not infer or guess ones not explicitly stated.
- Preserve exact spec notation: message names in ALL CAPS as written, IE names in hyphenated-case as written, spec refs as "TS XX.XXX §Y.Y".
- If an item isn't clearly defined in the sources, say so explicitly instead of filling it in — never fabricate.
- If nothing in the sources applies at all, say so explicitly instead of forcing an answer.
- Output as a numbered list, one item per entry, structured as: {{OUTPUT_ROW_FORMAT}}.
```

## Fill sheet — one row per `spec_query.py` operation

| `{{OPERATION}}` | When to use | `{{EXTRA_PARAMS}}` | `{{TASK_INSTRUCTION}}` | `{{OUTPUT_FIELDS}}` | `{{OUTPUT_ROW_FORMAT}}` |
|---|---|---|---|---|---|
| `skeleton` | Phase 3.1, iteration 1 — get standardized procedure phases | — | break down the STANDARDIZED procedure into sequential phases relevant to this top event | phase name, spec ref, mandatory messages, protocol layer | Phase name \| Spec ref \| Mandatory messages \| Protocol layer |
| `generate_hypotheses` | Fallback when `skeleton` returns empty | — | generate plausible ROOT CAUSE HYPOTHESES (procedure not standardized / internal logic) | hypothesis id, cause, spec ref (or "none"), gate AND/OR, IE names, message names, protocol layer | Hyp ID \| Cause \| Spec ref \| Gate \| IE names \| Message names \| Layer |
| `extract_ies` | Phase 3.2 Gate A refinement — need IE detail for a specific message | `MESSAGE: "{{MESSAGE_NAME}}"`, `HYPOTHESIS_ID: {{ID}}` | list the mandatory and optional IEs for this specific message, per spec | mandatory IEs, optional IEs, direction (UL/DL) | Mandatory IEs \| Optional IEs \| Direction |
| `find_commanded_values` | Phase 3.4 cross-reference — need commanded value for a base event | `BASE_EVENT_NAME: "{{NAME}}"`, `BASE_EVENT_LAYER: "{{LAYER}}"`, `UPSTREAM_MESSAGES: "{{MSG1}} {{MSG2}}"` | find the IE(s) in the upstream message(s) that COMMAND the value tied to this base event, and what UE is expected to do with it | IE name, message, meaning, spec ref, UE action, range/unit | IE name \| Message \| Meaning \| Spec ref \| UE action \| Range/unit |
| `expand_sub_causes` | Fallback when code expansion is empty — need spec-defined sub-causes under a parent cause | `PARENT_CAUSE: "{{CAUSE}}"`, `PARENT_SPEC_REF: "{{REF}}"` | determine whether spec defines further sub-causes under this parent cause; if yes, list them | sub-cause exists? (y/n), cause, spec ref, gate AND/OR, IE names, message names, layer | Sub-cause exists \| Cause \| Spec ref \| Gate \| IE names \| Message names \| Layer |
| `lightweight_procedure` | Phase 1/2 scoping — need timers/expected flow, not full FTA skeleton | `NEED: is_is_not or ecf` | (if `is_is_not`) list primary layers, key timers + expiry behavior, initiating message; (if `ecf`) list expected message flow in order | varies — timer name/duration/on-expiry, OR ordered message+direction+layer | Timer \| Duration \| On-expiry — OR — Order \| Message \| Direction \| Layer |

## Placeholder reference

| Placeholder | Fill with |
|---|---|
| `{{TOP_EVENT}}` | confirmed top event string (e.g. `VoLTE_Call_Drop_Unexpected_BYE`, `5G_HO_Execution_Failure`) — or prior iteration's base_event name for iteration ≥ 2 drill-downs |
| `{{PROCEDURE}}` | `scope_filter.procedure` (e.g. `VoLTE IMS Call`, `Intra-AMF 5G Handover`, `LTE Initial Attach`) |
| `{{RAT}}` | `LTE` / `5G NR` / `UMTS` / etc. |

## Workflow

1. Pick the operation row matching what you need.
2. Copy the master template.
3. Fill `{{TOP_EVENT}}` / `{{PROCEDURE}}` / `{{RAT}}` / `{{EXTRA_PARAMS}}` from the state file.
4. Fill `{{TASK_INSTRUCTION}}` / `{{OUTPUT_FIELDS}}` / `{{OUTPUT_ROW_FORMAT}}` from the row.
5. Paste into NotebookLM.
6. Validate the result against the corresponding stdout shape in
   [`spec-operations.md`](../.cline/skills/3gpp-spec-retrieval/references/spec-operations.md)
   before trusting it as spec-anchored (real `TS XX.XXX §Y.Y` refs, verbatim
   message/IE names, no fabricated content).
