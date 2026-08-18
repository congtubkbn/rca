# NotebookLM Spec Query — Quickstart

**Test notebook-spec-query skill for Phase 3.1 with VoLTE call drop scenario.**

---

## Prerequisites

```bash
# 1. Verify notebooklm CLI installed
notebooklm --version

# 2. Verify auth
notebooklm auth check --test --json

# If auth fails:
notebooklm login    # Opens browser
```

---

## Step 1: Create & Setup Notebook (One-Time, ~15 min)

```bash
cd .cline/skills/notebook-spec-query

# Run setup script (creates notebook, adds specs, waits for indexing)
bash test_setup.sh
```

**What it does:**
1. Creates NotebookLM notebook: "RCA: VoLTE_Call_Establishment:5G_NR"
2. Adds 4 3GPP specs (TS 24.229, 23.228, 38.331, 48.171)
3. Waits for indexing (shows progress)
4. Tests skeleton query for VoLTE call drop
5. Saves notebook ID to `/tmp/notebook-spec-query-test/notebook_id.txt`

**Expected output:**
```
✓ NotebookLM CLI ready
✓ Notebook ID: abc123-def456-...
✓ All sources ready
✓ Test query completed
  Recommendation: ACCEPT
  Output: /tmp/notebook-spec-query-test/skeleton_output.json
```

**Save this ID:**
```bash
NOTEBOOK_ID=$(cat /tmp/notebook-spec-query-test/notebook_id.txt)
echo $NOTEBOOK_ID
```

---

## Step 2: Test Skeleton Query Manually

```bash
NOTEBOOK_ID="<from Step 1>"

python3 notebook_spec_query.py \
  --operation skeleton \
  --procedure "VoLTE_Call_Establishment" \
  --rat "5G NR" \
  --top-event "Call_Drop_During_Media" \
  --notebook-id "$NOTEBOOK_ID" \
  --output /tmp/test_skeleton.json \
  --verbose
```

**Check result:**
```bash
# Display recommendation
jq '.validation.recommendation' /tmp/test_skeleton.json

# Display phases extracted
jq '.phases[] | {id, name, protocol_layer}' /tmp/test_skeleton.json

# Full validation
jq '.validation' /tmp/test_skeleton.json
```

**Expected validation:**
```json
{
  "structure_valid": true,
  "spec_refs_valid": 3,
  "spec_anchors_valid": 3,
  "content_score": 0.85,
  "hallucination_risk": false,
  "recommendation": "ACCEPT"
}
```

---

## Step 3: Compare with spec_query.py

```bash
NOTEBOOK_ID="<from Step 1>"

bash compare_with_spec_query.sh
```

**What it does:**
1. Runs notebook-spec-query skeleton query
2. Runs spec_query.py skeleton query (if available)
3. Compares phase names, counts, layers
4. Shows agreement score

**Expected output:**
```
[1] Query notebook-spec-query...
✓ notebook-spec-query completed
  Recommendation: ACCEPT
  Phases: 4

[2] Query spec_query.py (baseline)...
✓ spec_query.py completed
  Phases: 4

[3] Comparison
Phase count:
  NotebookLM: 4
  spec_query: 4
  ✓ Phase names match (content alignment)
```

---

## Step 4: Test Fallback Scenarios

### Test Content Validation (Deliberately Low Score)

Query with **wrong procedure** to trigger FALLBACK:

```bash
NOTEBOOK_ID="<from Step 1>"

python3 notebook_spec_query.py \
  --operation skeleton \
  --procedure "Billing_Procedure" \
  --rat "5G NR" \
  --top-event "Invoice_Error" \
  --notebook-id "$NOTEBOOK_ID"
```

**Expected:** FALLBACK (off-topic procedure, missing required layers)

### Test Hypotheses Fallback (Iteration ≥ 2)

```bash
NOTEBOOK_ID="<from Step 1>"

python3 notebook_spec_query.py \
  --operation generate_hypotheses \
  --event "Timer_Expiry" \
  --procedure "VoLTE_Call_Establishment" \
  --rat "5G NR" \
  --notebook-id "$NOTEBOOK_ID"
```

**Expected:** ACCEPT (hypotheses generated, ≥2 items)

---

## Step 5: Integrate into Phase 3.1

### Option A: Manual Integration (For Testing)

In Phase 3.1 skill (3gpp-fta-build-tree), replace spec_query call with:

```bash
# Instead of:
# python3 3gpp-tools/spec_query.py --operation skeleton ...

# Use:
NOTEBOOK_ID="<save this in state file meta.notebook_ids>"

python3 .cline/skills/notebook-spec-query/notebook_spec_query.py \
  --operation skeleton \
  --procedure "$PROCEDURE" \
  --rat "$RAT" \
  --top-event "$TOP_EVENT" \
  --notebook-id "$NOTEBOOK_ID" \
  --output /tmp/skeleton.json

RECOMMENDATION=$(jq -r '.validation.recommendation' /tmp/skeleton.json)

if [ "$RECOMMENDATION" = "ACCEPT" ]; then
  echo "Using NotebookLM phases"
  PHASES=$(jq '.phases' /tmp/skeleton.json)
else
  echo "Falling back to spec_query.py"
  python3 3gpp-tools/spec_query.py --operation skeleton ...
fi
```

### Option B: Replace Spec Query Calls

In Phase 3.1 skill pseudocode, change:

```python
# From:
phases = spec_query.py("skeleton", procedure, rat, top_event)

# To:
result = notebook_spec_query.py("skeleton", procedure, rat, top_event, notebook_id)
if result.recommendation == "ACCEPT":
  phases = result.phases
else:
  phases = spec_query.py("skeleton", ...)  # Fallback
```

---

## Step 6: Monitor & Measure

Track acceptance rate over multiple procedures:

```bash
# Create metrics log
METRICS_FILE=~/.notebooklm/phase31_metrics.txt

# After each test, log result
for procedure in "VoLTE_Call_Establishment" "LTE_Initial_Attach"; do
  RESULT=$(python3 notebook_spec_query.py \
    --operation skeleton \
    --procedure "$procedure" \
    --rat "5G NR" \
    --top-event "Generic_Failure" \
    --notebook-id "$NOTEBOOK_ID" | \
    jq -r '.validation.recommendation')

  echo "$(date) | $procedure | $RESULT" >> $METRICS_FILE
done

# Check acceptance rate
grep -c "ACCEPT" $METRICS_FILE
grep -c "FALLBACK" $METRICS_FILE
```

**Target:** ≥80% ACCEPT rate

---

## Step 7: Scale to Multiple Scenarios

Create separate notebooks for different procedures:

```bash
# For LTE Initial Attach
NOTEBOOK_ID_LTE=$(notebooklm create "RCA: LTE_Initial_Attach:LTE" --json | jq -r '.notebook.id')
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/24301/" -n "$NOTEBOOK_ID_LTE"  # NAS
# ... wait for indexing

# For 5G Handover
NOTEBOOK_ID_HO=$(notebooklm create "RCA: 5G_Handover:5G_NR" --json | jq -r '.notebook.id')
notebooklm source add "https://pubs.3gpp.org/3gpp/specs/38331/" -n "$NOTEBOOK_ID_HO"  # RRC
# ... wait for indexing

# Store in state file meta.notebook_ids
cat > ~/.notebooklm/notebooks.json << EOF
{
  "VoLTE_Call_Establishment:5G_NR": "$NOTEBOOK_ID_VOLTE",
  "LTE_Initial_Attach:LTE": "$NOTEBOOK_ID_LTE",
  "5G_Handover:5G_NR": "$NOTEBOOK_ID_HO"
}
EOF
```

---

## Troubleshooting

### Test Setup Fails

**Problem:** `notebooklm: command not found`
```bash
pip install notebooklm-py[browser]
notebooklm login
```

**Problem:** Auth error
```bash
notebooklm auth check --test --json
# Shows cookie issue → re-login
notebooklm login
```

**Problem:** Source indexing stuck
```bash
# Check status
notebooklm source list -n "$NOTEBOOK_ID" --json | jq '.sources[] | {title, status}'

# Wait longer (can take 10-30 min for large PDFs)
# Or try a different spec URL
```

### Skeleton Query Returns FALLBACK

**Problem:** `content_score` < 0.75
```bash
jq '.validation.issues[]' /tmp/result.json | grep "Missing"
# Check which required layers are missing
```

**Solution:**
- Ensure sources indexed before query
- Refine query prompt for clarity
- Use scenario-specific procedures (VoLTE vs 5G vs LTE)

**Problem:** `hallucination_risk` = true
```bash
jq '.validation.spec_anchors_hallucinated' /tmp/result.json
# Phases not cited to sources
```

**Solution:**
- Wait for source indexing to complete
- Retry query
- Check notebook sources: `notebooklm source list -n "$NOTEBOOK_ID"`

### Phase Names Don't Match spec_query.py

This is acceptable if:
- Phase count is same
- All required layers present
- Spec refs are valid

Different names = different phrasing from spec (not wrong).

**To force match:** Refine NotebookLM query with example phase names.

---

## Files Overview

| File | Purpose | When to Use |
|------|---------|-----------|
| `test_setup.sh` | One-time notebook creation & setup | `bash test_setup.sh` |
| `notebook_spec_query.py` | Core query + validate logic | Called by Phase 3.1 |
| `compare_with_spec_query.sh` | Benchmark against spec_query.py | `bash compare_with_spec_query.sh` |
| `SKILL.md` | Full specification | Reference doc |
| `README.md` | Detailed user guide | Setup / troubleshooting |
| `QUICKSTART.md` | This file | Quick walkthrough |

---

## Next Steps

1. ✓ Run `test_setup.sh` (creates notebook)
2. ✓ Test skeleton query manually
3. ✓ Compare with spec_query.py
4. ✓ Verify recommendation = ACCEPT
5. → Integrate into Phase 3.1 skill
6. → Test Phase 3.1 end-to-end with VoLTE call drop
7. → Scale to other procedures (LTE, handover, etc.)
8. → Monitor metrics over time

---

## Questions?

- Check README.md for detailed docs
- Check SKILL.md for specifications
- Review validation output: `jq .validation /tmp/result.json`
- Test with `--verbose` flag: `python3 notebook_spec_query.py --verbose ...`

---

**Ready to start?**

```bash
cd .cline/skills/notebook-spec-query
bash test_setup.sh
```

Estimated time: **15 minutes** (mostly waiting for source indexing)

