"""Supervisão routes (maya-blocks CONTRACT §4.3-4.5): strict `== 401`, owner-only scorecards/config, owner/admin
handoffs, empty states, validation codes, cursor paging, org isolation.
Seams: mock DB through the router's `get_supervisao_client`, real auth chain over a mocked session."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.modules.supervisao import metricas as m

from tests.support.julia_world import ADMIN_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
BASE = "/api/supervisao"


class Scene:
    def __init__(self, tc, world):
        self.tc, self.w = tc, world

    def call(self, method, url, body=None, headers=H):
        kw = {"json": body} if body is not None else {}
        return getattr(self.tc, method)(url, headers=headers, **kw)

    def ativar(self, horas=24):
        self.w.sw.set_table_data("supervisao_config", [{"org_id": ORG_ID, "supervisao_ativa": True, "horas_para_assumir": horas,
                                                        "updated_at": "2026-10-01T00:00:00+00:00"}])


def _scene(role):
    world = World()
    for t in ("supervisao_config", "agente_scorecards", "atendimento_handoffs", "atendimentos"):
        world.sw.set_table_data(t, [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"}, {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.modules.supervisao.router import get_supervisao_client

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_supervisao_client] = lambda: world.sw
        yield Scene(TestClient(app), world)
        app.dependency_overrides.pop(get_supervisao_client, None)


@pytest.fixture
def owner():
    yield from _scene("owner")


@pytest.fixture
def admin():
    yield from _scene("admin")


@pytest.fixture
def member():
    yield from _scene("member")


def _ontem():
    return (m.hoje_sp(datetime.now(timezone.utc)) - timedelta(days=1)).isoformat()


class TestAuth:
    @pytest.mark.parametrize("method,url", [
        ("get", f"{BASE}/scorecards"), ("get", f"{BASE}/handoffs"), ("get", f"{BASE}/config"), ("put", f"{BASE}/config"),
    ])
    def test_no_token_is_exactly_401(self, owner, method, url):
        assert owner.call(method, url, headers={}).status_code == 401

    @pytest.mark.parametrize("method,url,body", [
        ("get", f"{BASE}/scorecards", None), ("get", f"{BASE}/config", None),
        ("put", f"{BASE}/config", {"supervisao_ativa": True, "horas_para_assumir": 24}),
    ])
    def test_admin_is_not_owner_stable_code(self, admin, method, url, body):
        r = admin.call(method, url, body)
        assert r.status_code == 403 and r.json()["error"]["code"] == "exclusivo_proprietario"

    def test_admin_reads_handoffs_member_does_not(self, admin):
        assert admin.call("get", f"{BASE}/handoffs").status_code == 200

    def test_member_gets_403_everywhere(self, member):
        for url in ("scorecards", "handoffs", "config"):
            assert member.call("get", f"{BASE}/{url}").status_code == 403


class TestConfig:
    def test_default_then_roundtrip_and_org_isolation(self, owner):
        assert owner.call("get", f"{BASE}/config").json()["data"] == {
            "supervisao_ativa": False, "horas_para_assumir": 24, "updated_at": None, "updated_by": None}
        r = owner.call("put", f"{BASE}/config", {"supervisao_ativa": True, "horas_para_assumir": 48})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["supervisao_ativa"] is True and body["horas_para_assumir"] == 48 and body["updated_at"]
        assert body["updated_by"] == TEST_USER_ID
        rows = owner.w.sw.table("supervisao_config").select("*").execute().data
        assert [r["org_id"] for r in rows] == [ORG_ID]
        assert owner.call("get", f"{BASE}/config").json()["data"]["horas_para_assumir"] == 48

    @pytest.mark.parametrize("body", [
        {"supervisao_ativa": True}, {"supervisao_ativa": True, "horas_para_assumir": 0},
        {"supervisao_ativa": True, "horas_para_assumir": 169},
        {"supervisao_ativa": True, "horas_para_assumir": 24, "extra": 1},
    ])
    def test_invalid_body_is_422(self, owner, body):
        assert owner.call("put", f"{BASE}/config", body).status_code == 422


class TestScorecards:
    def test_off_with_no_history_is_empty(self, owner):
        assert owner.call("get", f"{BASE}/scorecards").json()["data"] == {"dia": _ontem(), "supervisao_ativa": False, "scorecards": []}

    def test_off_still_returns_stored_history(self, owner):
        owner.w.sw.set_table_data("agente_scorecards", [{"id": "s", "org_id": ORG_ID, "bloco": "sdr", "agent_key": "julia",
                                                         "dia": _ontem(), "metricas": {"leads_entrada": 3},
                                                         "rubrica_versao": "sdr.v1", "calculado_at": "2026-10-19T10:00:00+00:00"}])
        body = owner.call("get", f"{BASE}/scorecards").json()["data"]
        assert body["supervisao_ativa"] is False
        assert [(s["bloco"], s["metricas"]) for s in body["scorecards"]] == [("sdr", {"leads_entrada": 3})]

    def test_on_but_not_computed_is_empty(self, owner):
        owner.ativar()
        assert owner.call("get", f"{BASE}/scorecards").json()["data"] == {"dia": _ontem(), "supervisao_ativa": True, "scorecards": []}

    def test_lists_the_day_in_block_order_only_own_org(self, owner):
        owner.ativar()
        dia = _ontem()
        base = {"dia": dia, "calculado_at": "2026-10-19T10:00:12+00:00"}
        owner.w.sw.set_table_data("agente_scorecards", [
            {"id": "1", "org_id": ORG_ID, "bloco": "atendimento", "agent_key": None, "rubrica_versao": "atendimento.v1",
             "metricas": {"handoffs_recebidos": 2}, **base},
            {"id": "2", "org_id": ORG_ID, "bloco": "sdr", "agent_key": "julia", "rubrica_versao": "sdr.v1",
             "metricas": {"leads_entrada": 31, "qualificacao_taxa": None}, **base},
            {"id": "3", "org_id": OTHER_ORG_ID, "bloco": "sdr", "agent_key": "julia", "rubrica_versao": "sdr.v1",
             "metricas": {}, **base},
        ])
        body = owner.call("get", f"{BASE}/scorecards?dia={dia}").json()["data"]
        assert [s["bloco"] for s in body["scorecards"]] == ["sdr", "atendimento"]
        assert body["scorecards"][0] == {"bloco": "sdr", "agent_key": "julia", "rubrica_versao": "sdr.v1",
                                         "calculado_at": "2026-10-19T10:00:12+00:00",
                                         "metricas": {"leads_entrada": 31, "qualificacao_taxa": None}}

    @pytest.mark.parametrize("dia,code", [("2026-13-01", "dia_invalido"), ("ontem", "dia_invalido"), ("2999-01-01", "dia_futuro")])
    def test_bad_day_is_422_with_code(self, owner, dia, code):
        r = owner.call("get", f"{BASE}/scorecards?dia={dia}")
        assert r.status_code == 422 and r.json()["error"]["code"] == code

    def test_today_is_dia_futuro(self, owner):
        hoje = m.hoje_sp(datetime.now(timezone.utc)).isoformat()
        assert owner.call("get", f"{BASE}/scorecards?dia={hoje}").json()["error"]["code"] == "dia_futuro"


class TestHandoffs:
    def _h(self, scene, n, horas_atras, **over):
        criado = (datetime.now(timezone.utc) - timedelta(hours=horas_atras)).isoformat()
        row = {"id": f"00000000-0000-4000-8000-00000000{n:04d}", "org_id": ORG_ID, "de_bloco": "sdr",
               "para_bloco": "atendimento", "de_agent_key": "julia", "para_agent_key": None, "gatilho": "novo_lead",
               "origem_evento": f"00000000-0000-4000-9000-00000000{n:04d}", "status": "emitido", "created_at": criado,
               "assumido_at": None, "expirado_at": None, "contato_id": None, "lead_id": None, "atendimento_id": None,
               "atribuicao_id": None, "entrega_id": None, **over}
        scene.w.sw.table("atendimento_handoffs").insert(row).execute()
        return row

    def test_off_is_empty(self, admin):
        self._h(admin, 1, 1)
        assert admin.call("get", f"{BASE}/handoffs").json()["data"] == {"itens": [], "proximo_cursor": None}

    def test_shape_card_join_atrasado_and_newest_first(self, admin):
        admin.ativar(horas=24)
        admin.w.sw.set_table_data("atendimentos", [{"id": "a1", "org_id": ORG_ID, "titulo": "Maria — Apto 12"}])
        self._h(admin, 1, 30, atendimento_id="a1")
        self._h(admin, 2, 1, atendimento_id="gone")
        self._h(admin, 3, 2, status="assumido", assumido_at=datetime.now(timezone.utc).isoformat())
        self._h(admin, 4, 1, org_id=OTHER_ORG_ID)
        self._h(admin, 5, 24 * 30)  # outside the default 7-day window
        itens = admin.call("get", f"{BASE}/handoffs").json()["data"]["itens"]
        assert [i["id"][-1] for i in itens] == ["2", "3", "1"]
        velho = itens[2]
        assert velho["atrasado"] is True and velho["card"] == {"titulo": "Maria — Apto 12", "link": "/funil?card=a1"}
        assert velho["referencias"]["atendimento_id"] == "a1" and velho["de_agent_key"] == "julia"
        assert itens[0]["atrasado"] is False and itens[0]["card"] is None
        assert itens[1]["atrasado"] is False

    def test_filters_and_cursor_paging(self, owner):
        owner.ativar()
        for n in range(1, 6):
            self._h(owner, n, n)
        self._h(owner, 9, 1, status="expirado", expirado_at=datetime.now(timezone.utc).isoformat())
        assert len(owner.call("get", f"{BASE}/handoffs?status=expirado").json()["data"]["itens"]) == 1
        assert owner.call("get", f"{BASE}/handoffs?para_bloco=juridico").json()["data"]["itens"] == []
        p1 = owner.call("get", f"{BASE}/handoffs?status=emitido&limit=2").json()["data"]
        p2 = owner.call("get", f"{BASE}/handoffs?status=emitido&limit=2&cursor={p1['proximo_cursor']}").json()["data"]
        p3 = owner.call("get", f"{BASE}/handoffs?status=emitido&limit=2&cursor={p2['proximo_cursor']}").json()["data"]
        ids = [i["id"][-1] for p in (p1, p2, p3) for i in p["itens"]]
        assert ids == ["1", "2", "3", "4", "5"] and p3["proximo_cursor"] is None

    @pytest.mark.parametrize("q", ["status=zzz", "de_bloco=marketing", "desde=ontem", "limit=0", "limit=101",
                                   "limit=abc", "cursor=%%%", "desde=2026-10-10&ate=2026-10-01"])
    def test_bad_filter_is_422_filtro_invalido(self, owner, q):
        owner.ativar()
        r = owner.call("get", f"{BASE}/handoffs?{q}")
        assert r.status_code == 422 and r.json()["error"]["code"] == "filtro_invalido"
