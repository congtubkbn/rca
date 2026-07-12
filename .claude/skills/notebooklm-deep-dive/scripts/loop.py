"""notebooklm-deep-dive: mechanical core for the 10-round NotebookLM loop."""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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


NOTEBOOKLM_RUN_PY = "C:/Users/Win 11/.claude/skills/notebooklm/scripts/run.py"


def call_notebooklm(question, notebook_url, run_py=NOTEBOOKLM_RUN_PY,
                    timeout=180, runner=subprocess.run, python_exe=None):
    cmd = [
        python_exe or sys.executable, run_py, "ask_question.py",
        "--question", question, "--notebook-url", notebook_url,
    ]
    proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    return extract_answer(proc.stdout)
