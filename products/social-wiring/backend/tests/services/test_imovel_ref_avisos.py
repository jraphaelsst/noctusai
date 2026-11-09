"""Ref-divergence notices: the Vista sync NEVER erases our data, it WARNS (migration 333). Per-code refresh, listar sweep, discovery,
sticky pause, reappearance, the circuit breaker, the campaign card and the endpoints. FakeVistaAdapter + MockSupabaseClient."""
from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

import pytest
from noctusai_lib.domain.real_estate import Imovel, ImovelPage
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.testing import MockSupabaseClient

from app.services import imovel_ref_avisos as avisos
from app.services.imoveis_service import ImovelSyncService, _imovel_to_row
from tests.services.test_imoveis_sync_detalhes import _Db, _linha, _reg

ORG = uuid4()
ADMIN = str(uuid4())


@pytest.fixture
def core(monkeypatch):
    c = MockSupabaseClient()
    c.set_table_data("noctus_users", [{"id": ADMIN, "org_id": str(ORG), "org_role": "owner"}])
    c.set_table_data("notifications", [])
    monkeypatch.setattr("app.database.get_core_client", lambda: c)
    return c


def _imovel(codigo, **kw):
    return Imovel(codigo=codigo, status="Venda", valor_venda=200.0, data_atualizacao=date(2026, 11, 2), exibir_no_site=True, **kw)


def _db(*codigos, extra_mirror=()):
    db = _Db()
    db.set_table_data("imoveis", [{**_linha(c, org=ORG), "codigo_norm": c.upper()} for c in codigos] + list(extra_mirror))
    db.set_table_data("imovel_registry", [_reg(c, org=ORG) for c in codigos])
    for t in ("vista_divergencias_config", "imovel_campo_conflitos", "imovel_captacao", "imovel_dados", "julia_proprietarios_contatos", "imovel_ref_avisos"):
        db.set_table_data(t, [])
    return db


def _svc(db, adapter):
    return ImovelSyncService(db, adapter, duplicate_detector=lambda *a, **k: None)


def _vista(*codigos):
    a = FakeVistaAdapter()
    for c in codigos:
        a.add_imovel(_imovel(c))
    return a


def _rows(db, t, **eq):
    return [r for r in db.table(t).select("*").execute().data if all(r.get(k) == v for k, v in eq.items())]


def _detalhes(svc, **kw):
    return asyncio.run(svc.sync_detalhes(ORG, escopo="todos", descobrir=False, forcar=True, **kw))


# ─── a ref we have, Vista does not ───────────────────────────────────────


def test_a_ref_vista_no_longer_has_is_paused_and_noticed_with_every_datum_kept(core):
    db = _db("AP0001", "AP0002", "AP0003")
    rep = _detalhes(_svc(db, _vista("AP0001", "AP0002")))                     # AP0003 gone from Vista
    assert rep.removidos == 1
    [m] = _rows(db, "imoveis", codigo="AP0003")
    assert m["exibir_no_site"] is False and m["foto_destaque"] and m["valor_venda"] == 100.0       # paused, NOTHING erased
    assert len(_rows(db, "imoveis")) == 3 and _rows(db, "imovel_registry", codigo_canonical="AP0003")[0]["ativo_no_vista"] is False
    [a] = _rows(db, "imovel_ref_avisos")
    assert a["codigo_canonical"] == "AP0003" and a["tipo"] == "ref_sumiu_no_vista" and a["status"] == "pendente" and a["exibir_antes"] is True
    [n] = core.table("notifications").select("*").execute().data
    assert n["metadata"]["tipo"] == "ref_sumiu_no_vista" and "AP0003" in n["message"] and a["notificado_em"]


def test_one_in_app_warning_per_run_not_per_code_and_none_on_a_rerun(core):
    db = _db("AP0001", "AP0002", "AP0003", "AP0004", extra_mirror=())
    _detalhes(_svc(db, _vista("AP0001", "AP0002")))
    assert len(core.table("notifications").select("*").execute().data) == 1 and len(_rows(db, "imovel_ref_avisos")) == 2
    _detalhes(_svc(db, _vista("AP0001", "AP0002")))                           # still gone: no second notice, no second warning
    assert len(_rows(db, "imovel_ref_avisos")) == 2 and len(core.table("notifications").select("*").execute().data) == 1


def test_the_circuit_breaker_still_refuses_a_mass_removal_no_pause_no_notice(core):
    codigos = [f"AP{n:04d}" for n in range(80)]
    db = _db(*codigos)
    rep = _detalhes(_svc(db, _vista()))                                       # Vista answers "not found" for ALL 80
    assert rep.status == "removidos_excessivos" and rep.removidos == 0
    assert _rows(db, "imovel_ref_avisos") == [] and all(r["exibir_no_site"] is True for r in _rows(db, "imoveis"))
    assert core.table("notifications").select("*").execute().data == []


def test_a_transport_failure_is_never_a_disappearance(core):
    db = _db("AP0001")
    adapter = _vista("AP0001")

    async def cai(_c):
        raise RuntimeError("503")

    adapter.refresh_imovel = cai
    _detalhes(_svc(db, adapter))
    assert _rows(db, "imovel_ref_avisos") == [] and _rows(db, "imoveis")[0]["exibir_no_site"] is True


def test_the_per_code_intake_refresh_pauses_a_ref_it_holds_but_not_one_it_never_had(core):
    db = _db("AP0001")
    svc = _svc(db, _vista())
    asyncio.run(svc.refresh_codigo(ORG, "AP0001"))
    asyncio.run(svc.refresh_codigo(ORG, "ZZ9999"))                            # a typo'd REF: no mirror row, no notice
    assert [a["codigo_canonical"] for a in _rows(db, "imovel_ref_avisos")] == ["AP0001"]
    assert _rows(db, "imoveis", codigo="AP0001")[0]["exibir_no_site"] is False


# ─── sticky pause + reappearance ─────────────────────────────────────────


def test_a_code_that_reappears_in_vista_stays_paused_and_the_notice_gets_a_note(core):
    db = _db("AP0001", "AP0002")
    _detalhes(_svc(db, _vista("AP0001")))                                     # AP0002 gone -> paused
    _detalhes(_svc(db, _vista("AP0001", "AP0002")))                           # AP0002 is back in Vista (exibir_no_site=True there)
    assert _rows(db, "imoveis", codigo="AP0002")[0]["exibir_no_site"] is False                    # NOT silently restored
    [a] = _rows(db, "imovel_ref_avisos")
    assert a["status"] == "pendente" and any(n.get("tipo") == "reapareceu" for n in a["notas"])


def test_the_listar_path_also_keeps_a_paused_ref_paused(core):
    db = _db("AP0001")
    db.set_table_data("imovel_ref_avisos", [{"id": str(uuid4()), "org_id": str(ORG), "codigo_canonical": "AP0001", "tipo": "ref_sumiu_no_vista",
                                             "status": "confirmada_sumiu", "exibir_antes": True, "notas": [], "created_at": "2026-11-01T00:00:00+00:00"}])
    a = _vista("AP0001")
    rep = asyncio.run(_svc(db, a).sync(ORG, with_detalhes=False))
    assert rep.upserted >= 1 and _rows(db, "imoveis", codigo="AP0001")[0]["exibir_no_site"] is False
    [n] = _rows(db, "imovel_ref_avisos")
    assert n["status"] == "pendente"                                         # confirmed-gone REOPENS: a new fact needs a human


# ─── a ref Vista has, we did not ─────────────────────────────────────────


def test_a_new_ref_is_created_on_our_side_and_recorded_informationally_once_per_run(core):
    db = _db("AP0001")
    a = _vista("AP0001", "NEW001", "NEW002")
    rep = asyncio.run(_svc(db, a).sync_detalhes(ORG, escopo="todos", descobrir=True, forcar=True,
                                                descobridores=[lambda adapter, conhecidos, report: _achados(a, conhecidos)]))
    assert {r["codigo"] for r in _rows(db, "imoveis")} >= {"AP0001", "NEW001", "NEW002"} and rep.novos == 2
    novas = _rows(db, "imovel_ref_avisos", tipo="ref_nova_no_vista")
    assert sorted(r["codigo_canonical"] for r in novas) == ["NEW001", "NEW002"]
    [n] = core.table("notifications").select("*").execute().data              # ONE warning for the batch
    assert n["metadata"]["tipo"] == "ref_nova_no_vista" and "NEW001" in n["message"]


async def _achados(adapter, conhecidos):
    return {c: await adapter.refresh_imovel(c) for c in ("NEW001", "NEW002") if c not in conhecidos}


def test_the_first_ever_import_of_an_org_does_not_flood_new_ref_notices(core):
    db = _db()                                                                # empty mirror
    asyncio.run(_svc(db, _vista("AP0001", "AP0002")).sync(ORG, with_detalhes=False))
    assert _rows(db, "imovel_ref_avisos") == [] and core.table("notifications").select("*").execute().data == []


def test_the_intake_of_a_property_we_never_had_records_a_new_ref_notice(core):
    db = _db("AP0001")
    asyncio.run(_svc(db, _vista("AP0001", "NEW009")).refresh_codigo(ORG, "NEW009"))
    assert [a["codigo_canonical"] for a in _rows(db, "imovel_ref_avisos", tipo="ref_nova_no_vista")] == ["NEW009"]


# ─── resolutions ─────────────────────────────────────────────────────────


def _um_sumido(core):
    db = _db("AP0001", "AP0002")
    _detalhes(_svc(db, _vista("AP0001")))
    return db, _rows(db, "imovel_ref_avisos")[0]


def test_restore_unpauses_and_clears_in_one_step(core):
    db, a = _um_sumido(core)
    out = avisos.resolver(db, ORG, a["id"], "restaurar", user_id=ADMIN, nota="foi engano")
    assert out["status"] == "restaurada" and _rows(db, "imoveis", codigo="AP0002")[0]["exibir_no_site"] is True
    assert avisos.codigos_pausados(db, ORG) == set()


def test_confirm_gone_stays_paused_and_is_resolved_never_auto_unpaused(core):
    db, a = _um_sumido(core)
    out = avisos.resolver(db, ORG, a["id"], "confirmar_sumiu", user_id=ADMIN)
    assert out["status"] == "confirmada_sumiu" and out["resolvido_em"]
    assert _rows(db, "imoveis", codigo="AP0002")[0]["exibir_no_site"] is False and avisos.codigos_pausados(db, ORG) == {"AP0002"}
    _detalhes(_svc(db, _vista("AP0001")))                                     # still gone: no new notice, still paused
    assert len(_rows(db, "imovel_ref_avisos")) == 1


def test_a_resolution_must_fit_the_notice_type(core):
    db, a = _um_sumido(core)
    with pytest.raises(avisos.AcaoInvalida):
        avisos.resolver(db, ORG, a["id"], "ciente")
    with pytest.raises(LookupError):
        avisos.resolver(db, ORG, str(uuid4()), "restaurar")


# ─── the campaign card never sends a paused imóvel ───────────────────────


def test_a_paused_imovel_is_dropped_from_the_campanha_codes(core):
    from app.modules.meta_ads.services import campanha_resolucao as cr

    db, _a = _um_sumido(core)
    reg = {r["codigo_canonical"]: r["id"] if r.get("id") else str(uuid4()) for r in _rows(db, "imovel_registry")}
    db.set_table_data("imovel_registry", [{**r, "id": reg[r["codigo_canonical"]]} for r in _rows(db, "imovel_registry")])
    db.set_table_data("campanha_imoveis", [{"org_id": str(ORG), "campanha_id": "c1", "imovel_ref_id": v} for v in reg.values()])
    assert cr._codigos_da_campanha(db, ORG, "c1") == ["AP0001"]


# ─── endpoints ───────────────────────────────────────────────────────────


def test_the_endpoints_list_restore_and_resolve(core, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user_org_unified
    from app.modules.leads.deps import get_leads_client
    from app.modules.leads.routers import ad_lead_intake as r

    db, a = _um_sumido(core)
    monkeypatch.setattr(r, "require_org_admin_for", lambda *x, **k: None)
    from fastapi.responses import JSONResponse
    from noctusai_lib.primitives.exceptions import AppException

    app = FastAPI()
    app.add_exception_handler(AppException, lambda _req, e: JSONResponse({"error": {"code": e.code}}, status_code=e.status_code))
    app.include_router(r.router)
    app.dependency_overrides[get_current_user_org_unified] = lambda: (type("U", (), {"id": ADMIN})(), "tok", str(ORG))
    app.dependency_overrides[get_leads_client] = lambda: db
    c = TestClient(app)
    lista = c.get("/api/leads/ad-intake/ref-avisos", params={"tipo": "ref_sumiu_no_vista"}).json()["data"]
    assert lista["total"] == 1 and lista["items"][0]["codigo_canonical"] == "AP0002"
    assert c.post(f"/api/leads/ad-intake/ref-avisos/{a['id']}/resolver", json={"acao": "ciente"}).status_code == 422
    ok = c.post(f"/api/leads/ad-intake/ref-avisos/{a['id']}/restaurar", json={"nota": "ok"}).json()["data"]
    assert ok["status"] == "restaurada" and _rows(db, "imoveis", codigo="AP0002")[0]["exibir_no_site"] is True
    assert c.post(f"/api/leads/ad-intake/ref-avisos/{uuid4()}/restaurar").status_code == 404
