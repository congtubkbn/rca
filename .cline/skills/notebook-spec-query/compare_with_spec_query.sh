#!/bin/bash
# Compare notebook-spec-query output with spec_query.py baseline

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/../.."
TEST_DIR="/tmp/notebook-spec-query-compare"

# Config
PROCEDURE="VoLTE_Call_Establishment"
RAT="5G NR"
TOP_EVENT="Call_Drop_During_Media"

echo "=== Comparing notebook-spec-query vs spec_query.py ==="
echo ""
echo "Scenario: $PROCEDURE ($RAT)"
echo "Top Event: $TOP_EVENT"
echo ""

# Get notebook ID
if [ -z "$NOTEBOOK_ID" ]; then
    if [ -f "/tmp/notebook-spec-query-test/notebook_id.txt" ]; then
        NOTEBOOK_ID=$(cat /tmp/notebook-spec-query-test/notebook_id.txt)
        echo "Using notebook from previous test: $NOTEBOOK_ID"
    else
        echo "ERROR: NOTEBOOK_ID not set and test notebook not found"
        echo "Run test_setup.sh first"
        exit 1
    fi
fi

mkdir -p "$TEST_DIR"

echo ""
echo "[1] Query notebook-spec-query..."
python3 "$SCRIPT_DIR/notebook_spec_query.py" \
    --operation skeleton \
    --procedure "$PROCEDURE" \
    --rat "$RAT" \
    --top-event "$TOP_EVENT" \
    --notebook-id "$NOTEBOOK_ID" \
    --output "$TEST_DIR/notebook_result.json" \
    2>/dev/null

echo "✓ notebook-spec-query completed"
NOTEBOOK_RECOMMENDATION=$(jq -r '.validation.recommendation' "$TEST_DIR/notebook_result.json")
echo "  Recommendation: $NOTEBOOK_RECOMMENDATION"
echo "  Phases: $(jq '.phases | length' "$TEST_DIR/notebook_result.json")"
echo ""

# Try spec_query.py if available
if [ -f "$PROJECT_ROOT/3gpp-tools/spec_query.py" ]; then
    echo "[2] Query spec_query.py (baseline)..."

    # Create dummy state file for spec_query
    STATE_FILE="$TEST_DIR/rca_state_dummy.json"
    cat > "$STATE_FILE" << 'EOF'
{
  "meta": {"tool_dir": "3gpp-tools"},
  "phase1_scope_filter": {}
}
EOF

    python3 "$PROJECT_ROOT/3gpp-tools/spec_query.py" \
        --operation skeleton \
        --procedure "$PROCEDURE" \
        --rat "$RAT" \
        --top-event "$TOP_EVENT" \
        --state-file "$STATE_FILE" \
        > "$TEST_DIR/spec_result.json" 2>/dev/null || {
        echo "⚠ spec_query.py failed or unavailable"
        SPEC_AVAILABLE=0
    }

    if [ -f "$TEST_DIR/spec_result.json" ]; then
        echo "✓ spec_query.py completed"
        SPEC_PHASES=$(jq '.phases | length' "$TEST_DIR/spec_result.json" 2>/dev/null || echo "?")
        echo "  Phases: $SPEC_PHASES"
        SPEC_AVAILABLE=1
        echo ""
    else
        SPEC_AVAILABLE=0
    fi
else
    echo "[2] spec_query.py not found at $PROJECT_ROOT/3gpp-tools/spec_query.py"
    echo "    Skipping baseline comparison"
    SPEC_AVAILABLE=0
    echo ""
fi

# Detailed comparison
echo "[3] Comparison"
echo "=============="
echo ""

echo "Notebook-spec-query Results:"
echo "---"
echo "Validation:"
jq '.validation | {structure_valid, spec_refs_valid, content_score, hallucination_risk, recommendation}' "$TEST_DIR/notebook_result.json"
echo ""

echo "Phases:"
jq '.phases[] | {id, name, protocol_layer, spec_ref}' "$TEST_DIR/notebook_result.json" | head -30
echo ""

if [ "$SPEC_AVAILABLE" = "1" ]; then
    echo "spec_query.py Results (Baseline):"
    echo "---"
    jq '.phases[] | {id, name, protocol_layer, spec_ref}' "$TEST_DIR/spec_result.json" | head -30
    echo ""

    # Side-by-side comparison
    echo "Side-by-Side Comparison:"
    echo "---"

    NOTEBOOK_COUNT=$(jq '.phases | length' "$TEST_DIR/notebook_result.json")
    SPEC_COUNT=$(jq '.phases | length' "$TEST_DIR/spec_result.json")

    echo "Phase count:"
    echo "  NotebookLM: $NOTEBOOK_COUNT"
    echo "  spec_query: $SPEC_COUNT"

    # Extract phase names for comparison
    NOTEBOOK_NAMES=$(jq -r '.phases[].name' "$TEST_DIR/notebook_result.json" | sort)
    SPEC_NAMES=$(jq -r '.phases[].name' "$TEST_DIR/spec_result.json" | sort)

    if [ "$NOTEBOOK_NAMES" = "$SPEC_NAMES" ]; then
        echo "  ✓ Phase names match (content alignment)"
    else
        echo "  ⚠ Phase names differ"
        echo ""
        echo "NotebookLM phases:"
        jq -r '.phases[].name' "$TEST_DIR/notebook_result.json" | nl
        echo ""
        echo "spec_query phases:"
        jq -r '.phases[].name' "$TEST_DIR/spec_result.json" | nl
    fi

    # Extract protocol layers
    NOTEBOOK_LAYERS=$(jq -r '.phases[].protocol_layer' "$TEST_DIR/notebook_result.json" | sort -u)
    SPEC_LAYERS=$(jq -r '.phases[].protocol_layer' "$TEST_DIR/spec_result.json" | sort -u)

    echo ""
    echo "Protocol layers:"
    echo "  NotebookLM: $NOTEBOOK_LAYERS"
    echo "  spec_query: $SPEC_LAYERS"

    # Check for hallucination
    NOTEBOOK_HALLUCINATION=$(jq '.validation.hallucination_risk' "$TEST_DIR/notebook_result.json")
    if [ "$NOTEBOOK_HALLUCINATION" = "true" ]; then
        echo ""
        echo "⚠ Hallucination Risk Detected in NotebookLM output"
        echo "  phases may not be cited to real spec sources"
    fi

else
    echo "Note: spec_query.py baseline not available for comparison"
    echo ""
    echo "To compare, ensure:"
    echo "  1. $PROJECT_ROOT/3gpp-tools/spec_query.py exists"
    echo "  2. 3gpp-tools/ directory accessible"
fi

# Summary
echo ""
echo "[4] Summary"
echo "==========="
echo ""

if [ "$NOTEBOOK_RECOMMENDATION" = "ACCEPT" ]; then
    echo "✓ NotebookLM output ACCEPTED"
    echo "  Quality thresholds passed. Ready for Phase 3.1 integration."
else
    echo "✗ NotebookLM output REJECTED"
    echo "  Validation failed. Check issues above."
    echo "  Fallback to spec_query.py."
fi

if [ "$SPEC_AVAILABLE" = "1" ]; then
    echo ""
    echo "Comparison with spec_query.py:"
    if [ "$NOTEBOOK_COUNT" -eq "$SPEC_COUNT" ] && [ "$NOTEBOOK_NAMES" = "$SPEC_NAMES" ]; then
        echo "  ✓ Outputs match (high confidence in NotebookLM)"
    else
        echo "  ⚠ Outputs differ (review for accuracy)"
    fi
fi

echo ""
echo "Output files:"
echo "  NotebookLM: $TEST_DIR/notebook_result.json"
if [ "$SPEC_AVAILABLE" = "1" ]; then
    echo "  spec_query: $TEST_DIR/spec_result.json"
fi
echo ""
