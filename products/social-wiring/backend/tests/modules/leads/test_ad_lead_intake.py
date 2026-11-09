"""Ad-lead intake (CONTRACT products/social-wiring/projects/ad-lead-intake-CONTRACT.md): a Meta form lead -> its property
refreshed from Vista -> linked both ways -> corretor recorded / warned. FakeVistaAdapter + MockSupabaseClient; synthetic data.

The mock validates every write against the migrations (incl. 331), so these tests also pin the migration's column set."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.domain.real_estate.imovel import Corretor
from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaConfigError

from app.modules.leads.services import ad_lead_intake_backfill as backfill
from app.modules.leads.services import ad_lead_intake_service as intake
from app.modules.leads.services import lead_notice
from app.services.imoveis_service import _imovel_to_row
from tests.services.test_imoveis_sync_detalhes import _Db

ORG = uuid4()
LEAD = str(uuid4())
CLIENTE = str(uuid4())
CARD = str(uuid4())
META = "meta-lead-1"
REG = str(uuid4())
ADMIN = str(uuid4())
CORRETOR_A = str(uuid4())  # SW corretor of the LEAD
CORRETOR_B = str(uuid4())  # SW corretor that matches the property's Vista corretor by name
VISTA_J = Corretor(codigo="12", nome="Joao Silva", email="j@x.com", fone="11999990000")


def _imovel(codigo="ONE5", valor=1_250_000.0, corretores=(VISTA_J,)):
    return Imovel(codigo=codigo, status="Venda", valor_venda=valor, data_atualizacao=date(2026, 11, 2), exibir_no_site=True,
                  corretores=list(corretores))


def _vista(*imoveis):
    a = FakeVistaAdapter()
    for i in imoveis:
        a.add_imovel(i)
    return a


def _lead(**kw):
    base = {"id": LEAD, "org_id": str(ORG), "meta_lead_id": META, "codigo_imovel": "ONE5", "corretor_id": None, "corretor_raw": None,
            "imovel_ref_id": None, "qualificacao_form": None, "data_entrada": "2026-11-08", "created_at": "2026-11-08T10:00:00+00:00"}
    base.update(kw)
    return base


def _meta(**kw):
    base = {"id": META, "org_id": str(ORG), "created_time": "2026-11-08T10:00:00+00:00", "codigo_imovel": "ONE5",
            "answers": {"REF": "ONE5", "Até qual valor você pretende investir?": "Até R$ 1.500.000",
                        "Para entendermos melhor seu momento, em qual fase da compra você se encontra?": "Pesquisando",
                        "Você está buscando um imóvel na Granja Viana?": "Sim"}}
    base.update(kw)
    return base


def _db(*, lead=None, meta=None, registry=True, mirror=(), corretores_sw=(), aliases=(), captacao=(), divergencia_ativa=False, admins=True):
    db = _Db()
    seed = {
        "leads": [lead or _lead()], "meta_ads_leads": [meta or _meta()],
        "atendimentos": [{"id": CARD, "org_id": str(ORG), "cliente_id": CLIENTE, "lead_id": LEAD, "meta_ads_lead_id": META,
                          "substituida_por": None, "created_at": "2026-11-08T10:00:01+00:00"}],
        "atendimento_imoveis": [], "cliente_imovel_interesses": [],
        "imovel_registry": [{"id": REG, "org_id": str(ORG), "codigo_canonical": "ONE5", "codigo_display": "ONE5", "ativo_no_vista": True,
                             "origem_descoberta": "vista_sync"}] if registry else [],
        "imoveis": [dict(r) for r in mirror], "lead_corretores": [dict(r) for r in corretores_sw], "lead_corretor_aliases": [dict(r) for r in aliases],
        "imovel_corretores": [], "lead_corretor_divergencias": [], "lead_imovel_intakes": [],
        "vista_divergencias_config": [{"org_id": str(ORG), "ativa": True, "destino_user_id": None}] if divergencia_ativa else [],
        "imovel_captacao": [dict(r) for r in captacao], "imovel_dados": [], "julia_proprietarios_contatos": [], "imovel_campo_conflitos": [],
        "conversation_messages": [], "lead_sources": [],
    }
    for nome, rows in seed.items():
        db.set_table_data(nome, rows)
    return db


@pytest.fixture
def core(monkeypatch):
    """The core client the in-app warning writes to (`lead_notice._core` reads `app.database.get_core_client`)."""
    from noctusai_lib.testing import MockSupabaseClient

    c = MockSupabaseClient()
    c.set_table_data("noctus_users", [{"id": ADMIN, "org_id": str(ORG), "org_role": "admin"}])
    c.set_table_data("notifications", [])
    monkeypatch.setattr("app.database.get_core_client", lambda: c)
    return c


def _rodar(db, adapter=None, **kw):
    return intake.intake_imovel_do_lead(db, ORG, LEAD, adapter=adapter, **kw)


def _rows(db, tabela, **eq):
    return [r for r in db.table(tabela).select("*").execute().data if all(r.get(k) == v for k, v in eq.items())]


def _mirror_row(imovel):
    row = _imovel_to_row(imovel, ORG, "2026-10-23T00:00:00+00:00")
    row["codigo_norm"] = imovel.codigo.upper()
    return row


# ─── the happy path: new lead, new property ──────────────────────────────


def test_new_lead_new_property_links_both_ways_and_records_everything(core):
    db = _db()
    res = _rodar(db, _vista(_imovel()))

    assert res["status"] == "ok" and res["vista"] == "ok" and res["imovel"] == "novo"
    assert [r["codigo"] for r in _rows(db, "imoveis")] == ["ONE5"]                      # property created
    assert _rows(db, "leads")[0]["imovel_ref_id"] == REG                                # lead -> property (G1)
    [interesse] = _rows(db, "cliente_imovel_interesses")                                # property -> lead (G2): BOTH ids
    assert interesse["lead_id"] == LEAD and interesse["meta_ads_lead_id"] == META and interesse["codigo"] == "ONE5"
    assert [r["codigo"] for r in _rows(db, "atendimento_imoveis")] == ["ONE5"]
    [c] = _rows(db, "imovel_corretores")                                                # G4: structured, keyed by Vista Codigo
    assert c["vista_corretor_codigo"] == "12" and c["nome"] == "Joao Silva" and c["codigo_canonical"] == "ONE5" and c["ativo"] is True
    [row] = _rows(db, "lead_imovel_intakes")
    assert row["status"] == "ok" and row["tentativas"] == 1 and row["ultimo_erro"] is None and row["concluido_em"]


def test_the_form_qualification_lands_structured_on_the_lead(core):
    db = _db()
    _rodar(db, _vista(_imovel()))
    q = _rows(db, "leads")[0]["qualificacao_form"]
    assert q["orcamento_max"] == 1_500_000.0 and q["orcamento_texto"] == "Até R$ 1.500.000"
    assert q["fase_compra_texto"] == "Pesquisando"
    assert q["regiao_interesse"]["confirmou"] is True and "Granja Viana" in q["regiao_interesse"]["pergunta"]


# ─── existing property: always fetched, compared ─────────────────────────


def test_existing_property_unchanged_is_fetched_anyway_and_reports_no_change(core):
    imovel = _imovel()
    db = _db(mirror=[_mirror_row(imovel)])
    res = _rodar(db, _vista(imovel))
    assert res["imovel"] == "inalterado" and res["mudancas"] == {}


def test_existing_property_diverged_in_price_is_refreshed_and_the_change_recorded(core):
    db = _db(mirror=[_mirror_row(_imovel(valor=1_290_000.0))], divergencia_ativa=True,
             captacao=[{"org_id": str(ORG), "codigo_canonical": "ONE5", "valor_venda": 1_290_000.0, "updated_at": "2026-10-20T10:00:00+00:00"}])
    res = _rodar(db, _vista(_imovel(valor=1_250_000.0)))

    assert res["imovel"] == "atualizado"
    assert res["mudancas"]["valor_venda"] == {"antes": 1_290_000.0, "depois": 1_250_000.0}
    assert _rows(db, "imoveis")[0]["valor_venda"] == 1_250_000.0                      # the mirror now says what Vista says
    # …and the existing divergence mechanism opened the review row: OUR owned value (captação) vs Vista's
    assert [d["campo"] for d in res["divergencias_vista"]] == ["valor_venda"]
    [c] = _rows(db, "imovel_campo_conflitos", campo="valor_venda")
    assert c["status"] == "pendente" and c["valor_anterior"] == 1_290_000.0 and c["valor_proposto"] == 1_250_000.0


# ─── Vista outcomes ──────────────────────────────────────────────────────


def test_unknown_code_is_recorded_not_found_but_the_links_still_exist(core):
    db = _db()
    res = _rodar(db, _vista())  # Vista has no ONE5
    assert res["status"] == intake.ST_NAO_ENCONTRADO and res["vista"] == "sumiu"
    assert _rows(db, "leads")[0]["imovel_ref_id"] == REG
    assert len(_rows(db, "cliente_imovel_interesses")) == 1
    assert _rows(db, "imoveis") == []                                                  # never invent a property


def test_vista_not_configured_keeps_the_lead_linked_and_is_retryable_not_silent(core):
    db = _db()

    def sem_credencial(_org):
        raise VistaConfigError("Vista não configurada para esta empresa")

    res = intake.intake_imovel_do_lead(db, ORG, LEAD, adapter_factory=sem_credencial)
    assert res["status"] == intake.ST_RETRY and "Vista não configurada" in res["erros"][0]
    assert _rows(db, "leads")[0]["imovel_ref_id"] == REG and len(_rows(db, "cliente_imovel_interesses")) == 1
    [row] = _rows(db, "lead_imovel_intakes")
    assert row["status"] == "pendente_retry" and "Vista não configurada" in row["ultimo_erro"]

    # configured later: the SAME row is re-driven to ok (tentativas counted)
    res2 = intake.intake_imovel_do_lead(db, ORG, LEAD, adapter=_vista(_imovel()))
    assert res2["status"] == "ok"
    [row] = _rows(db, "lead_imovel_intakes")
    assert row["status"] == "ok" and row["tentativas"] == 2 and row["ultimo_erro"] is None


def test_vista_transport_failure_is_retryable_and_never_read_as_the_property_being_gone(core):
    from noctusai_lib.integrations.vista.client import VistaUpstreamError

    adapter = _vista(_imovel())

    async def cai(_codigo):
        raise VistaUpstreamError("503", status=503)

    adapter.refresh_imovel = cai
    db = _db()
    res = _rodar(db, adapter)
    assert res["status"] == intake.ST_RETRY and res["vista"] == "falhou"


def test_tentar_intake_never_raises_and_records_the_failure(core):
    db = _db()
    out = intake.tentar_intake(db, ORG, LEAD, adapter_factory=lambda _o: (_ for _ in ()).throw(RuntimeError("boom")))
    assert out["status"] == intake.ST_RETRY
    assert _rows(db, "lead_imovel_intakes")[0]["status"] == "pendente_retry"
    # a lead that does not even exist: still no exception
    assert intake.tentar_intake(db, ORG, str(uuid4()))["status"] == intake.ST_RETRY


def test_lead_without_a_code_is_recorded_sem_codigo_and_still_qualified(core):
    db = _db(lead=_lead(codigo_imovel=None), meta=_meta(codigo_imovel=None, answers={"Até qual valor você pretende investir?": "800 mil"}))
    res = _rodar(db, _vista())
    assert res["status"] == intake.ST_SEM_CODIGO
    assert _rows(db, "leads")[0]["qualificacao_form"]["orcamento_max"] == 800_000.0


# ─── corretor ────────────────────────────────────────────────────────────

_SW_CORRETORES = [
    {"id": CORRETOR_A, "org_id": str(ORG), "nome": "Maria Souza", "nome_norm": "MARIA SOUZA", "vista_codigo": None, "ativo": True},
    {"id": CORRETOR_B, "org_id": str(ORG), "nome": "Joao Silva", "nome_norm": "JOAO SILVA", "vista_codigo": None, "ativo": True},
]
_ALIASES = [{"org_id": str(ORG), "alias": "Joao Silva", "alias_norm": "JOAO SILVA", "corretor_id": CORRETOR_B}]


def test_lead_corretor_differing_from_the_property_corretor_warns_once_and_is_queryable(core):
    db = _db(lead=_lead(corretor_id=CORRETOR_A, corretor_raw="Maria Souza"), corretores_sw=_SW_CORRETORES, aliases=_ALIASES)
    res = _rodar(db, _vista(_imovel()))
    assert res["divergencia_corretor"]["divergencia"] is True and res["divergencia_corretor"]["nova"] is True
    [d] = _rows(db, "lead_corretor_divergencias")
    assert d["status"] == "pendente" and d["lead_id"] == LEAD and d["lead_corretor_nome"] == "Maria Souza" and d["notificado_em"]
    assert d["imovel_corretores"][0]["vista_corretor_codigo"] == "12" and d["imovel_corretores"][0]["resolvido"] is True
    [n] = core.table("notifications").select("*").execute().data
    assert n["metadata"]["tipo"] == "lead_corretor_divergente" and "ONE5" in n["title"] and "Joao Silva" in n["message"]
    # the Vista corretor resolved BY NAME is stamped with its Vista Codigo (the deterministic key from now on)
    assert _rows(db, "lead_corretores", id=CORRETOR_B)[0]["vista_codigo"] == "12"

    _rodar(db, _vista(_imovel()))  # re-run: no second row, no second warning
    assert len(_rows(db, "lead_corretor_divergencias")) == 1 and len(core.table("notifications").select("*").execute().data) == 1


def test_lead_corretor_matching_the_property_corretor_is_not_a_divergence(core):
    db = _db(lead=_lead(corretor_id=CORRETOR_B), corretores_sw=_SW_CORRETORES, aliases=_ALIASES)
    res = _rodar(db, _vista(_imovel()))
    assert res["divergencia_corretor"] == {"divergencia": False}
    assert _rows(db, "lead_corretor_divergencias") == [] and core.table("notifications").select("*").execute().data == []


def test_a_pending_divergence_auto_resolves_when_the_lead_corretor_aligns(core):
    db = _db(lead=_lead(corretor_id=CORRETOR_A), corretores_sw=_SW_CORRETORES, aliases=_ALIASES)
    _rodar(db, _vista(_imovel()))
    db.table("leads").update({"corretor_id": CORRETOR_B}).eq("id", LEAD).execute()
    _rodar(db, _vista(_imovel()))
    assert _rows(db, "lead_corretor_divergencias")[0]["status"] == "resolvida"


def test_lead_without_a_corretor_has_nothing_to_compare(core):
    db = _db()
    res = _rodar(db, _vista(_imovel()))
    assert res["divergencia_corretor"] == {"divergencia": False} and len(_rows(db, "imovel_corretores")) == 1


def test_a_corretor_that_left_the_property_is_deactivated_never_deleted(core):
    db = _db()
    _rodar(db, _vista(_imovel()))
    _rodar(db, _vista(_imovel(corretores=[Corretor(codigo="99", nome="Outro Corretor")])), refresh_cache=None)
    por_chave = {r["chave"]: r["ativo"] for r in _rows(db, "imovel_corretores")}
    assert por_chave == {"12": False, "99": True}


# ─── idempotence ─────────────────────────────────────────────────────────


def test_rerun_changes_nothing(core):
    db = _db()
    _rodar(db, _vista(_imovel()))
    antes = {t: len(_rows(db, t)) for t in ("cliente_imovel_interesses", "atendimento_imoveis", "imovel_corretores", "lead_imovel_intakes", "imovel_registry")}
    _rodar(db, _vista(_imovel()))
    assert {t: len(_rows(db, t)) for t in antes} == antes
    assert _rows(db, "lead_imovel_intakes")[0]["tentativas"] == 2 and _rows(db, "leads")[0]["imovel_ref_id"] == REG


def test_an_interesse_written_by_the_old_ingest_gets_its_lead_id_filled_never_duplicated(core):
    db = _db()
    db.set_table_data("cliente_imovel_interesses", [{"id": str(uuid4()), "org_id": str(ORG), "cliente_id": CLIENTE, "codigo": "ONE5", "origem": "lead",
                                                      "lead_id": None, "meta_ads_lead_id": META, "created_by": None, "created_at": "2026-11-08T10:00:00+00:00", "deleted_at": None}])
    _rodar(db, _vista(_imovel()))
    [i] = _rows(db, "cliente_imovel_interesses")
    assert i["lead_id"] == LEAD and i["meta_ads_lead_id"] == META


def test_a_removed_interesse_is_not_resurrected(core):
    db = _db()
    db.set_table_data("cliente_imovel_interesses", [{"id": str(uuid4()), "org_id": str(ORG), "cliente_id": CLIENTE, "codigo": "ONE5", "origem": "lead",
                                                      "lead_id": None, "meta_ads_lead_id": META, "created_by": None, "created_at": "2026-11-08T10:00:00+00:00",
                                                      "deleted_at": "2026-11-08T12:00:00+00:00"}])
    _rodar(db, _vista(_imovel()))
    [i] = _rows(db, "cliente_imovel_interesses")
    assert i["deleted_at"] is not None


# ─── backfill ────────────────────────────────────────────────────────────


def _db_varios(n=3):
    db = _db()
    leads, metas = [], []
    for k in range(n):
        lid = str(uuid4())
        mid = f"meta-{k:03d}"
        leads.append(_lead(id=lid, meta_lead_id=mid, codigo_imovel="ONE5"))
        metas.append(_meta(id=mid))
    db.set_table_data("leads", leads)
    db.set_table_data("meta_ads_leads", metas)
    db.set_table_data("atendimentos", [])
    return db


def test_backfill_is_a_dry_run_by_default_writes_nothing_and_never_calls_vista():
    db = _db_varios()
    out = backfill.backfill_intake(db, ORG, limite=10, adapter_factory=lambda _o: (_ for _ in ()).throw(AssertionError("Vista called in dry-run")))
    assert out["dry_run"] is True and out["lote"] == 3 and out["a_processar"] == 3 and out["codigos_distintos"] == 1 and out["processados"] == 0
    assert _rows(db, "lead_imovel_intakes") == []


def test_backfill_batches_are_resumable_and_fetch_each_code_once(core):
    db = _db_varios(3)
    chamadas = []
    adapter = _vista(_imovel())
    original = adapter.refresh_imovel

    async def conta(codigo):
        chamadas.append(codigo)
        return await original(codigo)

    adapter.refresh_imovel = conta
    p1 = backfill.backfill_intake(db, ORG, dry_run=False, limite=2, adapter_factory=lambda _o: adapter)
    assert p1["processados"] == 2 and p1["por_status"] == {"ok": 2} and p1["proximo_cursor"] == "meta-001" and chamadas == ["ONE5"]
    p2 = backfill.backfill_intake(db, ORG, dry_run=False, limite=2, cursor=p1["proximo_cursor"], adapter_factory=lambda _o: adapter)
    assert p2["processados"] == 1 and p2["proximo_cursor"] is None
    assert len(_rows(db, "lead_imovel_intakes")) == 3
    # a re-run has nothing left to do
    p3 = backfill.backfill_intake(db, ORG, dry_run=False, limite=10, adapter_factory=lambda _o: adapter)
    assert p3["a_processar"] == 0 and p3["ja_feitos"] == 3


def test_backfill_retries_only_the_pending_ones_in_modo_pendentes(core):
    db = _db_varios(2)

    def sem_credencial(_org):
        raise VistaConfigError("sem credencial")

    p1 = backfill.backfill_intake(db, ORG, dry_run=False, limite=10, adapter_factory=sem_credencial)
    assert p1["por_status"] == {"pendente_retry": 2}
    p2 = backfill.backfill_intake(db, ORG, dry_run=False, limite=10, modo="pendentes", adapter_factory=lambda _o: _vista(_imovel()))
    assert p2["por_status"] == {"ok": 2}
    assert backfill.resumo(db, ORG)["intakes"] == {"ok": 2}


def test_backfill_reports_meta_rows_without_a_lead_instead_of_creating_them():
    db = _db_varios(1)
    db.set_table_data("leads", [])
    out = backfill.backfill_intake(db, ORG, limite=10)
    assert out["sem_lead"] == 1 and out["a_processar"] == 0


def test_backfill_rejects_an_unknown_modo():
    with pytest.raises(ValueError):
        backfill.backfill_intake(_db(), ORG, modo="tudo")


# ─── form aliases + qualification (pure) ─────────────────────────────────


def test_phone_number_alias_is_read_when_the_form_schema_does_not_type_it():
    from app.modules.leads.services.meta_form_aliases import contato_das_respostas

    out = contato_das_respostas({"phone_number": "11 98888-7777", "Nome completo": "Bia", "Email": "b@x.com"})
    assert out["phone"] == "+5511988887777" and out["full_name"] == "Bia" and out["email"] == "b@x.com"


def test_leads_sync_fills_phone_from_the_alias_but_never_overrides_the_typed_promotion():
    from types import SimpleNamespace

    from app.modules.meta_ads.services.leads_sync_service import LeadsSyncService
    from noctusai_lib.testing import MockSupabaseClient

    db = MockSupabaseClient()
    svc = LeadsSyncService(admin_supabase=db)

    def lead(**fd):
        return SimpleNamespace(id="m1", form_id="f", ad_id=None, adset_id=None, campaign_id=None, campaign_name=None, platform=None,
                               is_organic=False, created_time=None, field_data=[SimpleNamespace(name=k, values=[v]) for k, v in fd.items()])

    form = SimpleNamespace(id="f", name=None)
    row = svc.upsert_lead(lead(phone_number="+5511977776666", Email="e@x.com"), org_id=ORG, form=form, key_types={})
    assert row["phone"] == "+5511977776666" and row["email"] == "e@x.com"
    typed = svc.upsert_lead(lead(Telefone="+5511911112222", phone_number="+5511977776666"), org_id=ORG, form=form, key_types={"Telefone": "PHONE"})
    assert typed["phone"] == "+5511911112222"


@pytest.mark.parametrize("texto,esperado", [
    ("Até R$ 1.500.000", 1_500_000.0), ("1,5 milhão", 1_500_000.0), ("500 mil a 800 mil", 800_000.0), ("R$ 900.000,00", 900_000.0),
    ("Entre 1 e 2 milhões", 2_000_000.0), ("2", None), ("não sei", None),
])
def test_parse_valor_brl(texto, esperado):
    from app.modules.leads.services.meta_form_aliases import parse_valor_brl

    assert parse_valor_brl(texto) == esperado


def test_mapear_qualificacao_ignores_contact_and_ref_and_empty_answers():
    from app.modules.leads.services.meta_form_aliases import mapear_qualificacao

    assert mapear_qualificacao({"REF": "ONE1", "Email": "a@b.c", "Telefone": "+5511", "Nome completo": "X"}) == {}
    assert mapear_qualificacao(None) == {} and mapear_qualificacao({"Para entendermos melhor seu momento, em qual fase": ""}) == {}
    q = mapear_qualificacao({"Você está buscando um imóvel na Granja Viana?": "Não"})
    assert q["regiao_interesse"]["confirmou"] is False


def test_lead_notice_corretor_warning_never_raises(monkeypatch):
    monkeypatch.setattr("app.database.get_core_client", lambda: (_ for _ in ()).throw(RuntimeError("core down")))
    assert lead_notice.avisar_corretor_divergente(ORG, lead_id=LEAD, codigo="ONE5", lead_corretor="A", imovel_corretores=["B"]) == 0
