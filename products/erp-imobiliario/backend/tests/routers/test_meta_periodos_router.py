"""
Tests for the Meta Períodos router + the pure date-math helpers in its service.

The date-math helpers (quinzena_bounds, mes_bounds, trimestre_bounds,
plan_trimestre_structure) are pure Python and need no DB — tested
directly. Router tests use the mock Supabase client.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import meta_periodos_service as svc


# ── Date-math helpers (pure, no DB) ─────────────────────────────────

class TestQuinzenaBounds:
    def test_first_half_of_march(self):
        assert svc.quinzena_bounds(date(2026, 3, 1))  == (date(2026, 3, 1),  date(2026, 3, 15))
        assert svc.quinzena_bounds(date(2026, 3, 15)) == (date(2026, 3, 1),  date(2026, 3, 15))

    def test_second_half_of_march(self):
        assert svc.quinzena_bounds(date(2026, 3, 16)) == (date(2026, 3, 16), date(2026, 3, 31))
        assert svc.quinzena_bounds(date(2026, 3, 31)) == (date(2026, 3, 16), date(2026, 3, 31))

    def test_second_half_of_february_non_leap(self):
        assert svc.quinzena_bounds(date(2026, 2, 28)) == (date(2026, 2, 16), date(2026, 2, 28))

    def test_second_half_of_february_leap(self):
        # 2028 is a leap year
        assert svc.quinzena_bounds(date(2028, 2, 29)) == (date(2028, 2, 16), date(2028, 2, 29))


class TestMesBounds:
    def test_march(self):
        assert svc.mes_bounds(date(2026, 3, 10)) == (date(2026, 3, 1), date(2026, 3, 31))

    def test_february_leap(self):
        assert svc.mes_bounds(date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))


class TestTrimestreBounds:
    def test_q1(self):
        assert svc.trimestre_bounds(2026, 1) == (date(2026, 1, 1), date(2026, 3, 31))

    def test_q4(self):
        assert svc.trimestre_bounds(2026, 4) == (date(2026, 10, 1), date(2026, 12, 31))

    def test_invalid_quarter(self):
        with pytest.raises(ValueError):
            svc.trimestre_bounds(2026, 5)


class TestPlanTrimestreStructure:
    def test_q1_shape(self):
        plan = svc.plan_trimestre_structure(2026, 1)
        assert plan["trimestre"]["tipo"] == "trimestral"
        assert plan["trimestre"]["data_inicio"] == "2026-01-01"
        assert plan["trimestre"]["data_fim"] == "2026-03-31"
        assert len(plan["meses"]) == 3
        # Each month has exactly 2 quinzenas
        for m in plan["meses"]:
            assert m["mes"]["tipo"] == "mensal"
            assert len(m["quinzenas"]) == 2
            assert all(q["tipo"] == "quinzenal" for q in m["quinzenas"])

    def test_names_use_portuguese_months(self):
        plan = svc.plan_trimestre_structure(2026, 2)
        nomes = [m["mes"]["nome"] for m in plan["meses"]]
        assert nomes == ["Abril 2026", "Maio 2026", "Junho 2026"]


# ── Router tests — /api/metas/periodos ──────────────────────────────

class TestListarPeriodos:
    def test_list_returns_200(self, client):
        client._mock_supabase.set_table_data("meta_periodos", [
            {"id": "p1", "nome": "Janeiro 2026", "tipo": "mensal", "data_inicio": "2026-01-01", "data_fim": "2026-01-31"},
        ])
        resp = client.get("/api/metas/periodos")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_list_filtered_by_tipo(self, client):
        client._mock_supabase.set_table_data("meta_periodos", [])
        resp = client.get("/api/metas/periodos?tipo=trimestral")
        assert resp.status_code == 200


class TestCriarPeriodo:
    def test_create_period(self, client):
        client._mock_supabase.set_table_data("meta_periodos", {
            "id": "p-new",
            "nome": "Q1 2026",
            "tipo": "trimestral",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-03-31",
        })
        resp = client.post("/api/metas/periodos", json={
            "nome": "Q1 2026",
            "tipo": "trimestral",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-03-31",
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["tipo"] == "trimestral"

    def test_create_invalid_tipo(self, client):
        resp = client.post("/api/metas/periodos", json={
            "nome": "Foo",
            "tipo": "decadenal",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
        })
        assert resp.status_code == 422

    def test_create_missing_fields(self, client):
        resp = client.post("/api/metas/periodos", json={"nome": "Foo"})
        assert resp.status_code == 422


class TestPreviewTrimestre:
    def test_preview_returns_structure_no_db(self, client):
        resp = client.post("/api/metas/periodos/preview", json={"year": 2026, "quarter": 1})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["trimestre"]["data_fim"] == "2026-03-31"
        assert len(data["meses"]) == 3

    def test_preview_rejects_bad_quarter(self, client):
        resp = client.post("/api/metas/periodos/preview", json={"year": 2026, "quarter": 7})
        assert resp.status_code == 422


class TestObterPeriodo:
    def test_get_existing(self, client):
        client._mock_supabase.set_table_data("meta_periodos", [
            {"id": "p1", "nome": "Março 2026", "tipo": "mensal"}
        ])
        resp = client.get("/api/metas/periodos/p1")
        assert resp.status_code == 200

    def test_get_missing_returns_404(self, client):
        client._mock_supabase.set_table_data("meta_periodos", [])
        resp = client.get("/api/metas/periodos/ghost")
        assert resp.status_code == 404


class TestAtualizarPeriodo:
    def test_update_status(self, client):
        client._mock_supabase.set_table_data("meta_periodos", {
            "id": "p1", "status": "em_avaliacao"
        })
        resp = client.patch("/api/metas/periodos/p1", json={"status": "em_avaliacao"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "em_avaliacao"

    def test_update_empty_body(self, client):
        client._mock_supabase.set_table_data("meta_periodos", [
            {"id": "p1", "status": "aberto"}
        ])
        resp = client.patch("/api/metas/periodos/p1", json={})
        assert resp.status_code == 200


class TestDeletarPeriodo:
    def test_delete_existing(self, client):
        client._mock_supabase.set_table_data("meta_periodos", [
            {"id": "p1", "nome": "Old"}
        ])
        resp = client.delete("/api/metas/periodos/p1")
        assert resp.status_code == 200
