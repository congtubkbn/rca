import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import loop
import json


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


def test_notebook_url_from_id():
    assert loop.notebook_url_from_id("abc123") == "https://notebooklm.google.com/notebook/abc123"


def test_init_task_creates_folder_and_config(tmp_path):
    d = loop.init_task(
        goal="Map RCA v6", seed="What is Phase 0?",
        notebook_id="abc123", output_root=str(tmp_path),
        timestamp="20260712-101500", max_rounds=10, language="en",
    )
    assert d.name == "20260712-101500_what-is-phase-0"
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    assert cfg["notebook_url"] == "https://notebooklm.google.com/notebook/abc123"
    assert cfg["max_rounds"] == 10
    assert cfg["goal"] == "Map RCA v6"
    assert (d / "00-task.md").exists()
    assert "Map RCA v6" in (d / "00-task.md").read_text(encoding="utf-8")


def test_write_round_files(tmp_path):
    parsed = {"answer": "a", "key_facts": "kf", "sources": "s",
              "coverage": "FULL", "gaps": "g", "next_query": "nq"}
    loop.write_round_files(str(tmp_path), 3, "QUERY-TEXT", "RAW-RESPONSE", parsed)
    assert (tmp_path / "round-03_query.md").read_text(encoding="utf-8") == "QUERY-TEXT"
    body = (tmp_path / "round-03_response.md").read_text(encoding="utf-8")
    assert "RAW-RESPONSE" in body
    assert "FULL" in body


def test_append_and_read_trace(tmp_path):
    loop.append_trace(str(tmp_path), 1, "q1", "PARTIAL", "q2", "notebooklm", ts="T1")
    loop.append_trace(str(tmp_path), 2, "q2", "FULL", "q3", "claude-dedup", ts="T2")
    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    import json as _j
    first = _j.loads(lines[0])
    assert first == {"round": 1, "query": "q1", "coverage": "PARTIAL",
                     "next_query": "q2", "next_query_source": "notebooklm", "ts": "T1"}
    assert loop.already_asked_from_trace(str(tmp_path)) == ["q1", "q2"]


def test_already_asked_empty_when_no_trace(tmp_path):
    assert loop.already_asked_from_trace(str(tmp_path)) == []
