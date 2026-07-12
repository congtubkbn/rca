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
