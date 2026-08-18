---
name: notebook-spec-query
description: >
  Replaces spec_query.py with NotebookLM for 3GPP spec retrieval.
  Supports skeleton (Phase 3.1 phases) and generate_hypotheses (fallback).
  Uses NotebookLM CLI to query indexed 3GPP specifications instead of GraphRAG.
  Validates output against spec anchors, structure, content relevance before acceptance.
  Fallback: uses spec_query.py if notebook validation fails.
  Triggers: "notebook spec query", "query notebook for phases", "use notebooklm for spec",
  "get phases from notebook", "notebooklm skeleton".
---

# NotebookLM Spec Query Skill

## Role

Replace `spec_query.py` tool with NotebookLM for retrieving standardized 3GPP procedure phases.
Eliminates dependency on local GraphRAG; uses cloud NotebookLM for flexibility and broader spec coverage.

## Operations

### Operation: `skeleton` (Phase 3.1 — Build Hybrid Fault Tree)

**Purpose:** Retrieve standardized procedural phases from 3GPP specs for a given procedure.

**Inputs:**
```json
{
  "operation": "skeleton",
  "procedure": "VoLTE_Call_Establishment",
  "rat": "5G NR",
  "top_event": "Call_Drop_During_Media",
  "notebook_id": "abc123..."  // from state file meta.notebook_ids[procedure:rat]
}
```

**Output (JSON, same as spec_query.py):**
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
      "mandatory_messages": ["INVITE", "100 Trying", "180 Ringing", "200 OK"],
      "protocol_layer": "SIP"
    },
    {
      "id": "P2",
      "name": "RTP_Stream_Establishment",
      "spec_ref": "TS 3GPP TS 48.171 §6.2",
      "mandatory_messages": ["INVITE with SDP", "200 OK with SDP"],
      "protocol_layer": "MEDIA"
    },
    {
      "id": "P3",
      "name": "RRC_Bearer_Setup",
      "spec_ref": "TS 38.331 §5.3.5",
      "mandatory_messages": ["RRCReconfiguration"],
      "protocol_layer": "RRC"
    }
  ],
  "gate_at_top": "OR",
  "source": "notebooklm",
  "validation": {
    "structure_valid": true,
    "content_score": 0.85,
    "spec_anchors_valid": 3,
    "hallucination_risk": false,
    "recommendation": "ACCEPT"
  }
}
```

**Execution Steps:**

1. **Check preconditions:**
   - `operation == "skeleton"`
   - `procedure`, `rat`, `top_event` provided
   - `meta.notebook_ids["{procedure}:{rat}"]` exists (notebook already created & indexed)

2. **Query NotebookLM:**
   ```bash
   notebooklm ask "For {procedure} with top_event '{top_event}' in {rat},
                  identify main procedural phases. Return as JSON with:
                  P#, name, TS ref (TS XX.XXX §Y), protocol_layer, mandatory_messages" \
     -n {notebook_id} --json
   ```

3. **Parse response:**
   - Extract phases from natural language
   - Regex: `P(\d+) (\w+).*TS\s+(\d+\.\d+\s+§[\d.]+).*(?:protocol|layer):\s*(\w+)`
   - Build phases array

4. **Validate (critical):**
   - Structure: ≥3 phases, all have id/name/spec_ref/protocol_layer
   - Spec refs: match TS XX.XXX §Y.Y.Z pattern, TS number in valid 3GPP range
   - Citations: phase has backing from notebook source (check references in response)
   - Content: for VoLTE must include SIP + RTP + RRC layers (scenario-specific)
   - Hallucination risk: if citations absent or too few, flag risk

5. **Decision:**
   - If all validation passes + content_score ≥ 0.75: return phases, set `recommendation: ACCEPT`
   - Else: fall back to `spec_query.py --operation skeleton`, set `recommendation: FALLBACK`

6. **Write to state file:**
   ```json
   {
     "phase3_hybrid_tree": {
       "spec_skeleton_source": {...phases...},
       "validation_result": {...validation...},
       "source": "notebooklm" | "spec_query_fallback"
     }
   }
   ```

---

### Operation: `generate_hypotheses` (Phase 3.1 Fallback — iterations ≥ 2)

**Purpose:** Generate hypothetical failure causes when spec skeleton is empty (expected for iteration ≥ 2).

**Inputs:**
```json
{
  "operation": "generate_hypotheses",
  "event": "Timer_Expiry",
  "procedure": "VoLTE_Call_Establishment",
  "rat": "5G NR",
  "notebook_id": "abc123..."
}
```

**Output (same as spec_query.py):**
```json
{
  "operation": "generate_hypotheses",
  "event": "Timer_Expiry",
  "hypotheses": [
    {
      "id": "H1",
      "name": "Timer_Not_Started",
      "reasoning": "Based on code patterns, timer may not be armed correctly"
    },
    {
      "id": "H2",
      "name": "Timer_Fired_Before_Expiry",
      "reasoning": "Clock drift or premature expiration"
    }
  ]
}
```

**Execution:**
1. Query NotebookLM: "For {event}, what are hypothetical failure causes in {procedure}?"
2. Parse hypotheses (less structured than skeleton, accept narrative)
3. Validate: ≥2 hypotheses, citations present
4. Return or fallback to `spec_query.py`

---

## Preconditions

### NotebookLM Setup (One-Time)

Before using this skill, prepare notebooks:

```bash
# Create notebook for each procedure:rat pair
NOTEBOOK_ID=$(notebooklm create "RCA: {Procedure}:{RAT}" --json | jq -r '.notebook.id')

# Add 3GPP spec sources (must be indexed before skill runs)
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/24229/" -n "$NOTEBOOK_ID"  # SIP
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/23228/" -n "$NOTEBOOK_ID"  # IMS arch
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/38331/" -n "$NOTEBOOK_ID"  # 5G RRC
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/48171/" -n "$NOTEBOOK_ID"  # IMS Telephony

# Wait for all sources to be ready
notebooklm source list -n "$NOTEBOOK_ID" --json | jq '.sources[] | select(.status != "ready")'

# Store notebook ID in state file
# meta.notebook_ids["VoLTE_Call_Establishment:5G_NR"] = "$NOTEBOOK_ID"
```

### State File Expectations

**meta section:**
```json
{
  "notebook_ids": {
    "VoLTE_Call_Establishment:5G_NR": "abc123-notebook-id",
    "LTE_Initial_Attach:LTE": "def456-notebook-id"
  },
  "tool_dir": "/workspace/3gpp-tools",
  "validation_thresholds": {
    "content_score_min": 0.75,
    "min_phases": 3,
    "spec_anchor_tolerance": 0.0
  }
}
```

**phase1_scope_filter (input):**
```json
{
  "procedure": "VoLTE_Call_Establishment",
  "rat": "5G NR"
}
```

---

## Implementation (Pseudocode)

```python
def query_notebook_for_phases(operation, procedure, rat, top_event, notebook_id):
    """
    Query NotebookLM and validate output.
    Returns: (phases_list, validation_result, recommendation)
    """
    
    # 1. Build query based on operation
    if operation == "skeleton":
        query = f"""
        For the 3GPP procedure '{procedure}' with top_event '{top_event}' in {rat},
        identify the main procedural phases that should be analyzed.
        Return phases in logical sequence, from initiation through completion.
        
        For each phase provide:
        1. Phase ID (P1, P2, P3, ...)
        2. Phase name (brief, no spaces)
        3. 3GPP spec reference (format: TS XX.XXX §Y.Y.Z)
        4. Protocol layer (SIP, RTP, RRC, IMS-NAS, MEDIA, PDCP, etc.)
        5. Mandatory messages in that phase
        6. Brief explanation of why this phase could cause '{top_event}'
        
        Format clearly so each phase is identifiable.
        """
    else:  # generate_hypotheses
        query = f"""
        For the event '{top_event}' in procedure '{procedure}' ({rat}),
        generate 3-5 hypothetical failure causes based on code and spec patterns.
        
        For each hypothesis:
        1. ID (H1, H2, ...)
        2. Name
        3. Reasoning (why this could cause the event)
        4. Spec/code evidence if available
        """
    
    # 2. Query NotebookLM
    response = notebooklm_ask(query, notebook_id)
    answer_text = response["answer"]
    references = response.get("references", [])
    
    # 3. Extract phases/hypotheses from text
    if operation == "skeleton":
        phases = extract_phases_via_regex(answer_text)
    else:
        phases = extract_hypotheses_via_regex(answer_text)
    
    # 4. Validate
    validation = {
        "structure_valid": validate_structure(phases),
        "spec_refs_valid": count_valid_spec_refs(phases),
        "spec_anchors_valid": len(references) if references else 0,
        "content_score": validate_content_relevance(phases, procedure, rat),
        "hallucination_risk": len(references) == 0,
        "issues": []
    }
    
    # 5. Decision
    if (validation["structure_valid"] and 
        validation["content_score"] >= 0.75 and
        not validation["hallucination_risk"]):
        recommendation = "ACCEPT"
    else:
        recommendation = "FALLBACK"
        # Will use spec_query.py --operation {operation} as fallback
    
    validation["recommendation"] = recommendation
    
    return phases, validation, recommendation


def validate_content_relevance(phases, procedure, rat):
    """
    Score phases for relevance to procedure+RAT combination.
    Returns: 0.0 - 1.0
    """
    
    if "VoLTE" in procedure or "IMS" in procedure:
        required = {"SIP", "RTP", "RRC", "MEDIA"}  # VoLTE layers
    elif "5G" in rat:
        required = {"RRC", "NAS", "PDCP"}
    else:
        return 1.0  # Accept all for unknown procedures
    
    found_layers = {p["protocol_layer"] for p in phases}
    score = len(required & found_layers) / len(required) if required else 1.0
    
    return score
```

---

## Fallback to spec_query.py

If NotebookLM validation fails (recommendation == "FALLBACK"):

```bash
# Fallback command
python3 {meta.tool_dir}/spec_query.py \
  --operation {operation} \
  --procedure "{procedure}" \
  --rat "{rat}" \
  --top-event "{top_event}" \
  --state-file {state_file_path}

# Log in state file
{
  "phase3_hybrid_tree": {
    "source": "spec_query_fallback",
    "reason": "NotebookLM validation failed: {validation.issues}",
    "fallback_triggered_at": <ISO timestamp>
  }
}
```

---

## Audit Trail

Every operation writes to `keyword_provenance_audit[]`:

```json
{
  "operation_id": "<uuid>",
  "operation": "skeleton",
  "procedure": "VoLTE_Call_Establishment",
  "rat": "5G NR",
  "notebook_id": "abc123...",
  "source": "notebooklm" | "spec_query_fallback",
  "phases_returned": 3,
  "validation_recommendation": "ACCEPT" | "FALLBACK",
  "timestamp": "<ISO>",
  "notebook_sources": [
    {"source_id": "...", "title": "TS 24.229", "status": "ready"}
  ]
}
```

---

## Testing Checklist

- [ ] Notebook created with VoLTE specs (TS 24.229, 23.228, 38.331, 48.171)
- [ ] All sources indexed (status="ready")
- [ ] Query returns ≥3 phases with SIP + RTP + RRC layers
- [ ] Spec refs match TS XX.XXX §Y.Y.Z pattern
- [ ] Citations present (no hallucination)
- [ ] Output matches or exceeds spec_query baseline
- [ ] Fallback triggers on invalid output
- [ ] State file updated correctly
- [ ] Audit trail recorded

---

## Known Limitations

- Requires NotebookLM account + CLI setup
- Source indexing can take 5-30 min per spec PDF
- Rate limiting possible on NotebookLM query (retry after 5-10 min)
- Regex extraction less robust than structured parsing (future: ask for JSON directly)
- Procedure-specific content validation rules are hardcoded (need lookup table for scale)

---

## Future Improvements

- Direct JSON response from NotebookLM (ask for `--json-output`)
- Caching layer (procedure:rat → phases cache, 24h TTL)
- Multi-notebook strategy (split by protocol layer)
- Automated notebook setup + spec ingestion
- Confidence scoring per phase

