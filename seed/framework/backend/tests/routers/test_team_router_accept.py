"""Tests for the seed `team` standard router — `/api/team/accept` happy path.

Scope: end-to-end exercise of the POST `/api/team/accept` endpoint through
`_create_team_router(...)`. Prior to the 2026-05-11 caller-side fix, the router
invoked `validate_invitation(db=..., schema=..., token=...)` and
`accept_invitation(db=..., schema=..., token=..., user_id=..., email=...,
password=..., name=...)` — but the domain helpers accept `(db, table: str,
token|invitation_id)` as positional args. **TypeError on first call.**

The drift survived because no integration test exercised the endpoint — only
the build-time signature-parse tests. This file closes that gap.

Test-data strategy: seed REAL invitation rows via the seed's `MockSupabaseClient`
(no monkey-patching of `noctusai_lib.domain.invitations` — per the
"no-monkey-patching-of-our-own-code" rule). The router's auth gate
(`deps.get_current_user`) is at the external boundary — `AsyncMock` is fine
there.

Status-code-assertion-rule: every body assertion is paired with a
`.status_code` assertion in the same method (defends against the
YouTube-Crawler Phase-1 false-green slip).

2026-08-06 — the SAME fix re-broke a different way. The 2026-05-11 rewrite
addressed `f"{deps._db.schema}.invitations"`, and these fixtures seeded
`"test.invitations"` to match. The mock keys tables by whatever string it is
handed, so fixture and caller agreed and the suite stayed green — while
PostgREST, which resolves table names RELATIVE to the schema already bound on
the client, answered every live invite with
`500 Could not find the table 'social_wiring.social_wiring.invitations'`.
Table names are BARE now, and `TestInvitationsTableIsBare` asserts on the
mock's own key set so the qualified form cannot come back green.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.testing.mocks import MockSupabaseClient
from noctusai_seed.routers import _create_team_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_invitation_row(
    *,
    token: str = "tok-xyz",
    status: str = "pending",
    expires_at: str | None = None,
    invitation_id: str = "inv-1",
    org_id: str = "org-1",
    email: str = "invitee@test.com",
) -> dict:
    """Build an invitation row matching `seed.invitations` shape."""
    if expires_at is None:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    return {
        "id": invitation_id,
        "org_id": org_id,
        "email": email,
        "role": "member",
        "invited_by": "u-admin",
        "token": token,
        "status": status,
        "expires_at": expires_at,
    }


def _fake_user(
    *,
    user_id: str = "u-admin",
    name: str = "Admin Tester",
    org_name: str = "Org Teste",
):
    """A gotrue-User-shaped stand-in: the router reads `.id` and
    `.user_metadata` only."""
    user = MagicMock()
    user.id = user_id
    user.user_metadata = {"name": name, "org_name": org_name}
    return user


@pytest.fixture
def auth_header() -> dict:
    """Any non-empty Authorization header — `get_current_user` is AsyncMock'd,
    so the VALUE is irrelevant; presence is what routes through the handler."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def team_app(fake_deps, fake_settings, product_name):
    """Mount the team router on a fresh FastAPI app with mock-backed deps.

    `deps._db.schema = "test"` (set by the seed conftest fixture) binds the
    client's schema — so the router addresses the BARE table `"invitations"`
    and PostgREST resolves it relative to that binding. We attach a
    `MockSupabaseClient` and pre-seed an invitation row so the
    /accept happy-path runs end-to-end.
    """
    mock_db = MockSupabaseClient(validate_schema=False, schema="test")
    fake_deps.get_admin_client = MagicMock(return_value=mock_db)

    # The authenticated endpoints (/invite, GET+DELETE /invitations) await
    # `deps.get_current_user(...)`. That is the EXTERNAL auth boundary —
    # AsyncMock is the right seam there (nothing of ours is patched).
    # `fake_deps.get_user_role` → "owner" and `get_org_id` → "org-123" already
    # come from the conftest fixture.
    fake_deps.get_current_user = AsyncMock(return_value=(_fake_user(), "tok"))

    app = FastAPI()
    router: APIRouter = _create_team_router(fake_deps, fake_settings, product_name)
    app.include_router(router)

    # Attach mock for per-test seeding.
    app.state.mock_db = mock_db
    return app


@pytest.fixture
def client(team_app):
    return TestClient(team_app)


# ---------------------------------------------------------------------------
# Happy-path tests — these FAIL with the pre-fix `db=, schema=, token=` kwargs
# and PASS once the router adapts to the domain signature `(db, table, token|id)`.
# ---------------------------------------------------------------------------


class TestAcceptInvitationEndpoint:
    """POST /api/team/accept end-to-end against `_create_team_router(...)`.

    Pre-fix shape (broken):
        validate_invitation(db=db, schema=schema, token=token)        # TypeError
        accept_invitation(db=db, schema=schema, token=..., user_id=..., ...)

    Post-fix shape (working):
        table = f"{schema}.invitations"
        inv = validate_invitation(db, table, payload.token)
        accept_invitation(db, table, inv["id"])

    These assertions would have raised TypeError before the fix, surfacing as
    HTTP 500. Post-fix, the happy path returns 200.
    """

    def test_accept_happy_path_returns_200(self, team_app, client):
        """Posting a valid token marks the invitation accepted and returns 200."""
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(token="happy-tok", invitation_id="inv-happy")],
        )

        resp = client.post("/api/team/accept", json={"token": "happy-tok"})

        # Status-code-assertion-rule: ALWAYS pair with status_code.
        # Pre-fix: TypeError inside the handler → 500. Post-fix: 200.
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}. "
            "Pre-fix the router invokes validate_invitation/accept_invitation "
            "with `db=, schema=, token=` kwargs but the domain helpers accept "
            "(db, table, token|id) positionally — TypeError surfaces as 500."
        )
        body = resp.json()
        assert "data" in body

    def test_accept_invalid_token_returns_404(self, team_app, client):
        """Unknown token → domain helper raises HTTPException(404)."""
        mock_db = team_app.state.mock_db
        # No matching row — `.single()` returns empty data.
        mock_db.set_table_data("invitations", [])

        resp = client.post("/api/team/accept", json={"token": "no-such-token"})

        assert resp.status_code == 404, (
            f"Expected 404 (not-found), got {resp.status_code}. Body: {resp.text}"
        )
        assert resp.json()["detail"] == "Convite nao encontrado"

    def test_accept_already_used_returns_400(self, team_app, client):
        """A non-pending invitation → domain helper raises HTTPException(400)."""
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [
                _make_invitation_row(
                    token="already-used",
                    status="accepted",
                    invitation_id="inv-used",
                )
            ],
        )

        resp = client.post("/api/team/accept", json={"token": "already-used"})

        assert resp.status_code == 400, (
            f"Expected 400 (already-used), got {resp.status_code}. Body: {resp.text}"
        )
        assert "ja foi utilizado" in resp.json()["detail"]

    def test_accept_expired_returns_400(self, team_app, client):
        """Expired invitation → domain helper raises HTTPException(400) +
        auto-expires the row."""
        mock_db = team_app.state.mock_db
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mock_db.set_table_data(
            "invitations",
            [
                _make_invitation_row(
                    token="expired-tok",
                    expires_at=past,
                    invitation_id="inv-exp",
                )
            ],
        )

        resp = client.post("/api/team/accept", json={"token": "expired-tok"})

        assert resp.status_code == 400, (
            f"Expected 400 (expired), got {resp.status_code}. Body: {resp.text}"
        )
        assert resp.json()["detail"] == "Convite expirado"


class TestValidateInvitationEndpoint:
    """GET /api/team/accept/validate — companion endpoint also affected by
    the same caller-side kwarg drift."""

    def test_validate_happy_path_returns_200(self, team_app, client):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(token="valid-tok", invitation_id="inv-v")],
        )

        resp = client.get("/api/team/accept/validate", params={"token": "valid-tok"})

        # Pre-fix: TypeError → 500. Post-fix: 200.
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}"
        )
        body = resp.json()
        assert body["data"]["token"] == "valid-tok"
        assert body["data"]["status"] == "pending"

    def test_validate_invalid_returns_404(self, team_app, client):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data("invitations", [])

        resp = client.get("/api/team/accept/validate", params={"token": "missing"})

        assert resp.status_code == 404, (
            f"Expected 404, got {resp.status_code}. Body: {resp.text}"
        )


class TestInvitationsTableIsBare:
    """The regression guard for the 2026-08-06 PostgREST 500.

    `_create_team_router` must address the BARE table `"invitations"`. The
    client from `deps.get_admin_client()` is already bound to
    `deps._db.schema`, so a qualified name (`f"{schema}.invitations"`) resolves
    as `<schema>.<schema>.invitations` and PostgREST 500s.

    Asserting on `mock_db._tables` — the mock's own key set — is what makes this
    catch the bug. Seeding a qualified fixture and reading it back only proves
    the mock is a dict; the KEY the router chose is the thing under test.
    """

    def _table_keys(self, mock_db) -> set:
        return set(mock_db._tables)

    def test_accept_addresses_bare_table(self, team_app, client):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(token="bare-tok", invitation_id="inv-bare")],
        )

        resp = client.post("/api/team/accept", json={"token": "bare-tok"})

        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}"
        )
        assert self._table_keys(mock_db) == {"invitations"}, (
            "Router addressed a schema-qualified table. PostgREST resolves "
            "table names relative to the schema already bound on the client, "
            f"so this 500s live. Keys touched: {self._table_keys(mock_db)!r}"
        )

    def test_validate_addresses_bare_table(self, team_app, client):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(token="bare-v", invitation_id="inv-bv")],
        )

        resp = client.get("/api/team/accept/validate", params={"token": "bare-v"})

        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}"
        )
        assert self._table_keys(mock_db) == {"invitations"}


class TestInviteEndpoint:
    """POST /api/team/invite — the endpoint that 500'd in social-wiring.

    No email seam is stubbed: `noctusai_lib.integrations.email.templates._send`
    already no-ops (logs + returns False) when `RESEND_API_KEY` is unset, which
    is the case under pytest. Nothing of ours is monkey-patched.
    """

    def test_invite_creates_row_in_bare_table(self, team_app, client, auth_header):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data("invitations", [])

        resp = client.post(
            "/api/team/invite",
            json={"email": "invitee@test.com", "role": "member"},
            headers=auth_header,
        )

        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}. "
            "Pre-fix the router passed f'{schema}.invitations' to a client "
            "already bound to that schema — PostgREST 500'd with "
            "\"Could not find the table '<schema>.<schema>.invitations'\"."
        )
        body = resp.json()
        assert body["data"]["email"] == "invitee@test.com"
        assert body["data"]["token"], "invite must carry a token for the email link"
        assert set(mock_db._tables) == {"invitations"}

    def test_invite_duplicate_pending_returns_409(self, team_app, client, auth_header):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(email="dupe@test.com", org_id="org-123")],
        )

        resp = client.post(
            "/api/team/invite",
            json={"email": "dupe@test.com", "role": "member"},
            headers=auth_header,
        )

        assert resp.status_code == 409, (
            f"Expected 409 (duplicate pending), got {resp.status_code}. "
            f"Body: {resp.text}"
        )
        assert "ja existe um convite pendente" in resp.json()["detail"].lower()


class TestListAndCancelInvitations:
    """GET + DELETE /api/team/invitations — both hit the same table."""

    def test_list_pending_returns_rows(self, team_app, client, auth_header):
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(invitation_id="inv-l", org_id="org-123")],
        )

        resp = client.get("/api/team/invitations", headers=auth_header)

        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}"
        )
        assert [r["id"] for r in resp.json()["data"]] == ["inv-l"]
        assert set(mock_db._tables) == {"invitations"}

    def test_cancel_passes_org_id_and_marks_canceled(
        self, team_app, client, auth_header
    ):
        """Pins BOTH 2026-08-06 fixes on this handler.

        `cancel_invitation(db, table, invitation_id, org_id)` takes org_id as a
        required 4th positional arg — it scopes the cancel so an admin of org A
        cannot cancel org B's invite. The router omitted it, so every DELETE
        raised TypeError → 500 before the table name even mattered.
        """
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(invitation_id="inv-c", org_id="org-123")],
        )

        resp = client.delete("/api/team/invitations/inv-c", headers=auth_header)

        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}. Body: {resp.text}. "
            "Pre-fix the router called cancel_invitation without org_id → "
            "TypeError → 500."
        )
        assert resp.json() == {"ok": True}
        payloads = mock_db.table("invitations").updated_payloads
        assert payloads == [{"status": "canceled"}], (
            f"Expected exactly one canceled UPDATE, got {payloads!r}"
        )
        assert set(mock_db._tables) == {"invitations"}

    def test_cancel_foreign_org_invitation_returns_404(
        self, team_app, client, auth_header
    ):
        """The org scoping the missing arg removed: org-123's admin must not
        be able to cancel org-999's invite."""
        mock_db = team_app.state.mock_db
        mock_db.set_table_data(
            "invitations",
            [_make_invitation_row(invitation_id="inv-foreign", org_id="org-999")],
        )

        resp = client.delete("/api/team/invitations/inv-foreign", headers=auth_header)

        assert resp.status_code == 404, (
            f"Expected 404 (not visible to this org), got {resp.status_code}. "
            f"Body: {resp.text}"
        )
        assert mock_db.table("invitations").updated_payloads == [], (
            "A foreign-org invitation must not be mutated"
        )


class TestRouterSurfaceUnchanged:
    """Guard: confirm the router still mounts the expected paths so the
    caller-side refactor didn't accidentally move routes around."""

    def test_team_router_exposes_accept_endpoints(self, team_app):
        paths = {route.path for route in team_app.router.routes if hasattr(route, "path")}
        assert "/api/team/accept" in paths
        assert "/api/team/accept/validate" in paths

    def test_team_router_exposes_invitation_management_endpoints(self, team_app):
        paths = {route.path for route in team_app.router.routes if hasattr(route, "path")}
        assert "/api/team/invite" in paths
        assert "/api/team/invitations" in paths
        assert "/api/team/invitations/{invitation_id}" in paths
