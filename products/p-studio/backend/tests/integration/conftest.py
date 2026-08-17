"""Fixtures for the framework-standard E2E suites — `tests/integration/` only.

The rest of the P Studio suite (`tests/routers`, `tests/services`, ...)
exercises P Studio's OWN single-tenant auth (`app.dependencies.get_current_user`
+ `app.database.get_user_client`) against the in-memory `FakeDB` defined in
`tests/conftest.py` — that fixture stays exactly as it is; this file must not
touch it.

But `test_e2e_flows.py` subclasses `noctusai_lib.testing.framework_test_suites`
suites, which exercise the FRAMEWORK's OWN standard routers (health /
notificacoes / team / status_paginas), mounted by `create_product_app()` via
its own internal `db = create_database_module(settings, schema)` +
`deps = create_dependencies(db)` — entirely separate from P Studio's
`app/database.py` / `app/dependencies.py` (P Studio never routes its own
domain code through `noctusai_seed.database.DatabaseModule`; it predates
absorption and ships a hand-rolled client layer instead). Patching
`app.database._db.*` (what every OTHER absorbed product's conftest does,
e.g. `products/igig/backend/tests/conftest.py`) would be a no-op here — there
is no such singleton to patch.

So this fixture patches `noctusai_seed.database.DatabaseModule` at the CLASS
level instead: `create_product_app()` builds its `db`/`deps` at import time
(inside `app/main.py`), but a class-level patch still intercepts every
instance's bound-method calls made AFTER the patch is applied, regardless of
when the instance itself was constructed — the same mechanism every other
absorbed product's conftest relies on.

A nested `client` fixture here SHADOWS the parent `tests/conftest.py`'s
`client` fixture for every test collected under this directory only — the
rest of the suite (330 passed / 1 skipped baseline) is untouched.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    AuthClient,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    with patch(
        "noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb
    ), patch(
        "noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb
    ), patch(
        "noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb
    ):
        from app.main import app

        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb — idempotent, safe even though P Studio registers no
        # consent-gated AI features. See KB § PATTERNS/testing.md § Consent-
        # guard product conftest pattern.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
