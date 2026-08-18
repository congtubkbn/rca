# notebook-spec-query Skill

**Replace `spec_query.py` GraphRAG with NotebookLM for 3GPP spec retrieval.**

Retrieves procedural phases from 3GPP specifications using Google NotebookLM instead of local Python GraphRAG tool.
Supports Phase 3.1 (skeleton) and fallback (generate_hypotheses).
Includes validation layer to ensure output quality before acceptance.

---

## Quick Start

### 1. Verify NotebookLM CLI

```bash
notebooklm --version
notebooklm auth check --test --json
# If auth fails: notebooklm login
```

### 2. Run Test Setup

```bash
cd .cline/skills/notebook-spec-query
bash test_setup.sh
```

This will:
- Create a NotebookLM notebook ("RCA: VoLTE_Call_Establishment:5G_NR")
- Add 4 3GPP specs (TS 24.229, 23.228, 38.331, 48.171)
- Wait for indexing (5-10 min)
- Test skeleton query for VoLTE call drop
- Display results with recommendation (ACCEPT or FALLBACK)

### 3. Test Skeleton Query Manually

```bash
NOTEBOOK_ID="<from test_setup output>"

python3 notebook_spec_query.py \
  --operation skeleton \
  --procedure "VoLTE_Call_Establishment" \
  --rat "5G NR" \
  --top-event "Call_Drop_During_Media" \
  --notebook-id "$NOTEBOOK_ID" \
  --output /tmp/result.json \
  --verbose

# Check recommendation
jq '.validation.recommendation' /tmp/result.json
```

### 4. Integrate into Phase 3.1 Skill

Once test passes (recommendation="ACCEPT"), use in Phase 3.1:

```bash
# In 3gpp-fta-build-tree SKILL.md Step 2, replace:
python3 3gpp-tools/spec_query.py --operation skeleton ...

# With:
python3 .cline/skills/notebook-spec-query/notebook_spec_query.py \
  --operation skeleton \
  --procedure "$PROCEDURE" \
  --rat "$RAT" \
  --top-event "$TOP_EVENT" \
  --notebook-id "$NOTEBOOK_ID" \
  --output /tmp/skeleton.json

RECOMMENDATION=$(jq -r '.validation.recommendation' /tmp/skeleton.json)
if [ "$RECOMMENDATION" = "ACCEPT" ]; then
  # Use NotebookLM output
  PHASES=$(jq '.phases' /tmp/skeleton.json)
else
  # Fallback to spec_query
  python3 3gpp-tools/spec_query.py --operation skeleton ...
fi
```

---

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill definition & specification |
| `notebook_spec_query.py` | Python implementation (query + validate) |
| `test_setup.sh` | One-time test setup (create notebook, add specs, verify) |
| `README.md` | This file |

---

## Supported Operations

### `skeleton` — Phase 3.1 Procedure Phases

Query 3GPP spec for standardized procedural phases of a procedure.

**Command:**
```bash
python3 notebook_spec_query.py \
  --operation skeleton \
  --procedure "VoLTE_Call_Establishment" \
  --rat "5G NR" \
  --top-event "Call_Drop_During_Media" \
  --notebook-id "abc123-notebook-id" \
  --output /tmp/phases.json
```

**Output:**
```json
{
  "operation": "skeleton",
  "procedure": "VoLTE_Call_Establishment",
  "rat": "5G NR",
  "phases": [
    {
      "id": "P1",
      "name": "SIP_INVITE_Exchange",
      "spec_ref": "TS 24.229 §6.1.1",
      "protocol_layer": "SIP",
      "mandatory_messages": ["INVITE", "100 Trying", "180 Ringing", "200 OK"]
    },
    {
      "id": "P2",
      "name": "RTP_Stream_Establishment",
      "spec_ref": "TS 48.171 §6.2",
      "protocol_layer": "MEDIA",
      "mandatory_messages": ["INVITE with SDP", "200 OK with SDP"]
    },
    ...
  ],
  "gate_at_top": "OR",
  "source": "notebooklm",
  "validation": {
    "structure_valid": true,
    "spec_refs_valid": 3,
    "spec_anchors_valid": 3,
    "content_score": 0.85,
    "hallucination_risk": false,
    "recommendation": "ACCEPT"
  }
}
```

**Exit codes:**
- 0: Success + ACCEPT recommendation
- 1: Success + FALLBACK recommendation (validation failed)
- 2: Error (query failed)

### `generate_hypotheses` — Phase 3.1 Fallback (Iterations ≥ 2)

Generate hypothetical failure causes when spec skeleton is empty.

**Command:**
```bash
python3 notebook_spec_query.py \
  --operation generate_hypotheses \
  --event "Timer_Expiry" \
  --procedure "VoLTE_Call_Establishment" \
  --rat "5G NR" \
  --notebook-id "abc123..."
```

**Output:**
```json
{
  "operation": "generate_hypotheses",
  "event": "Timer_Expiry",
  "procedure": "VoLTE_Call_Establishment",
  "hypotheses": [
    {
      "id": "H1",
      "name": "Timer_Not_Armed",
      "reasoning": "..."
    },
    ...
  ],
  "source": "notebooklm",
  "validation": {
    "structure_valid": true,
    "hallucination_risk": false,
    "recommendation": "ACCEPT"
  }
}
```

---

## Validation Logic

Output is accepted only if **all** conditions pass:

1. **Structure Valid**
   - ≥2 items (phases or hypotheses)
   - Each has id, name, (spec_ref for phases)

2. **Spec References Valid** (phases only)
   - Format: TS XX.XXX §Y.Y.Z
   - TS number in valid 3GPP range (23.228, 24.229, 38.331, etc.)

3. **Spec Anchors Valid**
   - Citations present in NotebookLM response
   - No hallucination risk (spec refs from real sources)

4. **Content Score ≥ 0.75**
   - For VoLTE: must include SIP + RTP + RRC layers
   - For 5G: must include RRC + NAS + PDCP
   - Scenario-specific layer requirements

**If any condition fails → FALLBACK recommendation → use `spec_query.py`**

---

## Scenario-Specific Requirements

### VoLTE Procedures
**Required layers:** SIP, RTP, RRC, MEDIA
**Optional:** IKEv2, PDCP
**Rejection:** Billing, Charging, Subscriber (off-topic)

### 5G Procedures
**Required layers:** RRC, NAS, PDCP
**Optional:** PHY, MAC

### LTE Procedures
**Required layers:** RRC, NAS, PDCP
**Optional:** PHY, MAC

---

## Notebook Setup

### Create Notebook

```bash
NOTEBOOK_ID=$(notebooklm create "RCA: {Procedure}:{RAT}" --json | jq -r '.notebook.id')
echo "$NOTEBOOK_ID"  # Save this
```

### Add Spec Sources

For VoLTE, add these 3GPP specs:

```bash
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/24229/" -n "$NOTEBOOK_ID"
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/23228/" -n "$NOTEBOOK_ID"
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/38331/" -n "$NOTEBOOK_ID"
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/48171/" -n "$NOTEBOOK_ID"
```

### Wait for Indexing

```bash
# Poll until all ready
while true; do
  READY=$(notebooklm source list -n "$NOTEBOOK_ID" --json | \
    jq '[.sources[] | select(.status == "ready")] | length')
  TOTAL=$(notebooklm source list -n "$NOTEBOOK_ID" --json | jq '.sources | length')
  echo "$READY / $TOTAL sources ready"
  
  [ "$READY" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ] && break
  sleep 10
done
```

---

## Fallback to spec_query.py

If NotebookLM validation fails (exit code 1):

```bash
# Use traditional spec_query
python3 3gpp-tools/spec_query.py \
  --operation skeleton \
  --procedure "$PROCEDURE" \
  --rat "$RAT" \
  --top-event "$TOP_EVENT" \
  --state-file /tmp/rca_state.json
```

The skill **does not** automatically fallback — Phase 3.1 skill must implement the conditional.

---

## Testing

### Unit Test: Skeleton Query

```bash
# From skill directory
python3 notebook_spec_query.py \
  --operation skeleton \
  --procedure "VoLTE_Call_Establishment" \
  --rat "5G NR" \
  --top-event "Call_Drop_During_Media" \
  --notebook-id "$NOTEBOOK_ID" \
  --output /tmp/test_skeleton.json \
  --verbose

# Check result
jq '.validation.recommendation' /tmp/test_skeleton.json
# Expected: "ACCEPT"
```

### Integrated Test: Phase 3.1 Flow

```bash
# Use in Phase 3.1 context
NOTEBOOK_ID="abc123..."

# Query
python3 .cline/skills/notebook-spec-query/notebook_spec_query.py \
  --operation skeleton \
  --procedure "VoLTE_Call_Establishment" \
  --rat "5G NR" \
  --top-event "Call_Drop_During_Media" \
  --notebook-id "$NOTEBOOK_ID" \
  > /tmp/phase31_phases.json

# Verify ACCEPT
grep -q '"recommendation": "ACCEPT"' /tmp/phase31_phases.json || {
  echo "Validation failed, falling back..."
  # ... fallback logic
}

# Use phases
PHASES=$(jq '.phases' /tmp/phase31_phases.json)
echo "Proceeding with $( echo "$PHASES" | jq length) phases"
```

---

## Troubleshooting

### NotebookLM Query Fails

**Error: "No result found for RPC ID"**
- Rate limiting. Wait 5-10 minutes and retry.

**Error: "Sources not ready"**
- Sources still indexing. Wait longer, check status:
  ```bash
  notebooklm source list -n "$NOTEBOOK_ID" --json | jq '.sources[] | {title, status}'
  ```

### Validation Fails (FALLBACK)

**Issue: Low content_score (< 0.75)**
```bash
# Check missing layers
jq '.validation.issues[]' /tmp/result.json | grep "Missing"

# Solution: Refine notebook or query prompt
```

**Issue: hallucination_risk = true**
```bash
# Phase has no citation from notebook sources
jq '.validation.issues[]' /tmp/result.json | grep "anchor"

# Solution: Ensure sources are indexed before query
```

**Issue: Malformed spec refs**
```bash
jq '.validation.issues[]' /tmp/result.json | grep "malformed"

# Solution: NotebookLM grammar issue, retry or refine prompt
```

### Phases Don't Match spec_query.py

Compare outputs:

```bash
# NotebookLM
python3 notebook_spec_query.py ... | jq '.phases[] | {name, spec_ref}'

# spec_query
python3 3gpp-tools/spec_query.py --operation skeleton ... | jq '.phases[] | {name, spec_ref}'

# Should be semantically equivalent (order may differ)
```

If consistently different:
- Specs may have conflicting information
- NotebookLM query needs refinement
- Use spec_query.py as authoritative fallback

---

## Performance

| Operation | Typical Time | Notes |
|-----------|--------------|-------|
| Notebook creation | Instant | |
| Source indexing | 5-10 min | Per 3GPP spec PDF |
| Skeleton query | 30-60 sec | After sources ready |
| Validation | <1 sec | Regex + checks |

**Total setup (one-time):** ~15 minutes

---

## Metrics to Track

When integrated into Phase 3.1:

```bash
# Track success rate
echo "$(date) | VoLTE_Call_Drop | $(jq -r .validation.recommendation /tmp/result.json) | score=$(jq .validation.content_score /tmp/result.json)" >> ~/notebook_spec_query_metrics.txt

# Check acceptance rate
grep ACCEPT ~/notebook_spec_query_metrics.txt | wc -l
```

**Acceptable baseline:** ≥80% ACCEPT rate

---

## Future Improvements

- [ ] Direct JSON output from NotebookLM (ask for structured format)
- [ ] Caching layer (procedure:rat → phases, 24h TTL)
- [ ] Multi-notebook per scenario (split by protocol layer)
- [ ] Automated notebook creation + ingestion
- [ ] Confidence scoring per phase
- [ ] Parallel queries for multiple procedures
- [ ] Spec version tracking (TS revisions)

---

## Integration Checklist

- [ ] Test setup passes with ACCEPT recommendation
- [ ] Phase 3.1 skill conditionally uses notebook-spec-query
- [ ] Fallback to spec_query.py on FALLBACK recommendation
- [ ] State file records source (notebooklm vs spec_query_fallback)
- [ ] Audit trail captured in keyword_provenance_audit
- [ ] Metrics tracked over time
- [ ] Documentation updated with notebook notebook_id
- [ ] Team has access to NotebookLM account

---

## Support

For issues or improvements:
1. Check troubleshooting section above
2. Review validation output: `jq .validation /tmp/result.json`
3. Test with different procedures to isolate scenario-specific issues
4. Compare against spec_query baseline
5. File issue with metrics + output files

---

**Last Updated:** 2026-08-16
**Skill Version:** 1.0
**Status:** Beta (ready for Phase 3.1 integration testing)
