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


# --- a skipped real-Postgres proof is UNMEASURED, never green (2026-11-15) -------------------------------------
# The event_store / transition_log proofs skip (no node/PGlite, no initdb) on a laptop or a scrubbed scoped run,
# and a bare "N skipped" reads as complete -- the merge queue then hung on exactly the tests that never ran.
# Say it LOUDLY, counted and named, with a stable marker (`REAL-PG-UNMEASURED`) the release steward's scoped
# check parses. Under NOC_REQUIRE_REAL_PG=1 (CI) these skips are failures already and this prints nothing.
_REAL_PG_SKIP_HINTS = ("postgres", "pglite")


def pytest_terminal_summary(terminalreporter):  # noqa: D401 - pytest hook
    skipped = [
        (rep.nodeid, rep.longrepr[2] if isinstance(rep.longrepr, tuple) else str(rep.longrepr))
        for rep in terminalreporter.stats.get("skipped", [])
    ]
    real_pg = [(n, why) for n, why in skipped if any(h in why.lower() for h in _REAL_PG_SKIP_HINTS)]
    if not real_pg:
        return
    terminalreporter.section("REAL-PG-UNMEASURED", sep="!", red=True, bold=True)
    terminalreporter.write_line(
        f"REAL-PG-UNMEASURED: {len(real_pg)} real-Postgres/PGlite test(s) SKIPPED, not run -- this green does not cover them "
        "(set NOCTUS_TEST_PG_BIN / install node + mcp/noctusai/node deps, run with NOC_REQUIRE_REAL_PG=1).", red=True)
    by_file: dict[str, int] = {}
    for node, _why in real_pg:
        by_file[node.split("::")[0]] = by_file.get(node.split("::")[0], 0) + 1
    for f, n in sorted(by_file.items()):
        terminalreporter.write_line(f"  {n:>3} skipped in {f}")
