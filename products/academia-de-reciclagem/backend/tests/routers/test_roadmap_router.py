"""Tests for `app/routers/roadmap_router.py` — contract §B.4.

Phases have no `POST` route (§B.4 lists only `GET`/`PATCH` for
`/api/roadmap`; only the A2 importer creates them) — tests seed a phase
directly into the `FakeKnowledgeStore`'s in-memory table, exactly the
shape `app/knowledge/fake.py` builds internally.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

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


def _seed_phase(store, *, codigo="P1", estado="em-andamento", ordem=1) -> dict:
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(), "org_id": _ORG, "codigo": codigo, "titulo": f"Fase {codigo}",
        "objetivo": "objetivo", "concluida_quando": None, "estado": estado, "ordem": ordem,
        "created_at": now, "updated_at": now,
    }
    store.roadmap_phases.append(row)
    return row


class TestAuthBoundary:
    def test_unauthenticated_is_401(self, client, store):
        resp = client.raw().get("/api/roadmap")
        assert resp.status_code == 401


class TestPhases:
    def test_list_ordered_by_ordem(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        _seed_phase(store, codigo="P2", ordem=2)
        _seed_phase(store, codigo="P1", ordem=1)
        resp = client.raw().get("/api/roadmap")
        assert resp.status_code == 200
        codes = [p["codigo"] for p in resp.json()["items"]]
        assert codes == ["P1", "P2"]

    def test_patch_unknown_codigo_is_404(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().patch("/api/roadmap/P-99", json={"estado": "concluida"})
        assert resp.status_code == 404

    def test_patch_updates_estado(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        _seed_phase(store, codigo="P1")
        resp = client.raw().patch("/api/roadmap/P1", json={"estado": "concluida"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["estado"] == "concluida"


class TestTasks:
    def test_create_unknown_fase_is_422(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().post(
            "/api/tasks", json={"titulo": "T1", "fase": "P-does-not-exist"}
        )
        assert resp.status_code == 422

    def test_create_and_list_and_update(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        _seed_phase(store, codigo="P1")
        created = client.raw().post("/api/tasks", json={"titulo": "T1", "fase": "P1"})
        assert created.status_code == 201, created.text
        codigo = created.json()["codigo"]

        listed = client.raw().get("/api/tasks?fase=P1")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        updated = client.raw().patch(f"/api/tasks/{codigo}", json={"estado": "em-andamento"})
        assert updated.status_code == 200
        assert updated.json()["estado"] == "em-andamento"

    def test_update_unknown_codigo_is_404(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        resp = client.raw().patch("/api/tasks/T-999", json={"estado": "concluida"})
        assert resp.status_code == 404


class TestSessionPrep:
    def test_shape(self, client, store, set_auth):
        set_auth(_user_ctx())
        _seed_role(client)
        _seed_phase(store, codigo="P1", estado="em-andamento")
        client.raw().post("/api/tasks", json={"titulo": "T1", "fase": "P1"})
        client.raw().post(
            "/api/questions",
            json={"pergunta": "Q?", "por_que_importa": "x", "bloqueia": True},
        )
        resp = client.raw().get("/api/session-prep")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fase_atual"]["codigo"] == "P1"
        assert len(body["proximas"]) == 1
        assert body["perguntas_abertas"] == 1
        assert len(body["perguntas_bloqueantes"]) == 1
