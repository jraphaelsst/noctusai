"""Vista-vs-ours divergences (TRANSITIONAL, `vista_divergencias`): detection through the REAL sync, normalisation, dedupe /
supersede, the human-only rule (the auto resolver skips `vista_sync`), the flag, the drift note, and the ONE digest per run.
FakeVistaAdapter + MockSupabaseClient; synthetic data."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from uuid import uuid4

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.testing import MockSupabaseClient

from app.services import divergencia_resolucao, vista_divergencias as div
from app.services.imoveis_service import ImovelSyncService
from tests.services.test_imoveis_sync_detalhes import _Db, _db as _db_base, _linha, _reg

ORG = uuid4()
OUTRA = uuid4()
DONO = "00000000-0000-4000-8000-0000000000d1"


def _db(*, ativa=True, destino=DONO, captacao=(), dados=(), proprietarios=(), mensagens=()):
    db = _db_base(mirror=[_linha("CA0001", org=ORG, valor_venda=900000.0)], registry=[_reg("CA0001", org=ORG)])
    # the helper above seeds with its own ORG: re-key to ours
    for t in ("imoveis", "imovel_registry"):
        db.set_table_data(t, [{**r, "org_id": str(ORG)} for r in db.table(t).select("*").execute().data])
    db.set_table_data("vista_divergencias_config", [{"org_id": str(ORG), "ativa": ativa, "destino_user_id": destino}] if ativa is not None else [])
    db.set_table_data("imovel_captacao", [{"org_id": str(ORG), "codigo_canonical": "CA0001", **r} for r in captacao])
    db.set_table_data("imovel_dados", [{"org_id": str(ORG), "codigo": "CA0001", **r} for r in dados])
    db.set_table_data("julia_proprietarios_contatos", [{"org_id": str(ORG), "imovel_codigo": "CA0001", **r} for r in proprietarios])
    db.set_table_data("conversation_messages", [{"org_id": str(ORG), **r} for r in mensagens])
    return db


def _vista(**kw):
    a = FakeVistaAdapter()
    a.add_imovel(Imovel(codigo="CA0001", status="Venda", valor_venda=900000.0, data_atualizacao=date(2026, 11, 2), exibir_no_site=True, **kw))
    return a


def _sync(db, adapter):
    svc = ImovelSyncService(db, adapter, duplicate_detector=lambda *a, **k: None)
    rep = asyncio.run(svc.sync_detalhes(ORG, escopo="todos", descobrir=False, forcar=True))
    return rep


def _conflitos(db, **filtro):
    rows = db.table("imovel_campo_conflitos").select("*").execute().data
    return [r for r in rows if all(r.get(k) == v for k, v in filtro.items())]


# ─── detection ─────────────────────────────────────────────────────────────


def test_a_real_difference_opens_a_pending_vista_sync_row_with_the_drift_note_and_never_touches_ours():
    db = _db(captacao=[{"valor_venda": 777000.0, "updated_at": "2026-10-20T10:00:00+00:00", "updated_por": "u-captador"}])
    rep = _sync(db, _vista())
    [c] = _conflitos(db, campo="valor_venda")
    assert c["status"] == "pendente" and c["origem_proposto"] == "vista_sync" and c["origem_anterior"] == "captacao_manual"
    assert c["valor_anterior"] == 777000.0 and c["valor_proposto"] == 900000.0 and c["codigo"] == "CA0001"
    n = c["notas"]
    assert n["vista"]["valor"] == 900000.0 and n["vista"]["definido_em"] == "2026-11-02"
    assert n["nosso"]["valor"] == 777000.0 and n["nosso"]["definido_em"] == "2026-10-20T10:00:00+00:00" and n["nosso"]["por"] == "u-captador"
    assert n["nosso"]["origem_rotulo"] == "captação manual" and n["links"]["vista_codigo"] == "CA0001" and n["links"]["sistema"] == "/imoveis/CA0001"
    assert db.table("imovel_captacao").select("*").execute().data[0]["valor_venda"] == 777000.0  # NEVER overwritten
    assert [r["codigo"] for r in rep.divergencias_linhas] == ["CA0001"] and rep.as_dict()["divergencias_novas"] == 1


@pytest.mark.parametrize("nosso,vista", [
    ({"valor_venda": 900000.00}, {}),                                   # money, same value
    ({"valor_venda": "900000"}, {}),
    ({"dormitorios": 3, "vagas": 2}, {"dormitorios": 3, "vagas": 2}),
])
def test_equal_numbers_are_never_a_divergence(nosso, vista):
    db = _db(captacao=[nosso])
    _sync(db, _vista(**vista))
    assert _conflitos(db) == []


def test_formatting_noise_in_text_is_ignored():
    db = _db(dados=[{"endereco_manual_bairro": "  GRANJA   Viânà ", "endereco_manual_cep": "06.700-000", "endereco_manual_uf": "sp",
                     "empreendimento_manual": "Condomínio  Águas"}])
    _sync(db, _vista(bairro="granja viana", cep="06700000", uf="SP", empreendimento="Condominio Aguas"))
    assert _conflitos(db) == []


def test_a_side_that_is_empty_is_not_a_divergence():
    db = _db(captacao=[{"valor_venda": None, "valor_iptu": 500.0}])  # ours has no price; Vista has no IPTU
    _sync(db, _vista())
    assert _conflitos(db) == []


def test_address_and_empreendimento_overrides_are_compared():
    db = _db(dados=[{"endereco_manual_logradouro": "Rua Nossa", "empreendimento_manual": "Cond Nosso", "updated_at": "2026-10-01T00:00:00+00:00",
                     "endereco_manual_confirmado_por": "u1", "endereco_manual_confirmado_em": "2026-10-02T00:00:00+00:00"}])
    _sync(db, _vista(logradouro="Rua Deles", empreendimento="Cond Deles"))
    campos = {c["campo"]: c for c in _conflitos(db)}
    assert set(campos) == {"logradouro", "empreendimento"} and campos["logradouro"]["origem_anterior"] == "imovel_dados_manual"
    assert campos["logradouro"]["notas"]["nosso"]["definido_em"] == "2026-10-02T00:00:00+00:00" and campos["logradouro"]["notas"]["nosso"]["por"] == "u1"


# ─── dedupe / supersede / decided ───────────────────────────────────────────


def test_the_same_pair_never_registers_twice():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    _sync(db, _vista())
    segunda = _sync(db, _vista())
    assert len(_conflitos(db, status="pendente")) == 1 and segunda.divergencias_linhas == []


def test_a_changed_vista_value_supersedes_the_old_pending_row():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    _sync(db, _vista())
    outra = FakeVistaAdapter()
    outra.add_imovel(Imovel(codigo="CA0001", status="Venda", valor_venda=950000.0, data_atualizacao=date(2026, 11, 3), exibir_no_site=True))
    _sync(db, outra)
    [pendente] = _conflitos(db, status="pendente")
    [velha] = _conflitos(db, status="rejeitado")
    assert pendente["valor_proposto"] == 950000.0 and velha["valor_proposto"] == 900000.0 and velha["decidido_por"] is None


def test_a_changed_our_value_with_the_same_vista_value_reopens_the_question():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    _sync(db, _vista())
    db.table("imovel_captacao").update({"valor_venda": 800000.0}).eq("codigo_canonical", "CA0001").execute()
    _sync(db, _vista())
    [pendente] = _conflitos(db, status="pendente")
    assert pendente["valor_anterior"] == 800000.0 and len(_conflitos(db, status="rejeitado")) == 1


def test_a_pair_a_human_decided_never_alerts_again_but_a_new_pair_does():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    _sync(db, _vista())
    [c] = _conflitos(db)
    div.resolver(db, None, ORG, "CA0001", c["id"], "nosso", None, DONO)
    again = _sync(db, _vista())
    assert again.divergencias_linhas == [] and len(_conflitos(db)) == 1
    db.table("imovel_captacao").update({"valor_venda": 123000.0}).eq("codigo_canonical", "CA0001").execute()
    assert len(_sync(db, _vista()).divergencias_linhas) == 1


def test_an_extraction_conflict_on_the_same_field_is_left_alone():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    db.set_table_data("imovel_campo_conflitos", [{"id": "x1", "org_id": str(ORG), "codigo": "CA0001", "campo": "valor_venda", "status": "pendente",
                                                  "origem_proposto": "matricula", "valor_proposto": 1, "valor_anterior": 2}])
    _sync(db, _vista())
    assert len(_conflitos(db)) == 1 and _conflitos(db)[0]["id"] == "x1"


# ─── the flag ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ativa", [False, None])
def test_flag_off_or_no_row_means_nothing_happens(ativa):
    db = _db(ativa=ativa, captacao=[{"valor_venda": 777000.0}])
    rep = _sync(db, _vista())
    assert _conflitos(db) == [] and rep.divergencias_linhas == [] and rep.divergencias_comparadas == 0


def test_the_flag_is_per_org():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    assert div.iniciar(db, OUTRA) is None and div.iniciar(db, ORG) is not None


# ─── the owner's WhatsApp confirmation: price, availability and the conversation ────


def _proprietario(**kw):
    return {"id": "p1", "telefone": "5511988887777", "confirmado_at": "2026-11-03T12:00:00+00:00", **kw}


def test_a_confirmed_price_that_differs_from_vista_cites_the_conversation_sanitised():
    db = _db(
        proprietarios=[_proprietario(preco_confirmado=850000.0, preco_tipo_confirmado="venda")],
        mensagens=[{"chat_id": "5511988887777@c.us", "direction": "inbound", "created_at": "2026-11-03T11:59:00+00:00",
                    "body": "Pode baixar pra 850 mil, me liga no 11 98888-7777 ou veja https://exemplo.com/x"},
                   {"chat_id": "5511988887777@c.us", "direction": "inbound", "created_at": "2026-11-04T09:00:00+00:00", "body": "mais nova, depois"}],
    )
    _sync(db, _vista())
    [c] = _conflitos(db, campo="valor_venda")
    conversa = c["notas"]["nosso"]["conversa"]
    assert c["origem_anterior"] == "julia_proprietario" and c["valor_anterior"] == 850000.0
    assert conversa["proprietario_contato_id"] == "p1" and conversa["telefone_final"] == "7777"
    assert conversa["trecho"] == "Pode baixar pra 850 mil, me liga no [telefone] ou veja [link]"  # the one BEFORE the confirmation, sanitised
    assert "11988887777" not in str(c["notas"])


def test_the_conversation_origin_carries_the_julia_contato_for_the_link():
    db = _db(proprietarios=[_proprietario(preco_confirmado=850000.0, preco_tipo_confirmado="venda")],
             mensagens=[{"chat_id": "5511988887777@c.us", "direction": "inbound", "created_at": "2026-11-03T11:59:00+00:00", "body": "pode ser 850"}])
    db.set_table_data("julia_contatos", [{"id": "jc-1", "org_id": str(ORG), "chat_id": "5511988887777@c.us"}])
    _sync(db, _vista())
    [c] = _conflitos(db, campo="valor_venda")
    api = div.para_api(c, {})
    assert api["origem"] == {"tipo": "julia", "contato_id": "jc-1", "thread_id": "5511988887777@c.us", "trecho": "pode ser 850"}


def test_the_valuation_areas_of_imovel_dados_are_compared_with_the_same_column_names():
    db = _db(dados=[{"area_terreno_m2": 500.0, "area_construida_m2": 200.0, "avaliacao_campos_atualizado_em": "2026-10-10T00:00:00+00:00",
                     "avaliacao_campos_atualizado_por": "u9"}])
    _sync(db, _vista(area_terreno=450.0, area_construida=200.0))
    [c] = _conflitos(db)
    assert (c["campo"], c["valor_anterior"], c["valor_proposto"], c["origem_anterior"]) == ("area_terreno_m2", 500.0, 450.0, "imovel_dados_manual")
    assert c["notas"]["nosso"]["por"] == "u9" and c["notas"]["nosso"]["definido_em"] == "2026-10-10T00:00:00+00:00"


def test_the_api_shape_pending_and_resolved():
    db = _db(captacao=[{"valor_venda": 777000.0, "updated_at": "2026-10-20T10:00:00+00:00", "updated_por": "u-cap"}])
    _sync(db, _vista())
    [c] = _conflitos(db)
    p = div.para_api(c, {"u-cap": "Capitã"})
    assert p == {"id": c["id"], "campo": "valor_venda", "status": "pendente", "valor_vista": 900000.0, "vista_em": "2026-11-02",
                 "valor_nosso": 777000.0, "nosso_em": "2026-10-20T10:00:00+00:00", "nosso_por": {"id": "u-cap", "nome": "Capitã"},
                 "origem": {"tipo": "captacao"}}
    r = div.resolver(db, None, ORG, "CA0001", c["id"], "manual", "815.000,50", DONO)
    assert r["status"] == "resolvido" and r["resolucao"]["escolha"] == "manual" and r["resolucao"]["valor"] == "815000.5"
    assert r["resolucao"]["por"]["id"] == DONO
    lista = div.listar_do_imovel(db, None, ORG, "CA0001")["items"]
    assert [i["status"] for i in lista] == ["resolvido"]


def test_a_row_the_system_superseded_is_not_listed_as_history():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    _sync(db, _vista())
    outra = FakeVistaAdapter()
    outra.add_imovel(Imovel(codigo="CA0001", status="Venda", valor_venda=950000.0, data_atualizacao=date(2026, 11, 3), exibir_no_site=True))
    _sync(db, outra)
    itens = div.listar_do_imovel(db, None, ORG, "CA0001")["items"]
    assert len(itens) == 1 and itens[0]["status"] == "pendente" and itens[0]["valor_vista"] == 950000.0


def test_availability_confirmed_as_sold_while_vista_still_lists_it_is_a_divergence():
    db = _db(proprietarios=[_proprietario(status_confirmado="vendido")])
    _sync(db, _vista())
    [c] = _conflitos(db, campo="disponibilidade")
    assert (c["valor_anterior"], c["valor_proposto"]) == ("indisponivel", "disponivel")


def test_a_confirmation_older_than_the_vista_edit_is_not_a_divergence():
    """The existing rule (`julia_imovel_confirmado`): a Vista edit after the confirmation wins -- nothing to review."""
    db = _db(proprietarios=[_proprietario(preco_confirmado=850000.0, preco_tipo_confirmado="venda", confirmado_at="2026-10-01T12:00:00+00:00")])
    _sync(db, _vista())
    assert _conflitos(db) == []


# ─── only a human decides ───────────────────────────────────────────────────


def test_the_automatic_resolver_never_decides_a_vista_sync_proposal():
    d = divergencia_resolucao.resolver_divergencia(
        "valor_venda", valor_atual=1, origem_atual="captacao_manual", valor_proposto=2, origem_proposto="vista_sync",
        mesmo_valor=lambda c, a, b: a == b, atual_humano=False,
    )
    assert d.requer_humano is True and d.vencedor is None and d.regra == "decisao_humana"


def test_the_imovel_backfill_resolver_skips_vista_sync_rows():
    from app.modules.imovel_hub import campos_extraidos_service as campos

    db = _db(captacao=[{"valor_venda": 777000.0}])
    _sync(db, _vista())
    out = campos.backfill_resolver_conflitos_pendentes(db, ORG)
    assert out["resolvidos"] == [] and any(r["origem_proposto"] == "vista_sync" for r in out["ignorados"])
    assert _conflitos(db)[0]["status"] == "pendente"
    with pytest.raises(Exception, match="Vista"):
        campos.resolver(db, ORG, "CA0001", _conflitos(db)[0]["id"], aceitar=True, decidido_por=None)


# ─── the digest: ONE per run, to a destination USER whose phone is read from core ───────


class _Core(MockSupabaseClient):
    pass


def _core(telefone="+55 11 98888-0000", org=ORG):
    c = _Core()
    c.set_table_data("noctus_users", [{"id": DONO, "org_id": str(org), "nome": "Dono", "telefone": telefone, "org_role": "owner"},
                                      {"id": "a2", "org_id": str(org), "org_role": "admin", "telefone": None}])
    c.set_table_data("notifications", [])
    return c


class _Enviador:
    def __init__(self, erro=None):
        self.enviadas, self.erro = [], erro

    async def __call__(self, org_id, telefone, texto):
        self.enviadas.append((str(org_id), telefone, texto))
        return self.erro


def _linhas_novas(db):
    return [r for r in _conflitos(db) if r["status"] == "pendente"]


def test_one_digest_per_run_lists_every_divergence_and_uses_the_phone_from_core():
    db = _db(captacao=[{"valor_venda": 777000.0, "dormitorios": 9}])
    rep = _sync(db, _vista(dormitorios=3))
    env = _Enviador()
    via = asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=env, base_url="https://sw.test"))
    assert via == "whatsapp" and len(env.enviadas) == 1  # ONE message for two fields
    org, tel, texto = env.enviadas[0]
    assert tel == "+5511988880000" and "2 campo(s) em 1 imóvel" in texto
    assert "CA0001 · valor de venda: Vista R$ 900.000,00 × nosso R$ 777.000,00 → https://sw.test/imoveis/CA0001" in texto
    assert "dormitórios: Vista 3 × nosso 9" in texto
    assert all(r["notificado_em"] for r in _linhas_novas(db))


def test_no_new_divergence_sends_nothing():
    env = _Enviador()
    assert asyncio.run(div.enviar_digest(_db(), _core(), ORG, [], enviar=env)) == "nada" and env.enviadas == []


@pytest.mark.parametrize("destino,core_tel,motivo", [
    (None, "+5511988880000", "sem_telefone_do_destino"), (DONO, None, "sem_telefone_do_destino"), (DONO, "abc", "sem_telefone_do_destino"),
])
def test_without_a_destination_or_phone_it_is_an_in_app_notice_never_silent(destino, core_tel, motivo, caplog):
    db = _db(destino=destino, captacao=[{"valor_venda": 777000.0}])
    rep = _sync(db, _vista())
    env = _Enviador()
    core = _core(core_tel)
    with caplog.at_level(logging.WARNING):
        via = asyncio.run(div.enviar_digest(db, core, ORG, rep.divergencias_linhas, enviar=env))
    assert via == f"in_app:{motivo}" and env.enviadas == []
    assert any("in-app notice instead" in r.getMessage() for r in caplog.records)
    assert all(r["notificado_em"] for r in _linhas_novas(db))


def test_a_failed_send_falls_back_to_in_app():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    rep = _sync(db, _vista())
    via = asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=_Enviador(erro="sem_linha")))
    assert via == "in_app:falha_envio:sem_linha"


def test_the_hourly_cap_turns_the_next_digest_into_an_in_app_notice():
    db = _db(captacao=[{"valor_venda": 777000.0}])
    rep = _sync(db, _vista())
    from datetime import datetime, timezone

    agora = datetime.now(timezone.utc).isoformat()
    db.set_table_data("imovel_campo_conflitos", [
        {"id": f"old{i}", "org_id": str(ORG), "codigo": f"X{i}", "campo": "valor_venda", "status": "rejeitado", "origem_proposto": "vista_sync",
         "notificado_em": f"{agora[:-6]}.{i:06d}+00:00"} for i in range(div.DIGESTS_POR_HORA)
    ] + db.table("imovel_campo_conflitos").select("*").execute().data)
    env = _Enviador()
    via = asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=env))
    assert via == "in_app:limite_por_hora" and env.enviadas == []


def test_the_run_orchestrator_sends_exactly_one_digest_for_a_whole_run():
    from app.services import imoveis_atualizacao_service as atualizacao

    db = _db(captacao=[{"valor_venda": 777000.0, "vagas": 9}])
    env = _Enviador()

    def fabrica(client, adapter, **kw):
        return ImovelSyncService(client, adapter, duplicate_detector=lambda *a, **k: None, **kw)

    import contextlib

    @contextlib.contextmanager
    def lease(*_a, **_k):
        yield True

    db.set_table_data("imoveis_sync_execucoes", [])
    res = asyncio.run(atualizacao.executar(db, _vista(vagas=2), ORG, modo="detalhes", escopo="todos", core=_core(), sync_factory=fabrica,
                                           lease_fn=lease, enviar_divergencia=env))
    assert res["status"] == "ok" and len(env.enviadas) == 1
    [exec_row] = db.table("imoveis_sync_execucoes").select("*").execute().data
    assert exec_row["relatorio"]["divergencias_digest"] == "whatsapp" and exec_row["relatorio"]["divergencias_novas"] == 2
