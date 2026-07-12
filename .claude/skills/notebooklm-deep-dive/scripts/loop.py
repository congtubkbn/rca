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
