"""Small text helpers shared by the summary/methodology services."""
from __future__ import annotations

import re

# Screen-recording filename noise that leaks a brand + timestamp into titles, e.g.
# "… - CORE Educação - Google Chrome 2026-05-21 14-23-09". Stripped for privacy/raw.
_TITLE_NOISE = [
    re.compile(r"\s*-\s*CORE Educação\b.*$"),
    re.compile(r"\s*-\s*Google Chrome \d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}\s*$"),
]


def clean_lesson_title(name: str) -> str:
    """Strip recording-tool/brand noise from a lesson title or filename stem."""
    for pat in _TITLE_NOISE:
        name = pat.sub("", name)
    return name.strip()


def strip_code_fence(text: str) -> str:
    """Remove a wrapping ```/```markdown fence the LLM sometimes adds around output."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    lines = lines[1:]  # drop opening ``` / ```markdown
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]  # drop closing ```
    return "\n".join(lines).strip()


__all__ = ["strip_code_fence", "clean_lesson_title"]
