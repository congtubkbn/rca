# Log Query Operations Reference

Detailed reference for `log_query.py` invocations across all phase tags.

## Phase Tag Validation (HARD STOP at script entry)

```python
ALLOWED_COMBINATIONS = {
  "phase1":          {"UE_3gpp_signaling_log"},
  "phase2":          {"UE_3gpp_signaling_log"},
  "phase3_gate_a":   {"UE_3gpp_signaling_log"},
  "phase3_gate_b":   {"UE_Trace_log"},
  "phase3_cross_ref": {"UE_3gpp_signaling_log", "UE_Trace_log"},
}
```

If `(phase_tag, table)` not in the allowed set → exit 3 with policy violation.

## Per-Phase Query Patterns

### Phase 1 Sanity Check (signaling)
SQL pattern:
```sql
SELECT COUNT(*) AS n, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts
FROM UE_3gpp_signaling_log
WHERE procedure = ? AND timestamp BETWEEN ? AND ?
```

Returns: count, first_ts, last_ts. Used for sanity-check confirmation only.

### Phase 2 Timeline (signaling)
SQL pattern:
```sql
SELECT timestamp, layer, direction, message_name, cause_code, ie_values
FROM UE_3gpp_signaling_log
WHERE layer IN (?) AND timestamp BETWEEN ? AND ?
ORDER BY timestamp
LIMIT 50
```

Returns: up to 50 rows for timeline classification.

### Phase 3 Gate A (signaling, hypothesis-targeted)
SQL pattern:
```sql
SELECT timestamp, layer, direction, message_name, ie_values, cause_code
FROM UE_3gpp_signaling_log
WHERE message_name IN (?)
  AND timestamp BETWEEN ? AND ?
  AND (
    JSON_HAS_ANY_KEY(ie_values, ?) OR
    cause_code IN (?)
  )
LIMIT 20
```

### Phase 3 Gate B (trace, hypothesis-targeted)
SQL pattern:
```sql
SELECT timestamp, log_tag, message
FROM UE_Trace_log
WHERE log_tag IN (?)
  AND (message LIKE '%kw1%' OR message LIKE '%kw2%' OR ...)
  AND timestamp BETWEEN ? AND ?
LIMIT 50
```

Keywords come from `failure_mode.log_keywords` (macro literals).

### Phase 3 Cross-Ref Signaling (commanded value extraction)
SQL pattern:
```sql
SELECT timestamp, message_name,
       JSON_EXTRACT(ie_values, '$.' || ?) AS ie_value
FROM UE_3gpp_signaling_log
WHERE message_name IN (?)
  AND timestamp BETWEEN ? AND ?
ORDER BY timestamp
LIMIT 10
```

With `--return-ie-values true`, the script also populates
`ie_value_extractions[]` parsing the `ie_value` column.

### Phase 3 Cross-Ref Trace (actual value extraction)
SQL pattern:
```sql
SELECT timestamp, log_tag, message
FROM UE_Trace_log
WHERE log_tag IN (?)
  AND message LIKE ANY (?)
  AND timestamp BETWEEN ? AND ?
ORDER BY timestamp
LIMIT 10
```

With `--return-ie-values true`, the script parses numeric values from the
`message` column using patterns like `-?\d+(\.\d+)? dBm`, `-?\d+ ms`, etc.
The expected unit comes from the spec sub-agent's Mode 6 response.

---

## Argument Reference

### Required args (all invocations)
- `--phase-tag` — one of phase1, phase2, phase3_gate_a, phase3_gate_b, phase3_cross_ref
- `--table` — UE_3gpp_signaling_log or UE_Trace_log
- `--keywords` — at least one keyword (script refuses empty)
- `--state-file` — path to active state file

### Optional args
- `--ie-names` — array; filters on IE keys present in ie_values JSON column
- `--log-tags` — array; restricts trace queries to specific log_tag values
- `--time-window-start-ms` and `--time-window-end-ms` — filter timestamps
- `--layers` — array; restricts signaling queries to specific layers
- `--hypothesis-id` — for state-file routing (which branch/child to update)
- `--return-ie-values` — boolean; enables value extraction for cross-ref
- `--max-tokens` — stdout token budget (default 1500)

### Required state-file updates per phase

| phase_tag | State-file path updated |
|---|---|
| phase1 | `phase1_scope_filter.signaling_sanity_check` |
| phase2 | `phase2_ecf.observable_symptoms.events[]` |
| phase3_gate_a | `phase3_hybrid_tree.branches[<hyp_id>].gate_a_result` |
| phase3_gate_b | `phase3_hybrid_tree.branches[*].children[<hyp_id>].gate_b_result` |
| phase3_cross_ref signaling | `phase3_cross_reference_findings[<hyp_id>].commanded_value` |
| phase3_cross_ref trace | `phase3_cross_reference_findings[<hyp_id>].actual_value` |

---

## Compression Rules

The script returns:
- Up to **5 key_events** in `key_events[]` (most representative)
- `evidence_summary`: one-sentence prose
- `keywords_with_hits` / `keywords_missed`: which input keywords got results

Raw rows beyond the 5 keepers are discarded — they do NOT cross the script
boundary. This keeps each invocation under the token budget.

---

## Anti-hallucination (enforced by script)

- Script refuses empty `--keywords`
- Auto-appends every input keyword to `keyword_provenance_audit` with
  `source: "3gpp-log-queries <phase_tag>"` and references which prior
  tool invocation produced the keyword (from the audit chain)
- Never returns rows that don't exist in the DB — empty result is empty
- `return_ie_values` extraction uses ONLY data present in the row; if no
  numeric value matches the pattern → `ie_value_extractions: []`
