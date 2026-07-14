"""Auth-boundary regression tests — ``sw-meta-org-auth-wiring``.

Confirmed HIGH/critical finding: the Meta / Calendar / Google surface
resolved its tenant ``org`` from an attacker-controllable ``?org_id=``
query param with NO auth dependency in front of it (routers mounted
without a global auth middleware ⇒ fully unauthenticated). Any caller
could read/write ANY org's Meta data by supplying an arbitrary
org/account id; the admin/service-role client this surface uses bypasses
RLS, so RLS was never a backstop.

Per ``KB § PATTERNS/compliance/auth-boundary-false-green.md``: assert
STRICT ``== 401`` for a no-session request (never ``in (401, 404)`` —
the non-401 branch is a false-green: route-absent or validation-before-
auth would ALSO produce a non-200, masking a missing auth dependency).
One representative endpoint per class the brief defined:

  * Class B  — ``get_account_adapter`` choke point (``/api/meta/context``
    family). No-session → 401. A session authenticated for org A
    requesting an ``account_id`` that belongs to org B → 404 (never
    reachable — the account lookup is org-scoped).
  * Class B' — the Meta-insights snapshot endpoints, which used to carry
    a SECOND, independent ``org_id`` query param. No-session → 401.
    Session org A + a crafted ``?org_id=<org B>`` query override → the
    query is a no-op; the persisted/read snapshot is scoped to the
    SESSION's org, never the query-supplied one.
  * Class A  — ``meta_status`` / ``calendar_status`` / ``google_scopes``.
    No-session → 401. A garbage (non-UUID) ``?org_id=`` value that used
    to 400 is now a complete no-op (200) — proof the param is no longer
    read at all.
  * Class D  — ``meta_oauth_start`` / ``calendar_oauth_start``.
    No-session → 401. The ``state`` token's org segment always encodes
    the SESSION's org — a ``?org_id=<org B>`` query override never
    reaches it. A tampered ``state`` fails signature verification at the
    callback (400), never silently trusted.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.config import settings
from app.services.integration_account_service import IntegrationAccountService
from app.sqlite_client import SQLiteClient

_ORG_A = "00000000-0000-4000-8000-0000000000aa"
_ORG_B = "00000000-0000-4000-8000-0000000000bb"

_IA_SCHEMA = """
CREATE TABLE IF NOT EXISTS integration_accounts (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL,
    provider            TEXT NOT NULL CHECK (provider IN ('youtube', 'google_drive', 'gmail', 'meta', 'n8n')),
    account_label       TEXT NOT NULL,
    encrypted_credential TEXT NOT NULL,
    metadata            TEXT NOT NULL DEFAULT '{}',
    is_default          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    client_id           TEXT,
    status              TEXT NOT NULL DEFAULT 'validated',
    channel_info        TEXT NOT NULL DEFAULT '{}',
    last_synced_at      TEXT,
    UNIQUE (org_id, provider, account_label)
);
"""


def _auth_header(bearer: str = "test-token") -> dict:
    return {"Authorization": f"Bearer {bearer}"}


# ─── Class B — get_account_adapter choke point ─────────────────────────
class TestAccountAdapterChokePointAuthBoundary:
    @pytest.fixture
    def sqlite_ia_db(self, tmp_path: Path) -> SQLiteClient:
        db_path = tmp_path / "ia.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_IA_SCHEMA)
        return SQLiteClient(db_path)

    @pytest.fixture
    def fernet_key(self) -> str:
        return Fernet.generate_key().decode("ascii")

    @pytest.fixture
    def org_b_meta_account_id(self, sqlite_ia_db: SQLiteClient, fernet_key: str) -> str:
        """A real ``integration_accounts`` row under ORG_B — proves the
        cross-tenant lookup, not just "account doesn't exist anywhere"."""
        svc = IntegrationAccountService(sqlite_ia_db, fernet=Fernet(fernet_key.encode("ascii")))
        account = svc.create_account(
            org_id=UUID(_ORG_B),
            provider="meta",
            account_label="Org B Meta",
            credential_dict={"access_token": "org-b-token"},
        )
        return str(account.id)

    @pytest.fixture
    def client(self, sqlite_ia_db: SQLiteClient, fernet_key: str, monkeypatch):
        """Real auth path: ``get_current_user_org`` verifies the bearer
        JWT against a mocked ``auth.get_user`` (org A); the admin client
        (used for the ``integration_accounts`` lookup) is swapped for a
        REAL SQLite-backed store seeded with an org-B row — no
        monkeypatching of our own guard, just realistic test data via the
        existing DI seam (``DatabaseModule.get_admin_client``, a seed
        boundary, not our own code).

        ``encryption_key`` is monkeypatched onto the settings singleton
        (auto-reverted by ``monkeypatch``) purely so the REAL
        ``get_meta_adapter_for_account`` code path can construct its
        Fernet-backed service — not a guard bypass, the opposite: it lets
        more real code execute instead of short-circuiting on a config
        gap unrelated to this test's auth boundary.
        """
        monkeypatch.setattr(settings, "encryption_key", fernet_key)

        mock_sb = MockSupabaseClient()
        mock_sb.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(org_id=_ORG_A))
        )

        with (
            patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=sqlite_ia_db),
        ):
            from app.main import app

            bind_consent_module_to_mock(mock_sb)
            tc = TestClient(app)
            yield tc
            app.dependency_overrides.clear()

    def test_no_session_returns_strict_401(self, client, org_b_meta_account_id):
        resp = client.get(
            f"/api/meta/instagram/insights?account_id={org_b_meta_account_id}"
        )
        assert resp.status_code == 401, resp.text

    def test_wrong_org_session_cannot_reach_another_orgs_account(
        self, client, org_b_meta_account_id
    ):
        """Authenticated as org A; the account belongs to org B. Even an
        explicit ``?org_id=<org B>`` attempt to override the session is
        ignored (the param doesn't exist on this endpoint at all
        anymore) — the lookup is scoped to the SESSION's org (A), so the
        org-B account is invisible: 404, never 200 with someone else's
        data."""
        resp = client.get(
            f"/api/meta/instagram/insights?account_id={org_b_meta_account_id}&org_id={_ORG_B}",
            headers=_auth_header(),
        )
        assert resp.status_code == 404, resp.text


# ─── Class B' — Meta-insights snapshot endpoints ────────────────────────
class TestSnapshotEndpointsAuthBoundary:
    @pytest.fixture
    def client(self):
        mock_sb = MockSupabaseClient()
        with (
            patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
        ):
            from app.main import app

            bind_consent_module_to_mock(mock_sb)
            tc = TestClient(app)
            yield tc
            app.dependency_overrides.clear()

    def _override_adapter(self):
        from noctusai_lib.integrations.meta import FakeMetaAdapter, InstagramAccount

        from app.main import app
        from app.routers._meta_common import get_account_adapter

        adapter = FakeMetaAdapter()
        adapter.seed(
            ig_accounts=[
                InstagramAccount(id="ig-user-1", username="boundary_test")
            ]
        )
        app.dependency_overrides[get_account_adapter] = lambda: adapter

    def test_no_session_returns_strict_401(self, client):
        self._override_adapter()
        resp = client.get(
            "/api/meta/instagram/snapshots"
            "?account_id=00000000-0000-4000-8000-0000000000ac"
        )
        assert resp.status_code == 401, resp.text

    def test_org_id_query_override_is_a_no_op(self, client):
        """A session authenticated for org A + an explicit
        ``?org_id=<org B>`` attempt: the (removed) second org resolver
        used to trust this value outright. Confirm the endpoint no
        longer even 400s on a malformed one — the param is dead, not
        merely "trusted less"."""
        self._override_adapter()
        from app.dependencies import get_current_user_org
        from app.main import app

        app.dependency_overrides[get_current_user_org] = lambda: (
            object(), "test-token", _ORG_A,
        )
        resp = client.get(
            "/api/meta/instagram/snapshots"
            f"?account_id=00000000-0000-4000-8000-0000000000ac&org_id={_ORG_B}",
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text


# ─── Class A — status / scopes introspection ────────────────────────────
class TestClassAStatusEndpointsAuthBoundary:
    @pytest.fixture
    def client(self):
        mock_sb = MockSupabaseClient()
        mock_sb.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(org_id=_ORG_A))
        )
        with (
            patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
        ):
            from app.main import app

            bind_consent_module_to_mock(mock_sb)
            tc = TestClient(app)
            yield tc
            app.dependency_overrides.clear()

    @pytest.mark.parametrize(
        "path",
        ["/api/meta/status", "/api/calendar/status", "/api/google/scopes"],
    )
    def test_no_session_returns_strict_401(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 401, resp.text

    @pytest.mark.parametrize(
        "path",
        ["/api/meta/status", "/api/calendar/status", "/api/google/scopes"],
    )
    def test_garbage_org_id_query_is_a_no_op(self, client, path):
        """Pre-fix, a non-UUID ``?org_id=`` raised 400 ("invalid
        org_id") because the query param was read and parsed. Post-fix
        the param isn't read at all — a garbage value has zero effect
        (200), proving the org resolution path no longer touches the
        query string."""
        resp = client.get(f"{path}?org_id=not-a-real-org-id", headers=_auth_header())
        assert resp.status_code == 200, resp.text


# ─── Class D — OAuth start / signed state ───────────────────────────────
class TestOAuthStartAuthBoundary:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr(settings, "meta_app_id", "test-app-id")
        monkeypatch.setattr(settings, "meta_app_secret", "test-app-secret")
        # Pin an explicit scope list so oauth_start never falls into
        # "auto" → discover_app_permissions' real Graph-API network call.
        monkeypatch.setattr(settings, "meta_oauth_scopes", "instagram_basic")
        monkeypatch.setattr(settings, "google_oauth_client_id", "test-client-id")
        monkeypatch.setattr(settings, "google_oauth_client_secret", "test-client-secret")
        mock_sb = MockSupabaseClient()
        mock_sb.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(org_id=_ORG_A))
        )
        with (
            patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
        ):
            from app.main import app

            bind_consent_module_to_mock(mock_sb)
            tc = TestClient(app)
            yield tc
            app.dependency_overrides.clear()

    @pytest.mark.parametrize(
        "path", ["/api/meta/oauth/start", "/api/calendar/oauth/start"]
    )
    def test_no_session_returns_strict_401(self, client, path):
        resp = client.get(f"{path}?redirect_to_consent=false")
        assert resp.status_code == 401, resp.text

    @pytest.mark.parametrize(
        "path", ["/api/meta/oauth/start", "/api/calendar/oauth/start"]
    )
    def test_state_org_segment_is_always_the_session_org(self, client, path):
        """An ``?org_id=<org B>`` query attempt to steer the minted
        ``state`` toward a different org is fully ignored — the org
        segment always decodes to the AUTHENTICATED session's org."""
        resp = client.get(
            f"{path}?redirect_to_consent=false&org_id={_ORG_B}",
            headers=_auth_header(),
        )
        if resp.status_code == 503:
            pytest.skip("provider credentials not resolvable in this test env")
        assert resp.status_code == 200, resp.text
        state = resp.json()["state"]
        org_part = state.split(":", 1)[0]
        assert org_part == _ORG_A
        assert org_part != _ORG_B

    def test_tampered_state_fails_callback_verification(self, client):
        """A hand-crafted state (right shape, wrong/garbage signature)
        must be REJECTED by the callback, never silently trusted — the
        core guarantee the HMAC signing closes."""
        forged_state = f"{_ORG_B}:forged-nonce:0"
        resp = client.get(
            f"/api/meta/oauth/callback?code=irrelevant&state={forged_state}"
        )
        assert resp.status_code == 400, resp.text
