"""
Pytest configuration and shared fixtures for Store backend tests.

The seed product uses the framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.
"""
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots — this file previously added only `_LIB`,
# which left `noctusai_seed` unresolvable in a worktree once
# `purge_shadowing_editable_finders` drops the venv's editable finder
# pointing at a sibling checkout (every OTHER product's conftest.py
# already does this; found + fixed while verifying
# `seed-trusted-org-resolution`, 2026-07-14 — mirrors ERP-P7's reference
# fix, see `products/daily-life/backend/tests/conftest.py`).
for _p in (_LIB, _FRAMEWORK):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noctusai_lib.testing import (  # noqa: F401 — re-exported for test imports
    MockSupabaseResponse,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_consent_module_to_mock,
)
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    with patch("app.database._db.get_client", return_value=mock_sb), \
         patch("app.database._db.get_core_client", return_value=mock_sb), \
         patch("app.database._db.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Idempotent — safe even if no consent features registered.
        # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)


# ── Store DI doubles ────────────────────────────────────────────────────────
import types as _types  # noqa: E402

from noctusai_lib.domain.payments import FakeEventInbox  # noqa: E402
from noctusai_lib.integrations.email import FakeEmailSender  # noqa: E402
from noctusai_lib.integrations.payments.checkout import FakeHostedCheckout  # noqa: E402
from noctusai_lib.integrations.storage.fake import FakeStorageBackend  # noqa: E402
from noctusai_lib.testing import bind_user_metadata  # noqa: E402,F401

from tests.support.fakes import FakePedidoStore, FakeSettingsStore  # noqa: E402

ADMIN_EMAIL = "owner@store.test"
WEBHOOK_TOKEN = "asaas-token-store-test"


@pytest.fixture
def store(client):
    """Install the Fakes through FastAPI's `dependency_overrides` (the DI seam —
    nothing in the product is patched) and hand them back for assertions.

    The auth dependency and `require_store_admin` themselves are NOT replaced:
    only the data/IO collaborators and the two config providers (the admin
    allow-list and the webhook token) are.
    """
    from app import store_deps
    from app.dependencies import get_store_admin_emails
    from app.main import app

    ns = _types.SimpleNamespace(
        settings=FakeSettingsStore(),
        pedidos=FakePedidoStore(),
        storage=FakeStorageBackend(),
        email=FakeEmailSender(),
        checkout=FakeHostedCheckout(),
        inbox=FakeEventInbox(),
        admin_email=ADMIN_EMAIL,
        webhook_token=WEBHOOK_TOKEN,
    )
    overrides = {
        store_deps.get_settings_store: lambda: ns.settings,
        store_deps.get_pedido_store: lambda: ns.pedidos,
        store_deps.get_storage: lambda: ns.storage,
        store_deps.get_checkout_factory: lambda: (lambda: ns.checkout),
        store_deps.get_event_inbox: lambda: ns.inbox,
        store_deps.get_email_sender: lambda: ns.email,
        store_deps.get_asaas_webhook_token: lambda: ns.webhook_token,
        get_store_admin_emails: lambda: frozenset({ADMIN_EMAIL}),
    }
    app.dependency_overrides.update(overrides)
    ns.client = client
    try:
        yield ns
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


def as_admin(client) -> None:
    bind_user_metadata(client, email=ADMIN_EMAIL, org_id="test-org-123")


def as_other_user(client) -> None:
    bind_user_metadata(client, email="someone.else@store.test", org_id="test-org-123")


ORG_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def keyed(client, monkeypatch):
    """Like `store`, but the Asaas key / webhook token are resolved FOR REAL
    through `key_provider` (the seed `resolve_api_key` seam) over a seed
    `FakeCredentialStore` — only the data/IO collaborators are swapped (DI), and
    the platform tier is stubbed empty so the ambient environment can't leak in.
    """
    from noctusai_lib.security.token_store.fake import FakeCredentialStore

    from app import store_deps
    from app.api_keys import key_provider
    from app.config import settings
    from app.dependencies import get_store_admin_emails
    from app.main import app

    monkeypatch.setattr(settings, "store_org_id", ORG_ID)  # self-patch-ok: configuration value, not a guard
    creds = FakeCredentialStore()
    key_provider.use(store=creds, resolver=lambda name, org: None)
    ns = _types.SimpleNamespace(
        settings=FakeSettingsStore(),
        pedidos=FakePedidoStore(),
        storage=FakeStorageBackend(),
        email=FakeEmailSender(),
        inbox=FakeEventInbox(),
        creds=creds,
        client=client,
    )
    overrides = {
        store_deps.get_settings_store: lambda: ns.settings,
        store_deps.get_pedido_store: lambda: ns.pedidos,
        store_deps.get_storage: lambda: ns.storage,
        store_deps.get_event_inbox: lambda: ns.inbox,
        store_deps.get_email_sender: lambda: ns.email,
        get_store_admin_emails: lambda: frozenset({ADMIN_EMAIL}),
    }
    app.dependency_overrides.update(overrides)
    try:
        yield ns
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)
        key_provider.reset()
