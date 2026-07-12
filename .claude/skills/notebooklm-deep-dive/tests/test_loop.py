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


def test_render_query_contains_all_parts():
    q = loop.render_query(
        goal="Map RCA v6", round_num=2, max_rounds=10,
        question="What fields are in the scope file?",
        already_asked=["What is Phase 0?"],
    )
    assert "Map RCA v6" in q
    assert "2/10" in q
    assert "What fields are in the scope file?" in q
    assert "What is Phase 0?" in q
    for label in ["ANSWER", "COVERAGE", "BEST_NEXT_QUERY"]:
        assert label in q


def test_render_query_round1_no_prior():
    q = loop.render_query("g", 1, 10, "seed?", [])
    assert "(none)" in q


def test_strip_reminder_removes_blurb():
    text = "Real answer here.\n\n" + loop.REMINDER_SENTINEL + " blah blah"
    assert loop.strip_reminder(text) == "Real answer here."


def test_strip_reminder_noop_when_absent():
    assert loop.strip_reminder("clean") == "clean"


def test_extract_answer_from_stdout():
    bar = "=" * 60
    stdout = (
        "  Progress...\n"
        f"{bar}\n"
        "Question: What is Phase 0?\n"
        f"{bar}\n"
        "\nPhase 0 scopes the issue.\nCOVERAGE: PARTIAL\n\n"
        f"{bar}\n"
    )
    ans = loop.extract_answer(stdout)
    assert "Phase 0 scopes the issue." in ans
    assert "COVERAGE: PARTIAL" in ans
    assert "Progress" not in ans
