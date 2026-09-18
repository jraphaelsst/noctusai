"""Shared node-toolchain-readiness predicate.

Every node-toolchain-dependent gate (`npx vite build` in a product frontend,
the lying-loading-state Mode-B ts-morph AST scan, ...) hits the SAME
false-red shape in a fresh `git worktree add` tree: `node_modules/` is
gitignored, so it is simply ABSENT there, and the vendor tool (vite / node)
then fails with a package-resolution error (`Cannot find module 'X'` /
`Cannot find package 'X'` / `sh: vite: command not found`) that reads
exactly like a REAL break. Four independent incidents hit this in one
session (2026-09-17) — two frontend engineers reading `tsc --noEmit` noise
as drift, `predeploy_check` reading it as a blocked deploy, and the MCP
toolkit's own test suite reading it as a detector regression. See
`KB § PATTERNS/common/self-branching-mode.md § 5a`.

Use `node_deps_ready()` BEFORE shelling into any node-toolchain command so
the caller can say "environment not provisioned" instead of surfacing the
raw vendor error. `noctus.dev.task_branch(action='start')` now provisions
this by default (`wire_env` defaults to `True`) — this predicate is the
DIAGNOSTIC half for the worktrees that were forked some other way (a bare
`git worktree add`, or an intentional `wire_env=False`).
"""
from __future__ import annotations

from pathlib import Path


def node_deps_ready(pkg_dir: Path | str, *, require: str | None = None) -> bool:
    """True iff `<pkg_dir>/node_modules` is provisioned — a real directory OR
    a symlink (a `wire_env`-wired worktree overlays a product's `node_modules`
    as a REAL dir full of per-entry symlinks; a seed frontend's is a plain
    whole-dir symlink to the primary — both must read as "ready").

    `require=<pkg>` narrows the check to one specific package (e.g.
    `'ts-morph'`) when the caller only depends on ONE entry of the vendor
    tree, not all of it.

    An existing-but-EMPTY `node_modules` (e.g. only a stray `.package-lock.
    json`, no real packages) is NOT "ready" either — `npm install` remains
    the correct fix rather than something this predicate should paper over.
    """
    nm = Path(pkg_dir) / "node_modules"
    if not nm.exists():  # covers "absent" AND "dangling symlink"
        return False
    if require:
        return (nm / require).exists()
    try:
        return any(nm.iterdir())
    except OSError:
        return False
