"""noctus.dev.version_guard — MAJOR-bump authorization gate.

The architect/agent autonomously authors PATCH (`4.0.0 → 4.0.1`) and MINOR
(`4.0.x → 4.1.0`) bumps per Conventional Commits semantics. MAJOR bumps
(`4.x.x → 5.0.0`) are the user's call — the *.0 ramp belongs to the human.

This gate compares the staged `VERSION` against `HEAD:VERSION`. If MAJOR
ticked up, the commit MUST be authorized by the presence of an
`.major-bump-authorized` marker file at repo root with a one-line rationale.
Without the marker, the gate refuses (severity high) — surfaced as a
blocking pre-commit check.

The marker is git-tracked (so the authorization is visible in history) but
short-lived: the same commit that bumps MAJOR removes the marker, so a
stale marker can't re-arm a future un-authorized bump.

KB § PATTERNS/common/versioning.md § Authorization gate.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?P<pre>-[a-zA-Z0-9.]+)?\s*$"
)

_MARKER_FILENAME = ".major-bump-authorized"


def _parse_semver(text: str) -> tuple[int, int, int, str] | None:
    """Parse a VERSION-style line. Returns (major, minor, patch, pre) or None."""
    m = _SEMVER_RE.match(text.strip())
    if not m:
        return None
    return (
        int(m.group("major")),
        int(m.group("minor")),
        int(m.group("patch")),
        m.group("pre") or "",
    )


def _read_head_version(root: Path) -> str:
    """Read VERSION at git HEAD. Empty string if VERSION doesn't exist in HEAD."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "show", "HEAD:VERSION"],
            capture_output=True,
            text=True,
        )
        return proc.stdout if proc.returncode == 0 else ""
    except OSError:
        return ""


def check_version_bump(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Refuse an unauthorized MAJOR bump.

    Compares working-tree VERSION against HEAD's VERSION. If MAJOR ticked up,
    requires `<repo_root>/.major-bump-authorized` to exist. Marker contents
    are surfaced in the return so the rationale travels with the audit trail.

    Returns: ``{ok, status, current, head, marker_present, marker_rationale,
    message}``.

    Status values:
      - ``no_change``      — VERSION unchanged vs HEAD
      - ``minor_or_patch`` — bump within current MAJOR (autonomous OK)
      - ``major_authorized`` — MAJOR bumped AND marker present
      - ``major_unauthorized`` — MAJOR bumped without marker (BLOCKS)
      - ``parse_error``    — couldn't parse one or both versions
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    version_file = root / "VERSION"

    if not version_file.exists():
        return {
            "ok": True,
            "status": "no_change",
            "current": None,
            "head": None,
            "message": "no VERSION file — gate is a no-op",
        }

    current_text = version_file.read_text(encoding="utf-8")
    head_text = _read_head_version(root)

    current = _parse_semver(current_text)
    head = _parse_semver(head_text) if head_text else None

    if current is None:
        return {
            "ok": False,
            "status": "parse_error",
            "current": current_text.strip(),
            "head": head_text.strip() if head_text else None,
            "message": f"unparseable working-tree VERSION: {current_text.strip()!r}",
        }

    if head is None:
        # VERSION didn't exist in HEAD yet (e.g. brand-new repo) — treat as
        # no-change, the file's being introduced.
        return {
            "ok": True,
            "status": "no_change",
            "current": current_text.strip(),
            "head": None,
            "message": "VERSION not in HEAD — initial introduction, no gate needed",
        }

    if current == head:
        return {
            "ok": True,
            "status": "no_change",
            "current": current_text.strip(),
            "head": head_text.strip(),
            "message": "VERSION unchanged",
        }

    if current[0] == head[0]:
        return {
            "ok": True,
            "status": "minor_or_patch",
            "current": current_text.strip(),
            "head": head_text.strip(),
            "message": (
                f"MINOR/PATCH bump within MAJOR={current[0]} — autonomous OK "
                f"({head_text.strip()} → {current_text.strip()})"
            ),
        }

    # MAJOR ticked up — require the marker.
    marker = root / _MARKER_FILENAME
    if marker.exists():
        try:
            rationale = marker.read_text(encoding="utf-8").strip()
        except OSError:
            rationale = ""
        return {
            "ok": True,
            "status": "major_authorized",
            "current": current_text.strip(),
            "head": head_text.strip(),
            "marker_present": True,
            "marker_rationale": rationale or "(no rationale recorded)",
            "message": (
                f"MAJOR bump {head[0]} → {current[0]} authorized by "
                f".major-bump-authorized: {rationale or '(empty)'}"
            ),
        }

    return {
        "ok": False,
        "status": "major_unauthorized",
        "current": current_text.strip(),
        "head": head_text.strip(),
        "marker_present": False,
        "message": (
            f"REFUSED: MAJOR bump {head[0]} → {current[0]} requires "
            f"explicit user authorization. Create "
            f"`{_MARKER_FILENAME}` at repo root with a one-line rationale, "
            f"stage it with the VERSION bump in the SAME commit, then retry. "
            f"The *.0 ramp belongs to the human; agents author PATCH/MINOR "
            f"autonomously. KB § PATTERNS/common/versioning.md § Authorization gate."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.version_guard",
        description=(
            "MAJOR-bump authorization gate. Refuses a working-tree VERSION "
            "whose MAJOR component exceeds HEAD's MAJOR unless "
            "`.major-bump-authorized` exists at repo root (the human's "
            "explicit consent token). Autonomous PATCH/MINOR bumps within "
            "the current MAJOR pass through. Returns `status` ∈ "
            "{no_change, minor_or_patch, major_authorized, "
            "major_unauthorized, parse_error}."
        ),
    )
    def _version_guard() -> dict:
        return check_version_bump()


__all__ = ["check_version_bump", "register"]
