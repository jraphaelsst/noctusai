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

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _virtual_rate_limit_clock():
    """Run every test on a VIRTUAL clock for the outbound rate limiter, so
    pacing/backoff LOGIC executes for real (tokens refill, retries count,
    acquire is genuinely called) but a test never wall-clock-waits on the
    3-req/s Meta pace. Without this the real-adapter Graph tests take ~50s
    instead of ~2s. Reset the bucket registry so buckets rebuild on the
    virtual clock, and restore the real clock on teardown."""
    from noctusai_lib.integrations import rate_limit

    rate_limit.set_default_clock(rate_limit.VirtualClock())
    rate_limit._reset_all_buckets()
    try:
        yield
    finally:
        rate_limit.reset_default_clock()
        rate_limit._reset_all_buckets()
