"""L2 memory extractor — parse ``MEMORY.md`` index + per-slug frontmatter.

Each memory file becomes a ``MEMORY`` node. ``[[name]]`` references in
bodies become ``MEMORY_LINK`` edges. Pointers from memory bodies to KB
paths become ``KB_POINTER`` edges, same as KB→KB.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_FRONTMATTER_FIELD_RE = re.compile(r"^(\w+):\s*(.*)$", re.MULTILINE)
_MEMORY_LINK_RE = re.compile(r"\[\[([a-zA-Z0-9_\-]+)\]\]")
_KB_POINTER_RE = re.compile(r"`?KB\s*§\s*([A-Za-z0-9_\-/]+\.md)(?:\s*§\s*[^`\n]+)?`?")


def memory_id(slug: str) -> str:
    return f"mem:{slug}"


def walk_memory(graph: Graph, memory_root: Path, *, repo_root: Path) -> None:
    """Index ``MEMORY.md`` + every sibling ``*.md``.

    ``memory_root`` is the directory holding ``MEMORY.md`` (e.g.
    ``~/.claude/projects/<workspace>/memory/``). Stored outside the repo;
    we accept an explicit absolute path.
    """
    if not memory_root.exists():
        logger.info("graph.extract_memory: memory_root %s missing — skipping", memory_root)
        return

    for md_path in sorted(memory_root.glob("*.md")):
        if md_path.name == "MEMORY.md":
            continue  # index, not a memory entry
        slug = md_path.stem
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(body)
        label = fm.get("name", slug)
        description = fm.get("description", "")
        mem_kind = fm.get("type", "feedback")

        node_id = memory_id(slug)
        graph.add_node(Node(
            id=node_id,
            label=label,
            kind=NodeKind.MEMORY,
            path=str(md_path),  # absolute — memory lives outside the repo
            confidence=Confidence.AUTHORED.value,
            meta=(
                ("description", description[:200]),
                ("type", mem_kind),
            ),
        ))

        # [[name]] → memory link
        for match in _MEMORY_LINK_RE.finditer(body):
            target_slug = match.group(1)
            graph.add_edge(Edge(
                source=node_id,
                target=memory_id(target_slug),
                kind=EdgeKind.MEMORY_LINK,
                confidence=Confidence.AUTHORED.value,
            ))

        # KB § pointers in memory bodies
        for match in _KB_POINTER_RE.finditer(body):
            target_rel = match.group(1)
            graph.add_edge(Edge(
                source=node_id,
                target=f"kb:{target_rel}",
                kind=EdgeKind.KB_POINTER,
                confidence=Confidence.AUTHORED.value,
            ))


def _parse_frontmatter(body: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(body)
    if not match:
        return {}
    fm_text = match.group(1)
    out: dict[str, str] = {}
    for line in fm_text.splitlines():
        m = _FRONTMATTER_FIELD_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out
