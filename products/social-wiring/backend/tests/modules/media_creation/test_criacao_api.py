"""Criação routes: strict 401, coded refusals, org scoping of the service call, the SSE stream's 404 (S6).

The service is a DI override (``get_criacao_service``): the HTTP layer is what is under test here; the graph itself is
``test_criacao_worker``.
"""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.realtime import JobProgress

from app.dependencies import coerce_org_uuid
from app.modules.media_creation.routers.criacao import PREFIX, get_criacao_service
from app.modules.media_creation.services.criacao_service import CriacaoError

POST = str(uuid.uuid4())
START = f"{PREFIX}/posts/{POST}/criacao"
STREAM = f"{PREFIX}/criacao/{POST}:1/progress"


class StubService:
    def __init__(self):
        self.calls: list[tuple] = []
        self.erro: CriacaoError | None = None

    async def enfileirar(self, post_id, *, org_id=None, ator_id=None):
        self.calls.append(("enfileirar", post_id, org_id, ator_id))
        if self.erro:
            raise self.erro
        return {"post_id": post_id, "rota": "reel_narrado", "rodada": 1, "passos": ["tts"], "progresso_id": f"{post_id}:1"}

    async def reexecutar(self, post_id, passo, *, org_id=None, ator_id=None):
        self.calls.append(("reexecutar", post_id, passo, org_id))
        return {"post_id": post_id, "rota": "reel_narrado", "rodada": 2, "passos": [passo], "progresso_id": f"{post_id}:2"}

    async def snapshot(self, org_id, post_id, rodada):
        self.calls.append(("snapshot", org_id, post_id, rodada))
        return JobProgress("concluido", 1.0, "concluido", "Criação concluída", True) if rodada == 1 else None


@pytest.fixture
def svc(client):
    s = StubService()
    client._tc.app.dependency_overrides[get_criacao_service] = lambda: s
    return s


class TestAuth:
    @pytest.mark.parametrize(
        "method,path,kw",
        [("post", START, {"json": {}}), ("post", START, {"json": {"passo": "mux"}}), ("get", STREAM, {})],
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
        assert client.post(f"{PREFIX}/posts/nao-e-id/criacao", json={}).status_code == 404
        assert svc.calls == []


class TestStream:
    def test_the_stream_opens_with_the_ledger_snapshot(self, client, svc):
        r = client.get(STREAM)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert '"terminal":true' in r.text and '"status":"concluido"' in r.text
        assert svc.calls[0] == ("snapshot", str(coerce_org_uuid("test-org-123")), POST, 1)

    def test_an_unknown_rodada_or_a_malformed_id_is_404(self, client, svc):
        assert client.get(f"{PREFIX}/criacao/{POST}:9/progress").status_code == 404
        assert client.get(f"{PREFIX}/criacao/lixo/progress").status_code == 404
