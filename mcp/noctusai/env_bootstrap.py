"""env_bootstrap — the ONE dotenv-loading path shared by the MCP server
(`server.py`) and the CLI/hooks (`cli.py`).

🔴 WHY THIS EXISTS (root-caused 2026-08-31 for the server; 2026-09-14 for the
CLI) — ``.mcp.json`` launches the MCP server with no ``env`` block and no
dotenv loading, so ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY`` /
``SUPABASE_ACCESS_TOKEN`` were absent from the server's ``os.environ`` even
though the repo-root ``.env`` has them (fixed 2026-08-31 by loading the
repo-root ``.env`` at server import time — see the git-blame history on this
module for the original ``server._load_repo_root_dotenv``). That fix covered
ONLY the server's own process: ``scripts/hooks/pre-push`` invokes
``cli.py`` directly, never imports ``server.py``, and ``cli.py`` never loaded
``.env`` at all — so ``check_migration_applied_ledger_drift`` kept SKIPping
("no supabase_access_token resolved") from the CLI/hook path even though the
SAME ``.env``, on the SAME disk, has ``SUPABASE_ACCESS_TOKEN`` set. Both
defects have the identical shape (a real credential sits in a gitignored
``.env`` and the consuming process's ``os.environ`` never sees it) — this
module is the single shared fix so no THIRD entry point can reintroduce the
gap under a different name.

Worktree wrinkle. A worktree never carries its own ``.env`` copy (gitignored,
not part of a worktree checkout), yet the CLI legitimately runs with
``settings.REPO_ROOT`` pointed AT a worktree — ``scripts/hooks/pre-push``
resolves ``cli.py`` from the pushing worktree deliberately, so the code under
review is what gets checked (KB § architect/seed-workspace.md worktree-
boundary detection). :func:`load_repo_env` therefore tries ``.env`` at
``repo_root`` first, then — via ``git rev-parse --git-common-dir`` — at the
PRIMARY checkout the worktree shares git state with, since secrets live ONLY
there. Same resolver shape as
``tools.noctus.dev.cache_backend._git_common_dir`` (kept independent here:
this module must be importable at CLI/server bootstrap time, before
``tools.*`` exists on ``sys.path``).
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_DOTENV_FILENAME = ".env"


@dataclass(frozen=True)
class EnvBootstrapResult:
    """Diagnostic result of a :func:`load_repo_env` call.

    Booleans + paths only — NEVER a secret value. Callers (e.g. the
    ``check_migration_applied_ledger_drift`` SKIP message) use this to name
    which sources were tried instead of a generic "not resolved".
    """

    attempted: tuple[Path, ...]
    loaded_from: tuple[Path, ...]
    dotenv_installed: bool
    supabase_url_present: bool
    supabase_service_role_key_present: bool
    supabase_access_token_present: bool


def _git_common_dir(repo_root: Path) -> Path:
    """Return the directory git uses for shared state across worktrees.

    For the primary tree: ``<repo>/.git``. For a linked worktree: still
    ``<primary>/.git`` (worktrees carry a stub ``.git`` file pointing back).
    Falls back to ``<repo_root>/.git`` when git is unavailable or
    ``repo_root`` isn't inside a git work tree at all (e.g. a bare tmp dir
    in a test).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        path_str = out.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return repo_root / ".git"
    common = Path(path_str)
    if not common.is_absolute():
        common = (repo_root / common).resolve()
    return common


def _candidate_roots(repo_root: Path) -> tuple[Path, ...]:
    """``.env`` search order: ``repo_root`` itself, then — only when
    ``repo_root`` resolves to a linked worktree — the PRIMARY checkout.
    Deduplicated; order preserved.
    """
    repo_root = repo_root.resolve()
    primary_root = _git_common_dir(repo_root).parent.resolve()
    candidates = [repo_root]
    if primary_root != repo_root:
        candidates.append(primary_root)
    return tuple(candidates)


def load_repo_env(
    repo_root: Path,
    *,
    logger: logging.Logger | None = None,
) -> EnvBootstrapResult:
    """Load the repo's ``.env`` into this process's environment.

    Never raises. A missing ``.env`` at every candidate root is not an error
    (fresh clone / CI must still boot) — logged once at INFO.
    ``override=False`` throughout: an already-set process env var always
    wins over any ``.env`` value, from either candidate root — this never
    clobbers a value the caller (shell, CI, launcher) deliberately set.

    ``logger`` defaults to this module's own logger; pass the caller's
    logger (e.g. ``logging.getLogger("server")``) to keep log provenance
    attributed to the calling entry point.
    """
    log = logger or logging.getLogger(__name__)
    try:
        from dotenv import load_dotenv
        dotenv_installed = True
    except ImportError as exc:  # pragma: no cover — dependency is pinned
        log.warning(
            "env_bootstrap: python-dotenv not installed (%s); relying on "
            "already-set env. Run `pip install -r "
            "mcp/noctusai/requirements.txt`.",
            exc,
        )
        dotenv_installed = False
        load_dotenv = None  # type: ignore[assignment]

    attempted = _candidate_roots(repo_root)
    loaded_from: list[Path] = []

    if dotenv_installed:
        for candidate in attempted:
            env_path = candidate / _DOTENV_FILENAME
            if not env_path.exists():
                continue
            before = len(os.environ)
            load_dotenv(env_path, override=False)
            after = len(os.environ)
            loaded_from.append(env_path)
            log.info(
                "env_bootstrap: loaded %s (%s new key(s), override=False so "
                "an already-set env var always wins).",
                env_path, after - before,
            )

    if not loaded_from:
        tried = ", ".join(str(c / _DOTENV_FILENAME) for c in attempted)
        log.info(
            "env_bootstrap: no repo-root .env found (tried: %s); relying on "
            "already-set process env (expected on a fresh clone / CI).",
            tried,
        )

    return EnvBootstrapResult(
        attempted=attempted,
        loaded_from=tuple(loaded_from),
        dotenv_installed=dotenv_installed,
        supabase_url_present=bool(os.environ.get("SUPABASE_URL")),
        supabase_service_role_key_present=bool(
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        ),
        supabase_access_token_present=bool(os.environ.get("SUPABASE_ACCESS_TOKEN")),
    )


__all__ = ["EnvBootstrapResult", "load_repo_env"]
