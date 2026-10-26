"""Org-specs seam: Http (user bearer forwarded), Fake, factory refusal, error mapping."""
from __future__ import annotations

import json

import httpx
import pytest

from noctusai_lib.integrations.agents import (
    AgentsBadRequest,
    AgentsNotConfigured,
    AgentsTokenInvalid,
    AgentsUpstreamError,
    FakeAgentsOrgSpecsClient,
    HttpAgentsOrgSpecsClient,
    OrgSpecDeclarada,
    make_agents_org_specs_client,
)

BODY = {
    "agent_key": "monica", "version_id": None, "versao": 2,
    "declaradas": [{"chave": "tom", "rotulo": "Tom", "descricao": "d", "tipo": "texto_longo", "obrigatoria": True, "exemplo": "x"}],
    "valores": [{"chave": "tom", "valor": "calmo"}], "faltando": [],
}


def _client(handler):
    return HttpAgentsOrgSpecsClient("http://agents", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_get_forwards_user_token_and_parses():
    seen = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen["auth"], seen["url"] = req.headers["authorization"], str(req.url)
        return httpx.Response(200, json=BODY)

    out = await _client(h).get_org_specs("monica", token="user-jwt")
    assert seen == {"auth": "Bearer user-jwt", "url": "http://agents/api/studio/agents/monica/specs"}
    assert out.valores == {"tom": "calmo"} and out.declaradas[0].tipo == "texto_longo" and out.versao == 2


@pytest.mark.asyncio
async def test_put_sends_valores_and_maps_422_with_conflitos():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.method == "PUT" and json.loads(req.read()) == {"valores": {"tom": "x"}}
        return httpx.Response(422, json={"detail": {"detail": "tom: conflita", "code": "spec_conflita_com_regra_fixa", "conflitos": ["opt_out"]}})

    with pytest.raises(AgentsBadRequest) as ei:
        await _client(h).put_org_specs("monica", {"tom": "x"}, token="t")
    assert ei.value.code == "spec_conflita_com_regra_fixa" and ei.value.fields == {"conflitos": ["opt_out"]}


@pytest.mark.asyncio
async def test_403_is_token_invalid_and_malformed_is_upstream():
    with pytest.raises(AgentsTokenInvalid):
        await _client(lambda r: httpx.Response(403, json={"detail": "forbidden"})).get_org_specs("m", token="t")
    with pytest.raises(AgentsUpstreamError):
        await _client(lambda r: httpx.Response(200, json={"nope": 1})).get_org_specs("m", token="t")


@pytest.mark.asyncio
async def test_missing_token_never_sends():
    with pytest.raises(ValueError):
        await _client(lambda r: httpx.Response(200, json=BODY)).get_org_specs("m", token="")


def test_factory_refuses_without_url_unless_fake_opted_in():
    with pytest.raises(AgentsNotConfigured):
        make_agents_org_specs_client(base_url=None)
    assert isinstance(make_agents_org_specs_client(base_url=None, allow_fake=True), FakeAgentsOrgSpecsClient)
    assert isinstance(make_agents_org_specs_client(base_url="http://a"), HttpAgentsOrgSpecsClient)


@pytest.mark.asyncio
async def test_fake_roundtrip_and_faltando():
    f = FakeAgentsOrgSpecsClient((OrgSpecDeclarada("tom", "Tom"),))
    assert (await f.get_org_specs("m", token="t")).faltando == ("tom",)
    out = await f.put_org_specs("m", {"tom": "ok"}, token="t")
    assert out.faltando == () and out.valores == {"tom": "ok"}
    with pytest.raises(AgentsBadRequest):
        await f.put_org_specs("m", {"outro": "x"}, token="t")
