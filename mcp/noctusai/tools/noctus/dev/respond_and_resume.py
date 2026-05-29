"""noctus.dev.respond_and_resume — tech-lead response leg of the surface-and-resume loop.

When a blocked agent has filed a surface note (via noctus.dev.surface_to_tech_lead),
the tech-lead calls this tool to:
  1. Write a response file (.claude/dispatches/<wt-slug>/response-<surface_id>.md)
  2. Update the surface file's frontmatter status=responded
  3. Compose a ResumeBundle — the full state the next dispatch needs

The ResumeBundle is what noctus.dev.dispatch_resume_brief consumes to produce the
ready-to-dispatch brief text. This two-step (respond → dispatch_resume_brief)
lets the tech-lead review the composed preamble before committing to the dispatch.

Security note: surface_id is validated against path-traversal (can only resolve
to files inside .claude/dispatches/). An adversarial surface_id that contains
../ or absolute paths is rejected with an error — path traversal is forbidden.

KB § PATTERNS/common/surface-and-resume-tooling.md.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


def _dispatches_dir() -> Path:
    from settings import REPO_ROOT
    return REPO_ROOT / ".claude" / "dispatches"


def _now_iso_readable() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_surface_id(surface_id: str) -> bool:
    """surface_id may only contain alphanumeric, hyphen, underscore, dot, @.
    No slashes, no null bytes, no path traversal. Returns True if safe."""
    return bool(re.match(r"^[a-zA-Z0-9._@-]+$", surface_id))


def _find_surface_file(dispatches_dir: Path, surface_id: str) -> Path | None:
    """Find a surface file by surface_id. Safe: only looks in dispatches_dir."""
    for f in dispatches_dir.glob("*/surface-*.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if f"surface_id: {surface_id}" in text:
            return f
    return None


def _update_surface_status(surface_path: Path, new_status: str) -> None:
    """Rewrite the status field in the frontmatter of a surface file."""
    text = surface_path.read_text(encoding="utf-8")
    updated = re.sub(
        r"^(status:\s*)pending-response",
        f"\\g<1>{new_status}",
        text,
        flags=re.MULTILINE,
    )
    surface_path.write_text(updated, encoding="utf-8")


def _read_brief_ledger_excerpt(wt_slug: str) -> str | None:
    """Try to pull the most recent brief for this worktree slug from the brief ledger."""
    try:
        from .brief_ledger import query
        entries = query(slug_substring=wt_slug, limit=1)
        if entries:
            e = entries[0]
            return (
                f"**Original brief excerpt** (from brief ledger, slug={e.get('slug')}):\n\n"
                f"Agent: {e.get('agent', 'unknown')} | ts: {e.get('ts', '?')}\n\n"
                f"{e.get('full_brief_excerpt', e.get('description', '(no excerpt available)'))}"
            )
    except Exception as exc:
        logger.debug("respond_and_resume: brief_ledger query failed: %s", exc)
    return None


def respond_and_resume(
    surface_id: str,
    decision: Literal["approve", "reject", "adapt"],
    rationale_md: str,
    updated_brief_md: str | None = None,
) -> dict[str, Any]:
    """Respond to a pending surface and compose the ResumeBundle.

    Args:
        surface_id: The surface_id from the SurfaceReceipt (returned by
                    surface_to_tech_lead). Must exist as a pending-response
                    surface file.
        decision: 'approve' (proceed as proposed) | 'reject' (abandon the
                  proposed route) | 'adapt' (proceed with modifications in
                  updated_brief_md).
        rationale_md: The tech-lead's rationale — this is the durable
                      knowledge attached to the decision. Required (empty
                      rationale defeats the purpose of the tool).
        updated_brief_md: On 'adapt', the revised brief text the resumed agent
                          should execute. Optional on approve/reject (may carry
                          additional context even then).

    Returns:
        ResumeBundle dict with original_brief_excerpt, surface_md, response_md,
        worktree_state_pointer, and resume_preamble.
    """
    # Security: validate surface_id
    if not _validate_surface_id(surface_id):
        return {
            "ok": False,
            "error": (
                f"surface_id {surface_id!r} contains invalid characters — "
                "path traversal is forbidden."
            ),
        }

    if not rationale_md or not rationale_md.strip():
        return {
            "ok": False,
            "error": "rationale_md must not be empty — rationale is the durable knowledge.",
        }

    dispatches_dir = _dispatches_dir()
    surface_file = _find_surface_file(dispatches_dir, surface_id)
    if surface_file is None:
        return {
            "ok": False,
            "error": f"No surface file found for surface_id={surface_id!r}. "
                     "Run noctus.dev.list_pending_surfaces to see available surfaces.",
        }

    # Read surface content
    surface_text = surface_file.read_text(encoding="utf-8")

    # Parse worktree info from frontmatter
    wt_match = re.search(r"^worktree:\s*(.+)$", surface_text, re.MULTILINE)
    sha_match = re.search(r"^worktree_sha:\s*(\S+)", surface_text, re.MULTILINE)
    reason_match = re.search(r"^reason:\s*(.+)$", surface_text, re.MULTILINE)

    worktree = wt_match.group(1).strip().strip("'\"") if wt_match else "unknown"
    worktree_sha = sha_match.group(1).strip() if sha_match else "unknown"
    reason = reason_match.group(1).strip().strip("'\"") if reason_match else surface_id

    # Derive wt_slug for ledger lookup
    wt_slug = Path(worktree).name

    # Try brief ledger for original brief
    original_brief_excerpt = _read_brief_ledger_excerpt(wt_slug)

    # Write response file
    ts = _now_iso_readable()
    response_content = f"""---
surface_id: {surface_id}
decision: {decision}
ts: {ts}
---

# Tech-Lead Response to Surface `{surface_id}`

**Decision:** {decision.upper()}

**Reason that was surfaced:** {reason}

## Rationale

{rationale_md}

{f"## Updated Brief{chr(10)}{chr(10)}{updated_brief_md}" if updated_brief_md else ""}
"""
    response_path = surface_file.parent / f"response-{surface_id}.md"
    try:
        response_path.write_text(response_content, encoding="utf-8")
    except OSError as exc:
        logger.error("respond_and_resume: failed to write response file: %s", exc)
        return {"ok": False, "error": str(exc)}

    # Update surface frontmatter status=responded
    try:
        _update_surface_status(surface_file, "responded")
    except OSError as exc:
        logger.warning(
            "respond_and_resume: could not update surface status (non-fatal): %s", exc
        )

    # Compose resume_preamble
    resume_preamble = (
        f"RESUMING after surface-and-response:\n"
        f"  1. Read the surface at: {surface_file}\n"
        f"  2. Read the response at: {response_path}\n"
        f"  3. Restore worktree state at: {worktree}@{worktree_sha}\n"
        f"  4. Tech-lead decision: {decision.upper()} — {rationale_md.splitlines()[0] if rationale_md else ''}\n"
        f"  5. Continue from where the previous attempt blocked.\n"
    )

    worktree_state_pointer = {
        "worktree_path": worktree,
        "worktree_sha": worktree_sha,
        "verify_cmd": f"git -C {worktree!r} rev-parse HEAD",
    }

    resume_bundle = {
        "ok": True,
        "surface_id": surface_id,
        "decision": decision,
        "surface_path": str(surface_file),
        "response_path": str(response_path),
        "original_brief_excerpt": original_brief_excerpt or "(not found in ledger)",
        "surface_md": surface_text,
        "response_md": response_content,
        "worktree_state_pointer": worktree_state_pointer,
        "resume_preamble": resume_preamble,
        "next_step": (
            "Call noctus.dev.dispatch_resume_brief(surface_id='{sid}') "
            "to get the full composed brief text ready for dispatch."
        ).format(sid=surface_id),
    }

    logger.info(
        "respond_and_resume: responded surface_id=%s decision=%s response=%s",
        surface_id, decision, response_path,
    )

    return resume_bundle


def register(server) -> None:
    @server.tool(
        name="noctus.dev.respond_and_resume",
        description=(
            "Tech-lead response leg of the surface-and-resume loop. Given a "
            "surface_id (from a pending surface note filed by noctus.dev.surface_to_tech_lead), "
            "decision (approve/reject/adapt), and rationale_md, writes the response "
            "file and composes the ResumeBundle. "
            "Decision 'adapt' should include updated_brief_md with the revised brief. "
            "Returns the ResumeBundle with resume_preamble + worktree_state_pointer. "
            "Call noctus.dev.dispatch_resume_brief next to get the dispatch-ready brief text. "
            "Security: surface_id validated against path-traversal. "
            "KB § PATTERNS/common/surface-and-resume-tooling.md."
        ),
    )
    def _respond(
        surface_id: str,
        decision: str,
        rationale_md: str,
        updated_brief_md: str | None = None,
    ) -> dict:
        valid_decisions = ("approve", "reject", "adapt")
        if decision not in valid_decisions:
            return {
                "ok": False,
                "error": f"decision must be one of {valid_decisions}; got {decision!r}",
            }
        return respond_and_resume(
            surface_id=surface_id,
            decision=decision,  # type: ignore[arg-type]
            rationale_md=rationale_md,
            updated_brief_md=updated_brief_md,
        )
