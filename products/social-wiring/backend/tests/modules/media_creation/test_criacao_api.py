"""Criação routes: strict 401, coded refusals, org scoping of the service call, the SSE stream's 404 (S6).

The service is a DI override (``get_criacao_service``): the HTTP layer is what is under test here; the graph itself is
``test_criacao_worker``.
"""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.realtime import JobProgress

from app.dependencies import coerce_org_uuid
from fastapi import HTTPException

from app.modules.media_creation.routers.criacao import PREFIX, get_cota_admin, get_cota_db, get_criacao_service
from tests.modules.media_creation.criacao_fakes import FakeDb
from app.modules.media_creation.services.criacao_service import CriacaoError

POST = str(uuid.uuid4())
START = f"{PREFIX}/esteira/posts/{POST}/criacao"
STREAM = f"{PREFIX}/esteira/criacao/{POST}:1/progress"
POST_STREAM = f"{PREFIX}/posts/{POST}/criacao/progress"
COTA = f"{PREFIX}/criacao/cota"


class StubService:
    def __init__(self):
        self.calls: list[tuple] = []
        self.erro: CriacaoError | None = None

    async def enfileirar(self, post_id, *, org_id=None, ator_id=None, passo=None):
        self.calls.append(("reexecutar", post_id, passo, org_id) if passo else ("enfileirar", post_id, org_id, ator_id))
        if self.erro:
            raise self.erro
        return {"post_id": post_id, "rota": "reel_narrado", "rodada": 1, "passos": ["tts"], "progresso_id": f"{post_id}:1"}

    async def reexecutar(self, post_id, passo, *, org_id=None, ator_id=None):
        self.calls.append(("reexecutar", post_id, passo, org_id))
        return {"post_id": post_id, "rota": "reel_narrado", "rodada": 2, "passos": [passo], "progresso_id": f"{post_id}:2"}

    async def snapshot(self, org_id, post_id, rodada):
        self.calls.append(("snapshot", org_id, post_id, rodada))
        return JobProgress("concluido", 1.0, "concluido", "Criação concluída", True) if rodada in (1, None) else None


@pytest.fixture
def svc(client):
    s = StubService()
    client._tc.app.dependency_overrides[get_criacao_service] = lambda: s
    return s


class TestAuth:
    @pytest.mark.parametrize(
        "method,path,kw",
        [("post", START, {"json": {}}), ("post", START, {"json": {"passo": "mux"}}), ("get", STREAM, {}),
         ("get", POST_STREAM, {}), ("get", COTA, {}), ("put", COTA, {"json": {"limite_usd_mes": 20}})],
    )
    def test_unauthenticated_is_401(self, client, svc, method, path, kw):
        r = getattr(client._tc, method)(path, **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)
        assert svc.calls == []  # the service is never reached without auth


class TestStart:
    def test_start_is_202_and_scoped_to_the_callers_org_and_user(self, client, svc):
        r = client.post(START, json={})
        assert r.status_code == 202, r.text
        assert r.json()["data"]["progresso_id"] == f"{POST}:1"
        (kind, post, org, ator) = svc.calls[0]
        assert kind == "enfileirar" and post == POST and org == str(coerce_org_uuid("test-org-123")) and ator

    def test_rerun_passes_the_step(self, client, svc):
        r = client.post(START, json={"passo": "render_motion"})
        assert r.status_code == 202 and svc.calls[0][:3] == ("reexecutar", POST, "render_motion")

    @pytest.mark.parametrize("code,status", [("rota_nao_implementada", 409), ("roteiro_incompleto", 409), ("post_nao_encontrado", 404)])
    def test_refusals_carry_their_code(self, client, svc, code, status):
        svc.erro = CriacaoError(status, code, "x")
        r = client.post(START, json={})
        assert r.status_code == status and r.json()["code"] == code

    def test_unknown_body_field_is_422_and_a_non_uuid_post_is_404(self, client, svc):
        assert client.post(START, json={"passo": "mux", "extra": 1}).status_code == 422
        assert client.post(f"{PREFIX}/esteira/posts/nao-e-id/criacao", json={}).status_code == 404
        assert svc.calls == []


class TestStream:
    def test_the_stream_opens_with_the_ledger_snapshot(self, client, svc):
        r = client.get(STREAM)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert '"terminal":true' in r.text and '"status":"concluido"' in r.text
        assert svc.calls[0] == ("snapshot", str(coerce_org_uuid("test-org-123")), POST, 1)

    def test_an_unknown_rodada_or_a_malformed_id_is_404(self, client, svc):
        assert client.get(f"{PREFIX}/esteira/criacao/{POST}:9/progress").status_code == 404
        assert client.get(f"{PREFIX}/esteira/criacao/lixo/progress").status_code == 404


    def test_the_post_stream_reads_the_latest_rodada(self, client, svc):
        r = client.get(POST_STREAM)
        assert r.status_code == 200 and '"status":"concluido"' in r.text
        assert svc.calls[0][:3] == ("snapshot", str(coerce_org_uuid("test-org-123")), POST)


class CotaDb(FakeDb):
    def __init__(self):
        super().__init__()
        self.tables["cs_criacao_cotas"] = []
        self.chamadas = []

    def _rpc_cs_criacao_cota_create(self, **kw):
        self.chamadas.append(("create", kw))
        self.tables["cs_criacao_cotas"].append({"id": "c1", "org_id": kw["p_org"], "limite_usd_cents": kw["p_row"]["limite_usd_cents"]})
        return {"status": "ok"}

    def _rpc_cs_criacao_cota_transition(self, **kw):
        self.chamadas.append(("transition", kw))
        row = self.tables["cs_criacao_cotas"][0]
        if row["limite_usd_cents"] != kw["p_from"]:
            return {"status": "refused", "code": "stale_state"}
        row["limite_usd_cents"] = kw["p_to"]
        return {"status": "ok"}


class TestCota:
    @pytest.fixture
    def db(self, client):
        db = CotaDb()
        db.admin = {"ok": True}

        def checar(auth, request):
            if not db.admin["ok"]:
                raise HTTPException(status_code=403, detail="forbidden")

        app = client._tc.app
        app.dependency_overrides[get_cota_db] = lambda: db
        app.dependency_overrides[get_cota_admin] = lambda: checar  # the org-admin predicate is the seed's own (tested there)
        return db

    def test_read_returns_the_default_state_in_dollars(self, client, db):
        r = client.get(COTA)
        assert r.status_code == 200 and r.json()["data"]["limite_usd_mes"] == 15.0 and r.json()["data"]["restante_usd"] == 15.0

    def test_first_set_creates_then_every_edit_is_a_transition_with_who_from_to(self, client, db):
        assert client.put(COTA, json={"limite_usd_mes": 20}).status_code == 200
        assert client.put(COTA, json={"limite_usd_mes": 40.5}).status_code == 200
        assert [c[0] for c in db.chamadas] == ["create", "transition"]
        t = db.chamadas[1][1]
        assert (t["p_from"], t["p_to"], t["p_event_type"], t["p_actor_kind"]) == (2000, 4050, "cota_alterada", "user")
        assert t["p_actor_id"] and t["p_key"] == {"entity_id": "c1"}
        assert client.put(COTA, json={"limite_usd_mes": 40.5}).status_code == 200 and len(db.chamadas) == 2  # no change, no event

    def test_a_non_admin_is_403_and_nothing_is_written(self, client, db):
        db.admin["ok"] = False
        assert client.put(COTA, json={"limite_usd_mes": 20}).status_code == 403 and db.chamadas == []

    @pytest.mark.parametrize("corpo", [{"limite_usd_mes": -1}, {"limite_usd_mes": 1000000}, {"limite_usd_mes": 1.234}, {"x": 1}, {}])
    def test_invalid_limits_are_422(self, client, db, corpo):
        assert client.put(COTA, json=corpo).status_code == 422 and db.chamadas == []
