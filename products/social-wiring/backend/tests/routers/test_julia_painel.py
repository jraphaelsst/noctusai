"""Julia wave 9 -- Inicio "Painel": the month math, Sao Paulo month/hour edges, agents-down, A7, strict 401.

Seams: mock DB + the product's `FakeAgentsClient` through the `get_agents_client_factory` DI seam."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import AgentsTimeout, AgentUso, FakeAgentsClient
from app.services import julia_painel_service as svc

from tests.support.julia_world import CONNECTION_ID, ENCRYPTION_KEY, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

URL = "/api/julia/painel"
H = {"Authorization": "Bearer test-token"}


def _c(created_at, *, canal="whatsapp", status="nao_pronto", out=False, org=ORG_ID, resp=None, **kw):
    return {
        "id": str(uuid4()), "org_id": org, "connection_id": CONNECTION_ID, "responsavel_user_id": resp,
        "canal": canal, "status_envio": status, "created_at": created_at,
        "ultimo_outbound_at": created_at if out else None, **kw,
    }


# 2026-10: UTC instants chosen so SP (UTC-3) differs from UTC
FIXTURE = [
    _c("2026-10-05T13:00:00+00:00", canal="GrupoZapLais", status="enviado", out=True),          # Mon 10h SP
    _c("2026-10-05T14:00:00+00:00", canal="GrupoZapLais", status="enviado_auto", out=True),     # Mon 11h
    _c("2026-10-06T00:30:00+00:00", canal="GrupoZapLais", status="erro", out=True),             # Mon 21:30 SP (fora)
    _c("2026-10-07T10:00:00+00:00", canal="whatsapp", out=True),                                # Wed 07h SP (fora)
    _c("2026-10-07T15:00:00+00:00", canal="whatsapp"),                                          # Wed 12h
    _c("2026-11-01T01:00:00+00:00", canal="whatsapp", status="enviado", out=True),              # Oct 31 22h SP (Sat, fora)
    _c("2026-10-01T02:30:00+00:00", canal="whatsapp"),                                          # Sep 30 23:30 SP -> September
    _c("2026-11-01T03:00:00+00:00", canal="whatsapp"),                                          # Nov 1 00:00 SP -> November
    _c("2026-08-10T15:00:00+00:00", canal="whatsapp", status="enviado"),                        # August
    _c("2026-04-10T15:00:00+00:00", canal="whatsapp"),                                          # outside the 6 months
]


class TestMath:
    def test_funnel_and_charts_for_the_month(self):
        d = svc.calcular(FIXTURE, mes="2026-10")
        # Oct (SP): rows 1-6 => 6 contatos
        assert d["funil"] == {"topo": 6, "atendidos": 5, "enviados": 3}
        assert d["por_canal"] == [{"canal": "GrupoZapLais", "total": 3}, {"canal": "whatsapp", "total": 3}]
        assert d["status_por_canal"] == [
            {"canal": "GrupoZapLais", "enviado": 2, "nao_pronto": 0, "erro": 1},
            {"canal": "whatsapp", "enviado": 1, "nao_pronto": 2, "erro": 0},
        ]

    def test_hours_are_sao_paulo_and_after_hours_pct(self):
        d = svc.calcular(FIXTURE, mes="2026-10")
        assert len(d["por_hora"]) == 24 and sum(d["por_hora"]) == 6
        assert d["por_hora"][10] == 1 and d["por_hora"][21] == 1 and d["por_hora"][22] == 1 and d["por_hora"][7] == 1
        assert d["por_hora"][13] == 0  # 13h UTC would be the wrong bucket
        assert d["fora_horario_pct"] == 50.0  # 21h, 07h, 22h of 6

    def test_business_hours_are_08_to_20_exclusive_end(self):
        rows = [_c("2026-10-05T11:00:00+00:00"), _c("2026-10-05T22:59:00+00:00"), _c("2026-10-05T23:00:00+00:00")]
        d = svc.calcular(rows, mes="2026-10")  # 08:00 in, 19:59 in, 20:00 out
        assert d["fora_horario_pct"] == 33.3

    def test_weekday_buckets_and_best_day(self):
        d = svc.calcular(FIXTURE, mes="2026-10")
        assert d["por_dia_semana"] == [3, 0, 2, 0, 0, 1, 0]  # Mon 3, Wed 2, Sat 1 (Oct 31 22h SP)
        assert d["melhor_dia"] == 0

    def test_month_edges_are_sao_paulo(self):
        sep = svc.calcular(FIXTURE, mes="2026-09")["funil"]["topo"]
        nov = svc.calcular(FIXTURE, mes="2026-11")["funil"]["topo"]
        assert (sep, nov) == (1, 1)

    def test_six_months_oldest_first_enviado_vs_nao_enviado(self):
        d = svc.calcular(FIXTURE, mes="2026-10")
        assert [m["mes"] for m in d["seis_meses"]] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
        by = {m["mes"]: m for m in d["seis_meses"]}
        assert by["2026-10"] == {"mes": "2026-10", "enviado": 3, "nao_enviado": 3}
        assert by["2026-08"] == {"mes": "2026-08", "enviado": 1, "nao_enviado": 0}
        assert by["2026-09"] == {"mes": "2026-09", "enviado": 0, "nao_enviado": 1}

    def test_year_boundary_window(self):
        assert svc.ultimos_meses("2026-02") == ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
        ini, fim = svc.janela("2026-12")
        assert (fim.year, fim.month, fim.day) == (2027, 1, 1)

    def test_empty_month(self):
        d = svc.calcular([], mes="2026-10")
        assert d["funil"] == {"topo": 0, "atendidos": 0, "enviados": 0}
        assert d["fora_horario_pct"] == 0.0 and d["melhor_dia"] is None and d["por_canal"] == []


class Scene:
    def __init__(self, tc, w, agents):
        self.tc, self.w, self.agents = tc, w, agents

    def get(self, url=URL, **kw):
        return self.tc.get(url, headers=H, **kw)


def _scene(*, role, agents):
    w = World()
    w.core.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role}])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    w.seed_connection()
    w.sw.set_table_data("julia_contatos", FIXTURE + [_c("2026-10-05T13:00:00+00:00", org=OTHER_ORG_ID)])
    w.sw.set_table_data("julia_eventos", [])
    w.sw.set_table_data("julia_visitas", [])
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app
        from app.routers.julia_agente_router import get_agents_client_factory

        bind_consent_module_to_mock(w.root)
        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: agents)
        yield Scene(TestClient(app), w, agents)
        app.dependency_overrides.pop(get_agents_client_factory, None)


@pytest.fixture
def agents():
    return FakeAgentsClient(uso=AgentUso(turnos=42, custo_usd=1.5, limite_diario_usd=5.0))


@pytest.fixture
def admin(agents):
    yield from _scene(role="owner", agents=agents)


@pytest.fixture
def member(agents):
    yield from _scene(role="member", agents=agents)


def _ev(tipo, contato_id, at):
    return {"id": str(uuid4()), "org_id": ORG_ID, "tipo": tipo, "contato_id": contato_id, "payload": {}, "created_at": at}


def _vis(contato_id, at):
    return {"id": str(uuid4()), "org_id": ORG_ID, "contato_id": contato_id, "created_at": at, "status": "solicitada"}


class TestRoute:
    def test_no_token_is_401(self, admin):
        assert admin.tc.get(URL).status_code == 401
        assert admin.tc.get(f"{URL}?mes=2026-10").status_code == 401

    @pytest.mark.parametrize("mes", ["2026-13", "2026-1", "x", "202610", "2026-00"])
    def test_bad_mes_is_422(self, admin, mes):
        r = admin.get(f"{URL}?mes={mes}")
        assert r.status_code == 422 and r.json()["error"]["code"] == "mes_invalido"

    def test_admin_gets_the_whole_org_shape(self, admin):
        w = admin.w
        c0 = FIXTURE[0]["id"]
        w.sw.set_table_data("julia_eventos", [
            _ev("cobranca_atendimento", c0, "2026-10-10T12:00:00+00:00"),
            _ev("cobranca_atendimento", None, "2026-10-11T12:00:00+00:00"),
            _ev("cobranca_atendimento", c0, "2026-09-10T12:00:00+00:00"),   # other month
            _ev("novo_lead", c0, "2026-10-10T12:00:00+00:00"),              # other type
        ])
        w.sw.set_table_data("julia_visitas", [_vis(c0, "2026-10-12T12:00:00+00:00"), _vis(c0, "2026-11-01T12:00:00+00:00")])
        r = admin.get(f"{URL}?mes=2026-10")
        assert r.status_code == 200
        d = r.json()["data"]
        assert set(d) == {"atividades", "funil", "por_canal", "status_por_canal", "por_hora", "fora_horario_pct",
                          "por_dia_semana", "melhor_dia", "seis_meses"}
        assert d["atividades"] == {
            "consumo": {"turnos": 42, "custo_usd": 1.5, "limite_diario_usd": 5.0},
            "cobrancas": 2, "pre_agendamentos": 1,  # Nov 1 12:00 UTC is Nov in SP too
        }
        assert d["funil"] == {"topo": 6, "atendidos": 5, "enviados": 3}  # the other org's contato never counted
        assert admin.agents.uso_calls == ["2026-10"]

    def test_agents_down_is_null_consumo_not_500(self):
        down = FakeAgentsClient(uso=AgentsTimeout("boom"))
        for scene in _scene(role="owner", agents=down):
            r = scene.get(f"{URL}?mes=2026-10")
        assert r.status_code == 200 and r.json()["data"]["atividades"]["consumo"] is None
        assert r.json()["data"]["funil"]["topo"] == 6

    def test_agents_not_configured_is_null_consumo(self):
        for scene in _scene(role="owner", agents=None):
            r = scene.get(f"{URL}?mes=2026-10")
        assert r.status_code == 200 and r.json()["data"]["atividades"]["consumo"] is None

    def test_member_sees_only_their_contatos_and_no_org_spend(self, member):
        w = member.w
        mine = [dict(FIXTURE[0], responsavel_user_id=TEST_USER_ID), dict(FIXTURE[4], responsavel_user_id=TEST_USER_ID)]
        others = [dict(c, responsavel_user_id=OWNER_ID) for c in FIXTURE[1:4]]
        rest = FIXTURE[5:]  # no responsavel: owned by the connection owner, not this member
        w.sw.set_table_data("julia_contatos", mine + others + rest)
        w.sw.set_table_data("julia_eventos", [
            _ev("cobranca_atendimento", mine[0]["id"], "2026-10-10T12:00:00+00:00"),
            _ev("cobranca_atendimento", others[0]["id"], "2026-10-10T12:00:00+00:00"),
        ])
        w.sw.set_table_data("julia_visitas", [_vis(others[1]["id"], "2026-10-12T12:00:00+00:00")])
        d = member.get(f"{URL}?mes=2026-10").json()["data"]
        assert d["funil"] == {"topo": 2, "atendidos": 1, "enviados": 1}
        assert d["atividades"] == {"consumo": None, "cobrancas": 1, "pre_agendamentos": 0}
        assert member.agents.uso_calls == []

    def test_default_mes_is_the_current_month(self, admin):
        r = admin.get(URL)
        assert r.status_code == 200
        assert r.json()["data"]["seis_meses"][-1]["mes"] == svc.mes_atual()
