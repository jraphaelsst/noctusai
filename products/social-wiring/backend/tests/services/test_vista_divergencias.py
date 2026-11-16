"""The Vista sync with HISTORY (`vista_divergencias`, owner 2026-11-04): a mirror change is written to `imovel_historico`; Vista wins
over our overlay (history `vista_prevaleceu`); an owner-confirmed price/availability is sent to Vista (switch on, PUT permitted, Julia
certain) or Vista wins and an approval opens; the in-app notices; the switch. FakeVistaAdapter + MockSupabaseClient; synthetic data.

DECISION REVERSED 2026-11-04, AMENDED 2026-11-15. The owner moved the sync to "Vista wins + history + in-app notices", then (option 1)
asked to KEEP the switchable WhatsApp digest: it now lists the APPROVALS a run opens (destination user, hourly cap, in-app fallback,
Notificações kind `vista_divergencias`)."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from uuid import uuid4

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaUpstreamError
from noctusai_lib.testing import MockSupabaseClient

from app.services import divergencia_resolucao, vista_divergencias as div
from app.services.imoveis_service import ImovelSyncService
from tests.services.test_imoveis_sync_detalhes import _Db, _db as _db_base, _linha, _reg

ORG = uuid4()
OUTRA = uuid4()
DONO = "00000000-0000-4000-8000-0000000000d1"


@pytest.fixture(autouse=True)
def _sem_cache_de_permissao():
    div._PERMISSAO.clear()
    yield
    div._PERMISSAO.clear()


def _db(*, ativa=True, escrita=False, captacao=(), dados=(), proprietarios=(), mensagens=(), espelho=None):
    db = _db_base(mirror=[_linha("CA0001", org=ORG, valor_venda=900000.0, **(espelho or {}))], registry=[_reg("CA0001", org=ORG)])
    # the helper above seeds with its own ORG: re-key to ours
    for t in ("imoveis", "imovel_registry"):
        db.set_table_data(t, [{**r, "org_id": str(ORG)} for r in db.table(t).select("*").execute().data])
    db.set_table_data("vista_divergencias_config", [{"org_id": str(ORG), "ativa": ativa, "vista_escrita_ativa": escrita}] if ativa is not None else [])
    db.set_table_data("imovel_captacao", [{"org_id": str(ORG), "codigo_canonical": "CA0001", **r} for r in captacao])
    db.set_table_data("imovel_dados", [{"org_id": str(ORG), "codigo": "CA0001", **r} for r in dados])
    db.set_table_data("julia_proprietarios_contatos", [{"org_id": str(ORG), "imovel_codigo": "CA0001", **r} for r in proprietarios])
    db.set_table_data("conversation_messages", [{"org_id": str(ORG), **r} for r in mensagens])
    db.set_table_data("imovel_historico", [])
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


def _hist(db, **filtro):
    rows = db.table("imovel_historico").select("*").execute().data
    return [r for r in rows if all(r.get(k) == v for k, v in filtro.items())]


# ─── 1. a mirror column changed: the upsert applies it AND the history says so ─────────────────────────────


def test_a_mirror_change_is_applied_and_written_to_the_history_old_to_new():
    db = _db(espelho={"dormitorios": 2, "vagas": 1})
    rep = _sync(db, _vista(dormitorios=3, vagas=1))
    assert db.table("imoveis").select("*").execute().data[0]["dormitorios"] == 3  # the mirror upsert, as before
    [h] = _hist(db)
    assert (h["acao"], h["origem"], h["campo"], h["valor_anterior"], h["valor_novo"], h["codigo_canonical"]) == (
        "campo_atualizado", "vista_sync", "dormitorios", 2, 3, "CA0001")
    assert h["org_id"] == str(ORG) and h["ator_user_id"] is None and h["ocorrido_em"]
    assert (rep.vista_imoveis_atualizados, rep.vista_campos_atualizados) == (1, 1) and rep.as_dict()["vista_campos_atualizados"] == 1


def test_prices_are_not_repeated_in_the_history_the_262_trigger_owns_them():
    db = _db()
    _sync(db, FakeVistaAdapter(imoveis={"CA0001": Imovel(codigo="CA0001", status="Venda", valor_venda=950000.0, data_atualizacao=date(2026, 11, 3), exibir_no_site=True)}))
    assert _hist(db) == []


def test_unchanged_or_emptied_fields_write_nothing_and_a_new_imovel_has_no_before():
    db = _db(espelho={"dormitorios": 2, "cidade": "Cotia"})
    _sync(db, _vista(dormitorios=2))  # same dormitorios; Vista's payload carries no cidade -> not a change
    assert _hist(db) == []
    db2 = _db()
    db2.set_table_data("imoveis", [])  # not in the mirror yet: first observation, nothing to compare with
    _sync_novo = asyncio.run(ImovelSyncService(db2, _vista(dormitorios=3), duplicate_detector=lambda *a, **k: None).sync_detalhes(
        ORG, escopo="todos", descobrir=True, descobridores=[lambda adapter, conhecidos, report: _achar()]))
    assert _hist(db2) == []


async def _achar():
    return {"CA0001": Imovel(codigo="CA0001", status="Venda", valor_venda=900000.0, data_atualizacao=date(2026, 11, 2), exibir_no_site=True, dormitorios=3)}


def test_the_listar_path_writes_the_history_too():
    db = _db(espelho={"dormitorios": 2})
    svc = ImovelSyncService(db, _vista(dormitorios=3), duplicate_detector=lambda *a, **k: None)
    asyncio.run(svc.sync(ORG, with_detalhes=False))
    assert [(h["campo"], h["valor_anterior"], h["valor_novo"]) for h in _hist(db)] == [("dormitorios", 2, 3)]


# ─── 2. an overlay field differs and is not owner-confirmed: Vista wins ────────────────────────────────


def test_vista_wins_over_a_captacao_value_and_the_history_says_so_with_no_approval():
    db = _db(captacao=[{"valor_venda": 777000.0, "updated_at": "2026-10-20T10:00:00+00:00", "updated_por": "u-captador"}])
    rep = _sync(db, _vista())
    assert db.table("imovel_captacao").select("*").execute().data[0]["valor_venda"] == 900000.0  # Vista's value is now ours
    [h] = _hist(db, acao="vista_prevaleceu")
    assert (h["campo"], h["valor_anterior"], h["valor_novo"], h["origem"]) == ("valor_venda", 777000.0, 900000.0, "vista_sync")
    assert _conflitos(db) == [] and rep.divergencias_linhas == [] and rep.vista_campos_atualizados == 1


def test_vista_wins_over_the_manual_address_and_empreendimento_by_clearing_the_override():
    db = _db(dados=[{"endereco_manual_logradouro": "Rua Nossa", "empreendimento_manual": "Cond Nosso",
                     "endereco_manual_confirmado_por": "u1", "endereco_manual_confirmado_em": "2026-10-02T00:00:00+00:00"}])
    _sync(db, _vista(logradouro="Rua Deles", empreendimento="Cond Deles"))
    d = db.table("imovel_dados").select("*").execute().data[0]
    assert d["endereco_manual_logradouro"] is None and d["empreendimento_manual"] is None
    assert {h["campo"] for h in _hist(db, acao="vista_prevaleceu")} == {"logradouro", "empreendimento"} and _conflitos(db) == []


def test_the_valuation_areas_of_imovel_dados_are_compared_with_the_same_column_names():
    db = _db(dados=[{"area_terreno_m2": 500.0, "area_construida_m2": 200.0}])
    _sync(db, _vista(area_terreno=450.0, area_construida=200.0))
    [h] = _hist(db, acao="vista_prevaleceu")
    assert (h["campo"], h["valor_anterior"], h["valor_novo"]) == ("area_terreno_m2", 500.0, 450.0)


@pytest.mark.parametrize("nosso,vista", [
    ({"valor_venda": 900000.00}, {}),                                   # money, same value
    ({"valor_venda": "900000"}, {}),
    ({"dormitorios": 3, "vagas": 2}, {"dormitorios": 3, "vagas": 2}),
])
def test_equal_numbers_are_never_a_difference(nosso, vista):
    db = _db(captacao=[nosso])
    _sync(db, _vista(**vista))
    assert _hist(db) == [] and _conflitos(db) == []


def test_formatting_noise_in_text_is_ignored():
    db = _db(dados=[{"endereco_manual_bairro": "  GRANJA   Viânà ", "endereco_manual_cep": "06.700-000", "endereco_manual_uf": "sp",
                     "empreendimento_manual": "Condomínio  Águas"}])
    _sync(db, _vista(bairro="granja viana", cep="06700000", uf="SP", empreendimento="Condominio Aguas"))
    assert _hist(db) == [] and _conflitos(db) == []


def test_a_side_that_is_empty_is_not_a_difference():
    db = _db(captacao=[{"valor_venda": None, "valor_iptu": 500.0}])  # ours has no price; Vista has no IPTU
    _sync(db, _vista())
    assert _hist(db) == []


# ─── the switch ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ativa", [False, None])
def test_switch_off_or_no_row_means_nothing_happens(ativa):
    db = _db(ativa=ativa, captacao=[{"valor_venda": 777000.0}], espelho={"dormitorios": 2})
    rep = _sync(db, _vista(dormitorios=3))
    assert _hist(db) == [] and _conflitos(db) == [] and rep.divergencias_comparadas == 0 and rep.vista_campos_atualizados == 0
    assert db.table("imovel_captacao").select("*").execute().data[0]["valor_venda"] == 777000.0


def test_the_switch_is_per_org_and_the_edit_switch_defaults_off():
    db = _db()
    assert div.iniciar(db, OUTRA) is None and div.iniciar(db, ORG) is not None
    assert div.config(db, ORG) == {"ativa": True, "vista_escrita_ativa": False, "destino_user_id": None}
    assert div.config(db, OUTRA) == {"ativa": False, "vista_escrita_ativa": False, "destino_user_id": None}


# ─── 3. an owner-confirmed price/availability: send to Vista, or Vista wins and an approval opens ──────


def _proprietario(**kw):
    return {"id": "p1", "telefone": "5511988887777", "confirmado_at": "2026-11-03T12:00:00+00:00", **kw}


CONF_PRECO = dict(preco_confirmado=850000.0, preco_tipo_confirmado="venda")
MSG = [{"chat_id": "5511988887777@c.us", "direction": "inbound", "created_at": "2026-11-03T11:59:00+00:00",
        "body": "Pode baixar pra 850 mil, me liga no 11 98888-7777 ou veja https://exemplo.com/x"}]


def _com_conversa(db):
    db.set_table_data("julia_contatos", [{"id": "jc-1", "org_id": str(ORG), "chat_id": "5511988887777@c.us"}])
    return db


def test_certain_switch_on_and_permitted_sends_our_value_to_vista_with_the_conversation_in_the_history():
    db = _com_conversa(_db(escrita=True, proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    vista = _vista()
    vista.set_registro("CA0001", {"ValorVenda": "900000", "ObsVenda": "Lote 1 Quadra 2\n10/10/26 Parceiro informa algo. (Ana)"})
    rep = _sync(db, vista)
    [(cod, campos)] = vista.atualizacoes
    assert cod == "CA0001" and campos["ValorVenda"] == "850000"
    [h] = _hist(db, acao="enviado_ao_vista")
    assert (h["campo"], h["origem"], h["valor_anterior"], h["valor_novo"]) == ("valor_venda", "julia", 900000.0, 850000.0)
    assert h["conversa"] == {"id": "jc-1", "url": "/julia/conversas?contato=jc-1"}
    # the history `detalhe` MIRRORS the note written into Vista's ObsVenda (a reason, the conversation link, our author label, no phone/e-mail)
    assert campos["ObsVenda"].split("\n")[0] == "Lote 1 Quadra 2" and campos["ObsVenda"].split("\n")[-1].startswith("10/10/26")
    assert h["detalhe"] in campos["ObsVenda"].split("\n") and "proprietário confirmou valor de venda" in h["detalhe"]
    assert "/julia/conversas?contato=jc-1" in h["detalhe"] and h["detalhe"].endswith("(NoctusAI)") and "11988887777" not in h["detalhe"]
    assert "valor de venda 900000 → 850000" in h["detalhe"]
    assert _conflitos(db) == [] and _hist(db, acao="aprovacao_pendente") == [] and rep.divergencias_linhas == [] and rep.vista_enviados == 1
    assert db.table("julia_proprietarios_contatos").select("*").execute().data[0]["preco_confirmado"] == 850000.0  # the confirmation stays


def test_a_value_already_sent_is_not_sent_again_while_vista_has_not_reflected_it():
    db = _com_conversa(_db(escrita=True, proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    vista = _vista()
    _sync(db, vista)
    _sync(db, vista)  # Vista still answers 900000 (the Fake never changes)
    assert len(vista.atualizacoes) == 1 and len(_hist(db, acao="enviado_ao_vista")) == 1


@pytest.mark.parametrize("motivo,escrita,permitido", [
    ("switch off", False, True),
    ("PUT not permitted", True, False),
    ("permission unknown", True, None),
])
def test_otherwise_vista_wins_and_an_approval_opens_with_the_conversation_link(motivo, escrita, permitido):
    db = _com_conversa(_db(escrita=escrita, proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    vista = _vista()
    vista.permitir_escrita(permitido)
    rep = _sync(db, vista)
    assert vista.atualizacoes == []  # never written
    [c] = _conflitos(db, campo="valor_venda")
    assert c["status"] == "pendente" and c["origem_anterior"] == "julia_proprietario" and (c["valor_anterior"], c["valor_proposto"]) == (850000.0, 900000.0)
    assert c["notas"]["nosso"]["conversa"]["contato_id"] == "jc-1" and "telefone" not in c["notas"]["nosso"]["conversa"]
    assert db.table("julia_proprietarios_contatos").select("*").execute().data[0]["preco_confirmado"] is None  # Vista wins: the confirmation is cleared
    assert sorted(h["acao"] for h in _hist(db)) == ["aprovacao_pendente", "vista_prevaleceu"]
    [pend] = _hist(db, acao="aprovacao_pendente")
    assert pend["conflito_id"] == c["id"] and pend["conversa"]["url"] == "/julia/conversas?contato=jc-1"
    assert [r["id"] for r in rep.divergencias_linhas] == [c["id"]]


def test_a_failed_send_is_recorded_and_falls_back_to_vista_wins_plus_approval():
    db = _com_conversa(_db(escrita=True, proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    vista = _vista()
    vista.permitir_escrita(True, VistaUpstreamError(500, "boom", "/imoveis/detalhes"))
    _sync(db, vista)
    assert sorted(h["acao"] for h in _hist(db)) == ["aprovacao_pendente", "envio_vista_falhou", "vista_prevaleceu"]
    [f] = _hist(db, acao="envio_vista_falhou")
    assert "VistaUpstreamError" in f["detalhe"] and "boom" not in str(f)
    assert len(_conflitos(db, status="pendente")) == 1


def test_a_failed_read_of_vistas_current_note_writes_nothing_and_falls_back_to_vista_wins_plus_approval():
    from noctusai_lib.integrations.vista import VistaNotFound

    db = _com_conversa(_db(escrita=True, proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    vista = _vista()
    vista.falhar_leitura(VistaNotFound(404, "x", "/imoveis/detalhes"))
    _sync(db, vista)
    assert vista.atualizacoes == [] and len(_hist(db, acao="envio_vista_falhou")) == 1 and len(_conflitos(db, status="pendente")) == 1


def test_availability_is_never_pushed_even_with_the_switch_on_it_takes_the_approval_path():
    db = _db(escrita=True, proprietarios=[_proprietario(status_confirmado="vendido")])
    vista = _vista()
    _sync(db, vista)
    [c] = _conflitos(db, campo="disponibilidade")
    assert (c["valor_anterior"], c["valor_proposto"]) == ("indisponivel", "disponivel") and vista.atualizacoes == []
    assert db.table("julia_proprietarios_contatos").select("*").execute().data[0]["status_confirmado"] is None


def test_the_same_approval_is_not_opened_twice():
    db = _db(proprietarios=[_proprietario(**CONF_PRECO)])
    _sync(db, _vista())
    segunda = _sync(db, _vista())
    assert len(_conflitos(db)) == 1 and segunda.divergencias_linhas == []


def test_certainty_is_an_explicit_recorded_confirmation_nothing_weaker():
    d = div.Divergencia("CA0001", "valor_venda", 1, 2, div.O_PROPRIETARIO, "2026-11-03T12:00:00+00:00", None, {"proprietario_contato_id": "p1"})
    assert div._certo(d) is True
    assert div._certo(div.Divergencia("CA0001", "valor_venda", 1, 2, div.O_PROPRIETARIO, None, None, {"proprietario_contato_id": "p1"})) is False  # no confirmado_at
    assert div._certo(div.Divergencia("CA0001", "valor_venda", 1, 2, div.O_PROPRIETARIO, "2026-11-03", None, None)) is False  # no owner contact
    assert div._certo(div.Divergencia("CA0001", "valor_venda", 1, 2, div.O_CAPTACAO, "2026-11-03", None, {"proprietario_contato_id": "p1"})) is False


def test_a_confirmation_older_than_the_vista_edit_is_not_a_difference():
    """The existing rule (`julia_imovel_confirmado`): a Vista edit after the confirmation wins -- nothing to review."""
    db = _db(escrita=True, proprietarios=[_proprietario(**CONF_PRECO, confirmado_at="2026-10-01T12:00:00+00:00")])
    vista = _vista()
    _sync(db, vista)
    assert _conflitos(db) == [] and _hist(db) == [] and vista.atualizacoes == []


def test_the_conversation_excerpt_is_sanitised_and_phone_free_in_the_approval_note():
    db = _com_conversa(_db(proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    _sync(db, _vista())
    [c] = _conflitos(db, campo="valor_venda")
    conversa = c["notas"]["nosso"]["conversa"]
    assert conversa["telefone_final"] == "7777" and conversa["trecho"] == "Pode baixar pra 850 mil, me liga no [telefone] ou veja [link]"
    api = div.para_api(c, {})
    assert api["origem"] == {"tipo": "julia", "contato_id": "jc-1", "thread_id": "5511988887777@c.us", "trecho": conversa["trecho"]}


def test_the_listing_hides_a_row_the_system_superseded():
    db = _db(proprietarios=[_proprietario(**CONF_PRECO)])
    _sync(db, _vista())
    itens = div.listar_do_imovel(db, None, ORG, "CA0001")["items"]
    assert len(itens) == 1 and itens[0]["status"] == "pendente" and itens[0]["valor_vista"] == 900000.0


# ─── approvals are decided by people; the automatic resolver never touches them ────────────────────────


def test_the_automatic_resolver_never_decides_a_vista_sync_proposal():
    d = divergencia_resolucao.resolver_divergencia(
        "valor_venda", valor_atual=1, origem_atual="captacao_manual", valor_proposto=2, origem_proposto="vista_sync",
        mesmo_valor=lambda c, a, b: a == b, atual_humano=False,
    )
    assert d.requer_humano is True and d.vencedor is None and d.regra == "decisao_humana"


def test_the_imovel_backfill_resolver_skips_vista_sync_rows():
    from app.modules.imovel_hub import campos_extraidos_service as campos

    db = _db(proprietarios=[_proprietario(**CONF_PRECO)])
    _sync(db, _vista())
    out = campos.backfill_resolver_conflitos_pendentes(db, ORG)
    assert out["resolvidos"] == [] and any(r["origem_proposto"] == "vista_sync" for r in out["ignorados"])
    assert _conflitos(db)[0]["status"] == "pendente"
    with pytest.raises(Exception, match="Vista"):
        campos.resolver(db, ORG, "CA0001", _conflitos(db)[0]["id"], aceitar=True, decidido_por=None)


def test_an_extraction_conflict_on_the_same_field_is_left_alone():
    db = _db(proprietarios=[_proprietario(**CONF_PRECO)])
    db.set_table_data("imovel_campo_conflitos", [{"id": "x1", "org_id": str(ORG), "codigo": "CA0001", "campo": "valor_venda", "status": "pendente",
                                                  "origem_proposto": "matricula", "valor_proposto": 1, "valor_anterior": 2}])
    _sync(db, _vista())
    assert len(_conflitos(db)) == 1 and _conflitos(db)[0]["id"] == "x1" and _hist(db, acao="aprovacao_pendente") == []


# ─── the in-app notices: operational class, admins only, NEVER WhatsApp / e-mail ───────────────────────


class _Core(MockSupabaseClient):
    pass


def _core(org=ORG, admins=True):
    c = _Core()
    c.set_table_data("noctus_users", [{"id": DONO, "org_id": str(org), "nome": "Dono", "telefone": "+5511988880000", "org_role": "owner"},
                                      {"id": "a2", "org_id": str(org), "org_role": "admin"}, {"id": "m3", "org_id": str(org), "org_role": "member"}]
                    if admins else [{"id": "m3", "org_id": str(org), "org_role": "member"}])
    c.set_table_data("notifications", [])
    return c


def _avisos(core):
    return core.table("notifications").select("*").execute().data


def _executar(db, vista, core):
    import contextlib

    from app.services import imoveis_atualizacao_service as atualizacao

    @contextlib.contextmanager
    def lease(*_a, **_k):
        yield True

    def fabrica(client, adapter, **kw):
        return ImovelSyncService(client, adapter, duplicate_detector=lambda *a, **k: None, **kw)

    db.set_table_data("imoveis_sync_execucoes", [])
    return asyncio.run(atualizacao.executar(db, vista, ORG, modo="detalhes", escopo="todos", core=core, sync_factory=fabrica, lease_fn=lease))


def test_one_notice_per_run_reports_how_many_imoveis_and_fields_vista_changed():
    db = _db(espelho={"dormitorios": 2, "vagas": 1})
    core = _core()
    res = _executar(db, _vista(dormitorios=3, vagas=2), core)
    assert res["status"] == "ok"
    avisos = _avisos(core)
    assert sorted(a["user_id"] for a in avisos) == sorted([DONO, "a2"])  # owners + admins, never a member
    a = next(x for x in avisos if x["user_id"] == DONO)
    assert a["metadata"]["tipo"] == "imoveis_vista_sincronizado" and a["title"] == "Vista atualizou 1 imóvel" and a["message"] == "Vista atualizou 1 imóvel (2 campos)."
    assert a["metadata"]["categoria"] == "operacional" and a["metadata"]["link"] == "/imoveis" and a["metadata"]["produto"] == "social-wiring"
    assert len(a["title"]) <= 60 and len(a["message"]) <= 160
    [exec_row] = db.table("imoveis_sync_execucoes").select("*").execute().data
    assert exec_row["relatorio"]["vista_campos_atualizados"] == 2 and "divergencias_digest" not in exec_row["relatorio"]


def test_no_notice_when_vista_changed_nothing():
    db = _db(espelho={"dormitorios": 3})
    core = _core()
    _executar(db, _vista(dormitorios=3), core)
    assert _avisos(core) == []


def test_an_approval_notice_links_to_the_imovel_and_carries_no_phone_or_email():
    db = _com_conversa(_db(proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    core = _core()
    _executar(db, _vista(), core)
    aprov = [a for a in _avisos(core) if a["metadata"]["tipo"] == "imovel_aprovacao_pendente"]
    assert len(aprov) == 2  # one per admin
    m = aprov[0]
    assert m["metadata"]["link"] == "/imoveis/CA0001" and m["metadata"]["entidade"] == {"tipo": "imovel", "id": "CA0001"} and m["title"] == "Aprovação pendente · CA0001"
    assert "R$ 850.000,00" in m["message"] and "R$ 900.000,00" in m["message"] and "@" not in m["message"] and "5511988887777" not in str(m)
    assert len(m["message"]) <= 160


# ─── the WhatsApp digest of the approvals a run opens: KEPT (owner 2026-11-15, option 1), switchable per kind ──────────────────


class _Enviador:
    def __init__(self, erro=None):
        self.enviadas, self.erro = [], erro

    async def __call__(self, org_id, telefone, texto):
        self.enviadas.append((str(org_id), telefone, texto))
        return self.erro


def _db_com_aprovacao(destino=DONO):
    """A fresh org state whose next sync opens ONE approval (owner-confirmed price differs from Vista, edit switch off)."""
    db = _com_conversa(_db(proprietarios=[_proprietario(**CONF_PRECO)], mensagens=MSG))
    rows = db.table("vista_divergencias_config").select("*").execute().data
    db.set_table_data("vista_divergencias_config", [{**r, "destino_user_id": destino} for r in rows])
    return db


def _aprovacoes(destino=DONO):
    """A run that opens ONE approval: the rows the digest lists."""
    db = _db_com_aprovacao(destino)
    rep = _sync(db, _vista())
    assert len(rep.divergencias_linhas) == 1
    return db, rep



def test_the_config_carries_the_digest_destination_and_the_edit_switch():
    db = _db()
    db.set_table_data("vista_divergencias_config", [{"org_id": str(ORG), "ativa": True, "vista_escrita_ativa": False, "destino_user_id": DONO}])
    assert div.config(db, ORG) == {"ativa": True, "vista_escrita_ativa": False, "destino_user_id": DONO}
    out = div.salvar_config(db, ORG, destino_user_id=None, mudar_destino=True)
    assert out["destino_user_id"] is None and out["ativa"] is True  # only the destination moved


def test_one_digest_lists_the_approvals_and_uses_the_phone_from_core():
    db, rep = _aprovacoes()
    env = _Enviador()
    via = asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=env, base_url="https://sw.test"))
    assert via == "whatsapp" and len(env.enviadas) == 1
    _org, tel, texto = env.enviadas[0]
    assert tel == "+5511988880000" and "1 campo(s) em 1 imóvel" in texto and "https://sw.test/imoveis/CA0001" in texto
    assert all(r["notificado_em"] for r in db.table("imovel_campo_conflitos").select("*").execute().data if r["status"] == "pendente")


def test_no_approval_sends_no_digest():
    env = _Enviador()
    assert asyncio.run(div.enviar_digest(_db(), _core(), ORG, [], enviar=env)) == "nada" and env.enviadas == []


def test_without_a_destination_it_is_an_in_app_notice_never_silent(caplog):
    db, rep = _aprovacoes(destino=None)
    env = _Enviador()
    with caplog.at_level(logging.WARNING):
        via = asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=env))
    assert via == "in_app:sem_telefone_do_destino" and env.enviadas == []
    assert any("in-app notice instead" in r.getMessage() for r in caplog.records)


def test_the_notificacoes_switch_turns_the_digest_off_and_the_send_is_ledgered():
    from noctusai_lib.domain.notification_catalog import FakeNotificationGate, configure_notification_gate

    from app.services.notification_kinds import PRODUCT

    gate = FakeNotificationGate(PRODUCT)
    configure_notification_gate(gate)
    try:
        db, rep = _aprovacoes()
        gate.disabled.add(div.KIND_DIGEST)
        env = _Enviador()
        assert asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=env)) == "desligada" and env.enviadas == []
        assert [s["status"] for s in gate.sends] == ["suppressed"]
        gate.disabled.clear()
        assert asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=env)) == "whatsapp"
        assert [s["status"] for s in gate.sends] == ["suppressed", "sent"]
    finally:
        configure_notification_gate(None)


def test_a_failed_send_falls_back_to_in_app():
    db, rep = _aprovacoes()
    via = asyncio.run(div.enviar_digest(db, _core(), ORG, rep.divergencias_linhas, enviar=_Enviador(erro="sem_linha")))
    assert via == "in_app:falha_envio:sem_linha"


def test_the_run_orchestrator_sends_one_digest_besides_the_in_app_notices():
    import contextlib

    from app.services import imoveis_atualizacao_service as atualizacao

    db = _db_com_aprovacao()
    env, core = _Enviador(), _core()

    @contextlib.contextmanager
    def lease(*_a, **_k):
        yield True

    def fabrica(client, adapter, **kw):
        return ImovelSyncService(client, adapter, duplicate_detector=lambda *a, **k: None, **kw)

    db.set_table_data("imoveis_sync_execucoes", [])
    res = asyncio.run(atualizacao.executar(db, _vista(), ORG, modo="detalhes", escopo="todos", core=core, sync_factory=fabrica, lease_fn=lease,
                                           enviar_divergencia=env))
    assert res["status"] == "ok" and len(env.enviadas) == 1
    [exec_row] = db.table("imoveis_sync_execucoes").select("*").execute().data
    assert exec_row["relatorio"]["divergencias_digest"] == "whatsapp" and exec_row["relatorio"]["divergencias_novas"] == 1
    assert exec_row["relatorio"]["avisos_aprovacao"] == 2  # the in-app approval notice (one per admin) is a separate channel


def test_no_recipients_is_logged_at_warning_and_never_raises(caplog):
    with caplog.at_level(logging.WARNING):
        assert div.notificar_sincronizado(_core(admins=False), ORG, 3, 5) == 0
    assert any("no recipients" in r.getMessage() for r in caplog.records)
    assert div.notificar_sincronizado(None, ORG, 3, 5) == 0 and div.notificar_sincronizado(_core(), ORG, 0, 0) == 0


def test_many_approvals_fold_into_one_extra_notice():
    linhas = [{"codigo": f"CA{i:04d}", "campo": "valor_venda", "valor_anterior": 1, "valor_proposto": 2} for i in range(12)]
    core = _core()
    div.notificar_aprovacoes(core, ORG, linhas, maximo=10)
    por_dono = [a for a in _avisos(core) if a["user_id"] == DONO]
    assert len(por_dono) == 11 and por_dono[-1]["title"] == "Aprovações pendentes"
