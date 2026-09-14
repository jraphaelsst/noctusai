"""Tests for `app/routers/content_router.py` — contract §B.5."""
from __future__ import annotations

from uuid import UUID

from noctusai_lib.api.auth.session.types import AuthContext

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_USER = UUID("00000000-0000-4000-8000-0000000000bb")


def _user_ctx() -> AuthContext:
    return AuthContext(
        org_id=_ORG, caller_kind="user", user_id=_USER, scopes=[],
        raw_token="s1", api_token_id=None,
    )


def _seed_role(client, role: str = "owner") -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(_USER), "org_id": str(_ORG), "org_role": role}]
    )


class TestAuthBoundary:
    def test_unauthenticated_is_401(self, client, store):
        resp = client.raw().get("/api/content")
        assert resp.status_code == 401


class TestCreateListGet:
    def test_create_roteiro_without_fontes_gets_aviso(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post(
            "/api/content",
            json={"tipo": "roteiro", "titulo": "Ep 1", "corpo_md": "# oi"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["codigo"].startswith("C-")
        assert body["aviso"] is not None

    def test_create_copy_without_fontes_has_no_aviso(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post(
            "/api/content",
            json={"tipo": "copy", "titulo": "Post", "corpo_md": "texto"},
        )
        assert resp.status_code == 201
        assert resp.json()["aviso"] is None

    def test_get_and_list(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        created = client.raw().post(
            "/api/content",
            json={"tipo": "quiz", "titulo": "Q1", "corpo_md": "x", "fontes": ["algum-slug"]},
        ).json()
        get_resp = client.raw().get(f"/api/content/{created['codigo']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["aviso"] is None

        list_resp = client.raw().get("/api/content?tipo=quiz")
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1

    def test_get_unknown_codigo_is_404(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().get("/api/content/C-999")
        assert resp.status_code == 404
