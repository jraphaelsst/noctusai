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
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)
