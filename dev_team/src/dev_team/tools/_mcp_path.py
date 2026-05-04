"""Internal helper — make `mcp/noctusai/` importable for wrap-target tools.

The wrap-target modules under `mcp/noctusai/tools/noctus/dev/` import from
top-level `settings` / `workspace` modules that live at `mcp/noctusai/`.
For dev_team to wrap them, we need `mcp/noctusai/` on `sys.path`.

This helper is idempotent — it only adds the path once.
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    """Locate the repo root by walking up until we find `mcp/noctusai/`."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "mcp" / "noctusai"
        if candidate.is_dir():
            return parent
    raise RuntimeError(
        "could not locate repo root (no `mcp/noctusai/` ancestor found from "
        f"{here}); dev_team must run from inside the noctusai repo."
    )


def ensure_mcp_path() -> Path:
    """Ensure `mcp/noctusai/` is on sys.path; return that path."""
    root = repo_root()
    mcp_dir = root / "mcp" / "noctusai"
    if str(mcp_dir) not in sys.path:
        sys.path.insert(0, str(mcp_dir))
    return mcp_dir


__all__ = ["ensure_mcp_path", "repo_root"]
