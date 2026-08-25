"""`GET /api/painel` — the agency panel that replaced the YouTube dashboard.

WHAT THESE PIN
--------------
- every tile counts something a person can act on TODAY, over the open board
  only — an archived or collapsed deal is not work;
- "untouched" is measured from `updated_at` OR, when nothing has ever edited
  the row, from `created_at`. A deal nobody has EVER opened is the worst case,
  not an exempt one;
- `em_negociacao` reads the same `atendimento_negociacao` source the funil
  columns total, so the panel and the board can never disagree;
- 🔴 one broken tile does not take the first screen down.

**Strict `== 401`** per `KB § PATTERNS/compliance/auth-boundary-false-green.md`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

from app.dependencies import coerce_org_uuid

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))
URL = "/api/painel"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _iso(delta_dias: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_dias)).isoformat()


def atendimento(aid=None, *, criado=-1.0, mexido=None, arquivado=False, status="aberta"):
    return {
        "id": aid or str(uuid4()),
        "org_id": ORG_ID,
        "cliente_id": str(uuid4()),
        "titulo": "Compra do apto",
        "status": status,
        "arquivado": arquivado,
        "substituida_por": None,
        "etapa_id": "etapa-1",
        "created_at": _iso(criado),
        "updated_at": _iso(mexido) if mexido is not None else None,
    }


def agendamento(atendimento_id, *, daqui_dias=1.0, tipo="visita"):
    return {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "atendimento_id": atendimento_id,
        "quando": _iso(daqui_dias),
        "tipo": tipo,
        "nota": None,
        "lembrete_minutos_antes": None,
        "deleted_at": None,
        "created_at": _iso(-1),
    }


def negociacao(atendimento_id, valor):
    return {
        "atendimento_id": atendimento_id,
        "org_id": ORG_ID,
        "valor_negociado": valor,
        "pct_comissao": None,
        "tem_parceria": False,
        "pct_parceria": 50,
        "pct_agencia": 50,
        "pct_agentes": 45,
        "pct_captador": 5,
        "formas_pagamento": None,
        "parcelas": None,
        "financiamento": False,
        "fgts": False,
        "imovel_codigo": None,
        "observacoes": None,
        "created_at": _iso(-1),
        "created_por": None,
        "updated_at": None,
        "updated_por": None,
    }


def _client_for(org_role="owner"):
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_RAW, org_role=org_role))
    )
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.dependencies import get_scoped_admin_client
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        scoped = get_scoped_admin_client("social_wiring")
        for tabela in (
            "atendimentos",
            "atendimento_agendamentos",
            "atendimento_negociacao",
            "clientes",
            "cliente_touches",
            "cliente_merges",
            "cliente_revisao_rejeitadas",
        ):
            scoped.set_table_data(tabela, [])
        tc = TestClient(app, raise_server_exceptions=True)
        tc.scoped = scoped
        yield tc


@pytest.fixture
def client():
    yield from _client_for()


def _painel(client) -> dict:
    resp = client.get(URL, headers=_auth())
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestAuth:
    def test_without_a_token_is_401(self, client):
        assert client.get(URL).status_code == 401


class TestNovos:
    def test_counts_only_this_week(self, client):
        client.scoped.set_table_data(
            "atendimentos",
            [atendimento(criado=-2), atendimento(criado=-3), atendimento(criado=-40)],
        )

        assert _painel(client)["novos"] == 2

    def test_an_archived_deal_is_not_new_work(self, client):
        client.scoped.set_table_data(
            "atendimentos", [atendimento(criado=-1, arquivado=True)]
        )

        assert _painel(client)["novos"] == 0


class TestParados:
    def test_counts_deals_untouched_for_two_weeks(self, client):
        client.scoped.set_table_data(
            "atendimentos",
            [
                atendimento(criado=-60, mexido=-20),  # parado
                atendimento(criado=-60, mexido=-2),   # mexido esta semana
            ],
        )

        painel = _painel(client)
        assert painel["parados"] == 1
        assert len(painel["atendimentos_parados"]) == 1

    def test_a_deal_nobody_ever_touched_counts_from_when_it_arrived(self, client):
        """🔴 `updated_at` is null until something edits the row. Skipping
        those would hide the deals nobody has EVER opened — the worst case,
        not an exempt one."""
        client.scoped.set_table_data(
            "atendimentos", [atendimento(criado=-45, mexido=None)]
        )

        assert _painel(client)["parados"] == 1

    def test_the_stalest_comes_first(self, client):
        velho = atendimento(criado=-90, mexido=-80)
        menos_velho = atendimento(criado=-40, mexido=-20)
        client.scoped.set_table_data("atendimentos", [menos_velho, velho])

        parados = _painel(client)["atendimentos_parados"]
        assert parados[0]["atendimento_id"] == velho["id"]


class TestAgenda:
    def test_counts_the_next_seven_days_only(self, client):
        a = atendimento()
        client.scoped.set_table_data("atendimentos", [a])
        client.scoped.set_table_data(
            "atendimento_agendamentos",
            [
                agendamento(a["id"], daqui_dias=1),
                agendamento(a["id"], daqui_dias=3),
                agendamento(a["id"], daqui_dias=30),   # fora da janela
                agendamento(a["id"], daqui_dias=-2),   # já passou
            ],
        )

        painel = _painel(client)
        assert painel["agendamentos"] == 2
        assert [i["tipo"] for i in painel["proximos_agendamentos"]] == ["visita", "visita"]

    def test_soonest_first(self, client):
        a = atendimento()
        client.scoped.set_table_data("atendimentos", [a])
        client.scoped.set_table_data(
            "atendimento_agendamentos",
            [
                agendamento(a["id"], daqui_dias=5, tipo="reuniao"),
                agendamento(a["id"], daqui_dias=1, tipo="ligacao"),
            ],
        )

        proximos = _painel(client)["proximos_agendamentos"]
        assert proximos[0]["tipo"] == "ligacao"

    def test_a_cancelled_appointment_is_not_on_the_agenda(self, client):
        a = atendimento()
        cancelado = agendamento(a["id"], daqui_dias=2)
        cancelado["deleted_at"] = _iso(-0.5)
        client.scoped.set_table_data("atendimentos", [a])
        client.scoped.set_table_data("atendimento_agendamentos", [cancelado])

        assert _painel(client)["agendamentos"] == 0


class TestEmNegociacao:
    def test_sums_the_negotiated_values_of_open_deals(self, client):
        a, b = atendimento(), atendimento()
        client.scoped.set_table_data("atendimentos", [a, b])
        client.scoped.set_table_data(
            "atendimento_negociacao",
            [negociacao(a["id"], 850000), negociacao(b["id"], 150000)],
        )

        assert _painel(client)["em_negociacao"] == 1000000

    def test_a_deal_without_a_price_contributes_nothing_rather_than_breaking(
        self, client
    ):
        a = atendimento()
        client.scoped.set_table_data("atendimentos", [a])
        client.scoped.set_table_data("atendimento_negociacao", [negociacao(a["id"], None)])

        assert _painel(client)["em_negociacao"] == 0

    def test_an_empty_board_is_zero_not_an_error(self, client):
        painel = _painel(client)
        assert painel["em_negociacao"] == 0
        assert painel["novos"] == 0
        assert painel["proximos_agendamentos"] == []


class TestResiliencia:
    def test_a_broken_tile_does_not_take_the_panel_down(self, client):
        """🔴 A panel is a summary. If one tile can 500 the first screen after
        login, people route around the screen — which is how it became
        decoration the first time."""
        with patch(
            "app.services.clientes_service.list_review_groups",
            side_effect=RuntimeError("boom"),
        ):
            painel = _painel(client)

        assert painel["revisao"] == 0
        assert "novos" in painel
