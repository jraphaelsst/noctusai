"""Test bootstrap: ensure `app` is importable regardless of invocation dir.

Mirrors the parallel-worktree venv shadowing fix every OTHER product's
``tests/conftest.py`` already carries (see ``seed/lib/backend/tests/
conftest.py`` / ``products/daily-life/backend/tests/conftest.py`` etc.) —
when the host venv carries an editable-install of ``noctusai_lib`` pointing
at a sibling worktree (or the primary checkout), that finder shadows THIS
worktree's local source tree, so a change made only here is silently
untested. Detect + drop the shadow so the local ``seed/lib/backend`` wins.

Found missing here while verifying ``seed-trusted-org-resolution``
(2026-07-14): editing ``noctusai_lib.api.auth`` in this worktree and running
KE's suite raised a stale-signature ``TypeError`` because the OLD
primary-checkout copy of the module was still shadowing the local one — the
bootstrap below must run, and must import ``noctusai_lib`` for the FIRST
time, only AFTER the shadow is purged.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
BACKEND = Path(__file__).resolve().parents[1]
for _p in (_LIB, _FRAMEWORK, BACKEND):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)

# Clear the slowapi in-memory limiter between tests — the Redis-down fallback
# leaks bucket state across tests under pytest-randomly (→ spurious 429s).
# Deliberately imported AFTER the shadow purge above (see module docstring).
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401,E402
