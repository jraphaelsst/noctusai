"""L2 doc extractor — KB patterns + KB pointers + findings/projects.

Each `KNOWLEDGE-BASE/*.md` file becomes a node (kind classified by its
folder). Inline `KB §` pointer references become `KB_POINTER` edges.
Code-path-like strings in KB bodies (``products/...``, ``seed/...``,
``noctusai_lib.X``) become `DOCUMENTS` edges to the corresponding code
nodes (best-effort — only emits when the code node was extracted).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_KB_FOLDER_KINDS: dict[str, NodeKind] = {
    "PATTERNS": NodeKind.KB_PATTERN,
    "GUIDES": NodeKind.KB_GUIDE,
    "INTEGRATIONS": NodeKind.KB_INTEGRATION,
    "backend": NodeKind.KB_BACKEND_SPEC,
    "frontend": NodeKind.KB_FRONTEND_SPEC,
    "MCP-SERVERS": NodeKind.KB_INTEGRATION,
    "INSTRUCTIONS": NodeKind.KB_GUIDE,
}

# Match "KB § PATTERNS/foo.md" or "KB § PATTERNS/foo.md § Section"
_KB_POINTER_RE = re.compile(r"`?KB\s*§\s*([A-Za-z0-9_\-/]+\.md)(?:\s*§\s*[^`\n]+)?`?")

# Match references to code paths in KB prose.
_CODE_PATH_RE = re.compile(
    r"`(products/[A-Za-z0-9_\-]+/(?:backend|frontend)/[A-Za-z0-9_\-/.]+\.(?:py|ts|tsx))`"
)


def kb_id(rel_path: str) -> str:
    """Stable id: ``kb:<rel-from-KB-root>`` (e.g. ``kb:PATTERNS/ast.md``)."""
    return f"kb:{rel_path}"


def walk_kb(graph: Graph, kb_root: Path, *, repo_root: Path) -> None:
    """Index every `.md` under ``KNOWLEDGE-BASE/`` and link to code nodes."""
    if not kb_root.exists():
        logger.warning("graph.extract_docs: KB root %s missing", kb_root)
        return

    code_node_ids = {n.id for n in graph.nodes if n.id.startswith("code:")}

    for md_path in kb_root.rglob("*.md"):
        rel = md_path.relative_to(kb_root).as_posix()
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Classify by the most specific folder under KB root that maps to a
        # known kind — walks the path parts from deepest to shallowest so a
        # file at `CONTEXT/PATTERNS/foo.md` classifies as PATTERN, not CONTEXT.
        parts = rel.split("/")
        kind = NodeKind.KB_PATTERN
        for part in parts[:-1]:  # skip the filename
            if part in _KB_FOLDER_KINDS:
                kind = _KB_FOLDER_KINDS[part]
        # If parent-folder name matches, prefer the most-specific (deepest) match.
        for part in reversed(parts[:-1]):
            if part in _KB_FOLDER_KINDS:
                kind = _KB_FOLDER_KINDS[part]
                break

        node_id = kb_id(rel)
        title = _extract_title(body) or md_path.stem
        first_line = _first_prose_line(body) or ""

        graph.add_node(Node(
            id=node_id,
            label=title,
            kind=kind,
            path=str(md_path.relative_to(repo_root).as_posix()),
            line=1,
            end_line=len(body.splitlines()),
            confidence=Confidence.AUTHORED.value,
            meta=(("first_line", first_line[:200]),) if first_line else (),
        ))

        # KB → KB pointer edges
        for match in _KB_POINTER_RE.finditer(body):
            target_rel = match.group(1)
            graph.add_edge(Edge(
                source=node_id,
                target=kb_id(target_rel),
                kind=EdgeKind.KB_POINTER,
                confidence=Confidence.AUTHORED.value,
            ))

        # KB → code DOCUMENTS edges (only when the code node exists)
        for match in _CODE_PATH_RE.finditer(body):
            target_code = f"code:{match.group(1)}"
            if target_code in code_node_ids:
                graph.add_edge(Edge(
                    source=node_id,
                    target=target_code,
                    kind=EdgeKind.DOCUMENTS,
                    confidence=Confidence.AUTHORED.value,
                ))


def _extract_title(body: str) -> str | None:
    """Return the first H1, stripped of leading ``#``."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _first_prose_line(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", ">", "-", "|", "```", "<!--")):
            continue
        return stripped
    return None


def walk_projects(graph: Graph, projects_root: Path, *, repo_root: Path) -> None:
    """Index `projects/**/PROJECT.md` and `products/*/projects/**/PROJECT.md`."""
    if not projects_root.exists():
        return
    for md_path in projects_root.rglob("PROJECT.md"):
        # Skip archived
        if "archive" in md_path.parts:
            continue
        rel = md_path.relative_to(repo_root).as_posix()
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        title = _extract_title(body) or md_path.parent.name
        node_id = f"project:{md_path.parent.name}"
        graph.add_node(Node(
            id=node_id,
            label=title,
            kind=NodeKind.PROJECT,
            path=rel,
            confidence=Confidence.AUTHORED.value,
        ))


def walk_findings(graph: Graph, repo_root: Path) -> None:
    """Index every `findings.md` in the active workspace (not archive)."""
    for md_path in repo_root.rglob("findings.md"):
        if "archive" in md_path.parts or "node_modules" in md_path.parts:
            continue
        rel = md_path.relative_to(repo_root).as_posix()
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        title = _extract_title(body) or f"findings — {md_path.parent.name}"
        node_id = f"finding:{md_path.parent.name}"
        graph.add_node(Node(
            id=node_id,
            label=title,
            kind=NodeKind.FINDING,
            path=rel,
            confidence=Confidence.AUTHORED.value,
        ))
