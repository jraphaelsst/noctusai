"""Lais wave 13 -- GET /api/lais/avaliacoes (+ /config): KPIs of the month, the 1..5 distribution, mean, total, latest
reviews, the `configurado` flags, A7 on the asks, admin-only config, strict `== 401`. Seams: mock DB through the
router's DI getters + the product's `FakeReviewsProvider`; real auth chain over a mocked session."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.services import lais_avaliacoes_service as av
from app.services.lais_reviews_provider import FakeReviewsProvider, NaoConfiguradoReviews, Review

from tests.support.lais_world import ADMIN_ID, CONNECTION_ID, CORRETOR_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
BASE = "/api/lais/avaliacoes"
MES = "2026-10"
LINK = "https://g.page/r/exemplo/review"


class Scene:
    def __init__(self, tc, world, provider):
        self.tc, self.w, self.provider = tc, world, provider

    def call(self, method, url, body=None, headers=H):
        kw = {"json": body} if body is not None else {}
        return getattr(self.tc, method)(url, headers=headers, **kw)

    def contato(self, n, *, responsavel=None, org=ORG_ID):
        row = {"id": f"00000000-0000-4000-8000-0000000c{n:04d}", "org_id": org, "connection_id": CONNECTION_ID,
               "chat_id": f"551190000{n:04d}@c.us", "telefone_e164": f"+551190000{n:04d}", "nome": f"Pessoa {n}",
               "operacao": "venda", "slots": {}, "gen": 0, "status_envio": "nao_pronto", "canal": "whatsapp",
               "responsavel_user_id": responsavel, "created_at": "2026-10-01T12:00:00+00:00"}
        return self.w.sw.table("lais_contatos").insert(row).execute().data[0]

    def pedido(self, contato, dia=10, status="enviado"):
        self.w.sw.table(av.T_PEDIDOS).insert({
            "id": str(uuid4()), "org_id": contato["org_id"], "contato_id": contato["id"], "status": status,
            "erro": "x" if status == "erro" else None, "enviado_at": f"2026-10-{dia:02d}T15:00:00+00:00"}).execute()

    def config(self, **over):
        self.w.sw.table(av.T_CONFIG).insert({"org_id": ORG_ID, "google_review_url": LINK, "gbp_location_id": None,
                                             "capi_ativo": False, "capi_pixel_id": None, **over}).execute()


def _scene(role, provider=None):
    world = World()
    for t in (av.T_CONFIG, av.T_PEDIDOS, av.T_CACHE):
        world.sw.set_table_data(t, [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"}, {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor"}, {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    prov = provider if provider is not None else NaoConfiguradoReviews()
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.lais_avaliacoes_router import get_avaliacoes_client, get_reviews_provider_factory

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_avaliacoes_client] = lambda: world.sw
        app.dependency_overrides[get_reviews_provider_factory] = lambda: (lambda org_id: prov)
        yield Scene(TestClient(app), world, prov)
        app.dependency_overrides.pop(get_avaliacoes_client, None)
        app.dependency_overrides.pop(get_reviews_provider_factory, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def member():
    yield from _scene("member")


def rv(i, nota, dia, mes=10):
    return Review(f"r{i}", f"Autor {i}", nota, f"texto {i}", datetime(2026, mes, dia, 12, tzinfo=timezone.utc), f"https://g.co/{i}")


class TestAuth:
    @pytest.mark.parametrize("method,url", [("get", BASE), ("get", f"{BASE}/config"), ("put", f"{BASE}/config")])
    def test_no_token_is_exactly_401(self, admin, method, url):
        assert admin.call(method, url, body={} if method == "put" else None, headers={}).status_code == 401


class TestPainel:
    def test_empty_shape_without_google_connected(self, admin):
        d = admin.call("get", f"{BASE}?mes={MES}").json()["data"]
        assert d == {"mes": MES, "pedidos_enviados": 0, "novas_avaliacoes": 0, "distribuicao": {str(n): 0 for n in range(1, 6)},
                     "media": None, "total": 0, "ultimas": [], "configurado": {"review_url": False, "gbp": False}}

    def test_kpis_distribution_mean_total_and_latest(self, admin):
        admin.config(gbp_location_id="accounts/1/locations/2")
        # NaoConfigurado by default: seed the cache directly
        for i, (nota, dia, mes) in enumerate([(5, 3, 10), (5, 9, 10), (4, 20, 10), (1, 25, 9)]):
            r = rv(i, nota, dia, mes)
            admin.w.sw.table(av.T_CACHE).insert({"id": str(uuid4()), "org_id": ORG_ID, "external_id": r.external_id, "autor": r.autor,
                                                 "nota": r.nota, "texto": r.texto, "publicado_at": r.publicado_at.isoformat(),
                                                 "link": r.link}).execute()
        c = admin.contato(1)
        admin.pedido(c, 10), admin.pedido(c, 11), admin.pedido(c, 12, status="erro")
        admin.pedido(admin.contato(2), 1)
        admin.w.sw.table(av.T_PEDIDOS).insert({"id": str(uuid4()), "org_id": ORG_ID, "contato_id": c["id"], "status": "enviado",
                                               "enviado_at": "2026-09-30T23:00:00+00:00"}).execute()  # September in SP: out
        d = admin.call("get", f"{BASE}?mes={MES}").json()["data"]
        assert d["pedidos_enviados"] == 3  # 2 + 1 of contato 2; the erro and the September ask are out
        assert d["novas_avaliacoes"] == 3 and d["total"] == 4
        assert d["distribuicao"] == {"1": 1, "2": 0, "3": 0, "4": 1, "5": 2} and d["media"] == 3.75
        assert [u["texto"] for u in d["ultimas"]] == ["texto 2", "texto 1", "texto 0", "texto 3"]
        assert set(d["ultimas"][0]) == {"autor", "data", "nota", "texto", "link"}
        assert d["configurado"] == {"review_url": True, "gbp": False}  # location set but Google not connected

    def test_gbp_flag_and_sync_when_a_provider_is_connected(self):
        prov = FakeReviewsProvider([rv(1, 5, 4), rv(2, 3, 5)])
        for scene in _scene("owner", prov):
            scene.config(gbp_location_id="accounts/1/locations/2")
            d = scene.call("get", f"{BASE}?mes={MES}").json()["data"]
            assert d["total"] == 2 and d["novas_avaliacoes"] == 2 and d["media"] == 4.0
            assert d["configurado"] == {"review_url": True, "gbp": True} and prov.chamadas == ["accounts/1/locations/2"]

    def test_a_provider_failure_still_renders_from_the_cache(self):
        for scene in _scene("owner", FakeReviewsProvider(erro=RuntimeError("down"))):
            scene.config(gbp_location_id="accounts/1/locations/2")
            assert scene.call("get", f"{BASE}?mes={MES}").status_code == 200

    @pytest.mark.parametrize("q", ["mes=2026-13", "mes=abc", "mes=2026-1"])
    def test_malformed_month_is_422(self, admin, q):
        r = admin.call("get", f"{BASE}?{q}")
        assert r.status_code == 422 and r.json()["error"]["code"] == "mes_invalido"

    def test_other_org_data_is_not_counted(self, admin):
        o = admin.contato(9, org=OTHER_ORG_ID)
        admin.pedido(o)
        admin.w.sw.table(av.T_CACHE).insert({"id": str(uuid4()), "org_id": OTHER_ORG_ID, "external_id": "x", "nota": 5,
                                             "publicado_at": "2026-10-05T12:00:00+00:00"}).execute()
        d = admin.call("get", f"{BASE}?mes={MES}").json()["data"]
        assert d["pedidos_enviados"] == 0 and d["total"] == 0


class TestA7:
    def test_member_counts_only_asks_to_own_contatos_admin_all(self, member):
        member.pedido(member.contato(1, responsavel=TEST_USER_ID))
        member.pedido(member.contato(2, responsavel=MEMBER_ID))
        assert member.call("get", f"{BASE}?mes={MES}").json()["data"]["pedidos_enviados"] == 1

    def test_admin_counts_all(self, admin):
        admin.pedido(admin.contato(1, responsavel=MEMBER_ID))
        admin.pedido(admin.contato(2, responsavel=OWNER_ID))
        assert admin.call("get", f"{BASE}?mes={MES}").json()["data"]["pedidos_enviados"] == 2


class TestConfig:
    def test_get_defaults_for_any_member(self, member):
        assert member.call("get", f"{BASE}/config").json()["data"] == av.CONFIG_PADRAO

    def test_admin_saves_partially_and_it_persists(self, admin):
        r = admin.call("put", f"{BASE}/config", {"google_review_url": LINK})
        assert r.status_code == 200 and r.json()["data"]["google_review_url"] == LINK
        r = admin.call("put", f"{BASE}/config", {"capi_ativo": True, "capi_pixel_id": "123456789012345"})
        d = r.json()["data"]
        assert d["google_review_url"] == LINK and d["capi_ativo"] is True and d["capi_pixel_id"] == "123456789012345"
        assert admin.call("get", f"{BASE}/config").json()["data"] == d
        assert admin.call("put", f"{BASE}/config", {"google_review_url": None}).json()["data"]["google_review_url"] is None

    def test_member_cannot_write_it(self, member):
        assert member.call("put", f"{BASE}/config", {"google_review_url": LINK}).status_code == 403
        assert not member.w.rows(av.T_CONFIG)

    @pytest.mark.parametrize("corpo", [{"google_review_url": "http://x.com"}, {"capi_pixel_id": "abc"}])
    def test_invalid_values_are_422(self, admin, corpo):
        r = admin.call("put", f"{BASE}/config", corpo)
        assert r.status_code == 422 and r.json()["error"]["code"] == "config_invalida"

    def test_unknown_field_is_422(self, admin):
        assert admin.call("put", f"{BASE}/config", {"google_review_url": LINK, "capi_token": "x"}).status_code == 422
