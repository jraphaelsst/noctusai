"""Bounded shell tool — `shell(cmd, allowlist)`.

Per design-reference.md §3 + Notes: every shell-using role gets a
**per-agent allowlist**. There is NO unrestricted shell. The Backend
allowlist is ``["pytest", "ruff", "mypy"]``; DevOps gets ``["docker",
"docker compose", "terraform plan"]``; etc.

The allowlist is matched against the FIRST whitespace-separated token of
the command (or the first two tokens for two-word allowlist entries like
``"docker compose"``).
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Callable, Sequence


def _command_is_allowed(cmd: str, allowlist: Sequence[str]) -> bool:
    """Match ``cmd`` against ``allowlist`` (longest-prefix wins).

    Handles multi-word entries: e.g. ``"docker compose"`` matches
    ``"docker compose up"`` but not just ``"docker run"``.
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError as exc:
        raise ValueError(f"could not tokenize command {cmd!r}: {exc}") from exc
    if not tokens:
        return False
    # Sort allowlist by descending word-count so multi-word entries match first.
    for entry in sorted(allowlist, key=lambda e: -len(e.split())):
        words = entry.split()
        if tokens[: len(words)] == words:
            return True
    return False


def shell(
    cmd: str,
    allowlist: Sequence[str] = (),
    *,
    cwd: str | None = None,
    timeout: int = 120,
) -> dict:
    """Run ``cmd`` if (and only if) its first token(s) match ``allowlist``.

    Args:
        cmd: The command string. Tokenized via :func:`shlex.split`.
        allowlist: Tuple/list of allowed command prefixes. Multi-word
            entries (``"docker compose"``) are matched as a unit.
            Empty allowlist refuses everything (caller must opt-in).
        cwd: Optional working directory.
        timeout: Hard kill timeout in seconds.

    Returns:
        ``{"returncode": int, "stdout": str, "stderr": str}``.

    Raises:
        PermissionError: command not in the allowlist.
    """
    if not _command_is_allowed(cmd, allowlist):
        raise PermissionError(
            f"command rejected — {cmd!r} not in allowlist {list(allowlist)!r}. "
            "Bounded shell: every role uses a per-agent allowlist; "
            "expand the allowlist via the role's tool-build kwargs if needed."
        )
    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def build_shell_tool(*, allowlist: Sequence[str] = (), **kwargs) -> Callable:
    """Return a shell tool bound to a specific allowlist.

    Tool factories typically pass ``allowlist=["pytest", "ruff", "mypy"]``
    (Backend) or ``["docker", "docker compose", "terraform plan"]`` (DevOps).
    """
    bound_allowlist = tuple(allowlist)

    def _shell(cmd: str, cwd: str | None = None, timeout: int = 120) -> dict:
        """Run ``cmd`` against the bound allowlist."""
        return shell(cmd, bound_allowlist, cwd=cwd, timeout=timeout)

    _shell.__doc__ = shell.__doc__
    return _shell


__all__ = ["shell", "build_shell_tool"]
