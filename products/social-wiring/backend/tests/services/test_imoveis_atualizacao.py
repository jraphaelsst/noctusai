"""One refresh RUN (`imoveis_atualizacao_service.executar`): the auto strategy (listar first, per-code fallback when listar is
silent), the persisted report, the once-a-day admin notice, single flight, the tiered scope."""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from noctusai_lib.domain.real_estate import Imovel, ImovelPage
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.integrations.vista.client import VistaNotFound
from noctusai_lib.testing import MockSupabaseClient

from app.services import imoveis_atualizacao_service as svc
from app.services.imoveis_service import ImovelSyncService
from tests.services.test_imoveis_sync_detalhes import _db as _db_base, _linha, _reg

ORG = uuid4()


def _db(mirror=True):
    db = _db_base(mirror=[_linha("CA0001", org=ORG)] if mirror else [], registry=[_reg("CA0001", org=ORG)] if mirror else [])
    db.set_table_data("imoveis_sync_execucoes", [])
    return db


def _fabrica(client, adapter, **kw):
    return ImovelSyncService(client, adapter, duplicate_detector=lambda *a, **k: None, **kw)


@contextlib.contextmanager
def _lease(*_a, **_k):
    yield True


def _vista(listar_vazio=False):
    class _A(FakeVistaAdapter):
        async def list_imoveis(self, **kw):
            if listar_vazio:
                raise VistaNotFound(404, "A pesquisa não retornou resultados", "/imoveis/listar")
            return await super().list_imoveis(**kw)

    a = _A()
    a.add_imovel(Imovel(codigo="CA0001", status="Venda", valor_venda=1.0, data_atualizacao=datetime(2026, 11, 3).date()))
    return a


class _Core(MockSupabaseClient):
    pass


def _core():
    c = _Core()
    c.set_table_data("noctus_users", [{"id": "adm", "org_id": str(ORG), "org_role": "admin"}, {"id": "mem", "org_id": str(ORG), "org_role": "member"}])
    c.set_table_data("notifications", [])
    return c


def _run(db, adapter, core=None, **kw):
    kw.setdefault("sonda_max_falhas", 2)  # a small probe: the default 40 misses per prefix is paced and slow
    return asyncio.run(svc.executar(db, adapter, ORG, sync_factory=_fabrica, lease_fn=_lease, core=core, **kw))


def _execucoes(db):
    return db.table("imoveis_sync_execucoes").select("*").execute().data


def test_auto_uses_listar_when_it_answers_and_the_per_code_walk_stops():
    db = _db()
    res = _run(db, _vista(), _core())
    assert res["status"] == "ok" and res["caminho"] == "listar"
    [ex] = _execucoes(db)
    assert ex["caminho"] == "listar" and ex["status"] == "ok" and ex["finalizado_em"] and ex["relatorio"]["caminho"] == "listar"
    assert "detalhes" not in ex["relatorio"]["chamadas"] or ex["relatorio"]["chamadas"]["detalhes"] <= 1  # enrichment only, no walk
    assert ex["aviso_listar_vazio"] is False


def test_auto_falls_back_to_the_per_code_refresh_when_listar_is_silent_and_says_so():
    db = _db()
    core = _core()
    res = _run(db, _vista(listar_vazio=True), core, escopo="todos")
    assert res["status"] == "ok" and res["caminho"] == "detalhes"
    [ex] = _execucoes(db)
    r = ex["relatorio"]
    assert ex["caminho"] == "detalhes" and r["listar"]["status"] == "listar_vazio" and r["caminho"] == "detalhes" and r["escopo"] == "todos"
    assert r["chamadas"]["detalhes"] == 1 and r["atualizados"] == 1 and {"novos", "inalterados", "removidos", "falhas"} <= set(r)
    assert ex["aviso_listar_vazio"] is True
    avisos = core.table("notifications").select("*").execute().data
    assert len(avisos) == 1 and avisos[0]["metadata"]["tipo"] == svc.KIND_AVISO and "imóvel a imóvel" in avisos[0]["message"]


def test_the_admin_notice_is_raised_once_a_day():
    db = _db()
    core = _core()
    _run(db, _vista(listar_vazio=True), core)
    _run(db, _vista(listar_vazio=True), core)
    flags = [e["aviso_listar_vazio"] for e in sorted(_execucoes(db), key=lambda e: e["iniciado_em"])]
    assert sorted(flags) == [False, True]
    assert svc.avisar_listar_vazio(db, core, ORG) is False  # already sent in the last 24h
    # a notice older than a day does not suppress a new one
    velhas = [{**e, "iniciado_em": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()} for e in _execucoes(db)]
    db.set_table_data("imoveis_sync_execucoes", velhas)
    assert svc.avisar_listar_vazio(db, core, ORG) is True


def test_modo_listar_never_falls_back():
    db = _db()
    res = _run(db, _vista(listar_vazio=True), _core(), modo="listar")
    assert res["status"] == "listar_vazio" and res["caminho"] == "listar"


def test_modo_detalhes_skips_listar_entirely():
    db = _db()
    res = _run(db, _vista(listar_vazio=False), _core(), modo="detalhes")
    assert res["caminho"] == "detalhes" and "listar" not in res["relatorio"]["chamadas"]


def test_single_flight_a_second_request_gets_the_running_one():
    db = _db()
    linha, nova = svc.iniciar(db, ORG, origem="manual", modo="auto", escopo="vitrine", user_id="u")
    assert nova is True and linha["status"] == "em_andamento"
    outra, nova2 = svc.iniciar(db, ORG, origem="manual", modo="auto", escopo="vitrine", user_id="u2")
    assert nova2 is False and outra["id"] == linha["id"] and len(_execucoes(db)) == 1
    # a run stuck for more than the lease TTL no longer blocks
    db.set_table_data("imoveis_sync_execucoes", [{**_execucoes(db)[0], "iniciado_em": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()}])
    assert svc.iniciar(db, ORG, origem="manual", modo="auto", escopo="vitrine", user_id=None)[1] is True


def test_executar_returns_the_running_run_instead_of_starting_another():
    db = _db()
    linha, _ = svc.iniciar(db, ORG, origem="manual", modo="auto", escopo="vitrine", user_id=None)
    out = _run(db, _vista(), _core())
    assert out["id"] == linha["id"] and out["status"] == "em_andamento" and len(_execucoes(db)) == 1


def test_a_lost_lease_is_recorded_as_ignorada():
    @contextlib.contextmanager
    def negado(*_a, **_k):
        yield False

    db = _db()
    res = asyncio.run(svc.executar(db, _vista(), ORG, sync_factory=_fabrica, lease_fn=negado, core=_core()))
    assert res["status"] == "ignorada" and _execucoes(db)[0]["status"] == "ignorada"


def test_a_crash_is_persisted_as_falhou_not_lost():
    class _Quebra:
        async def sync(self, *a, **k):
            raise RuntimeError("boom")

    db = _db()
    res = asyncio.run(svc.executar(db, _vista(), ORG, sync_factory=lambda *a, **k: _Quebra(), lease_fn=_lease, core=_core()))
    assert res["status"] == "falhou" and _execucoes(db)[0]["relatorio"]["erro"] == "RuntimeError" and _execucoes(db)[0]["finalizado_em"]


def test_the_scheduled_scope_sweeps_the_rest_once_a_day():
    db = _db()
    assert svc.escopo_do_agendamento(db, ORG, 86400) == "todos"
    _run(db, _vista(listar_vazio=True), _core(), escopo="todos")
    assert svc.escopo_do_agendamento(db, ORG, 86400) == "vitrine"
    assert svc.escopo_do_agendamento(db, ORG, 0) == "todos"  # interval elapsed


@pytest.mark.parametrize("modo,escopo", [("x", "vitrine"), ("auto", "y")])
def test_invalid_mode_or_scope_is_refused(modo, escopo):
    with pytest.raises(ValueError):
        _run(_db(), _vista(), None, modo=modo, escopo=escopo)
