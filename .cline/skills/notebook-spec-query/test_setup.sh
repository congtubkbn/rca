#!/bin/bash
# Test setup for notebook-spec-query skill
# VoLTE call drop scenario

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEST_DIR="/tmp/notebook-spec-query-test"
NOTEBOOK_CONFIG="$TEST_DIR/notebook_config.json"

echo "=== NotebookLM Spec Query Test Setup ==="
echo ""

# Step 1: Verify notebooklm CLI
echo "[1] Verifying NotebookLM CLI..."
if ! command -v notebooklm &> /dev/null; then
    echo "ERROR: notebooklm CLI not found. Install with: pip install notebooklm-py"
    exit 1
fi

notebooklm --version
notebooklm auth check --test --json > /dev/null || {
    echo "ERROR: NotebookLM authentication failed. Run: notebooklm login"
    exit 1
}
echo "✓ NotebookLM CLI ready"
echo ""

# Step 2: Create test directory
echo "[2] Setting up test directory..."
mkdir -p "$TEST_DIR"
echo "Test directory: $TEST_DIR"
echo ""

# Step 3: Create VoLTE notebook
echo "[3] Creating VoLTE notebook..."
NOTEBOOK_ID=$(notebooklm create "RCA: VoLTE_Call_Establishment:5G_NR" --json 2>/dev/null | jq -r '.notebook.id')

if [ -z "$NOTEBOOK_ID" ] || [ "$NOTEBOOK_ID" = "null" ]; then
    echo "ERROR: Failed to create notebook"
    exit 1
fi

echo "Notebook ID: $NOTEBOOK_ID"
echo "$NOTEBOOK_ID" > "$TEST_DIR/notebook_id.txt"
echo ""

# Step 4: Add spec sources
echo "[4] Adding 3GPP spec sources to notebook..."
echo "    (This will take 5-10 minutes for indexing. Sources must reach status='ready')"
echo ""

# 3GPP specs for VoLTE
SPECS=(
    "https://pubs.3gpp.org/3gpp/specs/24229/"  # SIP signaling
    "https://pubs.3gpp.org/3gpp/specs/23228/"  # IMS architecture
    "https://pubs.3gpp.org/3gpp/specs/38331/"  # 5G RRC
    "https://pubs.3gpp.org/3gpp/specs/48171/"  # IMS Multimedia Telephony
)

for spec_url in "${SPECS[@]}"; do
    echo "  Adding: $spec_url"
    notebooklm source add "$spec_url" -n "$NOTEBOOK_ID" 2>/dev/null || {
        echo "  ⚠ Failed to add source. May be temporarily rate-limited."
    }
done

echo ""
echo "[5] Waiting for sources to be indexed..."
echo "    (Polling every 10 seconds, timeout: 600s)"

TIMEOUT=600
ELAPSED=0

while [ $ELAPSED -lt $TIMEOUT ]; do
    SOURCES_JSON=$(notebooklm source list -n "$NOTEBOOK_ID" --json 2>/dev/null || echo '{"sources":[]}')
    TOTAL=$(echo "$SOURCES_JSON" | jq '.sources | length' 2>/dev/null || echo 0)
    READY=$(echo "$SOURCES_JSON" | jq '[.sources[] | select(.status == "ready")] | length' 2>/dev/null || echo 0)

    if [ "$TOTAL" -gt 0 ]; then
        echo "  [$ELAPSED/$TIMEOUT s] $READY / $TOTAL sources ready"
    fi

    if [ "$READY" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
        echo "✓ All sources ready"
        break
    fi

    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "⚠ Timeout waiting for sources. Proceeding anyway (may affect test quality)"
fi

echo ""

# Step 6: Save notebook config
echo "[6] Saving notebook configuration..."
cat > "$NOTEBOOK_CONFIG" << EOF
{
  "notebook_id": "$NOTEBOOK_ID",
  "created_at": "$(date -Iseconds)",
  "procedure": "VoLTE_Call_Establishment",
  "rat": "5G NR",
  "top_event": "Call_Drop_During_Media",
  "sources": [
    {"url": "https://pubs.3gpp.org/3gpp/specs/24229/", "title": "TS 24.229 - SIP Signaling"},
    {"url": "https://pubs.3gpp.org/3gpp/specs/23228/", "title": "TS 23.228 - IMS Architecture"},
    {"url": "https://pubs.3gpp.org/3gpp/specs/38331/", "title": "TS 38.331 - 5G RRC"},
    {"url": "https://pubs.3gpp.org/3gpp/specs/48171/", "title": "TS 48.171 - IMS Multimedia Telephony"}
  ]
}
EOF

cat "$NOTEBOOK_CONFIG" | jq .
echo ""

# Step 7: Test query
echo "[7] Testing skeleton query..."
python3 "$SCRIPT_DIR/notebook_spec_query.py" \
    --operation skeleton \
    --procedure "VoLTE_Call_Establishment" \
    --rat "5G NR" \
    --top-event "Call_Drop_During_Media" \
    --notebook-id "$NOTEBOOK_ID" \
    --output "$TEST_DIR/skeleton_output.json" \
    --verbose

RECOMMENDATION=$(jq -r '.validation.recommendation' "$TEST_DIR/skeleton_output.json")
echo ""
echo "✓ Test query completed"
echo "  Recommendation: $RECOMMENDATION"
echo "  Output: $TEST_DIR/skeleton_output.json"
echo ""

# Step 8: Display results
echo "[8] Results Summary"
echo "===================="
jq '.validation' "$TEST_DIR/skeleton_output.json"
echo ""
echo "Phases extracted:"
jq '.phases[] | {id, name, protocol_layer, spec_ref}' "$TEST_DIR/skeleton_output.json"
echo ""

# Step 9: Next steps
echo "[9] Next Steps"
echo "=============="
echo ""
echo "To test Phase 3.1 with this notebook:"
echo ""
echo "  NOTEBOOK_ID='$NOTEBOOK_ID'"
echo ""
echo "  python3 $SCRIPT_DIR/notebook_spec_query.py \\"
echo "    --operation skeleton \\"
echo "    --procedure 'VoLTE_Call_Establishment' \\"
echo "    --rat '5G NR' \\"
echo "    --top-event 'Call_Drop_During_Media' \\"
echo "    --notebook-id \"\$NOTEBOOK_ID\""
echo ""
echo "Configuration saved:"
echo "  $NOTEBOOK_CONFIG"
echo ""
echo "Test output:"
echo "  $TEST_DIR/skeleton_output.json"
echo ""

if [ "$RECOMMENDATION" = "ACCEPT" ]; then
    echo "✓ Notebook output ACCEPTED"
    echo "Ready to integrate into Phase 3.1 skill"
else
    echo "⚠ Notebook output REJECTED"
    echo "Validation failed. Check issues above."
    echo "May need to:"
    echo "  - Wait longer for source indexing"
    echo "  - Refine NotebookLM query prompt"
    echo "  - Use fallback to spec_query.py"
fi

echo ""
