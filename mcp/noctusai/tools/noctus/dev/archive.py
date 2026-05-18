"""Archive tool — auto-archive on close (project / feature / ad-hoc).

Implements the `noctus.dev.archive` MCP tool per `KB § PATTERNS/project-execution.md § 11.2 Archive system`.

Replaces the previous "delete on close" rule platform-wide. Closed projects/
features move to a structured `archive/` folder at repo root, preserving
content + chronological order + git history (via `git mv`).

Public surface:
    archive(target_path, mode=None, name=None, ..., skip_history=False) -> dict

When ``mode == "project"`` and ``skip_history`` is False (default), the tool
stamps a single record in ``project-history/ledger.ndjson`` BEFORE the
``git mv`` lands. Order is critical — the source project folder is the
input to ``history_record``; once moved, it's no longer at the original
path. Failures of ``history_record`` propagate (no silent skip).

MCP tool registration at module bottom via `register(server)` per the
per-file FastMCP registration pattern.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Import REPO_ROOT from settings per the centralization rule
# (`feedback_mcp_path_constants_from_settings.md`).
from settings import REPO_ROOT
from workspace import resolve_caller_root

# Sibling history-record tool — same file imports are cheap; tools share
# the dev-umbrella import surface.
from tools.noctus.dev.history import history_record

logger = logging.getLogger(__name__)

# Local timezone for date computation. Matches `noctusai_lib.api.scheduler`
# and sibling-product .env defaults (APP_TIMEZONE=America/Sao_Paulo).
_LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

_VALID_MODES = {"project", "feature", "ad_hoc"}

_NN_RE = re.compile(r"^(\d{2})-")


def _today_str() -> str:
    """Return today's date in local TZ as YYYY-MM-DD."""
    return datetime.now(tz=_LOCAL_TZ).strftime("%Y-%m-%d")


def _now_time_str() -> str:
    """Return current time in local TZ as HH-MM-SS (filesystem-safe)."""
    return datetime.now(tz=_LOCAL_TZ).strftime("%H-%M-%S")


def _detect_mode(target: Path) -> str:
    """Auto-detect mode from target path."""
    if target.name == "PROJECT.md":
        return "project"
    if target.is_dir() and (target / "PROJECT.md").exists():
        return "project"
    # Feature: .md file under features/ or products/<x>/features/ or core/features/
    if target.suffix == ".md":
        parts = target.parts
        if "features" in parts:
            return "feature"
    return "ad_hoc"


def _next_nn(date_dir: Path) -> int:
    """Compute next NN by listing date_dir and finding max(NN)+1.

    Examples folder content → next NN:
      []                                → 1
      ["01-foo", "02-bar"]              → 3
      ["01-foo"]                        → 2
      [".gitkeep"]                      → 1   (non-NN entries ignored)
    """
    if not date_dir.exists():
        return 1
    max_nn = 0
    for child in date_dir.iterdir():
        m = _NN_RE.match(child.name)
        if m:
            try:
                nn = int(m.group(1))
                if nn > max_nn:
                    max_nn = nn
            except ValueError:
                continue
    return max_nn + 1


def _git_mv(src: Path, dst: Path, repo_root: Path) -> None:
    """Run `git mv src dst`. Raises CalledProcessError on failure."""
    # Ensure parent of dst exists.
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "mv", str(src), str(dst)],
        check=True,
        cwd=str(repo_root),
        capture_output=True,
    )


def _derive_default_summary(project_md_text: str) -> str:
    """Derive a 1-sentence default summary from a PROJECT.md body.

    Best-effort: first non-empty, non-heading, non-blockquote line. Falls
    back to ``"(no summary available)"`` if nothing usable is found.
    Used only when the caller does not pass an explicit ``summary_md`` to
    ``archive()`` — explicit beats inferred.
    """
    for raw in project_md_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):  # heading
            continue
        if line.startswith(">"):  # blockquote (PROJECT.md uses ``>`` for status notes)
            continue
        if line.startswith("-") or line.startswith("*"):  # bullet
            # Strip bullet prefix and use the content.
            stripped = re.sub(r"^[-*]\s+", "", line)
            if stripped:
                return stripped
            continue
        return line
    return "(no summary available)"


def archive(
    target_path: str,
    mode: str | None = None,
    name: str | None = None,
    repo_root: Path | None = None,
    worktree_path: str | Path | None = None,
    skip_history: bool = False,
    status_at_close: str = "shipped",
    summary_md: str | None = None,
    review_md: str | None = None,
    outcome_signals: list[str] | None = None,
) -> dict:
    """Move target to the archive folder per `KB § PATTERNS/project-execution.md § 11.2`.

    Args:
        target_path: path to project folder, feature .md, or ad-hoc artifact.
            Relative to repo root or absolute.
        mode: "project" | "feature" | "ad_hoc" | None (auto-detect).
        name: ad-hoc only — descriptive name in `<date>_<time>_<name>`.
            Required when mode="ad_hoc"; ignored otherwise.
        repo_root: override (tests).
        worktree_path: **Caller-aware path resolution.** When set, the
            archive operation runs inside the given worktree (git mv lands
            files under ``<worktree>/archive/``) instead of the MCP server's
            startup workspace. Engineers in a git worktree pass their
            worktree root; architects on main noc omit. Mutually exclusive
            with ``repo_root`` (which is the test-seam override) — pass one
            or the other. See ``resolve_caller_root``.
        skip_history: when ``mode="project"`` and ``skip_history=False``
            (default), a single NDJSON record is appended to
            ``project-history/ledger.ndjson`` via
            ``noctus.dev.history_record`` BEFORE the ``git mv``. Pass
            ``True`` to opt-out (e.g. tests, backfill scripts, or when the
            ledger was already stamped manually). Ignored when
            ``mode != "project"``.
        status_at_close: one of ``shipped``, ``abandoned``, ``split``,
            ``deferred``, ``historical``. Defaults to ``"shipped"`` —
            archive's most common trigger. Only used when stamping the
            ledger.
        summary_md: 1-3 sentence summary; written to the ledger record's
            ``short_summary``. When ``None``, derived from PROJECT.md's
            first usable line.
        review_md: 5-10 bullet review; written to the ledger record's
            ``short_review``. When ``None``, defaults to the PROJECT.md
            body — phases are best-effort regex-extracted from it.
        outcome_signals: optional list of measured outcomes for the
            ledger record.

    Returns:
        {
          "archived_to": "<archive/relative/path>",  # path relative to repo root
          "mode": "project" | "feature" | "ad_hoc",
          "next_NN": int | None,                       # null for ad_hoc
          "history": <history_record_result_dict> | None,  # only when stamped
        }

    Raises:
        ValueError: invalid mode, missing name for ad_hoc, target doesn't exist,
            target already under archive/ (idempotency guard); also raised
            when ledger-stamp fails (propagated from ``history_record``).
        subprocess.CalledProcessError: git mv failure.
    """
    # Resolution order: explicit `repo_root` test seam wins; otherwise
    # route via `worktree_path` (caller-aware); otherwise fall back to
    # the server-startup REPO_ROOT.
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT
    target = Path(target_path)
    if not target.is_absolute():
        target = (root / target_path).resolve()
    else:
        target = target.resolve()

    if not target.exists():
        raise ValueError(f"target does not exist: {target}")

    archive_root = (root / "archive").resolve()
    if archive_root in target.parents or target == archive_root:
        raise ValueError(f"target already under archive/: {target}")

    # Resolve mode.
    resolved_mode = mode or _detect_mode(target)
    if resolved_mode not in _VALID_MODES:
        raise ValueError(f"invalid mode: {resolved_mode!r}, must be one of {_VALID_MODES}")

    # Slug derivation.
    if resolved_mode == "project":
        # If target is a PROJECT.md file, slug is parent folder name; we move the parent folder.
        if target.name == "PROJECT.md":
            target = target.parent
        slug = target.name
    elif resolved_mode == "feature":
        slug = target.stem  # filename without .md
    else:  # ad_hoc
        if not name or not name.strip():
            raise ValueError("name is required when mode='ad_hoc'")
        slug = name.strip()

    # Compute destination.
    today = _today_str()
    if resolved_mode == "project":
        date_dir = archive_root / "projects" / today
        nn = _next_nn(date_dir)
        dst = date_dir / f"{nn:02d}-{slug}"
    elif resolved_mode == "feature":
        date_dir = archive_root / "features" / today
        nn = _next_nn(date_dir)
        dst = date_dir / f"{nn:02d}-{slug}.md"
    else:  # ad_hoc
        nn = None
        time_str = _now_time_str()
        dst = archive_root / f"{today}_{time_str}_{slug}"

    # Ledger stamp — BEFORE the git mv, so the source path still exists
    # for `history_record` to read PROJECT.md / improvements.md /
    # proposals/. Only applies to project archives; opt-out via
    # ``skip_history=True``. Errors propagate (no silent skip per the
    # no-silent-errors rule).
    history_result: dict | None = None
    if resolved_mode == "project" and not skip_history:
        project_md_text = (target / "PROJECT.md").read_text(
            encoding="utf-8", errors="replace"
        )
        resolved_summary = (
            summary_md if summary_md is not None
            else _derive_default_summary(project_md_text)
        )
        resolved_review = (
            review_md if review_md is not None
            else project_md_text
        )
        history_result = history_record(
            project_path=str(target),
            status_at_close=status_at_close,
            summary_md=resolved_summary,
            review_md=resolved_review,
            outcome_signals=outcome_signals,
            repo_root=root,
        )
        logger.info(
            "archive: stamped ledger for slug=%s before git mv (line_count=%s)",
            slug, history_result.get("line_count"),
        )

    # Move via git mv (preserves history).
    _git_mv(target, dst, root)

    # Compute relative path for return.
    archived_to = str(dst.relative_to(root))

    logger.info(
        "archive: moved %s → %s (mode=%s, NN=%s)",
        target.relative_to(root) if root in target.parents or target == root else target,
        archived_to,
        resolved_mode,
        nn,
    )

    return {
        "archived_to": archived_to,
        "mode": resolved_mode,
        "next_NN": nn,
        "history": history_result,
    }
_ARCHIVE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _yesterday_str() -> str:
    """Return yesterday's date in local TZ as YYYY-MM-DD.

    Mirrors ``scripts/archive-clean.sh``'s local-time computation: the user
    invokes archive cleanup on *local-day* boundaries; UTC shifted the keep
    window forward by a day in the original 2026-05-12 incident.
    """
    return (datetime.now(tz=_LOCAL_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def archive_clean(
    repo_root: Path | None = None,
    *,
    worktree_path: str | Path | None = None,
    force: bool = False,
) -> dict:
    """Keep only today's + yesterday's ``archive/projects/<DATE>/`` folders.

    Behaviour-preserving native port of ``scripts/archive-clean.sh``.
    USER-INVOKED, NEVER AUTOMATIC (trigger phrases: "clean the archive" /
    "archive cleanup"). Anything D-2 or older is stale; today + yesterday
    are the recent-work window.

    Safety (identical to the shell script):
        * **Dry-run unless ``force=True``** — default lists stale folders
          but removes nothing.
        * Only operates on ``archive/projects/YYYY-MM-DD/`` folders. Never
          touches ``archive/features/`` or ad-hoc ``archive/<date>_<time>_*``.
        * Non-date entries (``README.md``, ``.gitkeep``) are skipped.
        * Removal uses ``git rm -rf`` so deletions are tracked (recoverable
          via ``git reset --hard`` pre-commit); falls back to filesystem
          ``rmtree`` only for non-git-tracked content (mirrors the script).

    Args:
        repo_root: repo-root override (test seam). Wins over
            ``worktree_path``.
        worktree_path: caller-aware path resolution — when set, operates on
            the caller's worktree (same contract as ``archive``).
        force: when ``False`` (default) the call is a DRY-RUN — stale
            folders are classified and returned but NOT removed. ``True``
            performs the ``git rm -rf``.

    Returns:
        ```
        {
          "archive_dir": "archive/projects",       # relative to repo root
          "keep_window": ["<yesterday>", "<today>"],
          "kept": ["<date-folder>", ...],
          "skipped": ["<non-date-entry>", ...],
          "stale": ["archive/projects/<date>", ...],   # rel paths, D-2+
          "dry_run": bool,                         # True == not force
          "removed": int,                          # 0 when dry_run
          "status": "ok" | "dry_run" | "removed" | "nothing",
        }
        ```
        ``status`` semantics mirror the script's exit behaviour:
        ``"nothing"`` — no ``archive/projects`` dir OR zero stale folders;
        ``"dry_run"`` — stale folders found, ``force=False``;
        ``"removed"`` — stale folders removed (``force=True``).
    """
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT

    archive_projects = (root / "archive" / "projects")
    rel_archive_dir = "archive/projects"

    if not archive_projects.is_dir():
        return {
            "archive_dir": rel_archive_dir,
            "keep_window": [_yesterday_str(), _today_str()],
            "kept": [],
            "skipped": [],
            "stale": [],
            "dry_run": not force,
            "removed": 0,
            "status": "nothing",
        }

    today = _today_str()
    yesterday = _yesterday_str()

    kept: list[str] = []
    skipped: list[str] = []
    stale_dirs: list[Path] = []
    stale_rel: list[str] = []

    for child in sorted(archive_projects.iterdir()):
        if not child.is_dir():
            # Mirrors the shell `[ -d "$dir" ] || continue` (README.md etc.).
            skipped.append(child.name)
            continue
        name = child.name
        if not _ARCHIVE_DATE_RE.match(name):
            skipped.append(name)
            continue
        if name == today or name == yesterday:
            kept.append(name)
        else:
            stale_dirs.append(child)
            stale_rel.append(f"{rel_archive_dir}/{name}")

    if not stale_dirs:
        return {
            "archive_dir": rel_archive_dir,
            "keep_window": [yesterday, today],
            "kept": kept,
            "skipped": skipped,
            "stale": [],
            "dry_run": not force,
            "removed": 0,
            "status": "nothing",
        }

    if not force:
        return {
            "archive_dir": rel_archive_dir,
            "keep_window": [yesterday, today],
            "kept": kept,
            "skipped": skipped,
            "stale": stale_rel,
            "dry_run": True,
            "removed": 0,
            "status": "dry_run",
        }

    removed = 0
    for d in stale_dirs:
        rel = str(d.relative_to(root))
        proc = subprocess.run(
            ["git", "rm", "-rf", "-q", rel],
            cwd=str(root),
            capture_output=True,
        )
        if proc.returncode == 0:
            removed += 1
        else:
            # Fallback for non-git-tracked content (mirrors the script's
            # `rm -rf "$dir"` fallback). shutil.rmtree is the Python analogue.
            try:
                shutil.rmtree(d)
                removed += 1
            except OSError as exc:
                logger.warning(
                    "archive_clean: failed to remove stale folder %s (%s)",
                    rel, exc,
                )

    logger.info(
        "archive_clean: removed %d stale folder(s) (keep window %s + %s)",
        removed, yesterday, today,
    )
    return {
        "archive_dir": rel_archive_dir,
        "keep_window": [yesterday, today],
        "kept": kept,
        "skipped": skipped,
        "stale": stale_rel,
        "dry_run": False,
        "removed": removed,
        "status": "removed",
    }


# ---------------------------------------------------------------------------
# FastMCP tool registration — see KB § PATTERNS/mcp-tool-conventions.md.
# ---------------------------------------------------------------------------

def register(server) -> None:
    """Register the archive MCP tool.

    Per `KB § PATTERNS/mcp-tool-conventions.md` — 3-segment dotted naming
    (`<vendor>.<service>.<action>`), direct function args matching the
    existing dev-umbrella convention.
    """
    @server.tool(
        name="noctus.dev.archive",
        description=(
            "Archive a project, feature, or ad-hoc artifact (replaces auto-delete on close). "
            "Mode auto-detected from path: PROJECT.md folder → project; .md under features/ → "
            "feature; else → ad_hoc (requires `name`). Lands at archive/projects/<today>/<NN>-"
            "<slug>/ or archive/features/<today>/<NN>-<slug>.md or archive/<date>_<time>_<name>/. "
            "Uses git mv (preserves history). Idempotency guard: refuses if target already under "
            "archive/. Pass `worktree_path` when called from inside a git worktree so the git mv "
            "+ archive landing happens in the worktree, not the MCP server's startup workspace. "
            "When mode=project and skip_history=False (default), a single NDJSON record is "
            "stamped into project-history/ledger.ndjson via noctus.dev.history_record BEFORE the "
            "git mv (status_at_close default 'shipped'; summary/review derived from PROJECT.md "
            "when not supplied). See KB § PATTERNS/project-execution.md § 11.2."
        ),
    )
    def _archive(
        target_path: str,
        mode: str | None = None,
        name: str | None = None,
        worktree_path: str | None = None,
        skip_history: bool = False,
        status_at_close: str = "shipped",
        summary_md: str | None = None,
        review_md: str | None = None,
        outcome_signals: list[str] | None = None,
    ) -> dict:
        return archive(
            target_path=target_path,
            mode=mode,
            name=name,
            worktree_path=worktree_path,
            skip_history=skip_history,
            status_at_close=status_at_close,
            summary_md=summary_md,
            review_md=review_md,
            outcome_signals=outcome_signals,
        )
    @server.tool(
        name="noctus.dev.archive_clean",
        description=(
            "Keep only today's + yesterday's archive/projects/<DATE>/ folders; "
            "classify everything D-2-or-older as stale. USER-INVOKED, NEVER "
            "AUTOMATIC (trigger phrases: 'clean the archive' / 'archive cleanup'). "
            "DRY-RUN by default — pass force=True to actually git rm -rf the stale "
            "folders (tracked removal; recoverable pre-commit via git reset --hard; "
            "filesystem-rmtree fallback only for non-git-tracked content). Only "
            "touches archive/projects/YYYY-MM-DD/ — never archive/features/ or "
            "ad-hoc archive/<date>_<time>_* dirs; non-date entries are skipped. "
            "Pass worktree_path when called from inside a git worktree. Behaviour-"
            "preserving port of scripts/archive-clean.sh. See KB § PATTERNS/"
            "project-execution.md § 11.2."
        ),
    )
    def _archive_clean(
        worktree_path: str | None = None,
        force: bool = False,
    ) -> dict:
        return archive_clean(worktree_path=worktree_path, force=force)
