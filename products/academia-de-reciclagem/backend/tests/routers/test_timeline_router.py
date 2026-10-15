"""Tests for `app/routers/timeline_router.py` — contract §B.5."""
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
        resp = client.raw().get("/api/timeline")
        assert resp.status_code == 401


class TestCreateAndList:
    def test_create_defaults_data_to_today(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post(
            "/api/timeline", json={"titulo": "Marco", "descricao": "algo aconteceu"}
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]

    def test_create_with_explicit_data(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post(
            "/api/timeline",
            json={"titulo": "Marco 2", "descricao": "desc", "data": "2026-01-15"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"] == "2026-01-15"

    def test_list_respects_limite(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        for i in range(3):
            client.raw().post(
                "/api/timeline",
                json={"titulo": f"E{i}", "descricao": "d", "data": f"2026-01-0{i + 1}"},
            )
        resp = client.raw().get("/api/timeline?limite=2")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2
        # newest first
        assert resp.json()["items"][0]["titulo"] == "E2"


class TestJsonModeWrite:
    """Fleet sweep 2026-10-15: `TimelineEventCreate.data` is a `date`; the router
    used `payload.model_dump()` so the PG store sent a `datetime.date` as the
    `p_data` RPC param -> supabase-py `Object of type date is not JSON
    serializable` (live 502 shape, orbity). Router -> REAL `PgKnowledgeStore`
    -> MockSupabase; the mock's `rpc` does not encode, so the test does."""

    def test_pg_store_rpc_params_are_json_serializable(self, client, set_auth):
        import json

        from app.dependencies import get_store
        from app.knowledge.pg import PgKnowledgeStore
        from app.main import app

        set_auth(_user_ctx())
        _seed_role(client)
        sb = client.mock_supabase
        sb.set_rpc_data("create_timeline_event", {
            "data": "2026-01-15", "titulo": "Marco", "descricao": "d",
        })
        app.dependency_overrides[get_store] = lambda: PgKnowledgeStore(sb)
        try:
            resp = client.raw().post(
                "/api/timeline",
                json={"titulo": "Marco", "descricao": "d", "data": "2026-01-15"},
            )
        finally:
            app.dependency_overrides.pop(get_store, None)
        assert resp.status_code == 201, resp.text
        name, params = sb.rpc_calls[-1]
        assert name == "create_timeline_event"
        assert json.loads(json.dumps(params))["p_data"] == "2026-01-15"

    def test_fake_lists_mixed_explicit_and_default_dates(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        client.raw().post("/api/timeline", json={"titulo": "A", "descricao": "d", "data": "2020-01-01"})
        client.raw().post("/api/timeline", json={"titulo": "B", "descricao": "d"})
        resp = client.raw().get("/api/timeline")
        assert resp.status_code == 200, resp.text
        assert [i["titulo"] for i in resp.json()["items"]] == ["B", "A"]
