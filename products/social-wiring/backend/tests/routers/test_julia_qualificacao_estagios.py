"""`GET /api/julia/qualificacao/estagios`: the stage list proxied from agents (Envio comparator uses `ordem`)."""
from __future__ import annotations

import httpx
import pytest

from app.clients.agents import (
    AgentsTimeout, AgentsTokenInvalid, AgentsUpstreamError, EstagioInfo, FakeAgentsClient, HttpAgentsClient, parse_estagios,
)
from tests.support.julia_world import ORG_ID
from noctusai_lib.testing import handler_status

URL = "/api/julia/qualificacao/estagios"


@pytest.fixture
def estagios(client):
    from app.dependencies import get_current_user_org
    from app.main import app
    from app.routers.julia_agente_router import get_agents_client_factory

    class W:
        raw = client.raw()
        agents: FakeAgentsClient | None = FakeAgentsClient()

    w = W()
    app.dependency_overrides[get_current_user_org] = lambda: (None, None, ORG_ID)
    app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: w.agents)
    yield w
    app.dependency_overrides.pop(get_current_user_org, None)
    app.dependency_overrides.pop(get_agents_client_factory, None)


def test_the_stage_list_is_proxied_with_the_agents_shape(estagios):
    estagios.agents = FakeAgentsClient(estagios=[
        EstagioInfo("qualificado", "Qualificado", 40, True), EstagioInfo("novo", "Novo", 0, False),
    ])
    r = estagios.raw.get(URL)
    assert r.status_code == 200
    assert r.json() == {"data": [
        {"chave": "novo", "rotulo": "Novo", "ordem": 0, "conclusivo": False},
        {"chave": "qualificado", "rotulo": "Qualificado", "ordem": 40, "conclusivo": True},
    ]}
    assert estagios.agents.estagios_calls == ["julia"]


def test_the_default_fake_stage_list_is_ordered(estagios):
    ordens = [e["ordem"] for e in estagios.raw.get(URL).json()["data"]]
    assert ordens == sorted(ordens) and len(ordens) > 1


@pytest.mark.parametrize("agents,status,code", [
    (None, 503, "agents_nao_configurado"),
    (FakeAgentsClient(errors={"estagios": AgentsTokenInvalid()}), 502, "agents_token_invalido"),
    (FakeAgentsClient(errors={"estagios": AgentsTimeout("boom: secret detail")}), 502, "agents_indisponivel"),
])
def test_failures_are_typed_codes_without_upstream_detail(estagios, agents, status, code):
    estagios.agents = agents
    r = estagios.raw.get(URL)
    assert handler_status(r) == status and r.json()["error"]["code"] == code
    assert "secret detail" not in r.text


def test_no_credential_is_exactly_401(client):
    assert client.raw().get(URL).status_code == 401


class TestParse:
    def test_a_bare_list_and_a_data_envelope_sort_by_ordem(self):
        itens = [{"chave": "b", "rotulo": "B", "ordem": 2, "conclusivo": True}, {"chave": "a", "ordem": 1}]
        assert [e.chave for e in parse_estagios(itens)] == ["a", "b"]
        assert parse_estagios({"data": itens})[0] == EstagioInfo("a", "a", 1, False)

    @pytest.mark.parametrize("body", [{}, "x", [{"chave": "a"}], [{"chave": "a", "ordem": True}], [{"ordem": 1}], [3]])
    def test_malformed_is_an_upstream_error(self, body):
        with pytest.raises(AgentsUpstreamError):
            parse_estagios(body)


@pytest.mark.asyncio
async def test_the_http_client_calls_the_agents_path_and_parses():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json=[{"chave": "novo", "rotulo": "Novo", "ordem": 0, "conclusivo": False}])

    c = HttpAgentsClient("http://agents.test", "tok", transport=httpx.MockTransport(handler))
    out = await c.estagios("julia")
    assert seen == [("GET", "/api/channels/agents/julia/qualificacao/estagios")]
    assert out == (EstagioInfo("novo", "Novo", 0, False),)
