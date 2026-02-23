"""
Tests for Condominios router — /api/condominios
"""
import pytest


class TestListarCondominios:
    def test_list_condominios(self, client):
        client._mock_supabase.set_table_data("condominios", [
            {"id": "cond1", "nome": "Edifício Aurora"},
        ])
        resp = client.get("/api/condominios")
        assert resp.status_code == 200
