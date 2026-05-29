"""noctus.dev.surface_to_tech_lead — ergonomic surface-note writer for blocked agents.

Why this exists
    The surface-and-resume pattern (KB § PATTERNS/common/dispatch-with-project-and-notes.md)
    requires a blocked agent to file a structured note and exit. Before this tool,
    the friction of writing a well-formed surface made --no-verify bypass feel
    cheaper: the tool closes that gap by making a lossless surface one call away.

    An agent that hits a wall (permission gap, architectural mismatch, keeper
    failure, missing prerequisite) calls ``surface_to_tech_lead`` once. The call:
      (a) captures the current worktree state (diff bytes, dirty files, sha)
      (b) writes a structured surface file to .claude/dispatches/<wt-slug>/surface-<ts>.md
      (c) returns the SurfaceReceipt containing the exit_marker_msg the agent
          prints verbatim as its FINAL output line so orchestrators can detect
          the surface condition from tool results.

    The tech-lead reads the surface, decides (approve/reject/adapt), and calls
    noctus.dev.respond_and_resume to compose the ResumeBundle. The resumed agent
    calls noctus.dev.dispatch_resume_brief to get the full composed next brief.

Bypass forbidden
    Surfacing MUST NOT be skipped to avoid friction. This tool makes the
    round-trip cheap enough that bypass has no justification. KB § bg-engineer-safety
    (in-flight codification) and engineer-seed §1c both mandate surfacing.

KB § PATTERNS/common/surface-and-resume-tooling.md.
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SurfaceReceipt:
    surface_id: str
    surface_path: str
    exit_marker_msg: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_iso_readable() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dispatches_dir() -> Path:
    """Return .claude/dispatches/ under the repo root (primary worktree)."""
    from .cache_backend import cache_dir
    # cache_dir() → <git-common-dir>/noctusai/cache; walk up to git-common-dir
    # then up once more to the repo root. The .claude/dispatches dir is repo-durable
    # (not per-worktree) so it lives in the primary checkout's .claude/.
    from settings import REPO_ROOT
    return REPO_ROOT / ".claude" / "dispatches"


def _detect_worktree_path(cwd: str | None = None) -> str:
    """Return the current git worktree root (the checked-out path, not the bare repo)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
            cwd=cwd or os.getcwd(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("surface_to_tech_lead: git rev-parse failed: %s", exc)
    return cwd or os.getcwd()


def _wt_slug(worktree_path: str) -> str:
    """Derive a slug from the worktree path (last component, sanitized)."""
    name = Path(worktree_path).name
    # Keep alphanumeric + hyphen + underscore; collapse rest to hyphen
    import re
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
    return slug or "unknown"


def _capture_state_snapshot(worktree_path: str) -> dict[str, Any]:
    """Capture git diff bytes, dirty file list, uncommitted count, current sha."""
    snapshot: dict[str, Any] = {
        "diff_bytes": 0,
        "dirty_files": [],
        "uncommitted_count": 0,
        "worktree_sha": "unknown",
    }
    cwd = worktree_path

    # Current sha
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=cwd,
        )
        if r.returncode == 0:
            snapshot["worktree_sha"] = r.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("state_snapshot: rev-parse failed: %s", exc)

    # Dirty files (status --porcelain covers both staged and unstaged)
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd,
        )
        if r.returncode == 0:
            lines = [l for l in r.stdout.splitlines() if l.strip()]
            snapshot["dirty_files"] = [l[3:].strip() for l in lines]
            snapshot["uncommitted_count"] = len(lines)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("state_snapshot: status failed: %s", exc)

    # Diff size (staged + unstaged combined)
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=cwd,
        )
        if r.returncode == 0:
            snapshot["diff_bytes"] = len(r.stdout.encode("utf-8"))
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("state_snapshot: diff failed: %s", exc)

    return snapshot


def _write_surface_file(
    dispatches_dir: Path,
    wt_slug: str,
    surface_id: str,
    ts: str,
    worktree_path: str,
    snapshot: dict[str, Any],
    reason: str,
    proposal_md: str,
    current_state_md: str,
    attempted_resolution_md: str,
) -> Path:
    """Write the structured surface markdown file."""
    wt_dir = dispatches_dir / wt_slug
    wt_dir.mkdir(parents=True, exist_ok=True)

    surface_path = wt_dir / f"surface-{ts}.md"

    dirty_files_yaml = "\n".join(
        f"          - {f}" for f in snapshot["dirty_files"]
    ) or "          []"
    if not snapshot["dirty_files"]:
        dirty_files_yaml_block = "        dirty_files: []"
    else:
        dirty_files_yaml_block = "        dirty_files:\n" + dirty_files_yaml

    frontmatter = f"""---
surface_id: {surface_id}
worktree: {worktree_path}
worktree_sha: {snapshot['worktree_sha']}
reason: {reason!r}
state_snapshot:
        diff_bytes: {snapshot['diff_bytes']}
{dirty_files_yaml_block}
        uncommitted_count: {snapshot['uncommitted_count']}
attempted_resolution: |
{chr(10).join('    ' + l for l in attempted_resolution_md.splitlines())}
status: pending-response
ts: {_now_iso_readable()}
---"""

    body = f"""# Surface Note: {reason}

> surface_id: `{surface_id}` | worktree: `{worktree_path}` | sha: `{snapshot['worktree_sha']}`

## Proposal / What the agent needs

{proposal_md}

## Current State

{current_state_md}

## Attempted Resolution

{attempted_resolution_md}

---
*Filed by `noctus.dev.surface_to_tech_lead`. Respond with `noctus.dev.respond_and_resume(surface_id="{surface_id}", ...)`.*
"""

    surface_path.write_text(frontmatter + "\n\n" + body, encoding="utf-8")
    return surface_path


def surface_to_tech_lead(
    reason: str,
    proposal_md: str,
    current_state_md: str,
    attempted_resolution_md: str,
    *,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """File a structured surface note and return the SurfaceReceipt.

    Args:
        reason: One-line summary of the blocker (used as the surface headline
                and the surface_id slug component).
        proposal_md: What the agent is proposing / what it needs approval for
                     (≤200 lines). May include code snippets and context.
        current_state_md: Where the agent is right now — files modified,
                          staged content, tests run, what works / what doesn't.
        attempted_resolution_md: What the agent already tried + why it stopped.
        worktree_path: Explicit worktree path. If None, auto-detected from cwd.

    Returns:
        Dict with surface_id, surface_path, exit_marker_msg (print this last).
    """
    # Validate inputs
    if not reason or not reason.strip():
        return {"ok": False, "error": "reason must not be empty"}
    if len(proposal_md.splitlines()) > 200:
        logger.warning(
            "surface_to_tech_lead: proposal_md is %d lines (limit 200) — "
            "trim to keep surfaces scannable",
            len(proposal_md.splitlines()),
        )

    # Detect worktree
    wt_path = worktree_path or _detect_worktree_path()

    # Capture state
    snapshot = _capture_state_snapshot(wt_path)

    # Build IDs
    ts = _now_iso()
    slug = _wt_slug(wt_path)
    surface_id = f"{slug}-{ts}"

    # Write surface file
    try:
        dispatches_dir = _dispatches_dir()
        surface_path = _write_surface_file(
            dispatches_dir=dispatches_dir,
            wt_slug=slug,
            surface_id=surface_id,
            ts=ts,
            worktree_path=wt_path,
            snapshot=snapshot,
            reason=reason,
            proposal_md=proposal_md,
            current_state_md=current_state_md,
            attempted_resolution_md=attempted_resolution_md,
        )
    except OSError as exc:
        logger.error("surface_to_tech_lead: failed to write surface file: %s", exc)
        return {"ok": False, "error": str(exc)}

    exit_marker_msg = (
        f"SURFACE_FILED:{surface_id} "
        f"path={surface_path} "
        f"reason={reason!r} "
        f"dirty_files={snapshot['uncommitted_count']} "
        f"WAITING_FOR_TECH_LEAD_RESPONSE"
    )

    logger.info(
        "surface_to_tech_lead: surface filed surface_id=%s path=%s",
        surface_id, surface_path,
    )

    return {
        "ok": True,
        "surface_id": surface_id,
        "surface_path": str(surface_path),
        "worktree": wt_path,
        "worktree_sha": snapshot["worktree_sha"],
        "dirty_files": snapshot["dirty_files"],
        "uncommitted_count": snapshot["uncommitted_count"],
        "exit_marker_msg": exit_marker_msg,
        "instruction": (
            "Print exit_marker_msg verbatim as your FINAL output line so the "
            "orchestrator's result parser detects the surface condition. "
            "Then stop — do NOT continue executing the blocked task."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.surface_to_tech_lead",
        description=(
            "File a structured surface note when BLOCKED — the ergonomic "
            "no-bypass round-trip. Captures worktree state (diff bytes, dirty "
            "files, sha) + writes .claude/dispatches/<wt-slug>/surface-<ts>.md "
            "with YAML frontmatter. Returns SurfaceReceipt with surface_id, "
            "surface_path, and exit_marker_msg (print this verbatim as the "
            "FINAL output line so the orchestrator detects the block). "
            "Bypass FORBIDDEN per engineer-seed §1c + bg-engineer-safety rule. "
            "Tech-lead responds with noctus.dev.respond_and_resume. "
            "KB § PATTERNS/common/surface-and-resume-tooling.md."
        ),
    )
    def _surface(
        reason: str,
        proposal_md: str,
        current_state_md: str,
        attempted_resolution_md: str,
        worktree_path: str | None = None,
    ) -> dict:
        return surface_to_tech_lead(
            reason=reason,
            proposal_md=proposal_md,
            current_state_md=current_state_md,
            attempted_resolution_md=attempted_resolution_md,
            worktree_path=worktree_path,
        )
