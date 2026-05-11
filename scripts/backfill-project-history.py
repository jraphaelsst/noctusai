#!/usr/bin/env python3
"""backfill-project-history.py — stamp historical ledger records from archive/.

Walks ``archive/projects/<date>/NN-<slug>/PROJECT.md`` and appends one
ledger row per archived project with ``status_at_close="historical"``.
Per ``projects/project-history-ledger/PROJECT.md § 6 Phase 4`` +
``§ 7 Q5 = (α) best-effort backfill of all closed-or-deleted projects``.

Behavior:

- **Idempotent.** Re-running does NOT duplicate ledger entries. The
  idempotency key is ``(slug, dates.closed)`` over historical rows only
  — a tuple computed from the existing ledger before the walk. Live
  close stamps (``status_at_close in {shipped, abandoned, ...}``) are
  NOT considered duplicates of historical entries, because the canonical
  flow IS: backfill once → live close from then on.
- **Fail-loud.** A missing PROJECT.md, malformed archive folder name, or
  malformed existing-ledger line raises ``BackfillError`` with the path.
  No silent-skip — methodology rule.
- **Best-effort field extraction.** PROJECT.md ``Created:`` line for
  ``dates_created`` (set to ``None`` only when truly absent; historical
  projects predate the convention). The archive folder's date segment
  drives ``dates_closed``. Slug = folder name minus ``NN-`` prefix.
  Summary = first prose line of ``## 1. Context & Purpose``.
- **No git mv, no commits.** This script only appends to the ledger;
  the archive folder is left where it is. The orchestrator commits.

Usage:
    python scripts/backfill-project-history.py             # backfill all
    python scripts/backfill-project-history.py --dry-run   # print, no write
    python scripts/backfill-project-history.py --verbose   # extra logging

References:
- ``projects/project-history-ledger/PROJECT.md § 6 Phase 4``
- ``mcp/noctusai/tools/noctus/dev/history.py``
- ``feedback_mcp_write_tools_resolve_caller_root.md`` (passes
  ``worktree_path`` so the ledger lands in the caller's workspace).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# Repo root resolved from this file's location — script lives at
# ``scripts/backfill-project-history.py``; parent's parent is the repo
# root in a normal checkout. In a worktree, ``Path(__file__).parents[1]``
# resolves to the worktree root, which is exactly what we want.
REPO = Path(__file__).resolve().parents[1]

# Make the MCP tools package importable. The history_record function
# lives in ``mcp/noctusai/tools/noctus/dev/history.py`` and depends on
# ``settings.REPO_ROOT`` + ``workspace.resolve_caller_root`` (siblings).
# Mirror the structure that ``mcp/noctusai/server.py`` uses.
_MCP_DIR = REPO / "mcp" / "noctusai"
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

# History tool — imported AFTER sys.path is patched.
from tools.noctus.dev.history import history_record  # noqa: E402

logger = logging.getLogger("backfill-project-history")


# ---------------------------------------------------------------------------
# Custom error type — surfaces malformed archives loudly instead of skipping.
# ---------------------------------------------------------------------------


class BackfillError(RuntimeError):
    """Raised when an archive folder violates expected backfill structure.

    Per the no-silent-errors rule (``feedback_no_silent_errors.md``):
    methodology slips at the data layer surface here instead of
    silently truncating the historical ledger.
    """


# ---------------------------------------------------------------------------
# Field extraction — best-effort but verifiable.
# ---------------------------------------------------------------------------

# Pattern for archive folder names: ``NN-<slug>`` (e.g. ``01-archive-system``).
_NN_PREFIX_RE = re.compile(r"^(\d{2})-(.+)$")

# Pattern for ``- **Created:** YYYY-MM-DD`` line in PROJECT.md.
_CREATED_RE = re.compile(
    r"^\s*[-*]\s+\*\*Created:\*\*\s+(\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)


def _strip_nn_prefix(folder_name: str) -> str:
    """Return the bare slug from a ``NN-<slug>`` archive folder name.

    Raises ``BackfillError`` if the folder doesn't match the expected
    shape (callers should never reach this from a well-formed archive).
    """
    m = _NN_PREFIX_RE.match(folder_name)
    if not m:
        raise BackfillError(
            f"archive folder name doesn't match 'NN-<slug>' shape: {folder_name!r}"
        )
    return m.group(2)


def _extract_created_date(project_md_text: str) -> str | None:
    """Extract the ISO ``Created:`` date from a PROJECT.md body.

    Returns ``None`` when no Created line is present (older historical
    projects predate the convention; logged but not error).
    """
    m = _CREATED_RE.search(project_md_text)
    return m.group(1) if m else None


def _derive_short_summary(project_md_text: str) -> str:
    """Best-effort short summary from PROJECT.md.

    Two-tier extraction:

    1. **Primary:** first prose paragraph under ``## 1. Context & Purpose``
       (skipping its own heading, sub-headings, blockquotes, and
       metadata bullet lines). This is the human-authored intent — the
       right signal for historical entries.
    2. **Fallback:** first non-heading/non-blockquote/non-bullet line
       (matches ``archive._derive_default_summary`` shape so live
       close-stamps without §1 still degrade gracefully).

    Metadata bullet lines (``- **Created:** ...``, ``- **Status:** ...``,
    ``- **Owner:** ...``, etc.) are explicitly skipped — they are not
    project descriptions and were polluting the historical ledger
    summary cells.
    """
    lines = project_md_text.splitlines()

    # Tier 1: locate ``## 1. Context & Purpose`` heading; collect first
    # prose paragraph after it.
    context_heading = re.compile(r"^##\s+1\.\s+Context.*$", re.IGNORECASE)
    next_section = re.compile(r"^##\s+\d+\.\s+")
    in_section = False
    for raw in lines:
        if not in_section:
            if context_heading.match(raw.strip()):
                in_section = True
            continue
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            # Heading inside §1 — bail only on a next major section.
            if next_section.match(line):
                break
            continue
        if line.startswith(">"):
            continue
        if line.startswith("- ") or line.startswith("* "):
            continue  # metadata bullets, never the summary
        return line

    # Tier 2 fallback: archive.py-style derivation with metadata-skip.
    metadata_bullet = re.compile(
        r"^[-*]\s+\*\*(?:Created|Last updated|Status|Owner|Related|Project slug|Branch)"
    )
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith(">"):
            continue
        if metadata_bullet.match(line):
            continue
        if line.startswith("- ") or line.startswith("* "):
            stripped = re.sub(r"^[-*]\s+", "", line)
            if stripped:
                return stripped
            continue
        return line
    return "(no summary available)"


def _scope_from_archive_path(archive_project_dir: Path, repo: Path) -> str:
    """Best-effort scope from the archive path.

    Historical archives all live under ``archive/projects/<date>/NN-<slug>``
    — we can't reliably tell from archive-only data whether a project
    originated at ``projects/<slug>/`` (cross-product) or
    ``products/<X>/projects/<slug>/`` (single-product). Default to
    ``cross-product`` — accurate for the majority shape; per-project
    override can be added in a future enhancement.
    """
    return "cross-product"


# ---------------------------------------------------------------------------
# Idempotency — pre-load the existing ledger before walking archives.
# ---------------------------------------------------------------------------


def _load_existing_keys(ledger_path: Path) -> set[tuple[str, str]]:
    """Return ``{(slug, closed_date)}`` for existing historical rows.

    Live close-stamps (status_at_close != 'historical') are excluded
    from the idempotency key — historical backfill and live close-stamps
    are orthogonal events that legitimately co-exist for the same slug.
    """
    keys: set[tuple[str, str]] = set()
    if not ledger_path.exists():
        return keys
    with ledger_path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise BackfillError(
                    f"existing ledger {ledger_path}:{lineno} is malformed: "
                    f"{e.msg} — fix or remove this row before backfilling"
                ) from e
            if rec.get("status_at_close") != "historical":
                continue
            slug = rec.get("slug", "")
            closed = (rec.get("dates") or {}).get("closed", "")
            keys.add((slug, closed))
    return keys


# ---------------------------------------------------------------------------
# Archive walking + stamping.
# ---------------------------------------------------------------------------


def discover_archives(archive_root: Path) -> list[Path]:
    """Return sorted list of ``archive/projects/<date>/NN-<slug>/`` paths.

    Each returned path is a project directory containing PROJECT.md.
    Folders without PROJECT.md raise ``BackfillError`` (the archive
    system guarantees PROJECT.md presence; absence is a data-integrity
    issue, not a backfill skip).
    """
    projects_root = archive_root / "projects"
    if not projects_root.is_dir():
        return []
    found: list[Path] = []
    for date_dir in sorted(projects_root.iterdir()):
        if not date_dir.is_dir():
            continue
        # Skip files (e.g. README.md) directly under projects/.
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_dir.name):
            logger.debug(
                "skipping non-date entry under archive/projects/: %s",
                date_dir.name,
            )
            continue
        for proj_dir in sorted(date_dir.iterdir()):
            if not proj_dir.is_dir():
                continue
            project_md = proj_dir / "PROJECT.md"
            if not project_md.exists():
                raise BackfillError(
                    f"archive folder missing PROJECT.md: {proj_dir} — "
                    f"data-integrity issue, not a backfill skip"
                )
            found.append(proj_dir)
    return found


def stamp_one(
    archive_project_dir: Path,
    repo: Path,
    existing_keys: set[tuple[str, str]],
    *,
    dry_run: bool = False,
) -> tuple[str, dict | None]:
    """Stamp one archive's ledger row.

    Returns a ``(outcome, result)`` tuple where outcome is one of:

    - ``"stamped"`` — newly stamped (real run only); ``result`` is the
      ``history_record`` return dict.
    - ``"skipped_existing"`` — already in the ledger as a historical row.
    - ``"would_stamp"`` — dry-run preview; would have stamped if real.

    The split keeps dry-run accounting honest (callers can count
    ``would_stamp`` separately from ``skipped_existing``).
    """
    date_dir_name = archive_project_dir.parent.name  # e.g. ``2026-05-10``
    folder_name = archive_project_dir.name  # e.g. ``01-adconnect-mvp-implementation``
    canonical_slug = _strip_nn_prefix(folder_name)

    # Idempotency check: this slug+close-date already historically stamped?
    key = (canonical_slug, date_dir_name)
    if key in existing_keys:
        logger.info(
            "skip (already-stamped): slug=%s closed=%s",
            canonical_slug, date_dir_name,
        )
        return ("skipped_existing", None)

    # Read PROJECT.md once; use for created-date extraction + summary
    # derivation + review body. ``errors="replace"`` mirrors archive.py
    # — historical PROJECT.md files may carry stray bytes.
    project_md_text = (archive_project_dir / "PROJECT.md").read_text(
        encoding="utf-8", errors="replace"
    )
    created = _extract_created_date(project_md_text)
    summary = _derive_short_summary(project_md_text)
    # Review body — pass the full PROJECT.md so phase regex extraction
    # in history_record gets material to work with.
    review = project_md_text

    scope = _scope_from_archive_path(archive_project_dir, repo)

    if dry_run:
        logger.info(
            "[dry-run] would stamp: slug=%s closed=%s created=%s scope=%s "
            "(summary[:60]=%r)",
            canonical_slug, date_dir_name, created, scope, summary[:60],
        )
        return ("would_stamp", None)

    # Mirror live close-stamp shape: pass archive_project_dir as
    # ``project_path``; ``slug_override`` strips the NN- prefix so the
    # ledger row matches canonical slug convention. ``worktree_path``
    # ensures the ledger lands in THIS worktree's project-history dir.
    result = history_record(
        project_path=str(archive_project_dir),
        status_at_close="historical",
        summary_md=summary,
        review_md=review,
        scope=scope,
        dates_created=created,
        dates_closed=date_dir_name,
        slug_override=canonical_slug,
        worktree_path=str(repo),
    )
    existing_keys.add(key)
    logger.info(
        "stamped: slug=%s closed=%s tokens=%d (line %d)",
        canonical_slug,
        date_dir_name,
        result["record"]["token_count"]["total"],
        result["line_count"],
    )
    return ("stamped", result)


def backfill(repo: Path, *, dry_run: bool = False) -> dict:
    """Walk ``archive/projects/`` and stamp every project's ledger row.

    Returns a summary dict for the CLI to surface.
    """
    ledger_path = repo / "project-history" / "ledger.ndjson"
    existing_keys = _load_existing_keys(ledger_path)
    initial_count = (
        sum(1 for _ in ledger_path.open("r", encoding="utf-8"))
        if ledger_path.exists()
        else 0
    )

    archive_root = repo / "archive"
    archives = discover_archives(archive_root)

    stamped = 0
    skipped = 0
    would_stamp = 0
    for proj_dir in archives:
        outcome, _ = stamp_one(proj_dir, repo, existing_keys, dry_run=dry_run)
        if outcome == "stamped":
            stamped += 1
        elif outcome == "would_stamp":
            would_stamp += 1
        else:  # skipped_existing
            skipped += 1

    final_count = (
        sum(1 for _ in ledger_path.open("r", encoding="utf-8"))
        if ledger_path.exists()
        else 0
    )
    summary = {
        "archives_seen": len(archives),
        "stamped": stamped,
        "skipped_already_present": skipped,
        "ledger_lines_before": initial_count,
        "ledger_lines_after": final_count,
        "ledger_path": (
            str(ledger_path.relative_to(repo))
            if repo in ledger_path.parents
            else str(ledger_path)
        ),
        "dry_run": dry_run,
    }
    if dry_run:
        summary["would_stamp"] = would_stamp
    return summary


# ---------------------------------------------------------------------------
# CLI entry point.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk + log what would be stamped, but don't write to the ledger.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    p.add_argument(
        "--repo",
        type=Path,
        default=REPO,
        help=f"Repo root (default: {REPO}).",
    )
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        summary = backfill(args.repo, dry_run=args.dry_run)
    except BackfillError as e:
        logger.error("backfill aborted: %s", e)
        return 2

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
