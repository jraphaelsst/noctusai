"""noctus.dev.scan_remediation_markers — batch-sweep the NOC-REMEDIATE deferral markers.

KB § PATTERNS/remediation-markers.md. The marker
``NOC-REMEDIATE[<class>]: <what + why> — <YYYY-MM-DD>`` is the sanctioned *non-silent*
deferral channel — the marker IS the named destination. This tool operationalizes the
batch sweep + triage the doc prescribes: find every marker, parse its class + age, group
by class, flag the malformed ones (no `[class]` / no date) and the **forbidden** ones (on
an ``except`` line — a marker must never suppress an error), and surface any class at
**N≥3** (the recurrence threshold ⇒ promote to a project / seed lift).

A *scan/query* tool (advisory) — recurrence gates enforcement, not querying — so it ships
ahead of the N≥3 a keeper would need. Exit 1 only on malformed/on-except markers (genuine
defects); a clean catalog of well-formed markers is exit 0.
"""
from __future__ import annotations

import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

# A REAL marker requires a non-placeholder ``[class]`` (no angle-brackets, non-empty)
# — that is the canonical shape AND the discriminator from prose that merely *mentions*
# the token (the defining docs use ``[<class>]`` or no bracket at all). Requiring a real
# ``[class]`` keeps the scanner from tripping on its own documentation (the same
# placeholder-exclusion lesson as the methodology doc-sync gate).
_MARKER_RE = re.compile(r"NOC-REMEDIATE\[(?P<cls>[^\]<>\s][^\]<>]*)\]\s*:?\s*(?P<text>.*)")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_EXCEPT_RE = re.compile(r"^\s*except\b")  # the line's CODE is an except clause (precise)


def _git_grep(root: Path) -> list[tuple[str, int, str]]:
    """(path, lineno, content) for every NOC-REMEDIATE occurrence in tracked files."""
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "grep", "-n", "--no-color", "NOC-REMEDIATE"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    out: list[tuple[str, int, str]] = []
    for ln in r.stdout.splitlines():
        parts = ln.split(":", 2)  # path:lineno:content
        if len(parts) == 3 and parts[1].isdigit():
            out.append((parts[0], int(parts[1]), parts[2]))
    return out


def scan_remediation_markers(
    repo_root: Path | None = None, worktree_path: str | None = None
) -> dict:
    """Sweep + triage NOC-REMEDIATE markers. See module docstring."""
    if repo_root is not None:
        root = Path(repo_root)
    elif worktree_path:
        root = Path(resolve_caller_root(worktree_path))
    else:
        root = REPO_ROOT
    today = date.today()

    markers: list[dict] = []
    malformed: list[dict] = []
    on_except: list[dict] = []
    by_class: dict[str, int] = {}

    for path, lineno, content in _git_grep(root):
        # Skip the doc that DEFINES the token + this scanner (self-reference).
        if path.endswith("remediation-markers.md") or "scan_remediation_markers" in path:
            continue
        m = _MARKER_RE.search(content)
        if not m:
            continue   # no real [class] ⇒ a prose/placeholder mention, not a marker
        cls = m.group("cls").strip()
        text = (m.group("text") or "").strip()
        dm = _DATE_RE.search(content)
        marker_date = dm.group(1) if dm else None
        age_days = None
        if marker_date:
            try:
                age_days = (today - datetime.strptime(marker_date, "%Y-%m-%d").date()).days
            except ValueError:
                marker_date = None
        rec = {
            "path": path, "line": lineno, "class": cls,
            "date": marker_date, "age_days": age_days, "text": text[:120],
        }
        markers.append(rec)
        if _EXCEPT_RE.match(content):   # FORBIDDEN — marker on an `except` (suppresses an error)
            on_except.append(rec)
        if not marker_date:            # malformed — a real marker missing its — <date>
            malformed.append(rec)
        by_class[cls] = by_class.get(cls, 0) + 1

    promote = sorted(c for c, n in by_class.items() if n >= 3)
    defects = len(malformed) + len(on_except)
    return {
        "ok": True,
        "total": len(markers),
        "by_class": dict(sorted(by_class.items(), key=lambda kv: -kv[1])),
        "promote_candidates": promote,   # class at N≥3 ⇒ promote to project / seed lift
        "malformed": malformed,          # missing [class] or — <date>
        "on_except": on_except,          # FORBIDDEN: a marker on an `except` line
        "oldest": sorted(
            (m for m in markers if m["age_days"] is not None),
            key=lambda m: -(m["age_days"] or 0),
        )[:10],
        "status": "defects" if defects else ("markers" if markers else "clean"),
        "exit_code": 1 if defects else 0,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scan_remediation_markers",
        description=(
            "Batch-sweep + triage the NOC-REMEDIATE deferral markers "
            "(KB § PATTERNS/remediation-markers.md). Finds every "
            "`NOC-REMEDIATE[<class>]: … — <YYYY-MM-DD>`, parses class + age, "
            "groups by class, flags malformed (no class/date) + FORBIDDEN "
            "on-`except` markers, and surfaces any class at N≥3 (promote to a "
            "project / seed lift). Advisory query — exit 1 only on defects. "
            "Pass worktree_path when called from inside a git worktree."
        ),
    )
    def _scan(worktree_path: str | None = None) -> dict:
        return scan_remediation_markers(worktree_path=worktree_path)


__all__ = ["scan_remediation_markers", "register"]
