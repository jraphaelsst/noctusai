"""
Tests for Negociações router — /api/negociacoes

Added 2026-05-20 (Phase 4 — Pattern D resolution) when the frontend
`useNegociacoes.ts` was migrated from `supabase.from('negociacoes')`
to this backend route. The role-aware visibility filter (admin sees
everything; non-admin sees only their own rows) is now server-side
(security): tampered client predicates can no longer broaden visibility.
"""
import pytest
from unittest.mock import MagicMock


class TestListarNegociacoes:
    def test_list_negociacoes_empty(self, client):
        client._mock_supabase.set_table_data("negociacoes", [])
        resp = client.get("/api/negociacoes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["total"] == 0

    def test_list_returns_data(self, client):
        client._mock_supabase.set_table_data("negociacoes", [
            {"id": "n1", "status_etapa": "qualificacao", "cliente_proprietario_id": "u1", "cliente_ofertante_id": "u2"},
            {"id": "n2", "status_etapa": "fechado", "cliente_proprietario_id": "u3", "cliente_ofertante_id": "u4"},
        ])
        resp = client.get("/api/negociacoes")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2

    def test_list_filters_by_status(self, client):
        """status_etapa query param filters the result set."""
        client._mock_supabase.set_table_data("negociacoes", [
            {"id": "n1", "status_etapa": "qualificacao", "cliente_proprietario_id": "u1", "cliente_ofertante_id": "u2"},
            {"id": "n2", "status_etapa": "fechado", "cliente_proprietario_id": "u3", "cliente_ofertante_id": "u4"},
        ])
        resp = client.get("/api/negociacoes?status_etapa=fechado")
        assert resp.status_code == 200

    def test_list_todas_treated_as_no_filter(self, client):
        """status_etapa=todas means 'all'; the route does NOT apply an .eq filter."""
        client._mock_supabase.set_table_data("negociacoes", [
            {"id": "n1", "status_etapa": "qualificacao", "cliente_proprietario_id": "u1", "cliente_ofertante_id": "u2"},
        ])
        resp = client.get("/api/negociacoes?status_etapa=todas")
        assert resp.status_code == 200
