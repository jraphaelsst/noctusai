"""The one-time knowledge backfill (`app.jobs.julia_conhecimento_backfill`): dry-run by default, idempotent, and it never
prints the knowledge text. The agents side is an `httpx.MockTransport` (the external boundary)."""
from __future__ import annotations

import json

import httpx
import pytest

from app.jobs import julia_conhecimento_backfill as job
from app.services import julia_conhecimento_service as conhecimento
from tests.support.julia_world import ORG_ID, World

pytestmark = pytest.mark.asyncio

URL = "https://agents.example.test"
SPEC = "conhecimento"


class Agents:
    """A tiny agents: GET/PUT of the org's specs, recording every call."""

    def __init__(self, valor: str | None = None, put_status: int = 200):
        self.valor, self.put_status = valor, put_status
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        assert request.headers["authorization"] == "Bearer admin-jwt"
        if request.method == "GET":
            vals = [{"chave": SPEC, "valor": self.valor, "updated_at": "x"}] if self.valor is not None else []
            return httpx.Response(200, json={"agent_key": "julia", "valores": vals, "declaradas": [], "faltando": []})
        if self.put_status >= 400:
            return httpx.Response(self.put_status, json={"detail": {"detail": "conteúdo secreto do org", "code": "spec_nao_declarada"}})
        self.valor = body["valores"][SPEC]
        return httpx.Response(200, json={"agent_key": "julia", "valores": [], "declaradas": [], "faltando": []})

    @property
    def writes(self) -> list:
        return [c for c in self.calls if c[0] == "PUT"]


@pytest.fixture
def world() -> World:
    w = World()
    w.sw.set_table_data(conhecimento.TABLE, [
        {"org_id": ORG_ID, "secao": "politicas", "dados": {"assinatura": "digital", "chaves": "acompanhado"}, "versao": 1,
         "updated_at": "2026-10-01T00:00:00+00:00"},
    ])
    return w


def _transport(a: Agents) -> httpx.MockTransport:
    return httpx.MockTransport(a)


async def _run(world: World, agents: Agents, **kw) -> job.BackfillResult:
    return await job.executar(world.sw, ORG_ID, agents_url=URL, token=kw.pop("token", "admin-jwt"), transport=_transport(agents), **kw)


async def test_dry_run_is_the_default_and_writes_nothing(world):
    a = Agents()
    r = await _run(world, a)
    assert (r.status, r.applied, r.secoes) == ("planned", False, 1) and r.chars > 0
    assert a.writes == []


async def test_apply_writes_the_rendered_text_as_the_org_spec(world):
    a = Agents()
    r = await _run(world, a, apply=True)
    assert (r.status, r.applied) == ("updated", True)
    (call,) = a.writes
    assert call[1] == "/api/studio/agents/julia/specs"
    texto = call[2]["valores"][SPEC]
    assert texto == conhecimento.render_md(world.sw, ORG_ID).strip() and len(texto) == r.chars


async def test_it_is_idempotent(world):
    a = Agents()
    await _run(world, a, apply=True)
    r = await _run(world, a, apply=True)
    assert r.status == "unchanged" and len(a.writes) == 1


async def test_keep_existing_never_overwrites_what_the_owner_edited_in_agents(world):
    a = Agents(valor="texto editado no agents")
    r = await _run(world, a, apply=True, keep_existing=True)
    assert r.status == "skipped_existing" and a.writes == [] and r.chars_no_agents == len("texto editado no agents")


async def test_without_keep_existing_it_overwrites(world):
    a = Agents(valor="antigo")
    assert (await _run(world, a, apply=True)).status == "updated"


async def test_no_stored_knowledge_is_not_an_error(world):
    world.sw.set_table_data(conhecimento.TABLE, [])
    a = Agents()
    r = await _run(world, a, apply=True)
    assert r.status == "sem_conhecimento" and a.calls == []


async def test_apply_without_a_token_refuses(world):
    a = Agents()
    r = await _run(world, a, apply=True, token=None)
    assert (r.status, r.erro) == ("error", "token_ausente") and a.calls == []


async def test_dry_run_without_a_token_still_plans_from_the_sw_side(world):
    r = await _run(world, Agents(), token=None)
    assert r.status == "planned" and r.chars > 0


async def test_an_agents_refusal_reports_the_code_only_never_the_body(world):
    r = await _run(world, Agents(put_status=422), apply=True)
    assert r.status == "error" and r.erro == "http_422:spec_nao_declarada"
    assert "secreto" not in json.dumps(r.as_dict())


async def test_a_network_failure_is_an_error_result_not_an_exception(world):
    def boom(_request):
        raise httpx.ConnectError("down")

    r = await job.executar(world.sw, ORG_ID, agents_url=URL, token="admin-jwt", transport=httpx.MockTransport(boom), apply=True)
    assert r.status == "error" and r.erro.startswith("rede:")


async def test_the_result_never_carries_the_text(world):
    r = await _run(world, Agents(), apply=True)
    blob = json.dumps(r.as_dict(), ensure_ascii=False)
    assert conhecimento.render_md(world.sw, ORG_ID).strip()[:40] not in blob
    assert set(r.as_dict()) == {"org_id", "agent_key", "spec_chave", "status", "secoes", "chars", "sha12", "chars_no_agents", "erro", "applied"}
