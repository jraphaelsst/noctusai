"""Tests for ``agents_bridge_router`` — the ``agents`` control plane's
One Chat bridge (SW1, ``project-history/roadmaps/julia-agents-academia-
2026-09.md``, contract §E.6).

Two DI seams drive these tests, mirroring
``test_whatsapp_connections_router.py``'s pattern (no patching of our
own symbols):

  - ``get_connection_store`` → a REAL SQLite-backed store (genuine CRUD
    persistence — same schema as that file's ``connections_client``
    fixture; duplicated here rather than shared, N=2 under the
    recurrence rule, flagged as a ``scoped-improvement:`` below).
  - ``app.dependencies.get_auth_context`` → overridden PER TEST to a
    fixed ``AuthContext`` for the 403/200 matrix (an honest FastAPI
    ``dependency_overrides`` seam — the SAME object ``require_scopes``
    depends on throughout the whole chain, per
    ``KB § PATTERNS/di-test-seam.md`` Class-A). The two 401 cases run
    through the REAL (un-overridden) dep chain instead, since a stub
    context can never exercise "no credential resolves".

Auth strictness: every 401 assertion is strict ``== 401`` (never
``in (401, 404, 422)``) per
``KB § PATTERNS/compliance/auth-boundary-false-green.md``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from noctusai_lib.api.auth.session import AuthContext

from app.services.whatsapp_connection_store import WhatsAppConnectionStore
from app.sqlite_client import SQLiteClient

_SCHEMA = """
CREATE TABLE whatsapp_connections (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT NOT NULL,
    session_name TEXT NOT NULL DEFAULT 'default',
    encrypted_api_key TEXT NOT NULL,
    webhook_url TEXT,
    webhook_token TEXT,
    auto_reply_enabled INTEGER NOT NULL DEFAULT 0,
    authorized_numbers TEXT NOT NULL DEFAULT '[]',
    bound_chats TEXT NOT NULL DEFAULT '[]',
    marca_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (org_id, user_id, label),
    UNIQUE (webhook_token)
);
"""

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_OTHER_ORG = UUID("00000000-0000-4000-8000-0000000000bb")
_USER = UUID("00000000-0000-4000-8000-0000000000cc")
_READ_SCOPE = "social-wiring:one-chat:read"
_TOGGLE_SCOPE = "social-wiring:one-chat:toggle"


@pytest.fixture
def store(tmp_path: Path) -> WhatsAppConnectionStore:
    db_path = tmp_path / "bridge_router.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
    return WhatsAppConnectionStore(
        SQLiteClient(db_path), fernet=Fernet(Fernet.generate_key())
    )


@pytest.fixture
def bridge_client(client, store):
    """``client``'s app + the REAL SQLite-backed ``store`` wired through
    ``get_connection_store``'s DI seam. Yields ``(client, store)``;
    teardown restores any prior override."""
    from app.main import app
    from app.routers.whatsapp_connections_router import get_connection_store

    _prev = app.dependency_overrides.get(get_connection_store)
    app.dependency_overrides[get_connection_store] = lambda: store

    yield client, store

    if _prev is None:
        app.dependency_overrides.pop(get_connection_store, None)
    else:
        app.dependency_overrides[get_connection_store] = _prev


@pytest.fixture
def override_ctx():
    """Install ``app.dependency_overrides[get_auth_context]`` to a fixed
    ``AuthContext`` — the honest DI-seam replacement for hand-minting a
    resolvable ``pk_*`` bearer (the product-local ``ApiTokenResolver``
    singleton is process-global and not test-isolated; see this file's
    module docstring)."""
    from app.main import app
    from app.dependencies import get_auth_context

    _prev = app.dependency_overrides.get(get_auth_context)

    def _apply(ctx: AuthContext):
        app.dependency_overrides[get_auth_context] = lambda: ctx
        return ctx

    yield _apply

    if _prev is None:
        app.dependency_overrides.pop(get_auth_context, None)
    else:
        app.dependency_overrides[get_auth_context] = _prev


def _product_ctx(
    *, scopes: list[str], issuer: str | None = "agents", org_id: UUID = _ORG
) -> AuthContext:
    return AuthContext(
        org_id=org_id,
        caller_kind="product",
        user_id=None,
        scopes=scopes,
        raw_token="test-product-token",
        api_token_id=uuid4(),
        issuer=issuer,
    )


def _user_ctx(*, org_id: UUID = _ORG) -> AuthContext:
    return AuthContext(
        org_id=org_id,
        caller_kind="user",
        user_id=_USER,
        scopes=[],
        raw_token="test-session-id",
        api_token_id=None,
    )


def _error_code(resp) -> str:
    """Return the route's machine ``code`` from the contract §0 error body.

    ``noctusai_lib.primitives.exceptions.http_exception_handler`` passes an
    ``HTTPException(detail={"detail": ..., "code": ...})`` through VERBATIM,
    so the client receives the flat seed error shape
    ``{"detail": "<msg>", "code": "<machine_code>"}``. Plain string details
    still use the legacy ``{"error": {...}}`` envelope, but every bridge
    error is raised in the seed shape. The assertion pins the shape itself:
    a regression back to the legacy wrapper fails here instead of being
    silently re-parsed.
    """
    body = resp.json()
    assert set(body) == {"detail", "code"}, body
    return body["code"]


def _seed_connection(
    store: WhatsAppConnectionStore,
    *,
    org_id: UUID = _ORG,
    label: str = "linha-1",
    auto_reply_enabled: bool = False,
    webhook_token: str = "wt-1",
) -> UUID:
    record = store.create_connection(
        org_id=org_id,
        user_id=_USER,
        label=label,
        base_url="https://waha.example.com",
        api_key="waha-secret",
        webhook_token=webhook_token,
    )
    if auto_reply_enabled:
        store.update_auto_reply(
            connection_id=record.id, org_id=org_id, enabled=True
        )
    return record.id


class TestAuthMatrix:
    """The full 401/403(each code)/404 matrix — read route as the
    representative; the toggle route's own dependency chain is
    identical (both compose ``require_scopes(..., restrict=
    "product_only")`` + the ``issuer`` check), exercised separately by
    ``TestToggle``."""

    def test_missing_credential_is_exactly_401(self, bridge_client):
        client, store = bridge_client
        connection_id = _seed_connection(store)
        resp = client.raw().get(f"/api/agents-bridge/one-chat/{connection_id}")
        assert resp.status_code == 401, resp.text

    def test_invalid_token_is_exactly_401(self, bridge_client):
        client, store = bridge_client
        connection_id = _seed_connection(store)
        resp = client.raw().get(
            f"/api/agents-bridge/one-chat/{connection_id}",
            headers={"Authorization": "Bearer pk_" + "0" * 64},
        )
        assert resp.status_code == 401, resp.text

    def test_user_caller_is_403_product_required(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(store)
        override_ctx(_user_ctx())

        resp = client.raw().get(f"/api/agents-bridge/one-chat/{connection_id}")

        assert resp.status_code == 403, resp.text
        assert _error_code(resp) == "product_required"

    def test_product_caller_missing_scope_is_403_scope_missing(
        self, bridge_client, override_ctx
    ):
        client, store = bridge_client
        connection_id = _seed_connection(store)
        override_ctx(_product_ctx(scopes=[]))

        resp = client.raw().get(f"/api/agents-bridge/one-chat/{connection_id}")

        assert resp.status_code == 403, resp.text
        assert _error_code(resp) == "scope_missing"

    def test_wrong_issuer_is_403_issuer_not_allowed(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(store)
        override_ctx(_product_ctx(scopes=[_READ_SCOPE], issuer="some-other-product"))

        resp = client.raw().get(f"/api/agents-bridge/one-chat/{connection_id}")

        assert resp.status_code == 403, resp.text
        assert _error_code(resp) == "issuer_not_allowed"

    def test_unknown_connection_is_404(self, bridge_client, override_ctx):
        client, _store = bridge_client
        override_ctx(_product_ctx(scopes=[_READ_SCOPE]))

        resp = client.raw().get(f"/api/agents-bridge/one-chat/{uuid4()}")

        assert resp.status_code == 404, resp.text

    def test_other_org_connection_is_404(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(store, org_id=_OTHER_ORG)
        # Caller's own org is _ORG; the connection belongs to _OTHER_ORG.
        override_ctx(_product_ctx(scopes=[_READ_SCOPE], org_id=_ORG))

        resp = client.raw().get(f"/api/agents-bridge/one-chat/{connection_id}")

        assert resp.status_code == 404, resp.text


class TestRead:
    def test_returns_the_stored_state(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(
            store, label="linha-julia", auto_reply_enabled=True
        )
        override_ctx(_product_ctx(scopes=[_READ_SCOPE]))

        resp = client.raw().get(f"/api/agents-bridge/one-chat/{connection_id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["connection_id"] == str(connection_id)
        assert body["label"] == "linha-julia"
        assert body["auto_reply_enabled"] is True


class TestToggle:
    def test_flips_the_state(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(store, auto_reply_enabled=False)
        override_ctx(_product_ctx(scopes=[_TOGGLE_SCOPE]))

        resp = client.raw().put(
            f"/api/agents-bridge/one-chat/{connection_id}/auto-reply",
            json={"enabled": True},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["connection_id"] == str(connection_id)
        assert body["auto_reply_enabled"] is True

        record = store.get_connection(connection_id=connection_id, org_id=_ORG)
        assert record.auto_reply_enabled is True

    def test_is_idempotent(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(store, auto_reply_enabled=True)
        override_ctx(_product_ctx(scopes=[_TOGGLE_SCOPE]))

        first = client.raw().put(
            f"/api/agents-bridge/one-chat/{connection_id}/auto-reply",
            json={"enabled": True},
        )
        second = client.raw().put(
            f"/api/agents-bridge/one-chat/{connection_id}/auto-reply",
            json={"enabled": True},
        )

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["auto_reply_enabled"] is True
        assert second.json()["auto_reply_enabled"] is True

    def test_missing_scope_is_403_scope_missing(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(store)
        override_ctx(_product_ctx(scopes=[_READ_SCOPE]))  # read, not toggle

        resp = client.raw().put(
            f"/api/agents-bridge/one-chat/{connection_id}/auto-reply",
            json={"enabled": True},
        )

        assert resp.status_code == 403, resp.text
        assert _error_code(resp) == "scope_missing"

    def test_other_org_connection_is_404(self, bridge_client, override_ctx):
        client, store = bridge_client
        connection_id = _seed_connection(store, org_id=_OTHER_ORG)
        override_ctx(_product_ctx(scopes=[_TOGGLE_SCOPE], org_id=_ORG))

        resp = client.raw().put(
            f"/api/agents-bridge/one-chat/{connection_id}/auto-reply",
            json={"enabled": True},
        )

        assert resp.status_code == 404, resp.text


class TestExistingJwtRouteUnchanged:
    """Regression guard: the pre-existing JWT-authenticated
    ``PUT /api/whatsapp/connections/{id}/auto-reply`` route
    (``whatsapp_connections_router.py``) behaves exactly as before —
    unaffected by this bridge's addition."""

    def test_jwt_route_still_toggles_via_the_authenticated_client(
        self, bridge_client
    ):
        client, store = bridge_client
        # `client` (not `client.raw()`) carries the legacy bearer JWT the
        # existing route resolves through `get_current_user_org`, which
        # projects `user_metadata["org_id"] == "test-org-123"` (the shared
        # `client` fixture's default `MockUser` — no re-bind needed).
        connection_id = _seed_connection(
            store, org_id=_coerce_test_org_uuid(), auto_reply_enabled=False
        )

        resp = client.put(
            f"/api/whatsapp/connections/{connection_id}/auto-reply",
            json={"enabled": True},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["connection_id"] == str(connection_id)
        assert body["auto_reply_enabled"] is True


def _coerce_test_org_uuid() -> UUID:
    """Mirror ``app.dependencies.coerce_org_uuid("test-org-123")`` — the
    shared ``client`` fixture's default ``MockUser`` org id is the
    opaque fixture string ``"test-org-123"``, not a UUID; the legacy JWT
    bridge derives a stable UUID via ``uuid5`` the same way."""
    from app.dependencies import coerce_org_uuid

    return coerce_org_uuid("test-org-123")
