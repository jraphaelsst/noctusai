"""Shared fixtures for seed library unit tests.

The library layer (`noctusai_lib.*`) is pure Python — no FastAPI, no DB
wrapper — so tests target functions directly. This conftest only makes
the sibling lib importable regardless of cwd.

When the host venv carries an editable-install of `noctusai_lib` pointing
at a sibling worktree (a real-world setup with multiple parallel
worktrees sharing one venv), that finder shadows the local `sys.path`
entry and the tests run against the wrong source tree. This conftest
detects the shadow and pops the offending finder so the local `_LIB`
entry wins. Side-effect-scoped to the test session.
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


def _purge_shadowing_editable_finders() -> None:
    """If a parent venv installed `noctusai_lib` editable from another
    worktree, its meta-path finder will shadow our local `_LIB`. Remove
    only finders whose `MAPPING` points outside this worktree's lib root.
    """
    local_root = str(_LIB.resolve())
    keep: list = []
    for finder in sys.meta_path:
        mapping = getattr(finder, "MAPPING", None)
        if isinstance(mapping, dict) and "noctusai_lib" in mapping:
            target = str(Path(mapping["noctusai_lib"]).resolve())
            if not target.startswith(local_root):
                # Editable finder pointing at a different worktree — drop it.
                continue
        keep.append(finder)
    sys.meta_path[:] = keep
    # Also drop any already-imported `noctusai_lib*` modules so they
    # re-resolve through our local source tree.
    for name in list(sys.modules):
        if name == "noctusai_lib" or name.startswith("noctusai_lib."):
            del sys.modules[name]


_purge_shadowing_editable_finders()
