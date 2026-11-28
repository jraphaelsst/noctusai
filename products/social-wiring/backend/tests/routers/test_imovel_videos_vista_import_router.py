"""`POST/GET /api/imoveis/videos-youtube/importar-vista` (S3): the bulk import of Vista's videos into `imovel_video_youtube`.

Tier PLATFORM: strict `== 401` without a session, 403 for an org owner who is not a platform admin. A POST returns 202 + the run id
and hands the run to the background (the scheduler seam keeps the coroutine; the test drives it, then polls the status route); dry
run by default (zero writes); 503 for an org without a Vista credential, before anything is queued; a second POST while a run is
going returns the running one. Seams: the routes' own `Depends`; nothing of ours is patched."""
from __future__ import annotations

import asyncio
import contextlib

import pytest
from fastapi import HTTPException
from noctusai_lib.integrations.vista import FakeVistaAdapter

from app.services import imovel_videos_vista_import_service as imp
from tests.routers.test_julia_equipe_protecao import admin, override_settings_factory, platform  # noqa: F401
from tests.support.julia_world import ORG_ID

URL = "/api/imoveis/videos-youtube/importar-vista"
V1 = "dQw4w9WgXcQ"


@contextlib.contextmanager
def _lease_ok(*_a, **_k):
    yield True


def _montar(scene, *, vista=True):
    from app.dependencies import get_admin_client
    from app.main import app
    from app.modules.imovel_hub.deps import get_imovel_hub_client
    from app.routers.imovel_videos_vista_import_router import get_import_agendador, get_import_lease, get_import_vista_provider

    sw = scene.w.sw
    sw.set_table_data("imovel_registry", [{"org_id": ORG_ID, "codigo_canonical": c, "codigo_display": c} for c in ("CA0001", "CA0002")])
    for t in ("imovel_video_youtube", "imovel_historico", "vista_divergencias_config"):
        sw.set_table_data(t, [])
    fake = FakeVistaAdapter()
    fake.add_imovel_videos("CA0001", [{"VideoCodigo": "1", "Video": V1, "Tipo": "youtube", "Destaque": "Sim"}])

    def provider(_org):
        if not vista:
            raise HTTPException(503, detail="Vista não configurada para esta empresa")
        return fake

    scene.pendentes = []
    imp.EXECUCOES._por_id.clear()  # the process-wide registry: each test starts with no run
    ov = {get_imovel_hub_client: lambda: sw, get_admin_client: lambda: scene.w.admin, get_import_lease: lambda: _lease_ok,
          get_import_vista_provider: lambda: provider, get_import_agendador: lambda: scene.pendentes.append}
    app.dependency_overrides.update(ov)
    scene.vista = fake
    yield scene
    for coro in scene.pendentes:
        coro.close()
    imp.EXECUCOES._por_id.clear()
    for k in ov:
        app.dependency_overrides.pop(k, None)


@pytest.fixture
def cena(platform):  # noqa: F811
    yield from _montar(platform)


@pytest.fixture
def cena_dono(admin):  # noqa: F811
    yield from _montar(admin)


@pytest.fixture
def cena_sem_vista(platform):  # noqa: F811
    yield from _montar(platform, vista=False)


def _drenar(scene) -> None:
    while scene.pendentes:
        asyncio.run(scene.pendentes.pop(0))


class TestAuth:
    @pytest.mark.parametrize("method,url", [("post", URL), ("get", URL), ("get", f"{URL}/00000000-0000-4000-8000-000000000001")])
    def test_no_session_is_strictly_401(self, cena, method, url):
        assert getattr(cena.tc, method)(url, **({"json": {}} if method == "post" else {})).status_code == 401

    def test_an_org_owner_who_is_not_a_platform_admin_is_403(self, cena_dono):
        assert cena_dono.req("post", URL, {}).status_code == 403
        assert cena_dono.pendentes == []


class TestImportar:
    def test_dry_run_by_default_202_then_the_status_has_the_report_and_nothing_was_written(self, cena):
        r = cena.req("post", URL, {})
        assert r.status_code == 202
        d = r.json()["data"]
        assert d["dry_run"] is True and d["status"] == "em_andamento" and d["ja_em_andamento"] is False and d["org_id"] == ORG_ID
        _drenar(cena)
        s = cena.req("get", f"{URL}/{d['execucao_id']}").json()["data"]
        assert s["status"] == "concluida" and s["contagens"]["criaria"] == 1 and s["contagens"]["sem_video"] == 1
        assert [x["codigo"] for x in s["linhas"]] == ["CA0001"] and s["linhas"][0]["youtube_video_id"] == V1
        todos = cena.req("get", f"{URL}/{d['execucao_id']}", params={"resultados": "todos"}).json()["data"]
        assert todos["linhas_total"] == 2
        assert cena.w.sw.table("imovel_video_youtube").select("*").execute().data == []
        assert [x["execucao_id"] for x in cena.req("get", URL).json()["data"]] == [d["execucao_id"]]

    def test_a_real_run_writes_origem_vista_and_never_vista(self, cena):
        d = cena.req("post", URL, {"dry_run": False, "codigos": ["ca0001"]}).json()["data"]
        _drenar(cena)
        assert cena.req("get", f"{URL}/{d['execucao_id']}").json()["data"]["contagens"]["criados"] == 1
        [row] = cena.w.sw.table("imovel_video_youtube").select("*").execute().data
        assert (row["codigo"], row["youtube_video_id"], row["origem"]) == ("CA0001", V1, "vista")
        assert cena.vista.atualizacoes == []

    def test_a_second_post_returns_the_running_one(self, cena):
        a = cena.req("post", URL, {}).json()["data"]
        b = cena.req("post", URL, {"dry_run": False}).json()["data"]
        assert b["execucao_id"] == a["execucao_id"] and b["ja_em_andamento"] is True and len(cena.pendentes) == 1

    def test_no_vista_credential_is_503_and_nothing_is_queued(self, cena_sem_vista):
        r = cena_sem_vista.req("post", URL, {})
        assert r.status_code == 503 and cena_sem_vista.pendentes == []

    @pytest.mark.parametrize("corpo", [{"limite": 0}, {"modo": "x"}, {"dry_run": "talvez"}])
    def test_a_bad_body_is_422(self, cena, corpo):
        assert cena.req("post", URL, corpo).status_code == 422

    def test_an_unknown_run_is_404(self, cena):
        assert cena.req("get", f"{URL}/00000000-0000-4000-8000-000000000001").status_code == 404
