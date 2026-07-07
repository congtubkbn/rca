---
name: 3gpp-spec-retrieval
description: >
  Shared utility skill for 3GPP specification retrieval via spec_query.py. Wraps
  all six spec operations (skeleton, lightweight_procedure, extract_ies,
  find_commanded_values, generate_hypotheses, expand_sub_causes) used across the
  pipeline phases. Each invocation calls spec_query.py with --state-file so the
  script writes structured results directly to the persistent state file. Returns
  compressed JSON summary to stdout. Use whenever a phase skill needs to retrieve
  3GPP specification data — never call spec_query.py directly from phase skills.
  Triggers: "call 3GPP spec GraphRAG", "spec retrieval for ...", "extract IEs",
  "find commanded values", "build procedure skeleton", "lightweight procedure
  retrieval".
---

# 3GPP Spec Retrieval Shared Skill

## Role

Single point of entry for all 3GPP specification retrievals. Other skills
delegate to this one rather than calling `spec_query.py` directly.

## When to use this skill

Invoke from any phase skill that needs 3GPP spec data. The caller specifies
the `operation` and arguments; this skill assembles and runs the Python
command and verifies the result.

## Supported operations

| Operation | Used by | Purpose |
|---|---|---|
| `skeleton` | `3gpp-fta-build-tree` | Standardized procedure phases for hybrid tree |
| `lightweight_procedure` | `3gpp-scoping`, `3gpp-event-timeline` | Fast procedure metadata (need=is_is_not or need=ecf) |
| `extract_ies` | `3gpp-fta-evaluate-branches` | IE structure for Gate A refinement |
| `find_commanded_values` | `3gpp-fta-cross-reference` | Commanded-value IEs for cross-ref |
| `generate_hypotheses` | `3gpp-fta-build-tree` (fallback) | When skeleton unavailable |
| `expand_sub_causes` | `3gpp-fta-evaluate-branches` (fallback) | When code expansion empty |

## Invocation contract

The caller provides:
- `operation` (one of the six above)
- Operation-specific arguments
- State file path (from `<workspace>/.rca/current_state_path.txt`)

This skill:
1. Resolves `tool_dir` from state file's `meta.tool_dir`
2. Assembles the `<execute_command>` with the right flags
3. Runs the Python script
4. Verifies exit code
5. Reads stdout JSON
6. Returns it to the caller (the script itself wrote to state file)

---

## Execution templates

### Operation: skeleton

Caller args: `procedure`, `rat`, `top_event`.

```
<execute_command>
python3 ${TOOL_DIR}/spec_query.py \
  --operation skeleton \
  --procedure "<procedure>" \
  --rat "<rat>" \
  --top-event "<top_event>" \
  --state-file "<state_path>" \
  --max-tokens 1500
</execute_command>
```

Expected stdout: `{"operation": "skeleton", "phases": [...], "spec_refs": [...], ...}`

State file write: `phase3_hybrid_tree.spec_skeleton_source` and initial `phase3_hybrid_tree.branches[]`

### Operation: lightweight_procedure

Caller args: `procedure`, `rat`, `need` (one of `is_is_not` or `ecf`).

```
<execute_command>
python3 ${TOOL_DIR}/spec_query.py \
  --operation lightweight_procedure \
  --procedure "<procedure>" \
  --rat "<rat>" \
  --need <is_is_not|ecf> \
  --state-file "<state_path>" \
  --max-tokens 600
</execute_command>
```

State file write:
- `--need is_is_not` → `phase1_scope_filter.spec_lookup`
- `--need ecf` → `phase2_ecf.observable_symptoms.expected_flow_source`

### Operation: extract_ies

Caller args: `message`, `procedure`, `spec_ref`, `hypothesis_id`.

```
<execute_command>
python3 ${TOOL_DIR}/spec_query.py \
  --operation extract_ies \
  --message "<message>" \
  --procedure "<procedure>" \
  --spec-ref "<spec_ref>" \
  --hypothesis-id "<id>" \
  --state-file "<state_path>" \
  --max-tokens 800
</execute_command>
```

State file write: `phase3_evaluations[<id>].spec_ie_extraction`

### Operation: find_commanded_values

Caller args: `base_event_name`, `base_event_layer`, `upstream_messages` (array).

```
<execute_command>
python3 ${TOOL_DIR}/spec_query.py \
  --operation find_commanded_values \
  --base-event-name "<name>" \
  --base-event-layer "<layer>" \
  --upstream-messages "<msg1>" "<msg2>" ... \
  --state-file "<state_path>" \
  --max-tokens 1000
</execute_command>
```

State file write: `phase3_cross_reference_findings[<id>].commanded_ie_lookup`

### Operation: generate_hypotheses (fallback)

Caller args: `event`, `procedure`, `rat`.

```
<execute_command>
python3 ${TOOL_DIR}/spec_query.py \
  --operation generate_hypotheses \
  --event "<event>" \
  --procedure "<procedure>" \
  --rat "<rat>" \
  --state-file "<state_path>" \
  --max-tokens 2000
</execute_command>
```

Used only when skeleton fails (procedure not standardized).

### Operation: expand_sub_causes (fallback)

Caller args: `parent_cause`, `parent_spec_ref`, `procedure`.

```
<execute_command>
python3 ${TOOL_DIR}/spec_query.py \
  --operation expand_sub_causes \
  --parent-cause "<cause>" \
  --parent-spec-ref "<ref>" \
  --procedure "<procedure>" \
  --state-file "<state_path>" \
  --max-tokens 1500
</execute_command>
```

Used only when code_search.py expand_failure_modes returns empty.

---

## Error handling

| Exit code | Action |
|---|---|
| 0 | Success — return stdout JSON |
| 1 | Invalid args — bug in this skill; report and halt |
| 2 | Tool unavailable (GraphRAG endpoint down) — halt pipeline with error |
| 3 | Policy violation — should not happen for spec; report and halt |
| 4 | Empty result — return empty JSON; caller decides fallback |

Always verify exit code before passing result back. Never fabricate output.

---

## Anti-Hallucination

This skill is a thin wrapper. It does NOT interpret results, does NOT filter
output beyond returning the JSON, does NOT add commentary. The Python script
is the authority — this skill is just the dispatcher.

The script itself enforces:
- IE names verbatim in spec hyphenated notation
- Message names verbatim in spec ALL CAPS notation
- Spec refs verbatim
- `keyword_provenance_audit` auto-appended

This skill must not modify any of those values before returning.

See `references/spec-operations.md` for per-operation parameter details.
