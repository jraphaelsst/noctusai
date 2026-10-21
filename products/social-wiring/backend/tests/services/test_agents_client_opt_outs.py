"""`AgentsClient` opt-out history / renotify / reactivate (owner decisions 2026-10-21): the Real over an `httpx.MockTransport`
(the HTTP seam), and the Fake held to the same contract (consistent with opt_out / opt_in / consentimento)."""
from __future__ import annotations

import json

import httpx
import pytest

from app.clients.agents import (
    FakeAgentsClient, HttpAgentsClient, LeadDesconhecido, SemOptOutAtivo, parse_opt_out_pagina,
)

pytestmark = pytest.mark.asyncio

LEAD = "22222222-2222-4222-8222-222222222222"
USER = "33333333-3333-4333-8333-333333333333"
EV = {
    "id": "ev-1", "tipo": "opt_out", "lead_ref": LEAD, "lead_nome": "Ana", "lead_telefone": "+5511988887777",
    "thread_id": None, "agent_id": "a1", "agent_key": "julia", "agent_nome": "Julia", "ator_user_id": None,
    "origem": "agente", "motivo": "lead_pediu_parar", "mensagem_lead": "para", "em": "2026-10-21T12:00:00Z",
    "participantes_encerrados": 1, "notificacao_status": "falhou", "notificacao_erro": "sem destinatarios", "notificado_em": None,
}


def _client(handler) -> HttpAgentsClient:
    return HttpAgentsClient("https://agents.example.test", "pk_test", transport=httpx.MockTransport(handler))


async def test_listar_sends_the_paging_params_and_parses_the_page():
    seen = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append((r.method, r.url.path, dict(r.url.params)))
        return httpx.Response(200, json={"items": [EV], "next_cursor": "c2"})

    page = await _client(handler).listar_opt_outs(limit=25, cursor="c1", lead_ref=LEAD)
    assert seen == [("GET", "/api/channels/opt-outs", {"limit": "25", "cursor": "c1", "lead_ref": LEAD})]
    assert page.next_cursor == "c2" and page.items[0].notificacao_status == "falhou" and page.items[0].notificacao_erro
    with pytest.raises(ValueError):
        await _client(handler).listar_opt_outs(limit=101)


async def test_a_malformed_record_is_an_upstream_error_not_a_silent_drop():
    from app.clients.agents import AgentsUpstreamError

    with pytest.raises(AgentsUpstreamError):
        parse_opt_out_pagina({"items": ["x"]})


async def test_renotificar_posts_the_actor():
    seen = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append((r.method, r.url.path, json.loads(r.content)))
        return httpx.Response(200, json={**EV, "notificacao_status": "enviada", "notificacao_erro": None})

    out = await _client(handler).renotificar_opt_out("ev-1", ator_user_id=USER)
    assert seen == [("POST", "/api/channels/opt-outs/ev-1/notificar", {"ator_user_id": USER})]
    assert out.notificacao_status == "enviada"


async def test_reativar_posts_motivo_and_actor_and_maps_the_409_and_404():
    seen = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append((r.method, r.url.path, json.loads(r.content)))
        if "sem-opt" in r.url.path:
            return httpx.Response(409, json={"detail": {"detail": "x", "code": "sem_opt_out_ativo"}})
        if "desconhecido" in r.url.path:
            return httpx.Response(404, json={"detail": {"detail": "x", "code": "lead_desconhecido"}})
        return httpx.Response(200, json={
            "lead_ref": LEAD, "opt_out_ativo": False, "opt_out_em": "2026-10-21T12:00:00Z",
            "evento": {**EV, "id": "ev-2", "tipo": "reativacao", "origem": "operador", "ator_user_id": USER}})

    c = _client(handler)
    out = await c.reativar_lead(LEAD, motivo="  o lead pediu  ", ator_user_id=USER)
    assert seen[0] == ("POST", f"/api/channels/leads/{LEAD}/reativar", {"ator_user_id": USER, "motivo": "o lead pediu"})
    assert out.consent.opt_out_ativo is False and out.evento.tipo == "reativacao"
    with pytest.raises(SemOptOutAtivo):
        await c.reativar_lead("sem-opt", motivo="m", ator_user_id=USER)
    with pytest.raises(LeadDesconhecido):
        await c.reativar_lead("desconhecido", motivo="m", ator_user_id=USER)
    for ruim in ("", "   ", "x" * 501):
        with pytest.raises(ValueError):
            await c.reativar_lead(LEAD, motivo=ruim, ator_user_id=USER)


async def test_the_fake_keeps_the_history_consistent_with_opt_out_and_reactivation():
    f = FakeAgentsClient()
    with pytest.raises(LeadDesconhecido):
        await f.reativar_lead(LEAD, motivo="m", ator_user_id=USER)
    await f.opt_out(LEAD, origem="operador", motivo="ligou", ator_user_id=USER)
    [e] = (await f.listar_opt_outs()).items
    assert e.tipo == "opt_out" and e.origem == "operador" and e.ator_user_id == USER and e.motivo == "ligou"
    assert (await f.consentimento(LEAD)).opt_out_motivo == "ligou"
    out = await f.reativar_lead(LEAD, motivo="voltou", ator_user_id=USER)
    assert out.consent.opt_out_ativo is False and out.evento.tipo == "reativacao"
    assert (await f.consentimento(LEAD)).opt_out_ativo is False
    assert [x.tipo for x in (await f.listar_opt_outs()).items] == ["reativacao", "opt_out"]
    with pytest.raises(SemOptOutAtivo):
        await f.reativar_lead(LEAD, motivo="de novo", ator_user_id=USER)
    ren = await f.renotificar_opt_out(e.id, ator_user_id=USER)
    assert ren.notificacao_status == "enviada" and f.renotificacoes == [(e.id, USER)]
