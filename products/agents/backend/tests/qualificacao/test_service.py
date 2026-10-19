"""The qualification service: registrar_perfil / registrar_evento_imovel /
avaliar / pode_concluir / LGPD, over the Fake stores. Refusals are typed codes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.qualificacao.service import ItemPerfil, VersaoNaoUtilizavel
from app.stores.errors import NotFound
from tests.qualificacao.harness import AGENTE, LEAD, ORG, OUTRA_ORG, montar_servico


def perfil(svc, vid, itens, msgs, **kw):
    return svc.registrar_perfil(ORG, LEAD, agent_id=AGENTE, versao_id=vid, itens=itens, mensagens_lead=msgs, **kw)


def test_avaliar_of_a_new_lead_is_novo():
    svc, _, _, vid = montar_servico()
    p = svc.avaliar(ORG, LEAD, vid).avaliar_payload()
    assert p["estagio"] == "novo" and p["score"] == 0 and p["proximo_criterio"]["chave"] == "operacao"


def test_registrar_perfil_appends_recomputes_and_caches():
    svc, _, leads, vid = montar_servico()
    r = perfil(svc, vid, [ItemPerfil("operacao", "compra", "quero comprar")], ["Oi, quero comprar uma casa"])
    assert r.ok and r.aceitos == ("operacao",) and not r.recusados
    assert r.estado.estagio == "em_conversa" and r.estado.score == 10
    [reg] = leads.listar_registros(ORG, LEAD)
    assert (reg.criterio_chave, reg.valor, reg.fonte, reg.trecho, reg.agent_id, reg.versao_id) == (
        "operacao", "compra", "lead_informou", "quero comprar", AGENTE, vid)
    cache = leads.obter_estado(ORG, LEAD)
    assert (cache.estagio, cache.score, cache.hash) == ("em_conversa", 10, r.estado.hash)
    assert r.to_payload()["avaliacao"]["estagio"] == "em_conversa"


def test_trecho_must_be_the_leads_own_words():
    svc, _, leads, vid = montar_servico()
    r = perfil(svc, vid, [ItemPerfil("operacao", "compra", "ele quer comprar")], ["oi, bom dia"])
    assert not r.ok and [(x.criterio, x.codigo) for x in r.recusados] == [("operacao", "trecho_nao_confere")]
    assert leads.listar_registros(ORG, LEAD) == []


def test_missing_trecho_is_refused_for_lead_informou():
    svc, _, _, vid = montar_servico()
    r = perfil(svc, vid, [ItemPerfil("operacao", "compra", None)], ["quero comprar"])
    assert r.recusados[0].codigo == "trecho_ausente"


def test_migracao_and_humano_need_no_trecho():
    svc, _, leads, vid = montar_servico()
    for fonte in ("migracao", "humano"):
        r = perfil(svc, vid, [ItemPerfil("operacao", "compra")], [], fonte=fonte)
        assert r.ok, fonte
    assert {x.fonte for x in leads.listar_registros(ORG, LEAD)} == {"migracao"}  # the 2nd, same value, was unchanged
    r = perfil(svc, vid, [ItemPerfil("tipo_imovel", "casa", "x" * 200)], [], fonte="migracao")
    assert r.recusados[0].codigo == "trecho_longo"


def test_refusal_codes_per_item_and_accepted_items_still_land():
    svc, _, leads, vid = montar_servico()
    msgs = ["quero comprar casa no centro, tenho 400 mil"]
    r = perfil(svc, vid, [
        ItemPerfil("operacao", "compra", "quero comprar"),
        ItemPerfil("fantasma", "x", "centro"),
        ItemPerfil("profissao", "medica", "centro"),
        ItemPerfil("deseja_visitar", True, "centro"),
        ItemPerfil("tipo_imovel", "castelo", "casa"),
        ItemPerfil("quartos_min", "dois", "casa"),
        ItemPerfil("operacao", "aluguel", "comprar"),
    ], msgs)
    assert not r.ok
    assert {(x.criterio, x.codigo) for x in r.recusados} == {
        ("fantasma", "criterio_desconhecido"), ("profissao", "nao_coletar"),
        ("deseja_visitar", "criterio_derivado"), ("tipo_imovel", "opcao_invalida"),
        ("quartos_min", "valor_invalido"), ("operacao", "criterio_repetido"),
    }
    assert r.aceitos == ("operacao",)
    assert [x.criterio_chave for x in leads.listar_registros(ORG, LEAD)] == ["operacao"]


def test_batch_limits_and_empty():
    svc, _, _, vid = montar_servico()
    assert perfil(svc, vid, [], ["x"]).codigo == "sem_itens"
    onze = [ItemPerfil("operacao", "compra", "x")] * 11
    assert perfil(svc, vid, onze, ["x"]).codigo == "itens_demais"
    assert perfil(svc, vid, [ItemPerfil("operacao", "compra", "compra")], ["compra"], fonte="inventada").codigo == "fonte_invalida"


def test_same_value_is_unchanged_not_appended():
    svc, _, leads, vid = montar_servico()
    it = [ItemPerfil("operacao", "compra", "comprar")]
    perfil(svc, vid, it, ["quero comprar"])
    r = perfil(svc, vid, it, ["quero comprar"])
    assert r.ok and r.inalterados == ("operacao",) and r.aceitos == ()
    assert len(leads.listar_registros(ORG, LEAD)) == 1


def test_changing_an_answer_appends_and_the_latest_wins():
    svc, _, leads, vid = montar_servico()
    perfil(svc, vid, [ItemPerfil("prazo_decisao", "6_12m", "ano que vem")], ["ano que vem"])
    r = perfil(svc, vid, [ItemPerfil("prazo_decisao", "imediato", "preciso agora")], ["preciso agora"])
    assert r.estado.valores["prazo_decisao"] == "imediato"
    assert len(leads.listar_registros(ORG, LEAD)) == 2  # history kept


def test_leads_are_org_scoped():
    svc, _, _, vid = montar_servico()
    perfil(svc, vid, [ItemPerfil("operacao", "compra", "comprar")], ["comprar"])
    assert svc.avaliar(OUTRA_ORG, LEAD, vid).estagio == "novo"


def test_a_draft_version_is_not_a_legal_pin():
    svc, padroes, _, vid = montar_servico()
    padrao = padroes.obter_padrao("imob-lead")
    rasc = padroes.criar_rascunho(padrao.id, None, vid)
    with pytest.raises(VersaoNaoUtilizavel):
        svc.avaliar(ORG, LEAD, rasc)
    assert perfil(svc, rasc, [ItemPerfil("operacao", "compra", "comprar")], ["comprar"]).codigo == "versao_nao_publicada"
    with pytest.raises(NotFound):
        from uuid import uuid4
        svc.avaliar(ORG, LEAD, uuid4())


def test_an_archived_pinned_version_still_evaluates():
    svc, padroes, _, vid = montar_servico()
    padrao = padroes.obter_padrao("imob-lead")
    novo = padroes.criar_rascunho(padrao.id, None, vid)
    padroes.publicar(novo, AGENTE)
    assert padroes.obter_versao(vid).status == "arquivada"
    assert svc.avaliar(ORG, LEAD, vid).estagio == "novo"


# ── imovel events ───────────────────────────────────────────────────────────

def evento(svc, vid, codigo, ev, **kw):
    return svc.registrar_evento_imovel(ORG, LEAD, agent_id=AGENTE, versao_id=vid, codigo_imovel=codigo, evento=ev, **kw)


def test_reaction_to_a_never_offered_code_is_refused():
    svc, _, _, vid = montar_servico()
    assert evento(svc, vid, "AP1", "gostou").codigo == "imovel_nao_oferecido"


def test_offer_then_react_and_no_reoffer():
    svc, _, leads, vid = montar_servico()
    assert evento(svc, vid, "AP1", "oferecido", lote=1).ok
    assert evento(svc, vid, "AP1", "oferecido", lote=2).codigo == "imovel_ja_oferecido"
    r = evento(svc, vid, "AP1", "gostou")
    assert r.ok and r.estado.valores["imoveis_gostou"] == 1
    assert evento(svc, vid, "AP1", "gostou").inalterado
    assert svc.codigos_oferecidos(ORG, LEAD) == ["AP1"]
    assert len(leads.listar_eventos(ORG, LEAD)) == 2


def test_pedido_lead_offer_is_idempotent():
    svc, _, leads, vid = montar_servico()
    assert evento(svc, vid, "AP9", "oferecido", origem="pedido_lead").ok
    assert evento(svc, vid, "AP9", "oferecido", origem="pedido_lead").inalterado
    assert len(leads.listar_eventos(ORG, LEAD)) == 1


@pytest.mark.parametrize("kw,codigo", [
    ({"evento": "casou"}, "evento_invalido"),
    ({"evento": "oferecido", "origem": "sorteio"}, "origem_invalida"),
    ({"evento": "oferecido", "codigo_imovel": "  "}, "codigo_invalido"),
    ({"evento": "oferecido", "motivo": "x" * 201}, "motivo_longo"),
    ({"evento": "oferecido", "lote": 0}, "lote_invalido"),
])
def test_event_validation_codes(kw, codigo):
    svc, _, _, vid = montar_servico()
    args = {"codigo_imovel": "AP1", **kw}
    r = svc.registrar_evento_imovel(ORG, LEAD, agent_id=AGENTE, versao_id=vid, **args)
    assert not r.ok and r.codigo == codigo


def test_proximo_lote_counts_offer_lotes():
    svc, _, _, vid = montar_servico()
    assert svc.proximo_lote(ORG, LEAD) == 1
    for c in ("A", "B", "C"):
        evento(svc, vid, c, "oferecido", lote=1)
    assert svc.proximo_lote(ORG, LEAD) == 2


def test_opening_scenario_ends_pronto_and_concluir_is_code_gated():
    svc, _, _, vid = montar_servico()
    assert svc.pode_concluir(ORG, LEAD, vid).codigo == "estagio_nao_conclusivo"
    msgs = ["quero comprar uma casa no centro, ate 500 mil, pago com financiamento e preciso fechar em 2 meses"]
    r = perfil(svc, vid, [
        ItemPerfil("operacao", "compra", "quero comprar"), ItemPerfil("tipo_imovel", "casa", "uma casa"),
        ItemPerfil("faixa_preco", {"max": 500000}, "ate 500 mil"), ItemPerfil("regioes", ["centro"], "no centro"),
        ItemPerfil("prazo_decisao", "ate_3m", "2 meses"), ItemPerfil("forma_pagamento", "financiamento", "financiamento"),
    ], msgs)
    assert r.ok and r.estado.estagio == "qualificado"
    assert svc.pode_concluir(ORG, LEAD, vid).codigo == "estagio_nao_conclusivo"
    for c in ("AP1", "AP2"):
        evento(svc, vid, c, "oferecido", lote=1)
    evento(svc, vid, "AP1", "nao_gostou")
    evento(svc, vid, "AP2", "gostou")
    evento(svc, vid, "AP2", "quer_visitar")
    c = svc.pode_concluir(ORG, LEAD, vid)
    assert c.ok and c.estagio == "pronto_para_corretor"
    assert c.lead_pronto["imoveis_gostou"] == ["AP2"] and c.lead_pronto["intencoes_visita"] == ["AP2"]
    assert c.lead_pronto["valores"]["operacao"] == "compra"
    assert svc.avaliar(ORG, LEAD, vid).pode_concluir


def test_obter_qualificacao():
    svc, _, _, vid = montar_servico()
    assert svc.obter_qualificacao(ORG, LEAD) is None
    perfil(svc, vid, [ItemPerfil("operacao", "compra", "comprar")], ["comprar"])
    evento(svc, vid, "AP1", "oferecido")
    q = svc.obter_qualificacao(ORG, LEAD)
    assert q.versao_id == vid and q.estado.estagio == "em_conversa" and len(q.eventos) == 1
    assert svc.obter_qualificacao(OUTRA_ORG, LEAD) is None


# ── LGPD ────────────────────────────────────────────────────────────────────

def test_apagar_por_lead_erases_everything_and_is_idempotent_and_org_scoped():
    svc, _, leads, vid = montar_servico()
    perfil(svc, vid, [ItemPerfil("operacao", "compra", "comprar")], ["comprar"])
    evento(svc, vid, "AP1", "oferecido")
    assert svc.apagar_por_lead(OUTRA_ORG, LEAD) == 0
    assert leads.listar_registros(ORG, LEAD)
    assert svc.apagar_por_lead(ORG, LEAD) == 3  # 1 registro + 1 evento + estado
    assert leads.listar_registros(ORG, LEAD) == [] and leads.listar_eventos(ORG, LEAD) == []
    assert leads.obter_estado(ORG, LEAD) is None
    assert svc.apagar_por_lead(ORG, LEAD) == 0


def test_purgar_inativos_erases_whole_leads_not_rows():
    svc, _, leads, vid = montar_servico()
    perfil(svc, vid, [ItemPerfil("operacao", "compra", "comprar")], ["comprar"])
    futuro = datetime.now(timezone.utc) + timedelta(days=181)
    assert svc.purgar_inativos(datetime.now(timezone.utc) - timedelta(days=180)) == 0
    assert svc.purgar_inativos(futuro) == 2
    assert leads.listar_registros(ORG, LEAD) == []
