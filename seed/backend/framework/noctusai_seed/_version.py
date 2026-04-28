"""Seed version resolution — primary + fallback + live-git.

Resolution order at import-time:

1. **Static (preferred)** — read `_version_static.__version__` if it's a real
   SHA (i.e., not the "bootstrap" placeholder). This is the install-time
   stamp written by `setup.py`; it represents the seed SHA the consumer
   **thinks** they have installed. Drift-detection uses this.

2. **Live-git fallback** — if `_version_static` holds "bootstrap" or is
   missing (fresh clone, first import before any install), compute
   `git rev-parse --short HEAD` at import. Tag the result `runtime:<sha>`
   so the keeper can tell "this came from live git, not from an install
   stamp." Still useful for sanity; loses the stale-install signal.

3. **Unknown** — no `_version_static`, no git on PATH. Return "unknown".
   Keeper treats this as a hard compliance failure (can't verify
   propagation at all).

This resolution runs ONCE per Python process (module import time).
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


__seed_version__ = _resolve()
