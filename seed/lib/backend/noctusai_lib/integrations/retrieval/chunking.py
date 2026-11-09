"""Markdown-aware chunking — pure, deterministic, no IO.

Sections follow `#` headings (the heading path is kept as the chunk's topic),
paragraphs are packed up to `max_chars`, a fenced code block is never split,
and a single paragraph longer than `max_chars` is window-split with `overlap`
characters carried between windows (overlap is only needed where a sentence
can be cut mid-way; packed paragraphs break on blank lines).
"""
from __future__ import annotations

import hashlib
import re

from .types import Chunk

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP = 150

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def content_hash(heading: str, content: str) -> str:
    return hashlib.sha256(f"{heading}\n{content}".encode("utf-8")).hexdigest()


def _blocks(lines: list[str]) -> list[str]:
    """Blank-line separated blocks; a fenced block stays one block."""
    blocks: list[str] = []
    cur: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


def _window_split(text: str, max_chars: int, overlap: int) -> list[str]:
    out: list[str] = []
    step = max_chars - overlap
    start = 0
    while start < len(text):
        out.append(text[start:start + max_chars].strip())
        if start + max_chars >= len(text):
            break
        start += step
    return [o for o in out if o]


def chunk_markdown(
    text: str, *, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[Chunk]:
    """Split `text` into ordered chunks. Empty/blank text -> `[]` (the caller
    decides whether an empty corpus is an error)."""
    if max_chars < 50:
        raise ValueError("max_chars must be >= 50")
    if not 0 <= overlap < max_chars // 2:
        raise ValueError("overlap must be >= 0 and < max_chars/2")
    sections: list[tuple[str, list[str]]] = []
    path: list[tuple[int, str]] = []
    cur_heading = ""
    cur_lines: list[str] = []
    in_fence = False
    for line in (text or "").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            sections.append((cur_heading, cur_lines))
            level, title = len(m.group(1)), m.group(2)
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
            cur_heading = " > ".join(t for _, t in path)
            cur_lines = []
        else:
            cur_lines.append(line)
    sections.append((cur_heading, cur_lines))

    chunks: list[Chunk] = []

    def emit(heading: str, body: str) -> None:
        body = body.strip()
        if body:
            chunks.append(Chunk(heading, body, len(chunks), content_hash(heading, body)))

    for heading, lines in sections:
        buf = ""
        for block in _blocks(lines):
            if len(block) > max_chars:
                emit(heading, buf)
                buf = ""
                for piece in _window_split(block, max_chars, overlap):
                    emit(heading, piece)
                continue
            candidate = f"{buf}\n\n{block}" if buf else block
            if len(candidate) > max_chars:
                emit(heading, buf)
                buf = block
            else:
                buf = candidate
        emit(heading, buf)
    return chunks
