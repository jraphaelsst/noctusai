"""`noctus.dev.record_applied_migrations` -- persist ``migrations-applied.json`` through an ISOLATED branch.

``migrate_product confirm=True`` runs the DDL in prod and must then mirror what it applied into
``products/<p>/backend/migrations-applied.json`` (the frozen-file source of truth for organ
migrations). Writing that file into whatever tree the tool reads from dirtied the PRIMARY checkout
(4 untracked files, 2026-10-14), which (a) violates self-branching (the primary stays clean) and
(b) later blocked ``task_branch integrate``'s primary fast-forward on the same paths.

Root fix: the record NEVER touches the caller's tree. This tool opens a ``task_branch`` worktree off
``origin/dev``, merges the rows in with ``record_applied``, commits on that branch and integrates it
(the integrate's own primary fast-forward then lands it). Semantics kept: the DDL already ran, so a
persist failure is REPORTED (``status='error'`` + ``error``), never raised -- the rows stay in the
result (``files``) so the call can be retried by hand with this tool.

KB § PATTERNS/backend/migrate-product-mcp-tool.md · KB § PATTERNS/common/branching.md
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .task_branch import task_branch as _task_branch

_COMMIT_TRAILER = (
    "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
)
_SAFE = re.compile(r"[^a-z0-9]+")


def _default_git(wt: str, *args: str) -> tuple[int, str, str]:
    p = subprocess.run(["git", "-C", wt, *args], capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _resolve_worktree(worktree: str, primary_root: str | None) -> str:
    if Path(worktree).is_absolute():
        return worktree
    from .task_branch import _resolve_primary_root

    return str(Path(_resolve_primary_root(primary_root)) / worktree)


def _cleanup_failed(tb: Callable[..., dict[str, Any]], slug: str, root_kw: dict[str, Any]) -> None:
    """Best-effort teardown of the branch/worktree a FAILED persist would otherwise leak."""
    try:
        tb(action="cleanup", slug=slug, confirm=True, **root_kw)
    except Exception:  # noqa: BLE001 -- teardown must never mask the original error
        pass


def record_applied_migrations(
    product: str,
    files: Mapping[str, str],
    *,
    task_branch_fn: Callable[..., dict[str, Any]] | None = None,
    git_fn: Callable[..., tuple[int, str, str]] | None = None,
    primary_root: str | None = None,
    slug_suffix: str | None = None,
) -> dict[str, Any]:
    """Returns ``{status, product, files, slug, path, commit, integrate, error}``.

    status: recorded | nothing_to_record | error. ``files`` is ``{filename: sha256}``.
    """
    result: dict[str, Any] = {"product": product, "files": dict(files), "error": None}
    if not files:
        return {**result, "status": "nothing_to_record"}
    tb = task_branch_fn or _task_branch
    git = git_fn or _default_git
    rel = f"products/{product}/backend/migrations-applied.json"
    slug = f"applied-record-{_SAFE.sub('-', product.lower()).strip('-')}-" \
           f"{slug_suffix or time.strftime('%Y%m%d-%H%M%S')}"
    result["slug"] = slug
    root_kw = {"primary_root": primary_root} if primary_root else {}
    started = False
    try:
        start = tb(action="start", slug=slug, confirm=True, wire_env=False, paths=[rel],
                   brief=f"record applied migrations for {product}", **root_kw)
        if start.get("status") != "started":
            return {**result, "status": "error", "error": f"task_branch start: {start.get('status')} "
                                                           f"{start.get('error') or start.get('message') or ''}"}
        started = True
        # task_branch returns the worktree RELATIVE to the primary root. Resolve against the
        # PRIMARY root, never the process cwd: the fresh-subprocess fallback runs with an
        # arbitrary cwd, which made record_applied see no file (2026-10-19 FileNotFoundError).
        wt = _resolve_worktree(start["worktree"], primary_root)
        from noctusai_lib.testing.migrations_applied import record_applied

        path = record_applied(Path(wt) / "products" / product / "backend", files)
        result["path"] = str(path)
        for args in (("add", "--", rel),
                     ("commit", "-q", "-m",
                      f"chore({product}): record applied migrations ({', '.join(sorted(files))})\n\n"
                      f"Written by noctus.dev.record_applied_migrations from an isolated branch "
                      f"(migrate_product never writes the primary).\n\n{_COMMIT_TRAILER}")):
            rc, _o, err = git(wt, *args)
            if rc != 0:
                _cleanup_failed(tb, slug, root_kw)
                return {**result, "status": "error", "error": f"git {args[0]} failed: {err[:300]}"}
        rc, sha, _e = git(wt, "rev-parse", "--short", "HEAD")
        result["commit"] = sha if rc == 0 else None
        integ = tb(action="integrate", slug=slug, confirm=True, **root_kw)
        result["integrate"] = {k: integ.get(k) for k in ("status", "message", "error")}
        if integ.get("status") not in ("integrated", "up_to_date"):
            return {**result, "status": "error",
                    "error": f"task_branch integrate: {integ.get('status')} {integ.get('error') or ''}"
                             f" -- branch feat/{slug} kept for manual integrate"}
        return {**result, "status": "recorded"}
    except Exception as exc:  # noqa: BLE001 -- DDL already ran: report, never raise
        if started:
            _cleanup_failed(tb, slug, root_kw)
        suffix = f" -- cleanup of feat/{slug} attempted" if started else ""
        return {**result, "status": "error", "error": f"{type(exc).__name__}: {exc}{suffix}"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.record_applied_migrations",
        description=(
            "Persist {filename: sha256} rows into products/<p>/backend/migrations-applied.json via an "
            "ISOLATED task_branch (start -> write -> commit -> integrate); never writes the caller's / "
            "primary tree. migrate_product confirm=True calls this itself; call it directly to retry "
            "after a reported record failure (rows are in migrate_product's applied_record.files). "
            "status: recorded|nothing_to_record|error. "
            "KB § PATTERNS/backend/migrate-product-mcp-tool.md."
        ),
    )
    def _record_applied_migrations(product: str, files: dict[str, str]) -> dict:
        return record_applied_migrations(product, files)
