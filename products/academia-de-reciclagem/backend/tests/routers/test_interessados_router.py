"""Tests for `app/routers/interessados_router.py` -- interessados-CONTRACT.md.

`store` overrides `app.dependencies.get_interessados_store` with a fresh
`FakeInteressadosStore` (state persists across a test's multiple
requests). `set_auth` overrides `app.dependencies.get_auth_context` --
both fixtures come from `tests/routers/conftest.py`, same seam every
other router suite in this package uses (see `test_import_router.py`).

Public-route requests go through `client.raw()` (no auth header at all)
-- the route declares no auth dependency, so this is the honest
"unauthenticated caller" shape. Admin-route requests also go through
`client.raw()`: `set_auth` overrides `get_auth_context` directly, so the
request's own headers are irrelevant to which `AuthContext` the route
sees -- using `.raw()` throughout keeps that visible rather than relying
on `client`'s default bearer token, which is a different (legacy-JWT)
code path this suite is not exercising.

Assertions read `interessados_store.rows` directly (a plain dict) rather
than awaiting the store's own async methods from a sync test function --
same direct-attribute-access convention `test_import_router.py` uses via
`store.kb_entries`/`store.kb_revisions`.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.api.auth.session.types import AuthContext

from app.dependencies import get_interessados_store
from app.interessados.fake import FakeInteressadosStore
from app.main import app

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_ADMIN_USER = UUID("00000000-0000-4000-8000-0000000000bb")
_MEMBER_USER = UUID("00000000-0000-4000-8000-0000000000cc")

_VALID_BODY = {
    "nome": "Maria Silva",
    "whatsapp": "(11) 98765-4321",
    "email": "maria@exemplo.com",
    "consentimento": True,
    "origem": "/como-funciona",
}


@pytest.fixture
def interessados_store():
    fake = FakeInteressadosStore()
    app.dependency_overrides[get_interessados_store] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_interessados_store, None)


def _admin_ctx() -> AuthContext:
    return AuthContext(
        org_id=_ORG, caller_kind="user", user_id=_ADMIN_USER, scopes=[],
        raw_token="s-admin", api_token_id=None,
    )


def _member_ctx() -> AuthContext:
    return AuthContext(
        org_id=_ORG, caller_kind="user", user_id=_MEMBER_USER, scopes=[],
        raw_token="s-member", api_token_id=None,
    )


def _seed_role(client, user_id: UUID, role: str) -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(user_id), "org_id": str(_ORG), "org_role": role}]
    )


def _body(**overrides) -> dict:
    body = dict(_VALID_BODY)
    body.update(overrides)
    return body


class TestPublicCreateHappyPath:
    def test_new_signup_returns_201_ok_true(self, client, interessados_store):
        resp = client.raw().post("/api/public/interessados", json=_VALID_BODY)
        assert resp.status_code == 201, resp.text
        assert resp.json() == {"ok": True}
        assert len(interessados_store.rows) == 1
        row = next(iter(interessados_store.rows.values()))
        assert row["email"] == "maria@exemplo.com"
        assert row["whatsapp"] == "+5511987654321"  # E.164 via normalize_phone

    def test_resubmission_same_email_same_response_no_leak(self, client, interessados_store):
        first = client.raw().post("/api/public/interessados", json=_VALID_BODY)
        second = client.raw().post(
            "/api/public/interessados", json=_body(nome="Maria S. Silva", origem="/a-carta")
        )
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json() == {"ok": True}
        assert len(interessados_store.rows) == 1  # upsert, never a duplicate row
        row = next(iter(interessados_store.rows.values()))
        assert row["nome"] == "Maria S. Silva"
        assert row["origem"] == "/a-carta"

    def test_no_auth_dependency_required(self, client, interessados_store):
        # No Authorization header at all -- the public route must still work.
        resp = client.raw().post("/api/public/interessados", json=_VALID_BODY)
        assert resp.status_code == 201


class TestPublicCreateValidation:
    """The router's own `_invalid()` raises `HTTPException(422, detail={
    "detail","code","field"})`; the seed's `http_exception_handler`
    passes a dict `exc.detail` carrying BOTH `"detail"` and `"code"`
    through VERBATIM (flat) -- so the response body IS that dict, not
    `{"detail": {...}}` (see `noctusai_lib.primitives.exceptions.
    http_exception_handler`'s own docstring)."""

    def test_nome_too_short_is_422_invalid(self, client, interessados_store):
        resp = client.raw().post("/api/public/interessados", json=_body(nome="A"))
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "invalid"
        assert body["field"] == "nome"
        assert isinstance(body["detail"], str) and body["detail"]

    def test_nome_too_long_is_422_invalid(self, client, interessados_store):
        resp = client.raw().post("/api/public/interessados", json=_body(nome="A" * 121))
        assert resp.status_code == 422
        assert resp.json()["field"] == "nome"

    def test_whatsapp_invalid_is_422_invalid(self, client, interessados_store):
        resp = client.raw().post("/api/public/interessados", json=_body(whatsapp="123"))
        assert resp.status_code == 422
        body = resp.json()
        assert body["field"] == "whatsapp"
        assert body["code"] == "invalid"

    def test_email_invalid_is_422_invalid(self, client, interessados_store):
        resp = client.raw().post("/api/public/interessados", json=_body(email="not-an-email"))
        assert resp.status_code == 422
        body = resp.json()
        assert body["field"] == "email"
        assert body["code"] == "invalid"

    def test_consentimento_false_is_422_invalid(self, client, interessados_store):
        resp = client.raw().post("/api/public/interessados", json=_body(consentimento=False))
        assert resp.status_code == 422
        body = resp.json()
        assert body["field"] == "consentimento"
        assert body["code"] == "invalid"

    def test_unknown_field_is_422(self, client, interessados_store):
        resp = client.raw().post(
            "/api/public/interessados", json=_body(campo_desconhecido="x")
        )
        assert resp.status_code == 422


class TestPublicCreateRateLimit:
    def test_sixth_request_in_a_minute_is_429(self, client, interessados_store):
        for i in range(5):
            resp = client.raw().post(
                "/api/public/interessados",
                json=_body(email=f"pessoa{i}@exemplo.com"),
            )
            assert resp.status_code == 201, resp.text
        sixth = client.raw().post(
            "/api/public/interessados", json=_body(email="pessoa5@exemplo.com")
        )
        assert sixth.status_code == 429

    def test_limit_is_per_visitor_behind_the_tunnel(self, client, interessados_store):
        # In prod every request arrives from the same tunnel peer; the visitor
        # is only distinguishable by CF-Connecting-IP. One visitor exhausting
        # the limit must not lock out the next one.
        visitor_a = {"CF-Connecting-IP": "203.0.113.7"}
        for i in range(5):
            resp = client.raw().post(
                "/api/public/interessados",
                json=_body(email=f"a{i}@exemplo.com"), headers=visitor_a,
            )
            assert resp.status_code == 201, resp.text
        assert client.raw().post(
            "/api/public/interessados", json=_body(email="a5@exemplo.com"), headers=visitor_a,
        ).status_code == 429
        other = client.raw().post(
            "/api/public/interessados",
            json=_body(email="b0@exemplo.com"), headers={"CF-Connecting-IP": "198.51.100.9"},
        )
        assert other.status_code == 201, other.text


class TestAdminAuthBoundary:
    def test_list_unauthenticated_is_401(self, client, interessados_store):
        resp = client.raw().get("/api/interessados")
        assert resp.status_code == 401

    def test_delete_unauthenticated_is_401(self, client, interessados_store):
        resp = client.raw().delete(f"/api/interessados/{uuid4()}")
        assert resp.status_code == 401

    def test_list_member_is_403_role_missing(self, client, interessados_store, set_auth):
        set_auth(_member_ctx())
        _seed_role(client, _MEMBER_USER, "member")
        resp = client.raw().get("/api/interessados")
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"

    def test_delete_member_is_403_role_missing(self, client, interessados_store, set_auth):
        set_auth(_member_ctx())
        _seed_role(client, _MEMBER_USER, "member")
        resp = client.raw().delete(f"/api/interessados/{uuid4()}")
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"


class TestAdminList:
    def test_admin_lists_signups(self, client, interessados_store, set_auth):
        client.raw().post("/api/public/interessados", json=_VALID_BODY)
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")

        resp = client.raw().get("/api/interessados")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["email"] == "maria@exemplo.com"
        assert body["items"][0]["whatsapp"] == "+5511987654321"


class TestAdminDelete:
    def test_admin_deletes_existing_signup(self, client, interessados_store, set_auth):
        client.raw().post("/api/public/interessados", json=_VALID_BODY)
        signup_id = next(iter(interessados_store.rows.keys()))

        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")
        resp = client.raw().delete(f"/api/interessados/{signup_id}")
        assert resp.status_code == 204

        assert len(interessados_store.rows) == 0

    def test_admin_deletes_unknown_id_is_404(self, client, interessados_store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")
        resp = client.raw().delete(f"/api/interessados/{uuid4()}")
        assert resp.status_code == 404

    def test_admin_deletes_malformed_id_is_404(self, client, interessados_store, set_auth):
        set_auth(_admin_ctx())
        _seed_role(client, _ADMIN_USER, "owner")
        resp = client.raw().delete("/api/interessados/not-a-uuid")
        assert resp.status_code == 404
