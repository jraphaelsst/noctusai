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

# Docs that DEFINE the marker convention are self-reference — never scanned
# (the placeholder-exclusion lesson: a scanner must not trip on the docs that
# spell out its own token, even when they show a concrete ``[codify]`` example).
_DEFINING_DOCS = (
    "remediation-markers.md",                # the token definition
    "methodology-codification-pipeline.md",  # the pipeline meta-doc
    "codify.md",                             # the /codify command
    "dev/compliance.py",                     # the check_codification_debt keeper (handles [codify])
)


def _is_frozen_history(path: str) -> bool:
    """A verbatim RECORD of past code, not live code.

    `git format-patch` output archived by `salvage_before_delete` embeds whole
    source files as `+` lines — markers and all. Scanning them asks "is this
    deferral still open?" of a snapshot that is, by construction, immutable:
    the marker cannot be fixed, because editing an archived patch would falsify
    the record it exists to preserve.

    Found 2026-08-11, in CI, on `main`: archiving `feat/harness-audit-refit`
    for deletion carried a `NOC-REMEDIATE[codify]` line inside the patch, and
    `check_codification_debt` reported it as a NEW high-severity malformed
    marker — a compliance regression manufactured purely by recording history.
    A gate that fires on its own archive is a scope error, not debt.
    """
    return path.startswith("project-history/") and path.endswith(".patch")


def _is_defining_doc(path: str) -> bool:
    # The marker-machinery's own source + test files are self-reference: their
    # tests carry fixture markers (true/false-positive shapes) that must not
    # count as real deferrals. Substring matches both `<tool>.py` and
    # `tests/test_<tool>.py`.
    return (
        path.endswith(_DEFINING_DOCS)
        or "scan_remediation_markers" in path
        or "codification_debt" in path
    )


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


def _resolve_root(repo_root: Path | None, worktree_path: str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    if worktree_path:
        return Path(resolve_caller_root(worktree_path))
    return REPO_ROOT


def _iter_markers(root: Path) -> list[dict]:
    """Parsed record for every well-formed NOC-REMEDIATE marker (real ``[class]``).

    One parser, two surfaces: ``scan_remediation_markers`` (all classes,
    advisory CLI/MCP) + ``markers_of_class`` / the ``check_codification_debt``
    keeper (one class, in the compliance gate). Each record carries the
    ``on_except`` flag so both surfaces classify defects identically.
    """
    today = date.today()
    out: list[dict] = []
    for path, lineno, content in _git_grep(root):
        if _is_defining_doc(path) or _is_frozen_history(path):
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
        out.append({
            "path": path, "line": lineno, "class": cls,
            "date": marker_date, "age_days": age_days, "text": text[:120],
            "on_except": bool(_EXCEPT_RE.match(content)),  # FORBIDDEN — suppresses an error
        })
    return out


def scan_remediation_markers(
    repo_root: Path | None = None, worktree_path: str | None = None
) -> dict:
    """Sweep + triage NOC-REMEDIATE markers. See module docstring."""
    root = _resolve_root(repo_root, worktree_path)
    markers = _iter_markers(root)
    malformed = [m for m in markers if not m["date"]]
    on_except = [m for m in markers if m["on_except"]]
    by_class: dict[str, int] = {}
    for m in markers:
        by_class[m["class"]] = by_class.get(m["class"], 0) + 1

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


def markers_of_class(
    repo_root: Path | None = None, cls: str = "", worktree_path: str | None = None
) -> list[dict]:
    """Marker records for ONE class (e.g. ``"codify"``), or all if ``cls`` is empty.

    Shares ``_iter_markers`` with ``scan_remediation_markers`` — one parser,
    two surfaces. Backs the ``check_codification_debt`` keeper
    (KB § PATTERNS/methodology-codification-pipeline.md) — the always-on
    compliance-gate form of the ``/codify`` command's *detection* half.
    """
    root = _resolve_root(repo_root, worktree_path)
    return [m for m in _iter_markers(root) if not cls or m["class"] == cls]


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


__all__ = ["scan_remediation_markers", "markers_of_class", "register"]
