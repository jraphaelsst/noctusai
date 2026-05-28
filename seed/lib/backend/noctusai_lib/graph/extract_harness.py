"""L2 harness extractor — `.claude/agents/`, `.claude/skills/`, `.claude/commands/`.

These are the methodology-fabric surfaces every fresh agent needs to orient on:
- agents = specialist subagents (architect / security / engineer-seed / …)
- skills = procedure docs auto-triggered on phrases (noc-self-branch, /codify, …)
- commands = user-invoked `/<name>` slash commands

Each surface becomes a node, with:
- HARNESS_AGENT → KB_PATTERN edges from frontmatter `owns_kb:` (OWNS_KB)
- HARNESS_SKILL → trigger-phrase decoration in node.meta (AUTO_TRIGGERS — synthetic
  phrase nodes intentionally NOT emitted; the trigger list is meta on the skill node
  itself, keeping the graph node-count bounded)
- KB_POINTER edges from any `KB §` reference in the body
- MEMORY_LINK edges from `[[slug]]` references

This is the layer the `/contextualize` skill + slash command reach into for fresh-
agent orientation: `noctus.graph.report focus_product=harness` or
`noctus.graph.query "skill" kinds=[harness_skill]`.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_OWNS_KB_BLOCK_RE = re.compile(r"^owns_kb:\s*\n((?:\s*-\s.*\n?)+)", re.MULTILINE)
_OWNS_KB_ITEM_RE = re.compile(r"^\s*-\s*(.+?)\s*$", re.MULTILINE)
_KB_POINTER_RE = re.compile(r"`?KB\s*§\s*([A-Za-z0-9_\-/]+\.md)(?:\s*§\s*[^`\n]+)?`?")
_MEMORY_LINK_RE = re.compile(r"\[\[([a-zA-Z0-9_\-]+)\]\]")
# `triggers/trigger phrases` in skill bodies — lines like:  - "phrase", "phrase2"
_TRIGGER_LINE_RE = re.compile(
    r'(?:trigger(?:s)?[^:\n]*:|fires (?:on|when)|use when)(.+?)(?=\n\n|\Z)',
    re.IGNORECASE | re.DOTALL,
)


def agent_id(name: str) -> str:
    return f"agent:{name}"


def skill_id(name: str) -> str:
    return f"skill:{name}"


def command_id(name: str) -> str:
    return f"command:{name}"


def walk_harness(graph: Graph, claude_dir: Path, *, repo_root: Path) -> None:
    """Walk `.claude/{agents,skills,commands}` and emit harness nodes."""
    if not claude_dir.exists():
        logger.info("graph.extract_harness: %s missing — skipping", claude_dir)
        return

    _walk_agents(graph, claude_dir / "agents", repo_root=repo_root)
    _walk_skills(graph, claude_dir / "skills", repo_root=repo_root)
    _walk_commands(graph, claude_dir / "commands", repo_root=repo_root)


def _walk_agents(graph: Graph, agents_dir: Path, *, repo_root: Path) -> None:
    if not agents_dir.exists():
        return
    for md_path in sorted(agents_dir.glob("*.md")):
        name = md_path.stem
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(body)
        node_id = agent_id(name)
        graph.add_node(Node(
            id=node_id,
            label=name,
            kind=NodeKind.HARNESS_AGENT,
            path=str(md_path.relative_to(repo_root).as_posix()),
            line=1,
            end_line=len(body.splitlines()),
            confidence=Confidence.AUTHORED.value,
            meta=_pack_meta({
                "description": fm.get("description", "")[:200],
                "model": fm.get("model"),
                "tools": fm.get("tools"),
            }),
        ))

        # OWNS_KB — agent → KB pattern (from frontmatter `owns_kb:` block)
        for kb_rel in _parse_owns_kb(body):
            graph.add_edge(Edge(
                source=node_id,
                target=f"kb:{kb_rel}",
                kind=EdgeKind.OWNS_KB,
                confidence=Confidence.AUTHORED.value,
            ))

        _emit_kb_and_memory_edges(graph, node_id, body)


def _walk_skills(graph: Graph, skills_dir: Path, *, repo_root: Path) -> None:
    if not skills_dir.exists():
        return
    # Skills can live as SKILL.md under a dir OR as a flat <name>.md.
    candidates: list[tuple[str, Path]] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir():
            sk = entry / "SKILL.md"
            if sk.exists():
                candidates.append((entry.name, sk))
        elif entry.is_file() and entry.suffix == ".md":
            candidates.append((entry.stem, entry))

    for name, md_path in candidates:
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(body)
        node_id = skill_id(name)

        triggers = _extract_triggers(body)
        graph.add_node(Node(
            id=node_id,
            label=name,
            kind=NodeKind.HARNESS_SKILL,
            path=str(md_path.relative_to(repo_root).as_posix()),
            line=1,
            end_line=len(body.splitlines()),
            confidence=Confidence.AUTHORED.value,
            meta=_pack_meta({
                "description": fm.get("description", "")[:200],
                "triggers": tuple(triggers[:10]) if triggers else None,
            }),
        ))
        _emit_kb_and_memory_edges(graph, node_id, body)


def _walk_commands(graph: Graph, commands_dir: Path, *, repo_root: Path) -> None:
    if not commands_dir.exists():
        return
    for md_path in sorted(commands_dir.glob("*.md")):
        name = md_path.stem
        try:
            body = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(body)
        node_id = command_id(name)
        graph.add_node(Node(
            id=node_id,
            label=f"/{name}",
            kind=NodeKind.HARNESS_COMMAND,
            path=str(md_path.relative_to(repo_root).as_posix()),
            line=1,
            end_line=len(body.splitlines()),
            confidence=Confidence.AUTHORED.value,
            meta=_pack_meta({
                "description": fm.get("description", "")[:200],
            }),
        ))
        _emit_kb_and_memory_edges(graph, node_id, body)


# ── Helpers ────────────────────────────────────────────────────────────────


def _parse_frontmatter(body: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(body)
    if not match:
        return {}
    fm_text = match.group(1)
    out: dict[str, str] = {}
    # Simple key: value parse — does NOT handle multi-line blocks (owns_kb handled elsewhere)
    for line in fm_text.splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _parse_owns_kb(body: str) -> list[str]:
    """Return KB rel-paths listed under `owns_kb:` block in frontmatter."""
    match = _FRONTMATTER_RE.match(body)
    if not match:
        return []
    fm_text = match.group(1)
    block = _OWNS_KB_BLOCK_RE.search(fm_text)
    if not block:
        return []
    return [m.group(1).strip().strip('"').strip("'") for m in _OWNS_KB_ITEM_RE.finditer(block.group(1))]


def _extract_triggers(body: str) -> list[str]:
    """Best-effort: pull quoted/listed trigger phrases from skill bodies."""
    triggers: list[str] = []
    for match in _TRIGGER_LINE_RE.finditer(body):
        chunk = match.group(1)
        for phrase in re.findall(r'"([^"]{3,80})"', chunk):
            triggers.append(phrase)
    return triggers


def _emit_kb_and_memory_edges(graph: Graph, source_id: str, body: str) -> None:
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


def _pack_meta(d: dict) -> tuple[tuple[str, object], ...]:
    """Drop None values + sort for hashability."""
    return tuple(sorted((k, v) for k, v in d.items() if v is not None))
