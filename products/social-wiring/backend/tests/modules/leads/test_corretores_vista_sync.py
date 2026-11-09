"""In-house brokers refined from Vista's roster (`corretores_vista_sync`): match by vista_codigo / alias / name, create, update, NEVER delete,
missing / Inativo marked + noticed, circuit breaker, incomplete read, the daily job. FakeVistaAdapter + MockSupabaseClient."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from uuid import uuid4

import pytest
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.integrations.vista.client import VistaFieldNotAvailable
from noctusai_lib.testing import MockSupabaseClient

from app.modules.leads.services import corretores_vista_job as job
from app.modules.leads.services import corretores_vista_sync as sync

ORG = uuid4()
ADMIN = str(uuid4())


@pytest.fixture
def core(monkeypatch):
    c = MockSupabaseClient()
    c.set_table_data("noctus_users", [{"id": ADMIN, "org_id": str(ORG), "org_role": "admin"}])
    c.set_table_data("notifications", [])
    monkeypatch.setattr("app.database.get_core_client", lambda: c)
    return c


def _sw(nome, vista_codigo=None, **kw):
    return {"id": str(uuid4()), "org_id": str(ORG), "nome": nome, "nome_norm": nome.upper(), "vista_codigo": vista_codigo, "ativo": True,
            "vista_status": None, **kw}


def _db(*corretores, aliases=()):
    db = MockSupabaseClient().schema("social_wiring")
    db.set_table_data("lead_corretores", [dict(c) for c in corretores])
    db.set_table_data("lead_corretor_aliases", [dict(a) for a in aliases])
    db.set_table_data("corretor_avisos", [])
    return db


def _vista(*itens):
    a = FakeVistaAdapter()
    for i in itens:
        a.add_corretor(i)
    return a


def _rows(db, t="lead_corretores", **eq):
    return [r for r in db.table(t).select("*").execute().data if all(r.get(k) == v for k, v in eq.items())]


def _rodar(db, adapter, **kw):
    return asyncio.run(sync.sincronizar(db, adapter, ORG, **kw))


GILSON = {"Codigo": "16", "Nome": "Gilson", "Nomecompleto": "Gilson Tangerino", "Email": "g@x.com", "Celular": "11999990000", "CRECI": "123",
          "Equipe": "Alpha", "CodigoEquipe": "3", "Gerente": "Sim", "Agenciador": "Sim", "Corretor": "Sim", "Inativo": "Nao",
          "Datasaida": "", "AtuacaoVenda": "Sim", "AtuacaoLocacao": "Nao"}


def test_mapear_item_reads_every_vista_field_and_is_case_tolerant():
    m = sync.mapear_item({**GILSON, "NomeCompleto": "Gilson T.", "Nomecompleto": None})
    assert m["vista_codigo"] == "16" and m["nome_completo"] == "Gilson T." and m["creci"] == "123" and m["codigo_equipe"] == "3"
    assert m["gerente"] is True and m["atuacao_locacao"] is False and m["vista_status"] == "ativo" and m["data_saida"] is None
    sai = sync.mapear_item({"Codigo": "9", "Nome": "X", "Inativo": "Sim", "Datasaida": "31/10/2026"})
    assert sai["vista_status"] == "inativo" and sai["data_saida"] == "2026-10-31"


def test_a_new_vista_broker_is_created_and_a_known_one_is_enriched_by_vista_codigo(core):
    maria = _sw("Maria Souza", "16")
    db = _db(maria)
    rel = _rodar(db, _vista(GILSON, {"Codigo": "20", "Nome": "Nova Pessoa"}))
    assert rel["criados"] == ["Nova Pessoa"] and rel["atualizados"] == 1 and rel["status"] == "ok"
    m = _rows(db, id=maria["id"])[0]
    assert m["nome"] == "Maria Souza" and m["vista_nome"] == "Gilson" and m["email"] == "g@x.com" and m["creci"] == "123" and m["vista_status"] == "ativo"   # OUR nome kept
    assert _rows(db, vista_codigo="20")[0]["nome"] == "Nova Pessoa"


def test_matching_falls_back_to_the_alias_map_then_the_name_and_stamps_vista_codigo(core):
    por_alias = _sw("Gilson Tangerino")
    por_nome = _sw("Priscila")
    db = _db(por_alias, por_nome, aliases=[{"org_id": str(ORG), "alias": "Gilson", "alias_norm": "GILSON", "corretor_id": por_alias["id"]}])
    rel = _rodar(db, _vista(GILSON, {"Codigo": "56", "Nome": "Priscila"}))
    assert rel["criados"] == [] and len(rel["vinculados_por_nome"]) == 2
    assert _rows(db, id=por_alias["id"])[0]["vista_codigo"] == "16" and _rows(db, id=por_nome["id"])[0]["vista_codigo"] == "56"


def test_a_broker_missing_from_vista_is_marked_noticed_and_never_deleted_or_deactivated(core):
    gone = _sw("Saiu", "99", vista_status="ativo")
    db = _db(_sw("Gilson", "16"), _sw("Outro", "17"), _sw("Mais um", "18"), gone)
    rel = _rodar(db, _vista(GILSON, {"Codigo": "17", "Nome": "Outro"}, {"Codigo": "18", "Nome": "Mais um"}))
    assert rel["ausentes"] == [gone["id"]]
    g = _rows(db, id=gone["id"])[0]
    assert g["vista_status"] == "ausente" and g["vista_ausente_em"] and g["ativo"] is True and len(_rows(db)) == 4          # NOTHING deleted, `ativo` untouched
    [a] = _rows(db, "corretor_avisos")
    assert a["tipo"] == "corretor_sumiu_no_vista" and a["status"] == "pendente" and a["vista_codigo"] == "99" and a["notificado_em"]
    [n] = core.table("notifications").select("*").execute().data
    assert n["metadata"]["tipo"] == "corretor_sumiu_no_vista" and "Saiu" in n["message"]
    _rodar(db, _vista(GILSON, {"Codigo": "17", "Nome": "Outro"}, {"Codigo": "18", "Nome": "Mais um"}))        # idempotent: no second notice
    assert len(_rows(db, "corretor_avisos")) == 1 and len(core.table("notifications").select("*").execute().data) == 1


def test_an_inativo_broker_is_marked_and_noticed_not_deleted(core):
    db = _db(_sw("Gilson", "16"))
    rel = _rodar(db, _vista({**GILSON, "Inativo": "Sim", "Datasaida": "2026-10-01"}))
    g = _rows(db)[0]
    assert rel["inativos"] == [g["id"]] and g["vista_status"] == "inativo" and g["data_saida"] == "2026-10-01" and len(_rows(db)) == 1
    assert _rows(db, "corretor_avisos")[0]["status"] == "pendente"


def test_a_broker_that_comes_back_keeps_the_notice_open_with_a_note(core):
    gone = _sw("Saiu", "99", vista_status="ativo")
    db = _db(_sw("A", "1"), _sw("B", "2"), _sw("C", "3"), gone)
    base = [{"Codigo": "1", "Nome": "A"}, {"Codigo": "2", "Nome": "B"}, {"Codigo": "3", "Nome": "C"}]
    _rodar(db, _vista(*base))
    _rodar(db, _vista(*base, {"Codigo": "99", "Nome": "Saiu"}))
    assert _rows(db, id=gone["id"])[0]["vista_status"] == "ativo" and _rows(db, id=gone["id"])[0]["vista_ausente_em"] is None
    [a] = _rows(db, "corretor_avisos")
    assert a["status"] == "pendente" and any(n.get("tipo") == "voltou" for n in a["notas"])


def test_the_circuit_breaker_refuses_a_mass_disappearance(core):
    db = _db(*[_sw(f"B{n}", str(n)) for n in range(1, 7)])
    rel = _rodar(db, _vista({"Codigo": "1", "Nome": "B1"}))
    assert rel["ausentes_recusados"] is True and rel["ausentes"] == [] and _rows(db, "corretor_avisos") == []
    assert all(r["vista_status"] != "ausente" for r in _rows(db))


def test_an_empty_or_failed_roster_marks_nobody_missing(core):
    db = _db(_sw("A", "1"))
    assert _rodar(db, _vista())["ausentes"] == []                                        # empty roster = Vista silent
    adapter = _vista({"Codigo": "2", "Nome": "Z"})

    async def cai(**_k):
        raise RuntimeError("503")

    adapter.list_corretores = cai
    rel = _rodar(db, adapter)
    assert rel["status"] == "incompleto" and rel["ausentes"] == [] and _rows(db, "corretor_avisos") == [] and _rows(db)[0].get("vista_status") is None


def test_rejected_fields_fall_back_to_the_plain_roster_and_say_so(core):
    adapter = _vista({"Codigo": "16", "Nome": "Gilson"})
    original = adapter.list_corretores

    async def so_basico(*, page=1, page_size=50, fields=None):
        if fields:
            raise VistaFieldNotAvailable(["Creci"], "Campo Creci não está disponível", "/corretores/listar")
        return await original(page=page, page_size=page_size, fields=None)

    adapter.list_corretores = so_basico
    db = _db()
    rel = _rodar(db, adapter)
    assert rel["campos"] == "basico" and rel["criados"] == ["Gilson"] and any("rejeitados" in e for e in rel["erros"])


def test_dry_run_classifies_and_writes_nothing(core):
    db = _db(_sw("Gilson", "16"))
    rel = _rodar(db, _vista(GILSON, {"Codigo": "20", "Nome": "Nova"}), dry_run=True)
    assert rel["criados"] == ["Nova"] and len(_rows(db)) == 1 and _rows(db)[0].get("email") is None


def test_pagination_walks_every_page(core):
    db = _db()
    rel = _rodar(db, _vista(*[{"Codigo": str(n), "Nome": f"P{n}"} for n in range(1, 121)]))
    assert rel["total_vista"] == 120 and len(_rows(db)) == 120 and rel["chamadas"] == 3


def test_resolve_a_notice_by_a_human(core):
    gone = _sw("Saiu", "99")
    db = _db(_sw("A", "1"), _sw("B", "2"), _sw("C", "3"), gone)
    _rodar(db, _vista({"Codigo": "1", "Nome": "A"}, {"Codigo": "2", "Nome": "B"}, {"Codigo": "3", "Nome": "C"}))
    [a] = sync.listar_avisos(db, ORG)
    out = sync.resolver_aviso(db, ORG, a["id"], "ignorada", ADMIN, "já sabíamos")
    assert out["status"] == "ignorada" and sync.listar_avisos(db, ORG) == [] and len(_rows(db)) == 4
    with pytest.raises(ValueError):
        sync.resolver_aviso(db, ORG, a["id"], "restaurar")
    with pytest.raises(LookupError):
        sync.resolver_aviso(db, ORG, str(uuid4()), "ignorada")


# ─── the daily job ───────────────────────────────────────────────────────


def test_the_job_syncs_each_org_under_its_lease_and_skips_a_held_one():
    db = MockSupabaseClient()
    chamados, leases = [], []

    @contextmanager
    def lease(nome):
        leases.append(nome)
        yield not nome.endswith("busy")

    async def fake_sync(c, adapter, org):
        chamados.append(str(org))
        return {"status": "ok"}

    o1, o2 = str(uuid4()), "busy"
    rel = asyncio.run(job.corretores_vista_job(admin_factory=lambda: db, discover_fn=lambda _a: [o1], adapter_factory=lambda _o: object(), lease_fn=lease, sync_fn=fake_sync))
    assert chamados == [o1] and rel[o1] == {"status": "ok"} and leases == [f"corretores_vista_sync:{o1}"]
    rel = asyncio.run(job.corretores_vista_job(admin_factory=lambda: db, discover_fn=lambda _a: [str(uuid4())], adapter_factory=lambda _o: None, lease_fn=lease, sync_fn=fake_sync))
    assert rel == {}                                                                       # no credential: skipped, logged


def test_the_job_isolates_a_failing_org():
    db = MockSupabaseClient()

    @contextmanager
    def livre(_n):
        yield True

    async def boom(*_a):
        raise RuntimeError("vista")

    o = str(uuid4())
    rel = asyncio.run(job.corretores_vista_job(admin_factory=lambda: db, discover_fn=lambda _a: [o], adapter_factory=lambda _o: object(), lease_fn=livre, sync_fn=boom))
    assert rel[o] == {"erro": True}
