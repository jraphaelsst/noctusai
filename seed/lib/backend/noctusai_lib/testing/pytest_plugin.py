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

logger = logging.getLogger(__name__)


def pytest_configure(config) -> None:  # noqa: D401 — pytest hook
    """Probe for `app.main` and import it to load the consent catalog.

    Runs once per pytest session, before any test or fixture. Silent
    no-op when `app.main` is not on the import path (seed-lib own tests,
    MCP tests, ad-hoc scripts).
    """
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
