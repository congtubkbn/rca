import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import loop


def test_slugify_basic():
    assert loop.slugify("What is Phase 0 of RCA v6?") == "what-is-phase-0-of-rca-v6"


def test_slugify_caps_length():
    out = loop.slugify("x" * 100)
    assert len(out) <= 40


def test_parse_output_wellformed():
    raw = (
        "ANSWER: Phase 0 scopes the issue.\n"
        "KEY_FACTS:\n- input: UE log\n- output: scope file\n"
        "SOURCES: design-v6.pdf\n"
        "COVERAGE: PARTIAL\n"
        "GAPS: no timing details\n"
        "BEST_NEXT_QUERY: What fields are in the scope file?\n"
    )
    p = loop.parse_output(raw)
    assert p["answer"] == "Phase 0 scopes the issue."
    assert "UE log" in p["key_facts"]
    assert p["coverage"] == "PARTIAL"
    assert p["next_query"] == "What fields are in the scope file?"


def test_parse_output_missing_field_is_empty():
    raw = "ANSWER: hi\nCOVERAGE: full\n"
    p = loop.parse_output(raw)
    assert p["answer"] == "hi"
    assert p["coverage"] == "FULL"
    assert p["next_query"] == ""


def test_parse_output_case_insensitive_labels():
    raw = "answer: yo\nbest_next_query: dig deeper\n"
    p = loop.parse_output(raw)
    assert p["answer"] == "yo"
    assert p["next_query"] == "dig deeper"
