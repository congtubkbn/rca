# notebooklm-deep-dive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a skill that mines one NotebookLM notebook across 10 fixed rounds — the notebook proposes each next query, Claude lightly guards it, every query/response is logged — as both a knowledge-extraction tool for RCA v6 and a benchmark of NotebookLM output quality.

**Architecture:** Hybrid. A stdlib-only Python module (`loop.py`) does the mechanical, testable work: init the task folder, render the input template, call the existing `notebooklm` skill's `ask_question.py` via subprocess, parse the 6-field output template, write per-round files + `trace.jsonl`. Claude (driven by `SKILL.md`) does the judgment: light-guard on the next query and final synthesis into `summary.md`. Claude and `loop.py` talk through a 3-subcommand CLI (`init`, `ask`, `trace`) and JSON on stdout.

**Tech Stack:** Python 3 (stdlib only: `argparse`, `json`, `re`, `subprocess`, `pathlib`, `datetime`), `pytest` for tests. The `notebooklm` skill (its own venv) is invoked as a subprocess — `loop.py` needs none of its dependencies.

## Global Constraints

- Notebook ID (RCA v6): `f5e859be-eb94-43be-bc12-bf9453bf7099`
- Notebook URL form: `https://notebooklm.google.com/notebook/<id>`
- `notebooklm` ask entrypoint: `python "C:/Users/Win 11/.claude/skills/notebooklm/scripts/run.py" ask_question.py --question "<q>" --notebook-url "<url>"`
- Fixed loop length: `max_rounds = 10`. **No early exit** — always run all 10 rounds.
- Query language: **English (technical)**.
- Next-query handling: **light guard** — verbatim unless empty / duplicate of a prior query / clearly off-goal; on edit, log `next_query_source` ∈ {`notebooklm`, `claude-fallback`, `claude-dedup`, `claude-reaim`}.
- Output-template fields, exact order: `ANSWER`, `KEY_FACTS`, `SOURCES`, `COVERAGE`, `GAPS`, `BEST_NEXT_QUERY`. `COVERAGE` ∈ {`FULL`, `PARTIAL`, `NOT_FOUND`}.
- `loop.py` is **stdlib-only** and never imports from the `notebooklm` skill — it shells out.
- Skill location: `e:\the.thoi\Project\rca-v6\.claude\skills\notebooklm-deep-dive\`.
- Output artifacts root: `e:\the.thoi\Project\rca-v6\output-notebooklm\` (one subfolder per task, git-ignored).

---

## File Structure

```
.claude/skills/notebooklm-deep-dive/
  SKILL.md                    # procedure Claude follows (drives loop + guard + synthesis)
  scripts/
    loop.py                   # stdlib mechanical core + CLI (init/ask/trace)
  tests/
    test_loop.py              # pytest unit tests for loop.py
output-notebooklm/            # runtime artifacts (git-ignored)
```

`loop.py` is one focused module (~250 lines): task-folder mechanics, template rendering, notebook subprocess call, output parsing, trace I/O, and a thin CLI. `SKILL.md` holds no logic — only the round-by-round procedure and the guard/synthesis instructions.

Run tests with: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/ -v` (from repo root). If pytest is missing: `python -m pip install pytest`.

`test_loop.py` imports the module via:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import loop
```

---

### Task 1: Scaffold + output parsing

**Files:**
- Create: `.claude/skills/notebooklm-deep-dive/scripts/loop.py`
- Test: `.claude/skills/notebooklm-deep-dive/tests/test_loop.py`

**Interfaces:**
- Produces:
  - `slugify(text: str) -> str` — lowercase, non-alnum → `-`, collapse repeats, trim, cap 40 chars.
  - `FIELDS: list[str]` = `["ANSWER","KEY_FACTS","SOURCES","COVERAGE","GAPS","BEST_NEXT_QUERY"]`
  - `parse_output(raw: str) -> dict` — returns `{"answer","key_facts","sources","coverage","gaps","next_query"}`, each a stripped string (empty string if the label is absent); `coverage` upper-cased.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_loop.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop'` (file not created yet).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/loop.py
"""notebooklm-deep-dive: mechanical core for the 10-round NotebookLM loop."""
import re

FIELDS = ["ANSWER", "KEY_FACTS", "SOURCES", "COVERAGE", "GAPS", "BEST_NEXT_QUERY"]
_KEY_MAP = {
    "ANSWER": "answer", "KEY_FACTS": "key_facts", "SOURCES": "sources",
    "COVERAGE": "coverage", "GAPS": "gaps", "BEST_NEXT_QUERY": "next_query",
}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].rstrip("-")


def parse_output(raw: str) -> dict:
    result = {v: "" for v in _KEY_MAP.values()}
    pattern = re.compile(
        r"^\s*(" + "|".join(FIELDS) + r")\s*:[ \t]*",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(pattern.finditer(raw))
    for i, m in enumerate(matches):
        field = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        value = raw[start:end].strip()
        if field == "COVERAGE":
            value = value.upper()
        result[_KEY_MAP[field]] = value
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/notebooklm-deep-dive/scripts/loop.py .claude/skills/notebooklm-deep-dive/tests/test_loop.py
git commit -m "feat(deep-dive): parse_output + slugify for notebooklm loop"
```

---

### Task 2: Input template + answer extraction

**Files:**
- Modify: `.claude/skills/notebooklm-deep-dive/scripts/loop.py`
- Test: `.claude/skills/notebooklm-deep-dive/tests/test_loop.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `render_query(goal: str, round_num: int, max_rounds: int, question: str, already_asked: list[str]) -> str` — the input template text sent to NotebookLM.
  - `REMINDER_SENTINEL: str` = `"EXTREMELY IMPORTANT: Is that ALL you need to know?"`
  - `strip_reminder(text: str) -> str` — remove the appended follow-up blurb.
  - `extract_answer(stdout: str) -> str` — pull the answer body out of `ask_question.py` stdout (which brackets the answer between `====…` banner lines after a `Question:` line), reminder stripped.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v -k "render_query or reminder or extract_answer"`
Expected: FAIL — `AttributeError: module 'loop' has no attribute 'render_query'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/loop.py`:

```python
REMINDER_SENTINEL = "EXTREMELY IMPORTANT: Is that ALL you need to know?"

_OUTPUT_TEMPLATE = """Answer ONLY from notebook sources. Cite every claim. Then fill this exact template, every field present:

ANSWER:
KEY_FACTS:
SOURCES:
COVERAGE: (FULL | PARTIAL | NOT_FOUND)
GAPS:
BEST_NEXT_QUERY: (ONE single most valuable follow-up toward TASK GOAL)"""


def render_query(goal, round_num, max_rounds, question, already_asked):
    asked = "\n".join(f"- {q}" for q in already_asked) if already_asked else "(none)"
    return (
        f"[TASK GOAL]     {goal}\n"
        f"[ROUND]         {round_num}/{max_rounds}\n"
        f"[QUESTION]      {question}\n"
        f"[ALREADY ASKED]\n{asked}\n\n"
        f"{_OUTPUT_TEMPLATE}\n"
    )


def strip_reminder(text):
    idx = text.find(REMINDER_SENTINEL)
    return text[:idx].rstrip() if idx != -1 else text


def extract_answer(stdout):
    parts = re.split(r"^={10,}\s*$", stdout, flags=re.MULTILINE)
    for i, p in enumerate(parts):
        if p.strip().startswith("Question:") and i + 1 < len(parts):
            return strip_reminder(parts[i + 1].strip())
    return strip_reminder(parts[-1].strip())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/notebooklm-deep-dive/scripts/loop.py .claude/skills/notebooklm-deep-dive/tests/test_loop.py
git commit -m "feat(deep-dive): input template render + answer extraction"
```

---

### Task 3: Task initialization

**Files:**
- Modify: `.claude/skills/notebooklm-deep-dive/scripts/loop.py`
- Test: `.claude/skills/notebooklm-deep-dive/tests/test_loop.py`

**Interfaces:**
- Consumes: `slugify` (Task 1).
- Produces:
  - `notebook_url_from_id(notebook_id: str) -> str`
  - `init_task(goal, seed, notebook_id, output_root, timestamp=None, max_rounds=10, language="en") -> pathlib.Path` — creates `<output_root>/<timestamp>_<slug>/`, writes `config.json` (keys: `goal, seed, notebook_id, notebook_url, max_rounds, language, created`) and human-readable `00-task.md`; returns the task dir. `timestamp` defaults to `datetime.now().strftime("%Y%m%d-%H%M%S")`; tests always pass it explicitly.

- [ ] **Step 1: Write the failing tests**

```python
import json


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v -k "init_task or notebook_url"`
Expected: FAIL — `AttributeError: module 'loop' has no attribute 'init_task'`.

- [ ] **Step 3: Write minimal implementation**

Add imports at top of `scripts/loop.py` (below the module docstring): `import json`, `from datetime import datetime`, `from pathlib import Path`. Then append:

```python
def notebook_url_from_id(notebook_id):
    return f"https://notebooklm.google.com/notebook/{notebook_id}"


def init_task(goal, seed, notebook_id, output_root,
              timestamp=None, max_rounds=10, language="en"):
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    task_dir = Path(output_root) / f"{timestamp}_{slugify(seed)}"
    task_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "goal": goal, "seed": seed, "notebook_id": notebook_id,
        "notebook_url": notebook_url_from_id(notebook_id),
        "max_rounds": max_rounds, "language": language, "created": timestamp,
    }
    (task_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (task_dir / "00-task.md").write_text(
        f"# Deep-dive task\n\n"
        f"- **Goal:** {goal}\n"
        f"- **Seed:** {seed}\n"
        f"- **Notebook:** {config['notebook_url']}\n"
        f"- **Max rounds:** {max_rounds}\n"
        f"- **Language:** {language}\n"
        f"- **Created:** {timestamp}\n",
        encoding="utf-8",
    )
    return task_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/notebooklm-deep-dive/scripts/loop.py .claude/skills/notebooklm-deep-dive/tests/test_loop.py
git commit -m "feat(deep-dive): task init (folder + config.json + 00-task.md)"
```

---

### Task 4: Round files + trace + already-asked

**Files:**
- Modify: `.claude/skills/notebooklm-deep-dive/scripts/loop.py`
- Test: `.claude/skills/notebooklm-deep-dive/tests/test_loop.py`

**Interfaces:**
- Consumes: `parse_output` output shape (Task 1).
- Produces:
  - `write_round_files(task_dir, round_num: int, query: str, response_raw: str, parsed: dict) -> None` — writes `round-NN_query.md` and `round-NN_response.md` (NN zero-padded 2).
  - `append_trace(task_dir, round_num, query, coverage, next_query, next_query_source, ts=None) -> None` — appends one JSON line to `trace.jsonl` with keys `round, query, coverage, next_query, next_query_source, ts`. `ts` defaults to `datetime.now().isoformat()`.
  - `already_asked_from_trace(task_dir) -> list[str]` — the `query` field of every prior trace line, in order (empty list if no `trace.jsonl`).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v -k "round_files or trace"`
Expected: FAIL — `AttributeError: module 'loop' has no attribute 'write_round_files'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/loop.py`:

```python
def _render_response_md(round_num, response_raw, parsed):
    return (
        f"# Round {round_num} response\n\n"
        f"## Parsed fields\n"
        f"- **COVERAGE:** {parsed.get('coverage', '')}\n"
        f"- **BEST_NEXT_QUERY:** {parsed.get('next_query', '')}\n\n"
        f"## Raw response\n\n{response_raw}\n"
    )


def write_round_files(task_dir, round_num, query, response_raw, parsed):
    d = Path(task_dir)
    nn = f"{round_num:02d}"
    (d / f"round-{nn}_query.md").write_text(query, encoding="utf-8")
    (d / f"round-{nn}_response.md").write_text(
        _render_response_md(round_num, response_raw, parsed), encoding="utf-8"
    )


def append_trace(task_dir, round_num, query, coverage, next_query,
                 next_query_source, ts=None):
    if ts is None:
        ts = datetime.now().isoformat()
    line = {
        "round": round_num, "query": query, "coverage": coverage,
        "next_query": next_query, "next_query_source": next_query_source, "ts": ts,
    }
    with open(Path(task_dir) / "trace.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def already_asked_from_trace(task_dir):
    p = Path(task_dir) / "trace.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln)["query"] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/notebooklm-deep-dive/scripts/loop.py .claude/skills/notebooklm-deep-dive/tests/test_loop.py
git commit -m "feat(deep-dive): round files, trace.jsonl I/O, already-asked"
```

---

### Task 5: NotebookLM subprocess caller

**Files:**
- Modify: `.claude/skills/notebooklm-deep-dive/scripts/loop.py`
- Test: `.claude/skills/notebooklm-deep-dive/tests/test_loop.py`

**Interfaces:**
- Consumes: `extract_answer` (Task 2).
- Produces:
  - `NOTEBOOKLM_RUN_PY: str` = `"C:/Users/Win 11/.claude/skills/notebooklm/scripts/run.py"`
  - `call_notebooklm(question, notebook_url, run_py=NOTEBOOKLM_RUN_PY, timeout=180, runner=subprocess.run, python_exe=None) -> str` — builds the command, invokes `runner`, returns `extract_answer(stdout)`. `runner` is injectable so tests avoid launching a real browser. `python_exe` defaults to `sys.executable`.

- [ ] **Step 1: Write the failing test**

```python
def test_call_notebooklm_uses_runner_and_extracts(monkeypatch):
    bar = "=" * 60
    captured = {}

    class FakeProc:
        stdout = f"progress\n{bar}\nQuestion: q?\n{bar}\n\nThe answer body.\n\n{bar}\n"
        stderr = ""
        returncode = 0

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    ans = loop.call_notebooklm(
        "q?", "https://notebooklm.google.com/notebook/abc123",
        runner=fake_runner,
    )
    assert ans == "The answer body."
    assert "ask_question.py" in captured["cmd"]
    assert "--question" in captured["cmd"]
    assert "q?" in captured["cmd"]
    assert "https://notebooklm.google.com/notebook/abc123" in captured["cmd"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v -k call_notebooklm`
Expected: FAIL — `AttributeError: module 'loop' has no attribute 'call_notebooklm'`.

- [ ] **Step 3: Write minimal implementation**

Add `import subprocess` and `import sys` at top of `scripts/loop.py`. Then append:

```python
NOTEBOOKLM_RUN_PY = "C:/Users/Win 11/.claude/skills/notebooklm/scripts/run.py"


def call_notebooklm(question, notebook_url, run_py=NOTEBOOKLM_RUN_PY,
                    timeout=180, runner=subprocess.run, python_exe=None):
    cmd = [
        python_exe or sys.executable, run_py, "ask_question.py",
        "--question", question, "--notebook-url", notebook_url,
    ]
    proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    return extract_answer(proc.stdout)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/notebooklm-deep-dive/scripts/loop.py .claude/skills/notebooklm-deep-dive/tests/test_loop.py
git commit -m "feat(deep-dive): notebooklm subprocess caller (injectable runner)"
```

---

### Task 6: CLI (init / ask / trace)

**Files:**
- Modify: `.claude/skills/notebooklm-deep-dive/scripts/loop.py`
- Test: `.claude/skills/notebooklm-deep-dive/tests/test_loop.py`

**Interfaces:**
- Consumes: all prior functions.
- Produces a CLI dispatched by `main(argv=None)`:
  - `init --goal G --seed S --notebook-id ID [--output-root R] [--timestamp T] [--max-rounds N] [--language L]` → prints the created task dir path.
  - `ask --task-dir D --round N --question Q` → loads `config.json` for goal/notebook_url/max_rounds, builds already-asked from `trace.jsonl`, renders + writes `round-NN_query.md`, calls NotebookLM, writes `round-NN_response.md`, and prints the parsed dict as JSON (with `round` added) to stdout.
  - `trace --task-dir D --round N --query Q --coverage C --next-query NQ --source SRC` → appends the trace line.
  - `main` returns `0` on success. Default `--output-root` = `output-notebooklm`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cli_init_prints_dir(tmp_path, capsys):
    rc = loop.main([
        "init", "--goal", "Map RCA v6", "--seed", "What is Phase 0?",
        "--notebook-id", "abc123", "--output-root", str(tmp_path),
        "--timestamp", "20260712-101500",
    ])
    assert rc == 0
    printed = capsys.readouterr().out.strip()
    assert printed.endswith("20260712-101500_what-is-phase-0")
    assert (pathlib.Path(printed) / "config.json").exists()


def test_cli_trace_appends(tmp_path):
    loop.main([
        "trace", "--task-dir", str(tmp_path), "--round", "1",
        "--query", "q1", "--coverage", "FULL",
        "--next-query", "q2", "--source", "notebooklm",
    ])
    assert loop.already_asked_from_trace(str(tmp_path)) == ["q1"]


def test_cli_ask_writes_files_and_prints_json(tmp_path, monkeypatch, capsys):
    d = loop.init_task("Map RCA v6", "What is Phase 0?", "abc123",
                       str(tmp_path), timestamp="20260712-101500")
    monkeypatch.setattr(
        loop, "call_notebooklm",
        lambda *a, **k: "ANSWER: Phase 0 scopes.\nCOVERAGE: PARTIAL\nBEST_NEXT_QUERY: next?\n",
    )
    rc = loop.main([
        "ask", "--task-dir", str(d), "--round", "1",
        "--question", "What is Phase 0?",
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["round"] == 1
    assert out["coverage"] == "PARTIAL"
    assert out["next_query"] == "next?"
    assert (d / "round-01_query.md").exists()
    assert (d / "round-01_response.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v -k cli`
Expected: FAIL — `AttributeError: module 'loop' has no attribute 'main'`.

- [ ] **Step 3: Write minimal implementation**

Add `import argparse` at top of `scripts/loop.py`. Then append:

```python
def _cmd_init(a):
    d = init_task(a.goal, a.seed, a.notebook_id, a.output_root,
                  timestamp=a.timestamp, max_rounds=a.max_rounds, language=a.language)
    print(str(d))
    return 0


def _cmd_ask(a):
    cfg = json.loads((Path(a.task_dir) / "config.json").read_text(encoding="utf-8"))
    query = render_query(cfg["goal"], a.round, cfg["max_rounds"],
                         a.question, already_asked_from_trace(a.task_dir))
    nn = f"{a.round:02d}"
    (Path(a.task_dir) / f"round-{nn}_query.md").write_text(query, encoding="utf-8")
    raw = call_notebooklm(a.question, cfg["notebook_url"])
    parsed = parse_output(raw)
    write_round_files(a.task_dir, a.round, query, raw, parsed)
    out = dict(parsed)
    out["round"] = a.round
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _cmd_trace(a):
    append_trace(a.task_dir, a.round, a.query, a.coverage, a.next_query, a.source)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="loop.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("--goal", required=True)
    pi.add_argument("--seed", required=True)
    pi.add_argument("--notebook-id", required=True)
    pi.add_argument("--output-root", default="output-notebooklm")
    pi.add_argument("--timestamp", default=None)
    pi.add_argument("--max-rounds", type=int, default=10)
    pi.add_argument("--language", default="en")
    pi.set_defaults(func=_cmd_init)

    pa = sub.add_parser("ask")
    pa.add_argument("--task-dir", required=True)
    pa.add_argument("--round", type=int, required=True)
    pa.add_argument("--question", required=True)
    pa.set_defaults(func=_cmd_ask)

    pt = sub.add_parser("trace")
    pt.add_argument("--task-dir", required=True)
    pt.add_argument("--round", type=int, required=True)
    pt.add_argument("--query", required=True)
    pt.add_argument("--coverage", required=True)
    pt.add_argument("--next-query", required=True)
    pt.add_argument("--source", required=True)
    pt.set_defaults(func=_cmd_trace)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/test_loop.py -v`
Expected: PASS (all tests, ~16).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/notebooklm-deep-dive/scripts/loop.py .claude/skills/notebooklm-deep-dive/tests/test_loop.py
git commit -m "feat(deep-dive): CLI wiring for init/ask/trace"
```

---

### Task 7: SKILL.md procedure + .gitignore

**Files:**
- Create: `.claude/skills/notebooklm-deep-dive/SKILL.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the `loop.py` CLI (Task 6).
- Produces: the skill Claude invokes; no code.

- [ ] **Step 1: Write `SKILL.md`**

Create `.claude/skills/notebooklm-deep-dive/SKILL.md`:

````markdown
---
name: notebooklm-deep-dive
description: Iteratively mine one NotebookLM notebook across 10 fixed rounds where the notebook proposes each next query. Use when the user wants a deep, logged, multi-round Q&A dive into a NotebookLM notebook — e.g. mapping RCA v6 internals, or benchmarking NotebookLM answer quality. Every query/response is saved to output-notebooklm/<task>/ for later synthesis. Triggers: "deep dive notebooklm", "khai thác notebook", "đào sâu notebooklm", "map RCA v6 from notebook".
---

# NotebookLM Deep Dive

Run a fixed 10-round research loop against ONE NotebookLM notebook. Each round the
notebook answers in a strict template and proposes the single best next query; you
lightly guard that query and feed it to the next round. Everything is logged.

## Prerequisites
- The `notebooklm` skill must be authenticated (`python "C:/Users/Win 11/.claude/skills/notebooklm/scripts/run.py" auth_manager.py setup` if not).
- Default notebook (RCA v6): `f5e859be-eb94-43be-bc12-bf9453bf7099`.

## Inputs to collect from the user
- **Goal** (constant every round), e.g. "Map RCA v6: inputs, outputs, technical functions of each phase."
- **Seed question** (round 1), e.g. "What is Phase 0 of RCA v6 — its inputs, outputs, and technical functions?"
- **Notebook ID** (default the RCA v6 one).

## Procedure

Let `SCRIPTS = .claude/skills/notebooklm-deep-dive/scripts/loop.py`.

1. **Timestamp:** get `TS` from the shell: `date +%Y%m%d-%H%M%S`.
2. **Init:**
   `python "SCRIPTS" init --goal "<goal>" --seed "<seed>" --notebook-id "<id>" --timestamp "<TS>"`
   Record the printed `TASK_DIR`. Set `question = <seed>`.
3. **For round N = 1..10:**
   a. `python "SCRIPTS" ask --task-dir "TASK_DIR" --round N --question "<question>"`
      → read the JSON printed on stdout (fields: `answer, key_facts, sources, coverage, gaps, next_query, round`).
   b. **Light-guard `next_query`** → produce `final_next` + `source`:
      - `next_query` empty → derive a query from `gaps` toward the goal; `source = claude-fallback`.
      - `next_query` duplicates any earlier round's question → rephrase to an unasked angle; `source = claude-dedup`.
      - `next_query` clearly off the goal → minimally re-aim at the goal; `source = claude-reaim`.
      - otherwise → `final_next = next_query`; `source = notebooklm`.
      (On round 10 you may set `final_next = ""` and `source = notebooklm` — it won't be used.)
   c. `python "SCRIPTS" trace --task-dir "TASK_DIR" --round N --query "<question>" --coverage "<coverage>" --next-query "<final_next>" --source "<source>"`
   d. Set `question = final_next` for the next round.
   Never stop early — run all 10 rounds even if `coverage` is FULL.
4. **Synthesize** `TASK_DIR/summary.md` yourself (use the Write tool):
   - **Findings toward the goal** — deduped `KEY_FACTS` across rounds.
   - **NotebookLM quality verdict** — COVERAGE distribution (# FULL / PARTIAL / NOT_FOUND from `trace.jsonl`), guard-edit counts by `source`, whether the query chain converged on the goal or wandered, and notable unanswered gaps.
5. Tell the user where the artifacts are (`TASK_DIR`) and give a 3-5 line recap.

## Notes
- Each `ask` opens a fresh, memory-less NotebookLM session; continuity rides entirely in the `[ALREADY ASKED]` block the script builds from `trace.jsonl`. This is expected.
- `ask` can take up to ~2 min/round (browser automation). 10 rounds ≈ up to 20 min.
- Do not edit `trace.jsonl` by hand — it is the machine-readable spine for later analysis (evaluation framework B).
````

- [ ] **Step 2: Ignore runtime artifacts**

Add to `.gitignore` (repo root):

```
# notebooklm-deep-dive runtime artifacts
output-notebooklm/
```

- [ ] **Step 3: Verify the skill loads (no test framework — manual)**

Run: `python -m pytest .claude/skills/notebooklm-deep-dive/tests/ -v`
Expected: PASS (regression — SKILL.md changes nothing in code).
Then confirm `SKILL.md` has valid frontmatter (`name`, `description`) by reading it back.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/notebooklm-deep-dive/SKILL.md .gitignore
git commit -m "feat(deep-dive): SKILL.md procedure + ignore output artifacts"
```

---

### Task 8: Live end-to-end validation

**Files:**
- None created (produces runtime artifacts under `output-notebooklm/`, git-ignored).

**Interfaces:**
- Consumes: the whole skill.

This task is a **real run** — it launches a browser against NotebookLM, so it cannot be a pytest. It validates the loop end-to-end and begins mapping RCA v6 for framework (B).

- [ ] **Step 1: Confirm auth**

Run: `python "C:/Users/Win 11/.claude/skills/notebooklm/scripts/run.py" ask_question.py --question "Say OK" --notebook-url "https://notebooklm.google.com/notebook/f5e859be-eb94-43be-bc12-bf9453bf7099"`
Expected: a coherent answer prints (proves auth + notebook reachable). If it says "Not authenticated", run the auth setup first.

- [ ] **Step 2: Run a SHORT 2-round smoke of the real loop**

Drive `loop.py` by hand for 2 rounds (not 10) to keep it fast:
- `TS=$(date +%Y%m%d-%H%M%S)`
- `python ".claude/skills/notebooklm-deep-dive/scripts/loop.py" init --goal "Map RCA v6: inputs, outputs, technical functions of each phase." --seed "What is Phase 0 of RCA v6 — its inputs, outputs, and technical functions?" --notebook-id "f5e859be-eb94-43be-bc12-bf9453bf7099" --timestamp "$TS"`
- `ask` round 1 with the seed → read JSON → guard → `trace` round 1.
- `ask` round 2 with the guarded next query → read JSON → guard → `trace` round 2.

Expected: `output-notebooklm/<TS>_*/` contains `config.json`, `00-task.md`, `round-01_query.md`, `round-01_response.md`, `round-02_*`, and a 2-line `trace.jsonl`. Each response file shows a real NotebookLM answer with the 6 fields.

- [ ] **Step 3: Verify artifacts**

Read `round-01_response.md` — confirm `COVERAGE` and `BEST_NEXT_QUERY` parsed correctly.
Read `trace.jsonl` — confirm 2 valid JSON lines with correct `next_query_source` values.
If the output template wasn't honored by NotebookLM (fields missing), note it — that is itself a NotebookLM-quality finding, and may warrant strengthening the template wording in `_OUTPUT_TEMPLATE`.

- [ ] **Step 4: Report**

Summarize to the user: did the loop run clean, did NotebookLM follow the template, how was COVERAGE, and confirm the full 10-round run is ready to launch via the skill. Do NOT commit artifacts (they are git-ignored).

---

## Self-Review

**1. Spec coverage:**
- Input template → Task 2 (`render_query`). ✓
- Output template (6 fields) → Task 1 (`parse_output`), Task 2 (`_OUTPUT_TEMPLATE`). ✓
- 10 fixed rounds, no early exit → Task 7 SKILL.md procedure (explicit "never stop early"). ✓
- NotebookLM proposes next query + light guard + logged `next_query_source` → Task 7 (guard) + Task 4/6 (trace). ✓
- English queries → Global Constraints + template. ✓
- Artifact layout (`00-task.md`, round files, `trace.jsonl`, `summary.md`) → Tasks 3, 4, 7. ✓
- NotebookLM quality signal (COVERAGE/GAPS + verdict) → Task 1 parse + Task 7 summary. ✓
- Timestamped task folder → Task 3 (`init_task`) + Task 7 (shell `date`). ✓
- Dependency on `notebooklm` skill call → Task 5. ✓
- Skill location + config defaults → Global Constraints, Tasks 3/6/7. ✓

**2. Placeholder scan:** No TBD/TODO/"add error handling"/"similar to". All code blocks complete. ✓

**3. Type consistency:** `parse_output` returns `{answer,key_facts,sources,coverage,gaps,next_query}` — used consistently in Tasks 4, 6, 7. Trace keys `{round,query,coverage,next_query,next_query_source,ts}` consistent across Tasks 4 and 6. `init_task` signature identical in Tasks 3 and 6. `call_notebooklm` signature consistent Tasks 5 and 6. ✓
