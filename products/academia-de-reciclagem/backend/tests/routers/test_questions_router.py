"""Tests for `app/routers/questions_router.py` — contract §B.3."""
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
        resp = client.raw().get("/api/questions")
        assert resp.status_code == 401


class TestCreateListAnswer:
    def test_create_defaults_to_aberta(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post(
            "/api/questions",
            json={"pergunta": "Qual regra?", "por_que_importa": "bloqueia T-001", "bloqueia": True},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["codigo"].startswith("Q-")
        assert body["estado"] == "aberta"

    def test_default_list_only_returns_open(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        client.raw().post(
            "/api/questions",
            json={"pergunta": "P1", "por_que_importa": "x", "bloqueia": False},
        )
        resp = client.raw().get("/api/questions")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_answer_returns_aviso_when_destino_kb_set(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        created = client.raw().post(
            "/api/questions",
            json={
                "pergunta": "P2", "por_que_importa": "x", "bloqueia": False,
                "destino_kb": "algum-slug",
            },
        ).json()

        resp = client.raw().post(f"/api/questions/{created['codigo']}/answer", json={"resposta": "R"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["estado"] == "respondida"
        assert body["resposta"] == "R"
        assert "algum-slug" in body["aviso"]

    def test_answer_twice_is_409(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        created = client.raw().post(
            "/api/questions",
            json={"pergunta": "P3", "por_que_importa": "x", "bloqueia": False},
        ).json()
        first = client.raw().post(f"/api/questions/{created['codigo']}/answer", json={"resposta": "R1"})
        assert first.status_code == 200
        second = client.raw().post(f"/api/questions/{created['codigo']}/answer", json={"resposta": "R2"})
        assert second.status_code == 409
        assert second.json()["code"] == "conflict"

    def test_answer_unknown_codigo_is_404(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post("/api/questions/Q-99/answer", json={"resposta": "R"})
        assert resp.status_code == 404
