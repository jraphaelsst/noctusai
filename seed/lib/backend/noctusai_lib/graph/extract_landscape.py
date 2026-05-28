"""L2 landscape extractor — CLAUDE.md + CLAUDE/*.md + CONTEXTUALIZE.md +
CHANGELOG.md + PROJECT-HISTORY.md.

These are first-class methodology surfaces the architect/router-discipline +
8-way-sync rules govern. Without them, the graph cannot answer "what's
loaded into every session?" — exactly what fresh agents need to know.

Each becomes a LANDSCAPE_DOC node + emits KB_POINTER edges to every `KB §`
reference and INVOKES_SKILL / INVOKES_AGENT edges for `skill <name>` / `agent
<name>` references the router carries.

KB chapter files (`KNOWLEDGE-BASE/0X-NAME.md`) become KB_CHAPTER nodes —
distinguished from KB_PATTERN because they're top-level orientation rather
than a single rule.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_KB_POINTER_RE = re.compile(r"`?KB\s*§\s*([A-Za-z0-9_\-/]+\.md)(?:\s*§\s*[^`\n]+)?`?")
_MEMORY_LINK_RE = re.compile(r"\[\[([a-zA-Z0-9_\-]+)\]\]")
# `skill <name>` or `· skill <name>` references (CLAUDE.md uses these)
_SKILL_REF_RE = re.compile(r"`skill\s+([a-z0-9\-]+)`|\bskill\s+`([a-z0-9\-]+)`")
# `agent <name>` references
_AGENT_REF_RE = re.compile(r"`agent\s+([a-z0-9\-]+)`|\bagent\s+`([a-z0-9\-]+)`")
# `/command-name` slash commands referenced inline
_COMMAND_REF_RE = re.compile(r"`/([a-z0-9\-]+)`")
# Top-level chapter regex: KB/<digits>-<name>.md
_CHAPTER_FILENAME_RE = re.compile(r"^(\d+)[a-z]?-[A-Z][A-Z0-9_\-]+\.md$")


def landscape_id(rel: str) -> str:
    """Stable id: `landscape:<repo-rel-path>`."""
    return f"landscape:{rel}"


def walk_landscape(graph: Graph, repo_root: Path) -> None:
    """Emit nodes for top-level methodology docs."""
    candidates: list[tuple[str, Path]] = []

    for name in ("CLAUDE.md", "CONTEXTUALIZE.md", "CHANGELOG.md", "VERSION"):
        p = repo_root / name
        if p.exists():
            candidates.append((name, p))

    claude_topic_dir = repo_root / "CLAUDE"
    if claude_topic_dir.is_dir():
        for p in sorted(claude_topic_dir.glob("*.md")):
            candidates.append((f"CLAUDE/{p.name}", p))

    project_history = repo_root / "project-history" / "PROJECT-HISTORY.md"
    if project_history.exists():
        candidates.append(("project-history/PROJECT-HISTORY.md", project_history))

    for rel, md_path in candidates:
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        node_id = landscape_id(rel)
        title = _extract_title(body) or md_path.stem
        graph.add_node(Node(
            id=node_id,
            label=title,
            kind=NodeKind.LANDSCAPE_DOC,
            path=rel,
            line=1,
            end_line=len(body.splitlines()),
            confidence=Confidence.AUTHORED.value,
        ))
        _emit_routing_edges(graph, node_id, body)


def walk_kb_chapters(graph: Graph, kb_root: Path, *, repo_root: Path) -> None:
    """Top-level `KNOWLEDGE-BASE/0X-NAME.md` chapters → KB_CHAPTER nodes.

    The general kb walker (extract_docs.walk_kb) already emits these — but
    classifies them as KB_PATTERN. We re-classify the top-level chapter
    set after-the-fact to make `noctus.graph.query kinds=[kb_chapter]`
    useful for orientation.
    """
    if not kb_root.exists():
        return
    for node in graph.nodes:
        if not node.id.startswith("kb:"):
            continue
        rel = node.id.removeprefix("kb:")
        leaf = rel.split("/")[-1]
        if "/" not in rel and _CHAPTER_FILENAME_RE.match(leaf):
            # Replace the node in place (dataclass frozen → reconstruct).
            from dataclasses import replace
            idx = next(i for i, n in enumerate(graph.nodes) if n.id == node.id)
            graph.nodes[idx] = replace(node, kind=NodeKind.KB_CHAPTER)


def _emit_routing_edges(graph: Graph, source_id: str, body: str) -> None:
    for match in _KB_POINTER_RE.finditer(body):
        graph.add_edge(Edge(
            source=source_id,
            target=f"kb:{match.group(1)}",
            kind=EdgeKind.KB_POINTER,
            confidence=Confidence.AUTHORED.value,
        ))
    for match in _MEMORY_LINK_RE.finditer(body):
        graph.add_edge(Edge(
            source=source_id,
            target=f"mem:{match.group(1)}",
            kind=EdgeKind.MEMORY_LINK,
            confidence=Confidence.AUTHORED.value,
        ))
    for match in _SKILL_REF_RE.finditer(body):
        name = match.group(1) or match.group(2)
        if name:
            graph.add_edge(Edge(
                source=source_id,
                target=f"skill:{name}",
                kind=EdgeKind.INVOKES_SKILL,
                confidence=Confidence.AUTHORED.value,
            ))
    for match in _AGENT_REF_RE.finditer(body):
        name = match.group(1) or match.group(2)
        if name:
            graph.add_edge(Edge(
                source=source_id,
                target=f"agent:{name}",
                kind=EdgeKind.INVOKES_AGENT,
                confidence=Confidence.AUTHORED.value,
            ))
    for match in _COMMAND_REF_RE.finditer(body):
        graph.add_edge(Edge(
            source=source_id,
            target=f"command:{match.group(1)}",
            kind=EdgeKind.INVOKES_SKILL,  # commands and skills overlap; the user invokes either
            confidence=Confidence.AUTHORED.value,
        ))


def _extract_title(body: str) -> str | None:
    for line in body.splitlines()[:50]:
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return None
