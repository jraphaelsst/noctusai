"""
Router tests covering Phase 6 (metas_equipe), Phase 8 (fechamentos),
Phase 9 (rankings). Consolidated for efficiency — the logic tested here
is small and each router has a narrow surface.
"""
from __future__ import annotations

import pytest

from app.services import meta_rankings_service as rank_svc
from app.services import meta_fechamentos_service as fech_svc


# ── Phase 6 — metas_equipe ──────────────────────────────────────────

class TestMetasEquipeRouter:
    def test_upsert_team_meta(self, client):
        client._mock_supabase.set_table_data("metas_empresa", [
            {"id": "me1", "periodo_id": "p1", "categoria": "vgv", "valor_meta": 30000000}
        ])
        client._mock_supabase.set_table_data("metas_equipe", {
            "id": "teq1", "periodo_id": "p1", "equipe_id": "e1",
            "categoria": "vgv", "valor_meta": 10000000,
        })
        resp = client.post("/api/metas/equipes-quotas", json={
            "periodo_id": "p1",
            "equipe_id": "e1",
            "valor_meta": 10000000,
            "enforce_cascade": False,
        })
        assert resp.status_code == 201

    def test_negative_rejected(self, client):
        resp = client.post("/api/metas/equipes-quotas", json={
            "periodo_id": "p1",
            "equipe_id": "e1",
            "valor_meta": -1,
        })
        assert resp.status_code == 422

    def test_resumo_agentes(self, client):
        client._mock_supabase.set_table_data("metas_equipe", [
            {"id": "teq1", "periodo_id": "p1", "equipe_id": "e1",
             "categoria": "vgv", "valor_meta": 10000000}
        ])
        client._mock_supabase.set_table_data("metas", [
            {"usuario_id": "u1", "meta_vgv": 4000000, "equipe_id": "e1", "periodo_id": "p1", "categoria": "vgv"},
            {"usuario_id": "u2", "meta_vgv": 3000000, "equipe_id": "e1", "periodo_id": "p1", "categoria": "vgv"},
        ])
        resp = client.get("/api/metas/equipes-quotas/resumo?equipe_id=e1&periodo_id=p1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["meta_equipe"] == 10000000
        assert data["alocado_em_agentes"] == 7000000
        assert data["saldo_a_alocar"] == 3000000


# ── Phase 8 — fechamentos ───────────────────────────────────────────

class TestFechamentosRouter:
    def test_listar_empty(self, client):
        client._mock_supabase.set_table_data("meta_fechamentos", [])
        resp = client.get("/api/metas/fechamentos")
        assert resp.status_code == 200

    def test_fechar_missing_period_returns_404(self, client):
        client._mock_supabase.set_table_data("meta_periodos", [])
        resp = client.post("/api/metas/fechamentos/fechar", json={"periodo_id": "ghost"})
        assert resp.status_code == 404


class TestCloseAggregation:
    """Pure-logic tests for the score-unificado formula used by close_periodo."""

    def test_score_formula_default_config(self):
        cfg = {"vgv_por_ponto": 10000, "peso_pontos": 1.0, "peso_vgv": 1.0}
        # 50 atividade pts + (1_000_000 VGV / 10000) = 50 + 100 = 150
        assert fech_svc._score_unificado(50, 1_000_000, cfg) == 150

    def test_score_formula_weighted(self):
        cfg = {"vgv_por_ponto": 10000, "peso_pontos": 2.0, "peso_vgv": 0.5}
        # 50*2 + (1_000_000/10000)*0.5 = 100 + 50 = 150
        assert fech_svc._score_unificado(50, 1_000_000, cfg) == 150


# ── Phase 9 — rankings ──────────────────────────────────────────────

class TestRankingsRouter:
    def test_rankings_empty(self, client):
        client._mock_supabase.set_table_data("meta_eventos", [])
        client._mock_supabase.set_table_data("metas_configuracao", [])
        resp = client.get("/api/metas/rankings")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pontos"] == []
        assert data["vgv"] == []
        assert data["unificado"] == []


class TestRankingsLogic:
    """Pure-logic tests for compute_rankings (mocked db)."""

    class _StubQ:
        def __init__(self, rows):
            self.rows = rows
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def gte(self, *a, **k): return self
        def lte(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self):
            class R: pass
            r = R(); r.data = self.rows; return r

    class _StubDb:
        def __init__(self, tables): self.tables = tables
        def table(self, name): return TestRankingsLogic._StubQ(self.tables.get(name, []))

    def test_pontos_ranking_descending(self):
        db = self._StubDb({
            "meta_eventos": [
                {"corretor_id": "u1", "equipe_id_snapshot": "e1", "pontos": 100, "valor_vgv": 500_000},
                {"corretor_id": "u2", "equipe_id_snapshot": "e1", "pontos": 50, "valor_vgv": 1_000_000},
                {"corretor_id": "u3", "equipe_id_snapshot": "e2", "pontos": 200, "valor_vgv": 0},
            ],
            "metas_configuracao": [
                {"vgv_por_ponto": 10000, "peso_pontos": 1.0, "peso_vgv": 1.0}
            ],
        })
        result = rank_svc.compute_rankings(db, org_id="org-1")
        # pontos ranking: u3 (200), u1 (100), u2 (50)
        assert [r["corretor_id"] for r in result["pontos"]] == ["u3", "u1", "u2"]
        # unified ranking: u1 = 100 + 50, u2 = 50 + 100, u3 = 200 + 0 → 200, 150, 150
        assert result["unificado"][0]["corretor_id"] == "u3"
