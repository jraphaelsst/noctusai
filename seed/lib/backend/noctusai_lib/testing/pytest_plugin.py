"""Pytest plugin — auto-loaded for every test session via the `pytest11`
entry point declared in `seed/lib/backend/pyproject.toml`.

**Why this exists.** Each product's `app/main.py` calls
`create_product_app(consent_features="app.services.ai_consent_features")`
which loads the consent catalog as part of FastAPI app construction. In
production, anything that imports the app gets the catalog. In tests,
unit tests that import a service directly (e.g.
`from app.services import ai_pipeline`) bypass `app.main`, so the
catalog stays empty and `is_granted` fails-closed even when the test
seeded `ai_consent` rows.

**What this plugin does.** At pytest session-start, probe for the
product's `app.main` module. If it resolves, import it — that triggers
`create_product_app(...)` which populates the catalog. If it does NOT
resolve (e.g. the seed-lib's own tests, MCP toolkit tests, anything that
isn't a product backend), the import is silently skipped — the plugin
becomes a no-op.

**Why entry-point auto-load instead of per-product `pytest_plugins =
[...]` in conftest.** The whole point is zero per-product boilerplate.
Auto-loaded plugins run wherever `noctusai-lib` is installed; the probe
fails fast in non-product contexts.

**Why it's safe.** A successful `app.main` import is idempotent (Python
caches the module). The cost is FastAPI app construction (~ms) which
happens anyway as soon as the first `client` fixture runs — this just
moves it earlier so unit tests get the catalog too.
"""
from __future__ import annotations

import importlib
import logging

import pytest

logger = logging.getLogger(__name__)


def declare_hermetic_seams() -> None:
    """The env seams every hermetic test session declares — idempotent.

    - NOCTUS_SETTINGS_NO_ENV_FILE=1: seed settings never read a tree-root
      .env (prod credentials) under pytest.
    - NOCTUS_RATE_LIMIT_MEMORY_ONLY=1: rate-limit counters are per-process,
      never a shared developer Redis.

    Both must hold BEFORE the first app.* import, because settings and the
    limiter are built at import time — and pytest imports the *initial*
    conftests (every directory on the command line) before any
    pytest_configure. Eight social-wiring module conftests import
    app.* at module level, so a seam set only in pytest_configure
    arrived too late for whichever shard collected them first (2026-10-10:
    the rate limiter came up Redis-backed and parallel runs reset each
    other's windows).
    """
    import os

    from noctusai_lib.api.rate_limit import MEMORY_ONLY_VAR
    from noctusai_lib.config.settings import NO_ENV_FILE_VAR

    os.environ[NO_ENV_FILE_VAR] = "1"
    os.environ[MEMORY_ONLY_VAR] = "1"


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args) -> None:  # noqa: D401 — pytest hook
    """Earliest hook a setuptools plugin gets: declare the hermetic seams
    before any conftest (and therefore any app.* module) is imported."""
    declare_hermetic_seams()


def pytest_collection_finish(session) -> None:  # noqa: D401 — pytest hook
    """Fail loud, before any test body runs, if a live Supabase env meets
    hermetic tests (see ``live_db_guard``). Runs after every conftest has
    applied its env, so ``own_test_env`` scrubs are honoured."""
    import pytest

    from noctusai_lib.testing.live_db_guard import assert_hermetic

    try:
        assert_hermetic(session.items)
    except RuntimeError as exc:
        raise pytest.UsageError(str(exc)) from exc


def pytest_configure(config) -> None:  # noqa: D401 — pytest hook
    """Probe for `app.main` and import it to load the consent catalog.

    Also declares the no-env-file seam (``NOCTUS_SETTINGS_NO_ENV_FILE=1``) so
    seed settings never read a tree-root ``.env`` under pytest.

    Runs once per pytest session, before any test or fixture. Silent
    no-op when `app.main` is not on the import path (seed-lib own tests,
    MCP tests, ad-hoc scripts).
    """
    # Idempotent re-declaration: a session started without the early hook
    # (e.g. -p plugin loading) still gets the seams before app.main.
    declare_hermetic_seams()
    try:
        importlib.import_module("app.main")
    except ModuleNotFoundError:
        # Not a product test session — nothing to bootstrap. This is the
        # expected path for seed-lib own tests + mcp tests.
        logger.debug("pytest_plugin: app.main not importable; skipping product bootstrap (expected for seed-lib / mcp tests)")
        return
    except Exception as exc:
        # `app.main` is importable but failed at construction time
        # (settings missing, router import error, etc.). Log a warning so
        # tests don't run with a half-initialized environment, but don't
        # block — the per-test failure mode will surface the real cause.
        logger.warning(
            "noctusai-product-bootstrap: app.main import failed (%s: %s). "
            "Consent catalog may be empty; tests that exercise the consent "
            "guard will fail-closed.",
            type(exc).__name__,
            exc,
        )
