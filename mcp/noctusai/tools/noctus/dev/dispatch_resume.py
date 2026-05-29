"""noctus.dev.dispatch_resume_brief — final leg of the surface-and-resume round-trip.

Given a surface_id that has been responded to (via noctus.dev.respond_and_resume),
composes the FULL brief text ready for Agent() dispatch. The orchestrator passes
this text verbatim as the resumed agent's brief.

The composed brief contains:
  - Resume preamble (state restoration instructions + worktree pointer)
  - Original goal / brief excerpt (from brief ledger or surface body)
  - The surface note body (what the previous agent was blocked on)
  - The tech-lead's response (decision + rationale + updated brief if any)
  - Cache-first reflex reminder (standing protocol, not per-agent boilerplate)
  - Safety rules reminder (stage-only, no-no-verify, worktree isolation)
  - The worktree path the resumed agent should target

Security: surface_id validated against path-traversal (same as respond_and_resume).

KB § PATTERNS/common/surface-and-resume-tooling.md.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _dispatches_dir() -> Path:
    from settings import REPO_ROOT
    return REPO_ROOT / ".claude" / "dispatches"


def _validate_surface_id(surface_id: str) -> bool:
    """Same validation as respond_and_resume — alphanumeric + safe chars only."""
    return bool(re.match(r"^[a-zA-Z0-9._@-]+$", surface_id))


def _find_surface_and_response(
    dispatches_dir: Path, surface_id: str
) -> tuple[Path | None, Path | None]:
    """Return (surface_path, response_path) for a surface_id. Safe: dispatches_dir only."""
    surface_path: Path | None = None
    response_path: Path | None = None

    for f in dispatches_dir.glob("*/surface-*.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if f"surface_id: {surface_id}" in text:
            surface_path = f
            break

    if surface_path is not None:
        candidate = surface_path.parent / f"response-{surface_id}.md"
        if candidate.exists():
            response_path = candidate

    return surface_path, response_path


def dispatch_resume_brief(surface_id: str) -> dict[str, Any]:
    """Compose the full brief text for dispatching a resumed agent.

    Args:
        surface_id: The surface_id from a responded surface note.

    Returns:
        Dict with ok, brief_text (the full brief string), worktree_path,
        and decision.
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

    dispatches_dir = _dispatches_dir()
    surface_path, response_path = _find_surface_and_response(dispatches_dir, surface_id)

    if surface_path is None:
        return {
            "ok": False,
            "error": (
                f"No surface file found for surface_id={surface_id!r}. "
                "Run noctus.dev.list_pending_surfaces(include_responded=True) "
                "to see all surfaces."
            ),
        }

    if response_path is None:
        return {
            "ok": False,
            "error": (
                f"No response file found for surface_id={surface_id!r}. "
                "Call noctus.dev.respond_and_resume first, then dispatch_resume_brief."
            ),
        }

    surface_text = surface_path.read_text(encoding="utf-8")
    response_text = response_path.read_text(encoding="utf-8")

    # Extract key fields from surface frontmatter
    wt_match = re.search(r"^worktree:\s*(.+)$", surface_text, re.MULTILINE)
    sha_match = re.search(r"^worktree_sha:\s*(\S+)", surface_text, re.MULTILINE)
    reason_match = re.search(r"^reason:\s*(.+)$", surface_text, re.MULTILINE)

    worktree = wt_match.group(1).strip().strip("'\"") if wt_match else "unknown"
    worktree_sha = sha_match.group(1).strip() if sha_match else "unknown"
    reason = reason_match.group(1).strip().strip("'\"") if reason_match else surface_id

    # Extract decision from response frontmatter
    decision_match = re.search(r"^decision:\s*(\S+)", response_text, re.MULTILINE)
    decision = decision_match.group(1).strip() if decision_match else "unknown"

    # Try brief ledger for original goal
    wt_slug = Path(worktree).name
    original_goal_section = ""
    try:
        from .brief_ledger import query
        entries = query(slug_substring=wt_slug, limit=1)
        if entries:
            e = entries[0]
            excerpt = e.get("full_brief_excerpt", e.get("description", ""))
            if excerpt:
                original_goal_section = f"""## Original Goal / Brief (from brief ledger)

{excerpt}

---
"""
    except Exception as exc:
        logger.debug("dispatch_resume_brief: brief_ledger query failed: %s", exc)

    # Build the composed brief
    brief_text = f"""# RESUMED DISPATCH — surface-and-resume round-trip

> This brief was composed by `noctus.dev.dispatch_resume_brief(surface_id="{surface_id}")`.
> It carries the original goal, the surface, the tech-lead response, and
> the resume preamble so you can pick up exactly where the previous agent stopped.

## Resume Preamble (read first)

You are RESUMING an agent session that stopped at a surface note.

1. **Verify your worktree:** your worktree is `{worktree}` (sha at surface time: `{worktree_sha}`)
   - Run: `git -C "{worktree}" rev-parse HEAD && git -C "{worktree}" status --porcelain`
   - If the worktree is gone or the sha diverged, surface again via
     `noctus.dev.surface_to_tech_lead` with reason="worktree-state-diverged".

2. **Read the surface** at: `{surface_path}`
3. **Read the response** at: `{response_path}`
4. **Tech-lead decision:** {decision.upper()} — see response below.
5. **Continue from where the previous agent blocked:** `{reason}`

---

{original_goal_section}## The Surface Note (what the previous agent filed)

> Source: `{surface_path}`

{surface_text}

---

## Tech-Lead Response (the decision you are acting on)

> Source: `{response_path}`

{response_text}

---

## Standing Protocol Reminders

### Cache-first reflex (non-negotiable, per engineer-seed §0)
- **Discovery** → MCP cache call FIRST: `noctus.dev.kb_search` / `code_search` /
  `memory_search` / `corpus_search` (semantic) · `noctus.graph.*` (structural)
- `grep` / `Read` / `Glob` are CONFIRMATION tools after the cache narrows scope, not discovery.
- Reaching for grep before a cache call is a methodology slip.

### Safety rules (non-negotiable, per engineer-seed §1-§2)
- Confirm you are IN your isolated worktree `{worktree}` (not the primary checkout).
- `git add` explicit paths only — never `-A` or `.`.
- Do NOT `git commit` or `git push` — architect-only.
- NEVER `--no-verify`. If a hook fails, surface again via `noctus.dev.surface_to_tech_lead`.
- Verify on-disk via `git diff --cached --name-only` + `grep` before reporting ready.

### Worktree path
```
{worktree}
```

---

## Your Task

Based on the tech-lead's decision ({decision.upper()}) and rationale above, continue
from where the previous agent stopped. The surface reason was: `{reason}`.

If you hit another blocker, call `noctus.dev.surface_to_tech_lead` again — do NOT
proceed past a genuine blocker, do NOT use `--no-verify` as a shortcut.
"""

    logger.info(
        "dispatch_resume_brief: composed brief surface_id=%s decision=%s worktree=%s",
        surface_id, decision, worktree,
    )

    return {
        "ok": True,
        "surface_id": surface_id,
        "decision": decision,
        "worktree_path": worktree,
        "brief_text": brief_text,
        "surface_path": str(surface_path),
        "response_path": str(response_path),
        "instruction": (
            "Pass brief_text verbatim as the agent's brief in your Agent() dispatch. "
            "Set the worktree path as the agent's working directory."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.dispatch_resume_brief",
        description=(
            "Final leg of the surface-and-resume round-trip. Given a surface_id "
            "that has been responded to (via noctus.dev.respond_and_resume), "
            "composes the FULL brief text ready for Agent() dispatch. The "
            "orchestrator passes brief_text verbatim as the resumed agent's brief. "
            "The composed brief includes: resume preamble (state restoration + "
            "worktree pointer) + original goal excerpt (from brief ledger) + "
            "surface note body + tech-lead response + cache-first reflex reminder "
            "+ safety rules + worktree path. "
            "Security: surface_id validated against path-traversal. "
            "KB § PATTERNS/common/surface-and-resume-tooling.md."
        ),
    )
    def _dispatch_resume(surface_id: str) -> dict:
        return dispatch_resume_brief(surface_id=surface_id)
