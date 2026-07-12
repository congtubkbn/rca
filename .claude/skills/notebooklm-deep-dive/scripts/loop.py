"""notebooklm-deep-dive: mechanical core for the 10-round NotebookLM loop."""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

class NotebookLMError(RuntimeError):
    pass


REMINDER_SENTINEL = "EXTREMELY IMPORTANT: Is that ALL you need to know?"


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].rstrip("-")


def render_query(goal, round_num, max_rounds, question, already_asked):
    # NotebookLM (cold automated session) returns grounded prose and does NOT
    # reliably self-format; structuring + steering are done by Claude afterward,
    # so the prompt only carries context + the plain question, no output template.
    asked = "\n".join(f"- {q}" for q in already_asked) if already_asked else "(none)"
    return (
        f"[TASK GOAL]     {goal}\n"
        f"[ROUND]         {round_num}/{max_rounds}\n"
        f"[QUESTION]      {question}\n"
        f"[ALREADY ASKED]\n{asked}\n\n"
        f"Answer the QUESTION using ONLY notebook sources, and cite every claim.\n"
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


def write_round_files(task_dir, round_num, query, response_raw):
    d = Path(task_dir)
    nn = f"{round_num:02d}"
    (d / f"round-{nn}_query.md").write_text(query, encoding="utf-8")
    (d / f"round-{nn}_response.md").write_text(
        f"# Round {round_num} response\n\n{response_raw}\n", encoding="utf-8"
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
    # Force UTF-8 in the child: ask_question.py prints emoji, and on Windows a
    # piped subprocess defaults to cp1252, which crashes on those characters.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = runner(cmd, capture_output=True, text=True, timeout=timeout,
                  env=env, encoding="utf-8", errors="replace")
    stdout = proc.stdout or ""
    if (proc.returncode != 0
            or "Failed to get answer" in stdout
            or "Not authenticated" in stdout):
        stderr = (proc.stderr or "")[:500]
        raise NotebookLMError(
            f"call_notebooklm failed: returncode={proc.returncode}, "
            f"stderr[:500]={stderr!r}, stdout_tail[-500:]={stdout[-500:]!r}"
        )
    return extract_answer(stdout)


def _cmd_init(a):
    d = init_task(a.goal, a.seed, a.notebook_id, a.output_root,
                  timestamp=a.timestamp, max_rounds=a.max_rounds, language=a.language)
    print(str(d))
    return 0


def _cmd_ask(a):
    cfg = json.loads((Path(a.task_dir) / "config.json").read_text(encoding="utf-8"))
    query = render_query(cfg["goal"], a.round, cfg["max_rounds"],
                         a.question, already_asked_from_trace(a.task_dir))
    raw = call_notebooklm(query, cfg["notebook_url"])
    write_round_files(a.task_dir, a.round, query, raw)
    print(json.dumps({"round": a.round, "answer": raw}, ensure_ascii=False))
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
