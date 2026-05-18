"""`noctus.dev.check_disk_usage` — warn before disk pressure becomes a lockout.

Behaviour-preserving native port of ``scripts/disk-usage-monitor.sh``.

Why this exists
    2026-05-11 incident: data volume hit 100% mid-session (664 MiB free of
    460 GiB) blocking Engineer III + the orchestrator's own Bash output
    staging. Recovery via worktree sweep recovered 68 GiB. This monitor
    catches the pressure BEFORE it locks the harness — at 70% (caution) and
    80% (action-required).

What it does
    Reports current % used on the data volume + estimates the agent-worktree
    footprint. The shell script's exit codes 0/1/2/3 are preserved verbatim
    and surfaced as ``status`` + ``exit_code`` fields:

        0  — under 70% (healthy)            → status "OK"
        1  — 70-79% (CAUTION)               → status "CAUTION"
        2  — 80-89% (WARNING)               → status "WARNING"
        3  — 90-100% (CRITICAL)             → status "CRITICAL"

Auto-clean
    The shell ``--auto-clean`` flag (run ``cleanup-stale-worktrees.sh
    --force`` when ≥70%) is preserved as ``auto_clean=True``, which delegates
    to the sibling native tool ``cleanup_stale_worktrees`` (forced) rather
    than shelling out — same effect, no script dependency. Default is
    advisory-only (``auto_clean=False``).
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from settings import REPO_ROOT
from workspace import resolve_caller_root

logger = logging.getLogger(__name__)

# Matches sibling-tool / .env defaults (APP_TIMEZONE=America/Sao_Paulo).
_LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

# Thresholds — verbatim from scripts/disk-usage-monitor.sh.
_PCT_CRITICAL = 90  # ≥90% → CRITICAL (exit 3)
_PCT_WARNING = 80   # ≥80% → WARNING  (exit 2)
_PCT_CAUTION = 70   # ≥70% → CAUTION  (exit 1)


def _classify(pct_used: int) -> tuple[str, int, str]:
    """(severity, exit_code, hint) for a usage percentage.

    Bands + hint strings preserved verbatim from the shell script's
    severity-classification block.
    """
    if pct_used >= _PCT_CRITICAL:
        return (
            "CRITICAL",
            3,
            "Harness lockout imminent. Manual recovery required NOW: "
            "cleanup stale worktrees (force); docker system prune -a -f; "
            "sudo purge",
        )
    if pct_used >= _PCT_WARNING:
        return (
            "WARNING",
            2,
            "Cleanup REQUIRED before new dispatches. Run the stale-worktree "
            "sweep (force).",
        )
    if pct_used >= _PCT_CAUTION:
        return (
            "CAUTION",
            1,
            "Schedule a sweep soon. Run the stale-worktree cleanup.",
        )
    return ("OK", 0, "")


def check_disk_usage(
    repo_root: Path | None = None,
    *,
    worktree_path: str | Path | None = None,
    target_path: str | Path | None = None,
    auto_clean: bool = False,
) -> dict:
    """Report disk pressure on the data volume + agent-worktree footprint.

    Behaviour-preserving native port of ``scripts/disk-usage-monitor.sh``.
    Read-only by default; ``auto_clean=True`` mirrors the shell
    ``--auto-clean`` flag.

    Args:
        repo_root: repo-root override (test seam). Wins over
            ``worktree_path``.
        worktree_path: caller-aware path resolution (same contract as the
            sibling dev tools).
        target_path: volume to measure. Defaults to ``/`` (the shell script
            uses ``df -P /``). Test seam — point at a tmp path to assert the
            stat plumbing without depending on the host's real disk.
        auto_clean: when ``True`` and severity ≥ CAUTION, delegates to the
            native ``cleanup_stale_worktrees(force=True)`` (the script
            shelled out to ``cleanup-stale-worktrees.sh --force``). Default
            ``False`` (advisory only).

    Returns:
        ```
        {
          "timestamp": "<YYYY-MM-DD HH:MM:SS>",
          "volume": "<path measured>",
          "pct_used": int,
          "avail_gb": float,
          "total_gb": int,
          "worktree_count": int,
          "worktree_size_bytes": int,
          "severity": "OK"|"CAUTION"|"WARNING"|"CRITICAL",
          "exit_code": 0|1|2|3,        # verbatim shell exit semantics
          "status": same as severity,  # convenience alias
          "hint": "<action string>",   # "" when OK
          "auto_clean_ran": bool,
          "auto_clean_result": <cleanup dict> | None,
        }
        ```
    """
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT

    volume = Path(target_path) if target_path is not None else Path("/")

    usage = shutil.disk_usage(str(volume))
    total = usage.total
    used = usage.used
    free = usage.free
    # `df -P` capacity is ceil(used / total * 100); shutil gives exact bytes.
    pct_used = int(round(used / total * 100)) if total else 0
    avail_gb = round(free / 1024 / 1024 / 1024, 1)
    total_gb = int(round(total / 1024 / 1024 / 1024))

    # Agent-worktree footprint (the shell `du -sh .claude/worktrees`).
    wtree_dir = root / ".claude" / "worktrees"
    wtree_count = 0
    wtree_size = 0
    if wtree_dir.is_dir():
        for child in wtree_dir.iterdir():
            if child.is_dir() and child.name.startswith("agent-"):
                wtree_count += 1
        for p in wtree_dir.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    wtree_size += p.stat().st_size
            except OSError:
                continue

    severity, exit_code, hint = _classify(pct_used)

    auto_clean_ran = False
    auto_clean_result: dict | None = None
    if auto_clean and exit_code >= 1:
        # Native delegation — the shell shelled out to
        # cleanup-stale-worktrees.sh --force; we call the sibling tool.
        from tools.noctus.dev.cleanup_worktrees import cleanup_stale_worktrees

        auto_clean_result = cleanup_stale_worktrees(
            repo_root=root, force=True,
        )
        auto_clean_ran = True
        logger.info(
            "check_disk_usage: auto-clean ran (severity=%s, removed=%s)",
            severity, auto_clean_result.get("removed"),
        )

    return {
        "timestamp": datetime.now(tz=_LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "volume": str(volume),
        "pct_used": pct_used,
        "avail_gb": avail_gb,
        "total_gb": total_gb,
        "worktree_count": wtree_count,
        "worktree_size_bytes": wtree_size,
        "severity": severity,
        "exit_code": exit_code,
        "status": severity,
        "hint": hint,
        "auto_clean_ran": auto_clean_ran,
        "auto_clean_result": auto_clean_result,
    }


def register(server) -> None:
    """Register the disk-usage MCP tool (3-segment dotted naming)."""

    @server.tool(
        name="noctus.dev.check_disk_usage",
        description=(
            "Warn before disk pressure becomes a 100% harness lockout. "
            "Reports data-volume %-used + agent-worktree footprint; preserves "
            "scripts/disk-usage-monitor.sh exit semantics (≥70% CAUTION / "
            "≥80% WARNING / ≥90% CRITICAL) as status+exit_code. Read-only by "
            "default; auto_clean=True delegates to the native stale-worktree "
            "sweep (force) when severity ≥ CAUTION. Pass worktree_path when "
            "called from inside a git worktree."
        ),
    )
    def _check_disk_usage(
        worktree_path: str | None = None,
        auto_clean: bool = False,
    ) -> dict:
        return check_disk_usage(
            worktree_path=worktree_path, auto_clean=auto_clean,
        )
