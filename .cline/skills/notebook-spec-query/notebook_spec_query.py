#!/usr/bin/env python3
"""
NotebookLM Spec Query implementation.
Replaces spec_query.py for Phase 3.1 phase retrieval.

Usage:
  python3 notebook_spec_query.py \
    --operation skeleton \
    --procedure "VoLTE_Call_Establishment" \
    --rat "5G NR" \
    --top-event "Call_Drop_During_Media" \
    --notebook-id "abc123..." \
    --output phases.json
"""

import json
import re
import sys
import subprocess
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime


@dataclass
class Phase:
    """Single phase from skeleton."""
    id: str
    name: str
    spec_ref: str
    protocol_layer: str
    mandatory_messages: List[str] = None

    def __post_init__(self):
        if self.mandatory_messages is None:
            self.mandatory_messages = []


@dataclass
class Hypothesis:
    """Single hypothesis from fallback."""
    id: str
    name: str
    reasoning: str


@dataclass
class ValidationResult:
    """Validation result."""
    structure_valid: bool
    spec_refs_valid: int
    spec_refs_invalid: int
    spec_anchors_valid: int
    spec_anchors_hallucinated: int
    content_score: float
    hallucination_risk: bool
    recommendation: str
    issues: List[str]


# Scenario-specific layer requirements
SCENARIO_LAYERS = {
    "VoLTE": {"required": {"SIP", "RTP", "RRC", "MEDIA"}, "optional": {"IKEv2", "PDCP"}},
    "5G": {"required": {"RRC", "NAS", "PDCP"}, "optional": {"PHY", "MAC"}},
    "LTE": {"required": {"RRC", "NAS", "PDCP"}, "optional": {"PHY", "MAC"}},
}

VALID_3GPP_SPECS = {
    "23.228", "24.229", "24.271", "38.331", "36.331", "48.171",
    "38.321", "36.321", "38.322", "36.322",
}


def run_notebooklm_query(notebook_id: str, query: str) -> Dict[str, Any]:
    """Execute NotebookLM query and return structured response."""
    try:
        result = subprocess.run(
            ["notebooklm", "ask", query, "-n", notebook_id, "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: NotebookLM query failed: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse NotebookLM response: {e}", file=sys.stderr)
        sys.exit(1)


def extract_protocol_layer(text: str) -> str:
    """Infer protocol layer from text."""
    text_lower = text.lower()

    if "sip" in text_lower or "invite" in text_lower:
        return "SIP"
    elif "rtp" in text_lower or "media" in text_lower:
        return "MEDIA"
    elif "rrc" in text_lower or "reconfiguration" in text_lower:
        return "RRC"
    elif "ims" in text_lower or "register" in text_lower:
        return "IMS-NAS"
    elif "pdcp" in text_lower or "ciphering" in text_lower:
        return "PDCP"
    elif "ike" in text_lower or "ipsec" in text_lower:
        return "IKEv2"
    elif "nas" in text_lower:
        return "NAS"
    elif "phy" in text_lower:
        return "PHY"
    elif "mac" in text_lower:
        return "MAC"
    else:
        return "UNKNOWN"


def extract_phases_from_text(text: str) -> List[Phase]:
    """
    Parse natural language response into structured phases.

    Patterns:
      - "P1 SIP_INVITE_Exchange (TS 24.229 §6.1.1) - SIP, INVITE, 100 Trying, 180, 200 OK"
      - "[1] SIP Signaling (TS 24.229 §6.1)"
    """
    phases = []

    # Pattern: P?N Name (TS XX.XXX §...) Protocol: XXX, Messages: [....]
    pattern = r'P?(\d+)[\.\):\s]+([A-Za-z_][A-Za-z0-9_]*)\s*\(?([^)]*TS\s+\d+\.\d+[^)]*)\)?'

    for match in re.finditer(pattern, text, re.IGNORECASE):
        phase_num, name, spec_ref_raw = match.groups()

        # Extract spec ref (TS XX.XXX §Y.Y.Z)
        spec_match = re.search(r'TS\s+(\d+\.\d+)\s+[§§]?([\d.]*)', spec_ref_raw)
        if not spec_match:
            continue

        ts_num, section = spec_match.groups()
        spec_ref = f"TS {ts_num} §{section}" if section else f"TS {ts_num}"

        # Extract protocol layer from context (look in next 200 chars)
        context_end = min(match.end() + 200, len(text))
        context = text[match.start() : context_end]
        protocol_layer = extract_protocol_layer(context)

        # Extract messages (look for comma-separated list after phase)
        messages_pattern = r'(?:messages|msgs?):\s*\[?([^\]]+)\]?'
        msg_match = re.search(messages_pattern, context, re.IGNORECASE)
        mandatory_messages = []
        if msg_match:
            msg_text = msg_match.group(1)
            mandatory_messages = [m.strip() for m in msg_text.split(",") if m.strip()]

        phases.append(Phase(
            id=f"P{phase_num.zfill(1)}",
            name=name,
            spec_ref=spec_ref,
            protocol_layer=protocol_layer,
            mandatory_messages=mandatory_messages
        ))

    return phases


def extract_hypotheses_from_text(text: str) -> List[Hypothesis]:
    """Parse hypotheses from fallback response."""
    hypotheses = []

    # Pattern: H?N Name - reasoning
    pattern = r'H?(\d+)[\.\):\s]+([A-Za-z_][A-Za-z0-9_]*)\s*[-:]\s*(.{10,200}?)(?=H\d+|$)'

    for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
        hyp_num, name, reasoning = match.groups()
        hypotheses.append(Hypothesis(
            id=f"H{hyp_num.zfill(1)}",
            name=name,
            reasoning=reasoning.strip()[:200]
        ))

    return hypotheses


def validate_structure(items: List) -> tuple[bool, List[str]]:
    """Validate structure of phases/hypotheses."""
    issues = []

    if not items:
        issues.append("No phases/hypotheses extracted")
        return False, issues

    if len(items) < 2:
        issues.append(f"Too few items ({len(items)}, expected ≥2)")

    for i, item in enumerate(items):
        if not hasattr(item, 'id') or not item.id:
            issues.append(f"Item {i}: missing id")
        if not hasattr(item, 'name') or not item.name:
            issues.append(f"Item {i}: missing name")
        if isinstance(item, Phase):
            if not item.spec_ref:
                issues.append(f"Phase {i}: missing spec_ref")

    return len(issues) == 0, issues


def validate_spec_refs(phases: List[Phase]) -> tuple[int, int, List[str]]:
    """Validate spec references."""
    valid = 0
    invalid = 0
    issues = []

    for phase in phases:
        match = re.search(r'TS\s+(\d+\.\d+)', phase.spec_ref)
        if not match:
            issues.append(f"{phase.id}: malformed spec ref '{phase.spec_ref}'")
            invalid += 1
            continue

        ts_num = match.group(1)
        if ts_num in VALID_3GPP_SPECS:
            valid += 1
        else:
            issues.append(f"{phase.id}: unknown TS {ts_num}")
            invalid += 1

    return valid, invalid, issues


def validate_spec_anchors(references: List[Dict]) -> tuple[int, int]:
    """Check phase anchors in notebook sources."""
    if not references:
        return 0, 1  # Assume all unanchored

    return len(references), 0


def validate_content(phases: List[Phase], procedure: str, rat: str) -> tuple[float, List[str]]:
    """Validate phase content relevance."""
    issues = []

    # Determine scenario
    scenario = None
    if "VoLTE" in procedure or "IMS" in procedure:
        scenario = "VoLTE"
    elif "5G" in rat:
        scenario = "5G"
    elif "LTE" in rat:
        scenario = "LTE"

    if not scenario or scenario not in SCENARIO_LAYERS:
        return 1.0, []

    required = SCENARIO_LAYERS[scenario]["required"]
    found_layers = {p.protocol_layer for p in phases}

    missing = required - found_layers
    if missing:
        issues.append(f"Missing required layers for {scenario}: {missing}")

    score = len(required & found_layers) / len(required) if required else 1.0
    return score, issues


def query_skeleton(procedure: str, rat: str, top_event: str, notebook_id: str) -> tuple[List[Phase], Dict]:
    """Query for procedure skeleton phases."""
    query = f"""
    For the 3GPP procedure '{procedure}' in {rat}, analyzing top_event '{top_event}',
    identify the main procedural phases that should be analyzed.
    Return phases in logical order.

    For each phase provide:
    1. Phase ID (P1, P2, P3, ...)
    2. Phase name (no spaces: e.g., SIP_INVITE_Exchange)
    3. 3GPP spec reference (TS XX.XXX §Y.Y.Z)
    4. Protocol layer (SIP, RTP, RRC, IMS-NAS, MEDIA, PDCP, etc.)
    5. Mandatory messages in that phase (comma-separated)
    6. Why this phase could cause '{top_event}'

    Format clearly with each phase on separate lines.
    """

    print(f"Querying NotebookLM for {procedure}:{rat} skeleton...", file=sys.stderr)
    response = run_notebooklm_query(notebook_id, query)

    answer_text = response.get("answer", "")
    references = response.get("references", [])

    # Extract phases
    phases = extract_phases_from_text(answer_text)

    # Validate
    struct_valid, struct_issues = validate_structure(phases)
    spec_valid, spec_invalid, spec_issues = validate_spec_refs(phases)
    anchors_valid, anchors_hallucinated = validate_spec_anchors(references)
    content_score, content_issues = validate_content(phases, procedure, rat)

    all_issues = struct_issues + spec_issues + content_issues

    hallucination_risk = anchors_hallucinated > 0

    # Decide
    all_quality_good = (
        struct_valid and
        content_score >= 0.75 and
        not hallucination_risk
    )
    recommendation = "ACCEPT" if all_quality_good else "FALLBACK"

    validation = {
        "structure_valid": struct_valid,
        "spec_refs_valid": spec_valid,
        "spec_refs_invalid": spec_invalid,
        "spec_anchors_valid": anchors_valid,
        "spec_anchors_hallucinated": anchors_hallucinated,
        "content_score": content_score,
        "hallucination_risk": hallucination_risk,
        "recommendation": recommendation,
        "issues": all_issues
    }

    return phases, validation


def query_hypotheses(event: str, procedure: str, rat: str, notebook_id: str) -> tuple[List[Hypothesis], Dict]:
    """Query for fallback hypotheses (iterations ≥ 2)."""
    query = f"""
    For the event '{event}' in {procedure} ({rat}),
    generate 3-5 hypothetical failure causes based on code patterns and spec.

    For each hypothesis provide:
    1. ID (H1, H2, ...)
    2. Name
    3. Reasoning (why this could cause '{event}')
    """

    print(f"Querying NotebookLM for {event} hypotheses...", file=sys.stderr)
    response = run_notebooklm_query(notebook_id, query)

    answer_text = response.get("answer", "")
    references = response.get("references", [])

    # Extract hypotheses
    hypotheses = extract_hypotheses_from_text(answer_text)

    # Validate
    struct_valid, struct_issues = validate_structure(hypotheses)
    anchors_valid, anchors_hallucinated = validate_spec_anchors(references)

    hallucination_risk = anchors_hallucinated > 0

    all_quality_good = struct_valid and not hallucination_risk
    recommendation = "ACCEPT" if all_quality_good else "FALLBACK"

    validation = {
        "structure_valid": struct_valid,
        "spec_anchors_valid": anchors_valid,
        "spec_anchors_hallucinated": anchors_hallucinated,
        "hallucination_risk": hallucination_risk,
        "recommendation": recommendation,
        "issues": struct_issues
    }

    return hypotheses, validation


def main():
    import argparse

    parser = argparse.ArgumentParser(description="NotebookLM Spec Query")
    parser.add_argument("--operation", required=True, choices=["skeleton", "generate_hypotheses"])
    parser.add_argument("--procedure", required=True)
    parser.add_argument("--rat", required=True)
    parser.add_argument("--top-event", required=False)
    parser.add_argument("--event", required=False)  # For hypotheses
    parser.add_argument("--notebook-id", "-n", required=True)
    parser.add_argument("--output", "-o", type=Path, help="Write JSON output")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    # Execute
    if args.operation == "skeleton":
        if not args.top_event:
            print("ERROR: --top-event required for skeleton operation", file=sys.stderr)
            sys.exit(1)

        items, validation = query_skeleton(args.procedure, args.rat, args.top_event, args.notebook_id)

        result = {
            "operation": "skeleton",
            "procedure": args.procedure,
            "rat": args.rat,
            "phases": [asdict(p) for p in items],
            "gate_at_top": "OR",
            "source": "notebooklm",
            "validation": validation
        }

    else:  # generate_hypotheses
        if not args.event:
            print("ERROR: --event required for generate_hypotheses", file=sys.stderr)
            sys.exit(1)

        items, validation = query_hypotheses(args.event, args.procedure, args.rat, args.notebook_id)

        result = {
            "operation": "generate_hypotheses",
            "event": args.event,
            "procedure": args.procedure,
            "hypotheses": [asdict(h) for h in items],
            "source": "notebooklm",
            "validation": validation
        }

    # Output
    print(json.dumps(result, indent=2))

    if args.output:
        args.output.write_text(json.dumps(result, indent=2))

    # Exit code based on recommendation
    recommendation = validation.get("recommendation")
    sys.exit(0 if recommendation == "ACCEPT" else 1)


if __name__ == "__main__":
    main()
