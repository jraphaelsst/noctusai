"""Archive tool — auto-archive on close (project / feature / ad-hoc).

Implements the `noctus.dev.archive` MCP tool per `KB § PATTERNS/project-execution.md § 11.2 Archive system`.

Replaces the previous "delete on close" rule platform-wide. Closed projects/
features move to a structured `archive/` folder at repo root, preserving
content + chronological order + git history (via `git mv`).

Public surface:
    archive(target_path, mode=None, name=None) -> dict

MCP tool registration at module bottom via `register(server)` per the
per-file FastMCP registration pattern.
"""
from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Import REPO_ROOT from settings per the centralization rule
# (`feedback_mcp_path_constants_from_settings.md`).
from settings import REPO_ROOT

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


def archive(
    target_path: str,
    mode: str | None = None,
    name: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Move target to the archive folder per `KB § PATTERNS/project-execution.md § 11.2`.

    Args:
        target_path: path to project folder, feature .md, or ad-hoc artifact.
            Relative to repo root or absolute.
        mode: "project" | "feature" | "ad_hoc" | None (auto-detect).
        name: ad-hoc only — descriptive name in `<date>_<time>_<name>`.
            Required when mode="ad_hoc"; ignored otherwise.
        repo_root: override (tests).

    Returns:
        {
          "archived_to": "<archive/relative/path>",  # path relative to repo root
          "mode": "project" | "feature" | "ad_hoc",
          "next_NN": int | None,                       # null for ad_hoc
        }

    Raises:
        ValueError: invalid mode, missing name for ad_hoc, target doesn't exist,
            target already under archive/ (idempotency guard).
        subprocess.CalledProcessError: git mv failure.
    """
    root = repo_root or REPO_ROOT
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
            "archive/. See KB § PATTERNS/project-execution.md § 11.2 Archive system."
        ),
    )
    def _archive(
        target_path: str,
        mode: str | None = None,
        name: str | None = None,
    ) -> dict:
        return archive(
            target_path=target_path,
            mode=mode,
            name=name,
        )
