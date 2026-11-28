"""`/api/julia/videos-prontos` (julia-videos-prontos-youtube S2): auth boundary (strict `== 401`), the org scope (a
submission of another org is a 404), the manual retry (202, 409 nao_retentavel). The service is the router's own
`get_videos_prontos_service` seam (fakes: `tests/support/julia_videos_prontos_fakes.py`); auth is the REAL chain over
a mocked session."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.services import julia_videos_prontos_service as svc
from tests.support.julia_videos_prontos_fakes import PASTA_A, ID_A, Video
from tests.support.julia_videos_prontos_fakes import World as VPWorld
from tests.support.julia_world import ORG_ID, OTHER_ORG_ID, World

BASE = "/api/julia/videos-prontos"
H = {"Authorization": "Bearer test-token"}
SEM = "00000000-0000-4000-8000-0000000000ff"


@pytest.fixture
def cena():
    world = World()
    world.core.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "member"}])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role="member")))
    vp = VPWorld(org=ORG_ID)
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.julia_videos_prontos_router import get_videos_prontos_service

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_videos_prontos_service] = lambda: vp.service
        yield TestClient(app), vp
        app.dependency_overrides.pop(get_videos_prontos_service, None)


def _falhou(vp: VPWorld) -> dict:
    vp.upload.pastas[ID_A] = [Video("ruim", "youtube", falhas=9)]
    vp.msg(f"ONE10898 {PASTA_A}")
    vp.relogio.avancar(8)
    vp.drenar()
    vp.relogio.avancar(120)
    vp.drenar()
    return vp.unica()


class TestAuth:
    @pytest.mark.parametrize("method,url", [("get", ""), ("post", f"/{SEM}/retry")])
    def test_no_token_is_exactly_401(self, cena, method, url):
        tc, _ = cena
        assert getattr(tc, method)(f"{BASE}{url}").status_code == 401


class TestListar:
    def test_lista_so_da_org(self, cena):
        tc, vp = cena
        row = _falhou(vp)
        vp.repo.rows["x"] = {**row, "id": "x", "org_id": OTHER_ORG_ID}
        r = tc.get(BASE, headers=H)
        assert r.status_code == 200
        assert [s["id"] for s in r.json()["data"]] == [row["id"]]


class TestRetry:
    def test_retry_manual_agendado(self, cena):
        tc, vp = cena
        row = _falhou(vp)
        assert row["status"] == svc.FALHOU
        r = tc.post(f"{BASE}/{row['id']}/retry", headers=H)
        assert r.status_code == 202, r.text
        assert r.json()["data"] == {"submissao_id": row["id"], "tentativa": 2, "agendado": True}
        assert vp.jobs.do_tipo(svc.JOB_RETRY)[-1]["payload"]["ator_id"] == TEST_USER_ID

    def test_concluida_nao_retentavel_409(self, cena):
        tc, vp = cena
        vp.upload.pastas[ID_A] = [Video("ok", "youtube")]
        vp.msg(f"ONE10898 {PASTA_A}")
        vp.relogio.avancar(8)
        vp.drenar()
        r = tc.post(f"{BASE}/{vp.unica()['id']}/retry", headers=H)
        assert r.status_code == 409 and r.json()["error"]["code"] == "nao_retentavel"

    def test_de_outra_org_404(self, cena):
        tc, vp = cena
        row = _falhou(vp)
        vp.repo.rows[row["id"]]["org_id"] = OTHER_ORG_ID
        r = tc.post(f"{BASE}/{row['id']}/retry", headers=H)
        assert r.status_code == 404 and r.json()["error"]["code"] == "nao_encontrada"
