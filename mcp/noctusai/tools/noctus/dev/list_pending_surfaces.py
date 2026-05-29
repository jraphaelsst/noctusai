"""noctus.dev.list_pending_surfaces — orchestrator read-side of the surface-and-resume loop.

Lists all surface notes under .claude/dispatches/*/surface-*.md that have
status=pending-response (i.e., filed by a blocked agent but not yet responded to).

Tech-leads call this at the start of an integration session to see what agents
surfaced during their absence. Each summary includes the surface_id, worktree,
reason headline, dirty-file count, and age so the tech-lead can triage quickly.

KB § PATTERNS/common/surface-and-resume-tooling.md.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SurfaceSummary:
    surface_id: str
    surface_path: str
    worktree: str
    reason: str
    dirty_file_count: int
    status: str
    ts: str
    age_hours: float


def _dispatches_dir() -> Path:
    from settings import REPO_ROOT
    return REPO_ROOT / ".claude" / "dispatches"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter key: value pairs (simple string values only).

    Handles the scalar fields surface_to_tech_lead writes (surface_id, worktree,
    worktree_sha, reason, status, ts, uncommitted_count). Nested dicts/lists
    (state_snapshot.dirty_files) are represented via sub-key indentation; we
    pull uncommitted_count by key-prefix matching.
    """
    result: dict[str, str] = {}
    if not text.startswith("---"):
        return result
    # Find end of frontmatter
    end = text.find("\n---", 3)
    if end == -1:
        return result
    fm_text = text[3:end]
    for line in fm_text.splitlines():
        # Top-level scalar: key: value (no leading spaces)
        m = re.match(r"^([a-zA-Z_]+):\s*(.+)", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip().strip("'\"")
            result[key] = val
        # Indented scalar for state_snapshot fields
        m2 = re.match(r"^\s+([a-zA-Z_]+):\s*(.+)", line)
        if m2:
            key2 = m2.group(1).strip()
            val2 = m2.group(2).strip().strip("'\"")
            result[key2] = val2
    return result


def _age_hours(ts_str: str) -> float:
    """Return float hours since ts_str (ISO 8601). Returns 999 on parse failure."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        return round(delta.total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        return 999.0


def list_pending_surfaces(
    include_responded: bool = False,
) -> list[dict[str, Any]]:
    """Walk .claude/dispatches and return surfaces matching the status filter.

    Args:
        include_responded: If True, return ALL surfaces (pending + responded).
                           Default False returns only pending-response.

    Returns:
        List of SurfaceSummary dicts, newest first.
    """
    dispatches_dir = _dispatches_dir()
    if not dispatches_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for surface_file in sorted(dispatches_dir.glob("*/surface-*.md"), reverse=True):
        try:
            text = surface_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("list_pending_surfaces: cannot read %s: %s", surface_file, exc)
            continue

        fm = _parse_frontmatter(text)
        status = fm.get("status", "unknown")

        if not include_responded and status != "pending-response":
            continue

        try:
            dirty_count = int(fm.get("uncommitted_count", "0"))
        except ValueError:
            dirty_count = 0

        ts_str = fm.get("ts", "")
        results.append({
            "surface_id": fm.get("surface_id", surface_file.stem),
            "surface_path": str(surface_file),
            "worktree": fm.get("worktree", "unknown"),
            "reason": fm.get("reason", "(no reason)"),
            "dirty_file_count": dirty_count,
            "status": status,
            "ts": ts_str,
            "age_hours": _age_hours(ts_str),
        })

    return results


def register(server) -> None:
    @server.tool(
        name="noctus.dev.list_pending_surfaces",
        description=(
            "List surface notes filed by blocked agents that are awaiting "
            "tech-lead response. Walks .claude/dispatches/*/surface-*.md and "
            "returns summaries for status=pending-response files. Each summary "
            "includes surface_id, worktree, reason headline, dirty-file count, "
            "and age. Tech-leads check this at session start / after a wave. "
            "Pass include_responded=True to see all surfaces including already-"
            "responded ones. Respond to a surface with noctus.dev.respond_and_resume. "
            "KB § PATTERNS/common/surface-and-resume-tooling.md."
        ),
    )
    def _list(include_responded: bool = False) -> list[dict]:
        surfaces = list_pending_surfaces(include_responded=include_responded)
        if not surfaces:
            return [{"message": "(0 pending surfaces)"}]
        return surfaces
