"""Library version resolution — mirrors `noctusai_seed._version`.

Both packages live in the same monorepo / same git HEAD, so the resolved
value is identical in a well-installed environment. Keeping the logic
duplicated avoids the lib depending on the framework's private helpers.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _read_static() -> str | None:
    try:
        from . import _version_static
        value = getattr(_version_static, "__version__", None)
        if isinstance(value, str) and value and value != "bootstrap":
            return value
    except ImportError:
        pass
    return None


def _read_git() -> str | None:
    try:
        here = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=here,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _resolve() -> str:
    static = _read_static()
    if static is not None:
        return static
    live = _read_git()
    if live is not None:
        return f"runtime:{live}"
    return "unknown"


__lib_version__ = _resolve()
