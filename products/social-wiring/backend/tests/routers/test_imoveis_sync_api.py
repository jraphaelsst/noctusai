"""`POST /api/imoveis/sync?modo=auto|listar|detalhes` (org admin, 202 + poll) and `GET /api/imoveis/sync/ultimo`."""
from __future__ import annotations

import asyncio

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.credential_resolvers import VISTA_PROVIDER
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.security.token_store import FakeCredentialStore

from app.services import vista_credenciais
from app.services.imoveis_service import ImovelSyncService
from tests.routers.test_julia_equipe_protecao import admin, member, override_settings_factory  # noqa: F401
from tests.services.test_imoveis_sync_detalhes import _Db, _linha
from tests.support.julia_world import ORG_ID

URL = "/api/imoveis/sync"
ULTIMO = "/api/imoveis/sync/ultimo"


class _ServicoSegurado(ImovelSyncService):
    """Holds the background run open until the test releases it, so "a run is going" is a fact the test
    controls, never a race against how fast the Fake answers (a no-change run is ~instant since the
    change-signal refresh)."""

    portao: "asyncio.Event | None" = None
    loop: "asyncio.AbstractEventLoop | None" = None

    async def _segurar(self) -> None:
        cls = type(self)
        cls.loop = asyncio.get_running_loop()
        cls.portao = cls.portao or asyncio.Event()
        await cls.portao.wait()

    async def sync(self, *a, **k):
        await self._segurar()
        return await super().sync(*a, **k)

    async def sync_detalhes(self, *a, **k):
        await self._segurar()
        return await super().sync_detalhes(*a, **k)


def _montar(scene, *, com_credencial=True, segurar=False):
    from app.dependencies import get_admin_client
    from app.main import app
    from app.routers.imoveis_router import get_core_for_sync, get_sync_service_factory

    db = _Db()
    db.set_table_data("imoveis", [_linha("CA0001", org=ORG_ID)])
    for t in ("imovel_registry", "imoveis_sync_execucoes", "vista_divergencias_config", "imovel_campo_conflitos"):
        db.set_table_data(t, [])
    store = FakeCredentialStore()
    if com_credencial:
        store.put(ORG_ID, VISTA_PROVIDER, {"base_url": "https://acme-rest.vistahost.com.br", "api_key": "k" * 24, "chave_final": "kkkk"})
    vista_credenciais.configure_store(lambda: store)

    def fabrica(client, adapter, **kw):  # the real adapter is never used: no network
        cls = _ServicoSegurado if segurar else ImovelSyncService
        return cls(client, FakeVistaAdapter(), duplicate_detector=lambda *a, **k: None, **kw)

    ov = {get_admin_client: lambda: db, get_core_for_sync: lambda: scene.w.root, get_sync_service_factory: lambda: fabrica}
    app.dependency_overrides.update(ov)
    scene.db = db
    yield scene
    loop = _ServicoSegurado.loop
    # The TestClient portal may already have closed its loop (the held run dies with it); release it only if open.
    if segurar and loop is not None and not loop.is_closed() and _ServicoSegurado.portao is not None:
        loop.call_soon_threadsafe(_ServicoSegurado.portao.set)
    _ServicoSegurado.portao = _ServicoSegurado.loop = None
    vista_credenciais.configure_store(None)
    for k in ov:
        app.dependency_overrides.pop(k, None)


@pytest.fixture
def cena(admin):  # noqa: F811
    yield from _montar(admin)


@pytest.fixture
def cena_em_andamento(admin):  # noqa: F811
    yield from _montar(admin, segurar=True)


@pytest.fixture
def cena_membro(member):  # noqa: F811
    yield from _montar(member)


@pytest.fixture
def cena_sem_credencial(admin):  # noqa: F811
    yield from _montar(admin, com_credencial=False)


class TestAuth:
    @pytest.mark.parametrize("method,url", [("post", URL), ("get", ULTIMO)])
    def test_no_session_is_strictly_401(self, cena, method, url):
        assert getattr(cena.tc, method)(url).status_code == 401

    def test_a_member_cannot_start_a_refresh(self, cena_membro):
        assert cena_membro.req("post", URL).status_code == 403
        assert cena_membro.db.table("imoveis_sync_execucoes").select("*").execute().data == []

    def test_a_member_can_read_the_last_run(self, cena_membro):
        assert cena_membro.req("get", ULTIMO).status_code == 200


class TestSync:
    def test_it_queues_the_run_and_returns_202_with_the_execution_id(self, cena):
        r = cena.req("post", f"{URL}?modo=detalhes&escopo=vitrine")
        assert r.status_code == 202
        d = r.json()
        assert d["status"] == "em_andamento" and d["ja_em_andamento"] is False and d["execucao_id"]
        [ex] = cena.db.table("imoveis_sync_execucoes").select("*").execute().data
        assert ex["origem"] == "manual" and ex["modo"] == "detalhes" and ex["escopo"] == "vitrine" and ex["iniciado_por"]

    def test_a_second_click_returns_the_running_one(self, cena_em_andamento):
        cena = cena_em_andamento
        a = cena.req("post", URL).json()
        b = cena.req("post", URL).json()
        assert b["execucao_id"] == a["execucao_id"] and b["ja_em_andamento"] is True
        assert len(cena.db.table("imoveis_sync_execucoes").select("*").execute().data) == 1

    @pytest.mark.parametrize("qs", ["?modo=nada", "?escopo=tudo"])
    def test_invalid_params_are_422(self, cena, qs):
        assert cena.req("post", URL + qs).status_code == 422

    def test_an_org_without_a_vista_credential_is_503(self, cena_sem_credencial):
        r = cena_sem_credencial.req("post", URL)
        assert r.status_code == 503 and "Vista não configurada para esta empresa" in r.text
        assert cena_sem_credencial.db.table("imoveis_sync_execucoes").select("*").execute().data == []


class TestUltimo:
    def test_no_run_yet_shows_the_mirror_timestamp(self, cena):
        d = cena.req("get", ULTIMO).json()
        assert d["execucao_id"] is None and d["em_andamento"] is False and d["sincronizado_em"] == "2026-10-23T00:00:00+00:00"

    def test_the_last_run_with_path_and_counts(self, cena):
        cena.db.set_table_data("imoveis_sync_execucoes", [
            {"id": "e1", "org_id": ORG_ID, "origem": "agendado", "modo": "auto", "status": "ok", "caminho": "listar",
             "iniciado_em": "2026-11-04T01:00:00+00:00", "finalizado_em": "2026-11-04T01:02:00+00:00", "relatorio": {"novos": 1}},
            {"id": "e2", "org_id": ORG_ID, "origem": "agendado", "modo": "auto", "status": "ok", "caminho": "detalhes",
             "iniciado_em": "2026-11-04T03:00:00+00:00", "finalizado_em": "2026-11-04T03:05:00+00:00",
             "relatorio": {"novos": 2, "atualizados": 30, "inalterados": 900, "removidos": 1, "falhas": 0, "chamadas": {"detalhes": 933, "sonda": 40}}},
            {"id": "x", "org_id": "00000000-0000-4000-8000-0000000000ff", "status": "ok", "iniciado_em": "2026-11-05T00:00:00+00:00"},
        ])
        d = cena.req("get", ULTIMO).json()
        assert d["execucao_id"] == "e2" and d["caminho"] == "detalhes" and d["status"] == "ok" and d["em_andamento"] is False
        assert (d["novos"], d["atualizados"], d["inalterados"], d["removidos"], d["falhas"]) == (2, 30, 900, 1, 0)
        assert d["chamadas"] == {"detalhes": 933, "sonda": 40}

    def test_a_running_run_is_flagged(self, cena_em_andamento):
        cena = cena_em_andamento
        cena.req("post", URL)
        assert cena.req("get", ULTIMO).json()["em_andamento"] is True
