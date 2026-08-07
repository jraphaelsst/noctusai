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
from types import SimpleNamespace
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


#: The identity `auth.admin.create_user` returns for a brand-new invitee.
NEW_USER_ID = "new-user-1"


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

    # `noctus_users` + `auth.users` are PLATFORM tables in `public`, reached
    # through the CORE client — a distinct connection from the product-schema
    # one. /accept writes to both, so the two must be separate mocks or the
    # test cannot tell which client the router used.
    core_db = MockSupabaseClient(validate_schema=False, schema="public")
    core_db.set_table_data("noctus_users", [])
    core_db.auth.admin.list_users.return_value = []
    core_db.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=NEW_USER_ID)
    )
    fake_deps.get_core_client = MagicMock(return_value=core_db)

    # The authenticated endpoints (/invite, GET+DELETE /invitations) await
    # `deps.get_current_user(...)`. That is the EXTERNAL auth boundary —
    # AsyncMock is the right seam there (nothing of ours is patched).
    # `fake_deps.get_user_role` → "owner" and `get_org_id` → "org-123" already
    # come from the conftest fixture.
    fake_deps.get_current_user = AsyncMock(return_value=(_fake_user(), "tok"))

    app = FastAPI()
    router: APIRouter = _create_team_router(fake_deps, fake_settings, product_name)
    app.include_router(router)

    # Attach mocks for per-test seeding.
    app.state.mock_db = mock_db
    app.state.core_db = core_db
    return app


#: What the AcceptInvitePage organ actually submits.
SIGNUP = {"nome": "Nova Pessoa", "password": "hunter2"}


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

        resp = client.post("/api/team/accept", json={"token": "happy-tok", **SIGNUP})

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

        resp = client.post("/api/team/accept", json={"token": "no-such-token", **SIGNUP})

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

        resp = client.post("/api/team/accept", json={"token": "already-used", **SIGNUP})

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

        resp = client.post("/api/team/accept", json={"token": "expired-tok", **SIGNUP})

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

        resp = client.post("/api/team/accept", json={"token": "bare-tok", **SIGNUP})

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


class TestAcceptActuallyCreatesTheMember:
    """The 2026-08-07 gap: /accept used to ONLY flip the invitation status.

    It created no identity, no `public.noctus_users` profile and no org
    membership, and discarded the `nome`/`password` the AcceptInvitePage organ
    submits. The invitee saw a success screen and then could not log in
    anywhere — core's `/api/sso/launch/{slug}` reads that profile row to mint an
    SSO token and 404s "Perfil não encontrado" without it, so the account could
    not open ANY product.
    """

    def _seed(self, team_app, **kw):
        team_app.state.mock_db.set_table_data(
            "invitations", [_make_invitation_row(**kw)]
        )

    # ── Anonymous accept: identity + membership ────────────────────────
    def test_creates_the_auth_identity(self, team_app, client):
        self._seed(team_app, token="t1", email="invitee@test.com")
        resp = client.post("/api/team/accept", json={"token": "t1", **SIGNUP})

        assert resp.status_code == 200, resp.text
        core = team_app.state.core_db
        core.auth.admin.create_user.assert_called_once()
        payload = core.auth.admin.create_user.call_args[0][0]
        assert payload["email"] == "invitee@test.com"
        assert payload["password"] == "hunter2"
        assert payload["email_confirm"] is True

    def test_creates_the_noctus_users_membership_row(self, team_app, client):
        """The row core's SSO launch requires. Without it the invitee has an
        identity that cannot open a single product."""
        self._seed(team_app, token="t2", org_id="org-1", email="invitee@test.com")
        resp = client.post("/api/team/accept", json={"token": "t2", **SIGNUP})

        assert resp.status_code == 200, resp.text
        inserted = team_app.state.core_db.table("noctus_users").inserted_payloads
        assert len(inserted) == 1, inserted
        assert inserted[0]["id"] == NEW_USER_ID
        assert inserted[0]["org_id"] == "org-1"
        assert inserted[0]["org_role"] == "member"
        assert inserted[0]["email"] == "invitee@test.com"
        assert inserted[0]["nome"] == "Nova Pessoa"

    def test_membership_is_written_to_the_CORE_client_not_the_product_one(
        self, team_app, client
    ):
        """`noctus_users` lives in `public`. Writing it through the
        product-schema client would target `<schema>.noctus_users` — a table
        that does not exist."""
        self._seed(team_app, token="t3")
        resp = client.post("/api/team/accept", json={"token": "t3", **SIGNUP})

        assert resp.status_code == 200, resp.text
        assert "noctus_users" in set(team_app.state.core_db._tables)
        assert "noctus_users" not in set(team_app.state.mock_db._tables)

    def test_invite_role_becomes_the_org_role(self, team_app, client):
        self._seed(team_app, token="t4")
        team_app.state.mock_db.set_table_data(
            "invitations", [{**_make_invitation_row(token="t4"), "role": "admin"}]
        )
        resp = client.post("/api/team/accept", json={"token": "t4", **SIGNUP})

        assert resp.status_code == 200, resp.text
        inserted = team_app.state.core_db.table("noctus_users").inserted_payloads
        assert inserted[0]["org_role"] == "admin"
        assert inserted[0]["role"] == "user", (
            "an org-level invite must never confer a PLATFORM role"
        )

    def test_org_context_is_mirrored_into_user_metadata(self, team_app, client):
        """`get_org_id(user)` reads `user_metadata["org_id"]` and 403s without
        it, so a member whose metadata was never written is locked out of the
        product's own endpoints until their first SSO launch."""
        self._seed(team_app, token="t5", org_id="org-1")
        resp = client.post("/api/team/accept", json={"token": "t5", **SIGNUP})

        assert resp.status_code == 200, resp.text
        core = team_app.state.core_db
        core.auth.admin.update_user_by_id.assert_called_once()
        meta = core.auth.admin.update_user_by_id.call_args[0][1]["user_metadata"]
        assert meta["org_id"] == "org-1"
        assert meta["org_role"] == "member"

    def test_invitation_records_who_accepted(self, team_app, client):
        self._seed(team_app, token="t6", invitation_id="inv-6")
        resp = client.post("/api/team/accept", json={"token": "t6", **SIGNUP})

        assert resp.status_code == 200, resp.text
        payloads = team_app.state.mock_db.table("invitations").updated_payloads
        assert len(payloads) == 1, payloads
        assert payloads[0]["status"] == "accepted"
        assert payloads[0]["accepted_by"] == NEW_USER_ID
        assert "accepted_at" in payloads[0]

    def test_response_reports_the_new_user(self, team_app, client):
        self._seed(team_app, token="t7")
        resp = client.post("/api/team/accept", json={"token": "t7", **SIGNUP})

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["user_id"] == NEW_USER_ID
        assert data["created_identity"] is True

    # ── The email comes from the INVITATION, never the body ────────────
    def test_body_cannot_override_the_invited_email(self, team_app, client):
        """Otherwise a leaked token enrolls an attacker's address instead of
        the one that was actually invited."""
        self._seed(team_app, token="t8", email="invitee@test.com")
        resp = client.post(
            "/api/team/accept",
            json={"token": "t8", "email": "attacker@evil.com", **SIGNUP},
        )

        assert resp.status_code == 200, resp.text
        created = team_app.state.core_db.auth.admin.create_user.call_args[0][0]
        assert created["email"] == "invitee@test.com"

    # ── Input validation on the anonymous path ─────────────────────────
    def test_missing_token_returns_400(self, team_app, client):
        resp = client.post("/api/team/accept", json={**SIGNUP})
        assert resp.status_code == 400, resp.text
        assert "Token" in resp.json()["detail"]

    def test_missing_nome_returns_400(self, team_app, client):
        self._seed(team_app, token="t9")
        resp = client.post(
            "/api/team/accept", json={"token": "t9", "password": "hunter2"}
        )
        assert resp.status_code == 400, resp.text
        assert "Nome" in resp.json()["detail"]

    def test_short_password_returns_400(self, team_app, client):
        """Matches the organ's own client-side rule (>= 6). A backend that
        accepted what the form rejects would be a contract the FE cannot see."""
        self._seed(team_app, token="t10")
        resp = client.post(
            "/api/team/accept",
            json={"token": "t10", "nome": "X", "password": "abc"},
        )
        assert resp.status_code == 400, resp.text
        assert "Senha" in resp.json()["detail"]

    def test_no_identity_is_created_when_validation_fails(self, team_app, client):
        self._seed(team_app, token="t11")
        client.post("/api/team/accept", json={"token": "t11", "nome": "X"})
        team_app.state.core_db.auth.admin.create_user.assert_not_called()

    # ── Existing identity ──────────────────────────────────────────────
    def test_existing_identity_is_linked_not_recreated(self, team_app, client):
        """Someone who already signed up on core and is now invited here."""
        core = team_app.state.core_db
        core.set_table_data(
            "noctus_users",
            [{"id": "existing-1", "email": "invitee@test.com",
              "nome": "Existing", "org_id": None}],
        )
        self._seed(team_app, token="t12", email="invitee@test.com")

        resp = client.post("/api/team/accept", json={"token": "t12", **SIGNUP})

        assert resp.status_code == 200, resp.text
        core.auth.admin.create_user.assert_not_called()
        assert resp.json()["data"]["created_identity"] is False
        assert core.table("noctus_users").updated_payloads == [
            {"org_id": "org-1", "org_role": "member"}
        ]

    def test_member_of_another_org_gets_409(self, team_app, client):
        """Membership is a single-org FK — accepting would EVICT them from
        their current org and every product licensed to it."""
        core = team_app.state.core_db
        core.set_table_data(
            "noctus_users",
            [{"id": "existing-1", "email": "invitee@test.com",
              "nome": "Existing", "org_id": "other-org", "org_role": "owner"}],
        )
        self._seed(team_app, token="t13", org_id="org-1", email="invitee@test.com")

        resp = client.post("/api/team/accept", json={"token": "t13", **SIGNUP})

        assert resp.status_code == 409, resp.text
        assert core.table("noctus_users").updated_payloads == []

    def test_conflict_leaves_the_invitation_pending(self, team_app, client):
        """A refused accept must stay retryable — burning the token on a 409
        would strand the invite permanently."""
        core = team_app.state.core_db
        core.set_table_data(
            "noctus_users",
            [{"id": "e1", "email": "invitee@test.com", "nome": "E",
              "org_id": "other-org"}],
        )
        self._seed(team_app, token="t14", email="invitee@test.com")

        client.post("/api/team/accept", json={"token": "t14", **SIGNUP})

        assert team_app.state.mock_db.table("invitations").updated_payloads == []

    # ── Authenticated accept ───────────────────────────────────────────
    def test_authenticated_accept_uses_the_caller_identity(
        self, team_app, client, auth_header
    ):
        """Someone already signed in is accepting FOR THEMSELVES — no account
        is created and no password is needed."""
        self._seed(team_app, token="t15", org_id="org-1")
        resp = client.post(
            "/api/team/accept", json={"token": "t15"}, headers=auth_header,
        )

        assert resp.status_code == 200, resp.text
        core = team_app.state.core_db
        core.auth.admin.create_user.assert_not_called()
        inserted = core.table("noctus_users").inserted_payloads
        assert inserted[0]["id"] == "u-admin", inserted
        assert resp.json()["data"]["created_identity"] is False

    def test_authenticated_accept_ignores_a_submitted_password(
        self, team_app, client, auth_header
    ):
        self._seed(team_app, token="t16")
        resp = client.post(
            "/api/team/accept",
            json={"token": "t16", "password": "attacker-chosen"},
            headers=auth_header,
        )
        assert resp.status_code == 200, resp.text
        team_app.state.core_db.auth.admin.create_user.assert_not_called()

    def test_unusable_auth_header_falls_back_to_the_anonymous_path(
        self, team_app, fake_deps, client
    ):
        """An expired token in the header must not block a legitimate signup —
        the anonymous path is the whole point of an invitation link."""
        from fastapi import HTTPException as _HTTPException

        fake_deps.get_current_user = AsyncMock(
            side_effect=_HTTPException(status_code=401, detail="expired")
        )
        self._seed(team_app, token="t17")

        resp = client.post(
            "/api/team/accept",
            json={"token": "t17", **SIGNUP},
            headers={"Authorization": "Bearer stale"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["created_identity"] is True

    # ── Compensating rollback ──────────────────────────────────────────
    def test_orphan_identity_is_deleted_when_membership_fails(
        self, team_app, client
    ):
        """An identity we just created, with no membership, is unreachable AND
        blocks the retry (its email is now taken). Leaving it behind turns a
        transient failure into a permanent one."""
        core = team_app.state.core_db
        self._seed(team_app, token="t18")

        # Break ONLY the insert on the real builder — select/eq/execute stay
        # genuine, so the failure is the one under test and not a mock that
        # cannot answer the lookup.
        core.table("noctus_users").insert = MagicMock(
            side_effect=RuntimeError("insert failed")
        )

        resp = client.post("/api/team/accept", json={"token": "t18", **SIGNUP})

        assert resp.status_code == 500, resp.text
        core.auth.admin.delete_user.assert_called_once_with(NEW_USER_ID)

    def test_failed_membership_leaves_the_invitation_pending(
        self, team_app, client
    ):
        """The rollback must be complete: a burned token plus a deleted
        identity would leave the invitee with no way back in at all."""
        core = team_app.state.core_db
        self._seed(team_app, token="t18b")
        core.table("noctus_users").insert = MagicMock(
            side_effect=RuntimeError("insert failed")
        )

        client.post("/api/team/accept", json={"token": "t18b", **SIGNUP})

        assert team_app.state.mock_db.table("invitations").updated_payloads == []

    def test_a_PRE_EXISTING_identity_is_never_deleted_on_failure(
        self, team_app, client
    ):
        """It is not ours to delete — that account existed before this invite
        and belongs to someone who may be using it elsewhere."""
        core = team_app.state.core_db
        # No profile row, but the identity DOES exist in auth.users — the
        # "signed up on core, never joined an org" case. `provision_invited_identity`
        # links it, so `created_identity` is False and it must survive.
        core.auth.admin.list_users.return_value = [
            SimpleNamespace(id="existing-1", email="invitee@test.com")
        ]
        self._seed(team_app, token="t19", email="invitee@test.com")
        core.table("noctus_users").insert = MagicMock(
            side_effect=RuntimeError("insert failed")
        )

        resp = client.post("/api/team/accept", json={"token": "t19", **SIGNUP})

        assert resp.status_code == 500, resp.text
        core.auth.admin.delete_user.assert_not_called()


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
