"""
Tests for Atividades router — /api/atividades
"""
import pytest


class TestListarAtividades:
    def test_list_atividades(self, client):
        client._mock_supabase.set_table_data("atividades", [
            {"id": "a1", "tipo": "ligacao", "descricao": "Ligou para cliente"},
        ])
        resp = client.get("/api/atividades?cliente_id=c1")
        assert resp.status_code == 200

    def test_list_without_cliente_id(self, client):
        resp = client.get("/api/atividades")
        assert resp.status_code == 200


class TestCriarAtividade:
    def test_create_atividade(self, client):
        client._mock_supabase.set_table_data("atividades", {"id": "a-new", "tipo": "visita"})
        resp = client.post("/api/atividades", json={
            "cliente_id": "c1",
            "tipo": "visita",
            "descricao": "Visita ao imóvel",
        })
        assert resp.status_code == 200

    def test_create_atividade_missing_descricao(self, client):
        resp = client.post("/api/atividades", json={"cliente_id": "c1", "tipo": "ligacao"})
        assert resp.status_code == 422

    def test_create_atividade_with_date(self, client):
        client._mock_supabase.set_table_data("atividades", {"id": "a-date", "tipo": "ligacao"})
        resp = client.post("/api/atividades", json={
            "cliente_id": "c1", "tipo": "ligacao",
            "descricao": "Follow-up", "data_execucao": "2026-02-23T10:00:00",
        })
        assert resp.status_code == 200

    def test_create_atividade_rejects_unknown_field_with_422(self, client):
        """StrictHttpModel migration guard — unknown keys 422 (was silently dropped).

        Pre-migration (`pydantic.BaseModel`, `extra="ignore"`) silently dropped
        `bogus_field`. Post-migration (`StrictHttpModel`, `extra="forbid"`) the
        schema rejects with 422 and names the offending `loc`. Defends against
        the silent-drop misroute class (`KB § PATTERNS/pydantic-strict-http.md`).
        """
        resp = client.post("/api/atividades", json={
            "cliente_id": "c1",
            "tipo": "ligacao",
            "descricao": "Follow-up",
            "bogus_field": "should-422",
        })
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert any(
            "bogus_field" in str(err.get("loc", ""))
            for err in body.get("detail", [])
        )
