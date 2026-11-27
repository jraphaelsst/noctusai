"""`GET/PUT/DELETE /api/imoveis/{codigo}/video-youtube` (migration 371): the manual set / edit / clear of the imóvel's published
YouTube video. Strict `== 401` without a session; any org member may read and write (tier org); a PUT takes a URL or an id
(`origem = manual`, replace semantics, history written); 422 for a bad link or a Short; 404 for an unknown código. Seams: the
routes' own `Depends` (service built on the mock DB + FakeVistaAdapter); nothing of ours is patched."""
from __future__ import annotations

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter

from tests.routers.test_julia_equipe_protecao import member, override_settings_factory  # noqa: F401
from tests.support.julia_world import ORG_ID

COD = "CA0001"
URL = f"/api/imoveis/{COD}/video-youtube"
V1 = "dQw4w9WgXcQ"
V2 = "9bZkp7q19f0"


@pytest.fixture
def cena(member):  # noqa: F811
    from app.main import app
    from app.routers.imovel_video_youtube_router import get_imovel_video_youtube_service
    from app.services.imovel_video_youtube_service import build_imovel_video_youtube_service

    sw = member.w.sw
    sw.set_table_data("imovel_registry", [{"org_id": ORG_ID, "codigo_canonical": COD}])
    for t in ("imovel_video_youtube", "imovel_historico", "vista_divergencias_config"):
        sw.set_table_data(t, [])
    member.vista = FakeVistaAdapter(imoveis={COD: Imovel(codigo=COD)})
    app.dependency_overrides[get_imovel_video_youtube_service] = lambda: build_imovel_video_youtube_service(
        sw, vista_provider=lambda _org: member.vista)
    yield member
    app.dependency_overrides.pop(get_imovel_video_youtube_service, None)


class TestAuth:
    @pytest.mark.parametrize("method", ["get", "put", "delete"])
    def test_no_session_is_strictly_401(self, cena, method):
        kw = {"json": {"youtube": V1}} if method == "put" else {}
        assert getattr(cena.tc, method)(URL, **kw).status_code == 401


class TestFluxo:
    def test_empty_then_put_url_then_replace_then_delete(self, cena):
        assert cena.req("get", URL).json() == {"data": None}
        r = cena.req("put", URL, {"youtube": f"https://www.youtube.com/watch?v={V1}"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert (d["codigo"], d["youtube_video_id"], d["youtube_url"], d["origem"]) == (
            COD, V1, f"https://www.youtube.com/watch?v={V1}", "manual")
        assert d["definido_por"]
        r = cena.req("put", URL, {"youtube": V2, "motivo": "vídeo novo do imóvel"})
        assert r.status_code == 200 and cena.req("get", URL).json()["data"]["youtube_video_id"] == V2
        hist = cena.w.sw.table("imovel_historico").select("*").execute().data
        assert [h["acao"] for h in hist] == ["video_youtube_definido", "video_youtube_definido"]
        assert hist[1]["valor_anterior"].endswith(V1) and hist[1]["detalhe"] == "vídeo novo do imóvel"
        assert cena.vista.atualizacoes == []  # the org's Vista-edit switch is off
        r = cena.req("delete", URL, params={"motivo": "vídeo errado"})
        assert r.status_code == 200 and r.json()["data"]["youtube_video_id"] == V2
        assert cena.req("get", URL).json() == {"data": None}

    @pytest.mark.parametrize("valor", [f"https://youtube.com/shorts/{V1}", "não é link"])
    def test_a_short_or_garbage_is_422(self, cena, valor):
        assert cena.req("put", URL, {"youtube": valor}).status_code == 422
        assert cena.w.sw.table("imovel_video_youtube").select("*").execute().data == []

    def test_unknown_field_is_422(self, cena):
        assert cena.req("put", URL, {"youtube": V1, "origem": "julia"}).status_code == 422

    def test_unknown_codigo_is_404(self, cena):
        assert cena.req("put", "/api/imoveis/XX9999/video-youtube", {"youtube": V1}).status_code == 404
