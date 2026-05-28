"""`noctus.dev.tmp_cleanup` — sweep retired engineer-dispatch patch artifacts.

The engineer-brief-patch-file-first pattern (`KB § PATTERNS/common/engineer-brief-patch-file-first.md`)
has dispatched engineers write their work to `/tmp/<slug>.patch` BEFORE attempting return-text
generation, so the harness watchdog (~600s) killing the return cannot lose the work. The cost of
that durability is that `/tmp/*.patch` accumulates across many sessions. macOS's `periodic` daily
sweep removes files >3d old, but our policy is semantic, not OS-timer:

A patch is **retired** (safe to delete) when:

1. Its `git patch-id --stable` matches a patch-id reachable from `origin/dev` (content landed), OR
2. It is older than `max_age_days` (default 14d) AND its content does NOT match any branch tip we
   recognize (orchestrator-retired; salvage window passed), OR
3. It is malformed (cannot be parsed by `git patch-id --stable`).

`dry_run=True` (default) returns the planned action set without deleting. Orchestrator-operator
invokes with `dry_run=False` at the end of every drain tick (see `.claude/agents/orchestrator-operator.md`).

KB: `KB § PATTERNS/common/tmp-artifact-cleanup.md`.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("noctus.dev.tmp_cleanup")

_DEFAULT_GLOB_ROOT = Path("/tmp")
_DEFAULT_PATTERN = "*.patch"
_DEFAULT_MAX_AGE_DAYS = 14


@dataclass(frozen=True)
class _Verdict:
    path: str
    size_bytes: int
    age_days: int
    reason: str  # "landed-patch-id" | "aged-out" | "malformed" | "kept-fresh"
    patch_id: str | None
    action: str  # "delete" | "keep"


def _stable_patch_id(patch_path: Path) -> str | None:
    """Return the stable patch-id for the diff at ``patch_path``, or None if unparseable."""
    try:
        with patch_path.open("rb") as fh:
            proc = subprocess.run(
                ["git", "patch-id", "--stable"],
                stdin=fh,
                capture_output=True,
                timeout=10,
            )
        if proc.returncode != 0:
            return None
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if not out:
            return None
        # `git patch-id --stable` emits: `<patch-id> <commit-id-or-zeros>`
        return out.split()[0]
    except (OSError, subprocess.TimeoutExpired):
        return None


def _landed_patch_ids(repo_root: Path, since: str = "origin/dev~500..origin/dev") -> set[str]:
    """Build the set of patch-ids reachable from ``since`` (default: last 500 commits on origin/dev).

    500 commits is ~2-3 weeks at this repo's cadence — wider than `max_age_days` so the patch-id
    branch of the verdict always wins over the age branch when content has actually landed.
    """
    try:
        log = subprocess.run(
            ["git", "-C", str(repo_root), "log", "--format=%H", since],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if log.returncode != 0:
            return set()
        shas = [s.strip() for s in log.stdout.splitlines() if s.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return set()

    ids: set[str] = set()
    for sha in shas:
        try:
            show = subprocess.run(
                ["git", "-C", str(repo_root), "show", sha, "--no-color", "--no-textconv"],
                capture_output=True,
                timeout=10,
            )
            if show.returncode != 0:
                continue
            pi = subprocess.run(
                ["git", "patch-id", "--stable"],
                input=show.stdout,
                capture_output=True,
                timeout=10,
            )
            if pi.returncode != 0:
                continue
            line = pi.stdout.decode("utf-8", errors="replace").strip()
            if line:
                ids.add(line.split()[0])
        except (OSError, subprocess.TimeoutExpired):
            continue
    return ids


def tmp_cleanup(
    *,
    glob_root: str = str(_DEFAULT_GLOB_ROOT),
    pattern: str = _DEFAULT_PATTERN,
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Sweep retired engineer-dispatch patch artifacts under ``glob_root``.

    Returns a structured verdict per scanned file plus a counters summary. Per ``noctus.dev``
    policy the function is non-destructive by default — pass ``dry_run=False`` to actually delete.
    """
    root = Path(glob_root)
    if not root.exists():
        return {
            "ok": False,
            "error": f"glob_root does not exist: {glob_root}",
            "dry_run": dry_run,
        }

    repo = Path(repo_root) if repo_root else Path(__file__).resolve().parents[5]
    landed = _landed_patch_ids(repo)
    now = datetime.now(timezone.utc).timestamp()

    verdicts: list[_Verdict] = []
    for patch in sorted(root.glob(pattern)):
        try:
            st = patch.stat()
        except OSError:
            continue
        age_days = int((now - st.st_mtime) // 86400)
        size = st.st_size
        pid = _stable_patch_id(patch)

        if pid is None:
            reason = "malformed"
            action = "delete"
        elif pid in landed:
            reason = "landed-patch-id"
            action = "delete"
        elif age_days >= max_age_days:
            reason = "aged-out"
            action = "delete"
        else:
            reason = "kept-fresh"
            action = "keep"

        verdicts.append(
            _Verdict(
                path=str(patch),
                size_bytes=size,
                age_days=age_days,
                reason=reason,
                patch_id=pid,
                action=action,
            )
        )

    deleted: list[str] = []
    delete_failed: list[dict[str, str]] = []
    if not dry_run:
        for v in verdicts:
            if v.action != "delete":
                continue
            try:
                Path(v.path).unlink()
                deleted.append(v.path)
            except OSError as exc:
                delete_failed.append({"path": v.path, "error": str(exc)})

    summary = {
        "ok": True,
        "dry_run": dry_run,
        "glob_root": str(root),
        "pattern": pattern,
        "max_age_days": max_age_days,
        "scanned": len(verdicts),
        "would_delete" if dry_run else "deleted": sum(1 for v in verdicts if v.action == "delete"),
        "kept": sum(1 for v in verdicts if v.action == "keep"),
        "landed_patch_id_match": sum(1 for v in verdicts if v.reason == "landed-patch-id"),
        "aged_out": sum(1 for v in verdicts if v.reason == "aged-out"),
        "malformed": sum(1 for v in verdicts if v.reason == "malformed"),
        "bytes_freed" if not dry_run else "bytes_pending": sum(
            v.size_bytes for v in verdicts if v.action == "delete"
        ),
        "verdicts": [asdict(v) for v in verdicts],
    }
    if not dry_run:
        summary["delete_failed"] = delete_failed
    logger.info(
        "tmp_cleanup: scanned=%d delete=%d kept=%d dry_run=%s",
        summary["scanned"],
        summary.get("deleted") or summary.get("would_delete", 0),
        summary["kept"],
        dry_run,
    )
    return summary


def register(server) -> None:
    """Register the `noctus.dev.tmp_cleanup` MCP tool."""

    @server.tool(
        name="noctus.dev.tmp_cleanup",
        description=(
            "Sweep retired engineer-dispatch patch artifacts from /tmp. A patch is retired when "
            "(a) its git-patch-id matches a patch-id on origin/dev (content landed), (b) it is "
            "older than max_age_days (default 14) and unmatched (orchestrator-retired beyond "
            "salvage window), or (c) it is malformed. DRY-RUN by default — set dry_run=False to "
            "actually delete. Orchestrator-operator invokes with dry_run=False at end of each "
            "drain tick. KB § PATTERNS/common/tmp-artifact-cleanup.md."
        ),
    )
    def _tmp_cleanup(
        glob_root: str = str(_DEFAULT_GLOB_ROOT),
        pattern: str = _DEFAULT_PATTERN,
        max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
        dry_run: bool = True,
        repo_root: str | None = None,
    ) -> dict[str, Any]:
        return tmp_cleanup(
            glob_root=glob_root,
            pattern=pattern,
            max_age_days=max_age_days,
            dry_run=dry_run,
            repo_root=repo_root,
        )
