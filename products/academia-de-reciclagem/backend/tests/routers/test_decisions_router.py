"""Tests for `app/routers/decisions_router.py` — contract §B.2."""
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


_PAYLOAD = {"titulo": "Usar X", "contexto": "ctx", "decisao": "usar X", "motivo": "porque sim"}


class TestAuthBoundary:
    def test_unauthenticated_is_401(self, client, store):
        resp = client.raw().get("/api/decisions")
        assert resp.status_code == 401

    def test_viewer_cannot_create(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client, "viewer")
        resp = client.raw().post("/api/decisions", json=_PAYLOAD)
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"


class TestCreateAndList:
    def test_create_allocates_code(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post("/api/decisions", json=_PAYLOAD)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["codigo"].startswith("D-")
        assert body["estado"] == "vigente"

        get_resp = client.raw().get(f"/api/decisions/{body['codigo']}")
        assert get_resp.status_code == 200

    def test_get_unknown_codigo_is_404(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().get("/api/decisions/D-99")
        assert resp.status_code == 404

    def test_list_filters_by_estado(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        client.raw().post("/api/decisions", json=_PAYLOAD)
        resp = client.raw().get("/api/decisions?estado=vigente")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestSupersede:
    def test_supersede_returns_nova_and_substituida(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        first = client.raw().post("/api/decisions", json=_PAYLOAD).json()

        resp = client.raw().post(
            f"/api/decisions/{first['codigo']}/supersede",
            json={"titulo": "Usar Y", "contexto": "ctx2", "decisao": "usar Y", "motivo": "mudou"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert set(body.keys()) == {"nova", "substituida"}
        assert body["nova"]["substitui"] == first["codigo"]
        assert body["substituida"]["estado"] == "superseded"
        assert body["substituida"]["superseded_by"] == body["nova"]["codigo"]

    def test_supersede_already_superseded_is_409(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        first = client.raw().post("/api/decisions", json=_PAYLOAD).json()
        client.raw().post(
            f"/api/decisions/{first['codigo']}/supersede",
            json={"titulo": "Usar Y", "contexto": "c2", "decisao": "usar Y", "motivo": "m2"},
        )
        second = client.raw().post(
            f"/api/decisions/{first['codigo']}/supersede",
            json={"titulo": "Usar Z", "contexto": "c3", "decisao": "usar Z", "motivo": "m3"},
        )
        assert second.status_code == 409
        assert second.json()["code"] == "conflict"
