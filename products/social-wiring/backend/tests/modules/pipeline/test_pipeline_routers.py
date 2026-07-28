"""Router tests for social-wiring's Funil de Vendas + Processos de Venda.

What these protect, beyond "it responds 200":

* **Org scoping.** This module talks to a schema-scoped ADMIN client, so RLS is
  NOT doing the filtering — every query must carry `org_id` itself. A test that
  only ever sees one tenant would never catch a missing filter, so the fixtures
  seed another org's stage and assert it never appears.
* **The history write.** Every move goes through the shared `move_card`, which
  is the only reason this board has an audit trail at all.
* **Role-keyed accept.** The seam resolves the gate stage by `papel`, so
  renaming "Proposta" cannot break it.
* **No create endpoint.** Cards come from the lead trigger; a POST would be a
  second, forkable way to make one.
"""
from __future__ import annotations

import pytest

from .conftest import (
    OTHER_ORG_STAGE,
    PROC_STAGE_ID,
    STAGE_ID,
    auth_headers,
    negociacao,
    processo,
)


class TestFunilBoard:
    def test_emits_every_configured_stage(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "novo")])
        r = http_client.get("/api/funil", headers=auth_headers())
        assert r.status_code == 200
        colunas = r.json()["data"]
        assert [c["stage"]["slug"] for c in colunas] == [
            "novo", "contato", "qualificado", "proposta", "negociacao", "fechado"
        ]
        assert [c["etapa"] for c in colunas] == [s for s in STAGE_ID.values()]

    def test_another_orgs_stage_never_appears(self, http_client):
        """The admin client sees every tenant; the QUERY must not."""
        r = http_client.get("/api/funil", headers=auth_headers())
        assert r.status_code == 200
        ids = [c["etapa"] for c in r.json()["data"]]
        assert OTHER_ORG_STAGE["id"] not in ids

    def test_groups_and_totals(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [
            negociacao("neg-1", "proposta", valor_estimado=1000),
            negociacao("neg-2", "proposta", valor_estimado=500),
            negociacao("neg-3", "novo", valor_estimado=250),
        ])
        r = http_client.get("/api/funil", headers=auth_headers())
        colunas = {c["stage"]["slug"]: c for c in r.json()["data"]}
        assert colunas["proposta"]["total"] == 2
        assert colunas["proposta"]["valorTotal"] == 1500
        assert colunas["novo"]["total"] == 1

    def test_closed_deals_are_off_the_board(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [
            negociacao("neg-1", "fechado", status="aceita", closed_at="2026-07-28T00:00:00Z"),
        ])
        r = http_client.get("/api/funil", headers=auth_headers())
        assert all(c["total"] == 0 for c in r.json()["data"])

    def test_dto_strips_unknown_columns(self, http_client):
        http_client.scoped.set_table_data(
            "negociacoes_venda", [negociacao("neg-1", "novo", coluna_interna="não vaza")]
        )
        r = http_client.get("/api/funil", headers=auth_headers())
        cards = [c for col in r.json()["data"] for c in col["cards"]]
        assert cards and "coluna_interna" not in cards[0]


class TestNoCreateEndpoint:
    def test_post_negociacoes_is_not_routable(self, http_client):
        """Cards exist because a lead arrived — the DB trigger owns creation."""
        r = http_client.post("/api/negociacoes-venda", json={}, headers=auth_headers())
        assert r.status_code == 405


class TestMoverEtapa:
    def test_move_writes_history(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "novo")])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 200
        rows = http_client.scoped.table("pipeline_movimentos").inserted_payloads
        assert len(rows) == 1
        assert rows[0]["pipeline"] == "funil"
        assert rows[0]["entidade_id"] == "neg-1"
        assert rows[0]["de_etapa_id"] == STAGE_ID["novo"]
        assert rows[0]["para_etapa_id"] == STAGE_ID["contato"]
        # org stamped, because this history table is org-scoped
        assert rows[0]["org_id"]

    def test_same_stage_move_writes_no_history(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "novo")])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["novo"], "novo_indice": 2},
            headers=auth_headers(),
        )
        assert r.status_code == 200
        assert http_client.scoped.table("pipeline_movimentos").inserted_payloads == []

    def test_move_to_another_orgs_stage_404s(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "novo")])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/mover-etapa",
            json={"para_etapa_id": OTHER_ORG_STAGE["id"]},
            headers=auth_headers(),
        )
        assert r.status_code == 404

    def test_move_refuses_a_closed_deal(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [
            negociacao("neg-1", "fechado", status="aceita", closed_at="2026-07-28T00:00:00Z"),
        ])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["novo"]},
            headers=auth_headers(),
        )
        assert r.status_code == 400


class TestAceitarProposta:
    def test_accept_from_the_role_stage_spawns_a_processo(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "proposta")])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["already_accepted"] is False
        inserted = http_client.scoped.table("processos_venda").inserted_payloads
        assert len(inserted) == 1
        # lands on the FIRST configured processos stage, derived from order
        assert inserted[0]["etapa_id"] == PROC_STAGE_ID["contrato"]
        assert inserted[0]["negociacao_venda_id"] == "neg-1"

    def test_accept_is_refused_outside_the_role_stage(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "novo")])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 400
        assert http_client.scoped.table("processos_venda").inserted_payloads == []

    def test_accept_follows_the_ROLE_after_the_stage_is_renamed(self, http_client):
        """The whole point of `papel`: rename the column, keep the feature."""
        renamed = [
            {**s, "label": "Proposta Enviada"} if s["slug"] == "proposta" else s
            for s in http_client.scoped.table("pipeline_stages").select("*").execute().data
        ]
        http_client.scoped.set_table_data("pipeline_stages", renamed)
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "proposta")])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 200

    def test_second_accept_is_idempotent(self, http_client):
        http_client.scoped.set_table_data("negociacoes_venda", [negociacao("neg-1", "proposta")])
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1")])
        r = http_client.post(
            "/api/negociacoes-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 200
        assert r.json()["data"]["already_accepted"] is True
        assert http_client.scoped.table("processos_venda").inserted_payloads == []


class TestProcessosBoard:
    def test_emits_every_configured_stage(self, http_client):
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1", "briefing")])
        r = http_client.get("/api/processos-venda", headers=auth_headers())
        assert r.status_code == 200
        colunas = r.json()["data"]
        assert [c["stage"]["slug"] for c in colunas] == [
            "contrato", "onboarding", "briefing", "planejamento",
            "execucao", "entrega", "faturamento",
        ]
        briefing = next(c for c in colunas if c["stage"]["slug"] == "briefing")
        assert briefing["total"] == 1

    def test_move_writes_history_for_this_pipeline_too(self, http_client):
        """The gap that existed on erp's Processos board cannot recur here."""
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1", "contrato")])
        r = http_client.post(
            "/api/processos-venda/proc-1/mover-etapa",
            json={"para_etapa_id": PROC_STAGE_ID["briefing"]},
            headers=auth_headers(),
        )
        assert r.status_code == 200
        rows = http_client.scoped.table("pipeline_movimentos").inserted_payloads
        assert len(rows) == 1
        assert rows[0]["pipeline"] == "processos_venda"
        assert rows[0]["para_etapa_id"] == PROC_STAGE_ID["briefing"]

    def test_archive_toggles(self, http_client):
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1", "faturamento")])
        r = http_client.post("/api/processos-venda/proc-1/arquivar", headers=auth_headers())
        assert r.status_code == 200
        assert http_client.scoped.table("processos_venda").updated_payloads == [{"arquivado": True}]


class TestNoAuth:
    """Strict `== 401`. A non-401 here would be a false green — it would mean
    the route is absent or validating before authenticating."""

    @pytest.mark.parametrize("method,path,payload", [
        ("get", "/api/funil", None),
        ("get", "/api/funil/etapas", None),
        ("post", "/api/funil/etapas", {"label": "Nova"}),
        ("patch", "/api/funil/etapas/fstage-0", {"label": "Nova"}),
        ("delete", "/api/funil/etapas/fstage-0", None),
        ("post", "/api/funil/etapas/reordenar", {"ordem": ["fstage-0"]}),
        ("get", "/api/negociacoes-venda", None),
        ("post", "/api/negociacoes-venda/neg-1/mover-etapa", {"para_etapa_id": "fstage-1"}),
        ("post", "/api/negociacoes-venda/neg-1/aceitar-proposta", None),
        ("post", "/api/negociacoes-venda/neg-1/perder", {}),
        ("get", "/api/processos-venda", None),
        ("get", "/api/processos-venda/etapas", None),
        ("post", "/api/processos-venda/proc-1/mover-etapa", {"para_etapa_id": "pstage-1"}),
        ("post", "/api/processos-venda/proc-1/arquivar", None),
    ])
    def test_requires_auth(self, http_client, method, path, payload):
        fn = getattr(http_client, method)
        r = fn(path, json=payload) if payload is not None else fn(path)
        assert r.status_code == 401


class TestStageEditor:
    def test_lists_only_this_pipelines_stages_for_this_org(self, http_client):
        r = http_client.get("/api/funil/etapas", headers=auth_headers())
        assert r.status_code == 200
        rows = r.json()["data"]
        assert {s["pipeline"] for s in rows} == {"funil"}
        assert OTHER_ORG_STAGE["id"] not in {s["id"] for s in rows}

    def test_create_appends_and_slugifies(self, http_client):
        r = http_client.post(
            "/api/funil/etapas", json={"label": "Reunião Agendada"}, headers=auth_headers()
        )
        assert r.status_code == 200
        payload = http_client.scoped.table("pipeline_stages").inserted_payloads[-1]
        assert payload["slug"] == "reuniao_agendada"
        assert payload["posicao"] == 6
        assert payload["pipeline"] == "funil"

    def test_delete_refuses_a_role_bearing_stage(self, http_client):
        r = http_client.delete(
            f"/api/funil/etapas/{STAGE_ID['proposta']}", headers=auth_headers()
        )
        assert r.status_code == 400
        assert "papel" in r.json()["error"]["message"]

    def test_opcoes_serves_the_valid_tokens(self, http_client):
        r = http_client.get("/api/funil/etapas/opcoes", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "primary" in data["cores"]
        assert "proposta_aceite" in data["papeis"]
