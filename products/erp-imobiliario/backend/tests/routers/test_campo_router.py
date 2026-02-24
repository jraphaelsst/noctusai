"""
Tests for the Campo (Field Operations) router — /api/campo
Covers check-in, checkin list, quick inspection, nearby properties, sync, and offline data.
"""
import pytest
from unittest.mock import patch, AsyncMock


class TestRegistrarCheckin:
    def test_checkin_success(self, client):
        client._mock_supabase.set_table_data("checkins", {
            "id": "ck-new", "corretor_id": "test-user-123",
            "latitude": -23.5505, "longitude": -46.6333, "tipo": "visita",
        })
        resp = client.post("/api/campo/checkin", json={
            "latitude": -23.5505,
            "longitude": -46.6333,
            "tipo": "visita",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "ck-new"

    def test_checkin_with_optional_fields(self, client):
        client._mock_supabase.set_table_data("checkins", {
            "id": "ck-full", "corretor_id": "test-user-123",
            "latitude": -23.5505, "longitude": -46.6333, "tipo": "vistoria",
            "imovel_id": "im-1", "observacoes": "Tudo ok",
        })
        resp = client.post("/api/campo/checkin", json={
            "latitude": -23.5505,
            "longitude": -46.6333,
            "tipo": "vistoria",
            "imovel_id": "im-1",
            "observacoes": "Tudo ok",
            "fotos": ["foto1.jpg", "foto2.jpg"],
        })
        assert resp.status_code == 200

    def test_checkin_missing_latitude(self, client):
        resp = client.post("/api/campo/checkin", json={
            "longitude": -46.6333,
            "tipo": "visita",
        })
        assert resp.status_code == 422

    def test_checkin_missing_longitude(self, client):
        resp = client.post("/api/campo/checkin", json={
            "latitude": -23.5505,
            "tipo": "visita",
        })
        assert resp.status_code == 422

    def test_checkin_missing_tipo(self, client):
        resp = client.post("/api/campo/checkin", json={
            "latitude": -23.5505,
            "longitude": -46.6333,
        })
        assert resp.status_code == 422

    def test_checkin_invalid_tipo(self, client):
        resp = client.post("/api/campo/checkin", json={
            "latitude": -23.5505,
            "longitude": -46.6333,
            "tipo": "invalido",
        })
        assert resp.status_code == 422

    def test_checkin_latitude_out_of_range(self, client):
        resp = client.post("/api/campo/checkin", json={
            "latitude": 100,
            "longitude": -46.6333,
            "tipo": "visita",
        })
        assert resp.status_code == 422

    def test_checkin_longitude_out_of_range(self, client):
        resp = client.post("/api/campo/checkin", json={
            "latitude": -23.5505,
            "longitude": 200,
            "tipo": "visita",
        })
        assert resp.status_code == 422


class TestListarCheckins:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("checkins", [
            {"id": "ck1", "tipo": "visita", "latitude": -23.55, "longitude": -46.63},
            {"id": "ck2", "tipo": "captacao", "latitude": -23.56, "longitude": -46.64},
        ])
        resp = client.get("/api/campo/checkins")
        assert resp.status_code == 200
        assert "data" in resp.json()
        assert "pagination" in resp.json()

    def test_filter_by_corretor(self, client):
        client._mock_supabase.set_table_data("checkins", [])
        resp = client.get("/api/campo/checkins?corretor_id=user-abc")
        assert resp.status_code == 200

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("checkins", [])
        resp = client.get("/api/campo/checkins?tipo=vistoria")
        assert resp.status_code == 200

    def test_filter_by_date_range(self, client):
        client._mock_supabase.set_table_data("checkins", [])
        resp = client.get("/api/campo/checkins?data_inicio=2026-02-01&data_fim=2026-02-28")
        assert resp.status_code == 200

    def test_pagination(self, client):
        client._mock_supabase.set_table_data("checkins", [])
        resp = client.get("/api/campo/checkins?page=1&page_size=10")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 10


class TestVistoriaRapida:
    def test_vistoria_success(self, client):
        client._mock_supabase.set_table_data("checkins", {
            "id": "ck-vist", "tipo": "vistoria", "corretor_id": "test-user-123",
        })
        client._mock_supabase.set_table_data("vistorias_rapidas", {
            "id": "vr-new", "imovel_id": "im-1", "estado_geral": "bom",
        })
        resp = client.post("/api/campo/vistoria-rapida", json={
            "imovel_id": "im-1",
            "latitude": -23.5505,
            "longitude": -46.6333,
            "estado_geral": "bom",
        })
        assert resp.status_code == 200

    def test_vistoria_with_checklist(self, client):
        client._mock_supabase.set_table_data("checkins", {
            "id": "ck-vist2", "tipo": "vistoria", "corretor_id": "test-user-123",
        })
        client._mock_supabase.set_table_data("vistorias_rapidas", {
            "id": "vr-2", "imovel_id": "im-2", "estado_geral": "regular",
            "itens_checklist": {"pintura": True, "hidraulica": False},
        })
        resp = client.post("/api/campo/vistoria-rapida", json={
            "imovel_id": "im-2",
            "latitude": -23.5505,
            "longitude": -46.6333,
            "estado_geral": "regular",
            "itens_checklist": {"pintura": True, "hidraulica": False},
            "observacoes": "Precisa de reparos na hidraulica",
        })
        assert resp.status_code == 200

    def test_vistoria_missing_imovel_id(self, client):
        resp = client.post("/api/campo/vistoria-rapida", json={
            "latitude": -23.5505,
            "longitude": -46.6333,
            "estado_geral": "bom",
        })
        assert resp.status_code == 422

    def test_vistoria_missing_estado_geral(self, client):
        resp = client.post("/api/campo/vistoria-rapida", json={
            "imovel_id": "im-1",
            "latitude": -23.5505,
            "longitude": -46.6333,
        })
        assert resp.status_code == 422

    def test_vistoria_invalid_estado_geral(self, client):
        resp = client.post("/api/campo/vistoria-rapida", json={
            "imovel_id": "im-1",
            "latitude": -23.5505,
            "longitude": -46.6333,
            "estado_geral": "excelente",
        })
        assert resp.status_code == 422


class TestImoveisProximos:
    def test_proximos_success(self, client):
        client._mock_supabase.set_table_data("ativos", [
            {
                "id": "im-1", "natureza": "imovel", "tipo_imovel": "apartamento",
                "titulo_anuncio": "Apto Centro", "valor": 500000,
                "cidade": "Sao Paulo", "bairro": "Centro", "logradouro": "Rua A",
                "numero": "100", "estado": "SP", "latitude": "-23.5505",
                "longitude": "-46.6333", "quartos": 3, "area_privativa": 80,
                "fotos": [], "status": "ativo", "finalidade": "venda",
            },
        ])
        resp = client.get("/api/campo/proximos?latitude=-23.5510&longitude=-46.6340")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_proximos_with_raio(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/campo/proximos?latitude=-23.55&longitude=-46.63&raio_km=10")
        assert resp.status_code == 200

    def test_proximos_missing_latitude(self, client):
        resp = client.get("/api/campo/proximos?longitude=-46.63")
        assert resp.status_code == 422

    def test_proximos_missing_longitude(self, client):
        resp = client.get("/api/campo/proximos?latitude=-23.55")
        assert resp.status_code == 422

    def test_proximos_empty_results(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/campo/proximos?latitude=-23.55&longitude=-46.63")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestSincronizarDados:
    def test_sync_success(self, client):
        client._mock_supabase.set_table_data("checkins", [])
        client._mock_supabase.set_table_data("vistorias_rapidas", [])
        with patch(
            "app.routers.campo.CampoService.processar_sync",
            new_callable=AsyncMock,
            return_value={"checkins_criados": 1, "vistorias_criadas": 0, "erros": []},
        ):
            resp = client.post("/api/campo/sync", json={
                "checkins": [
                    {
                        "latitude": -23.5505,
                        "longitude": -46.6333,
                        "tipo": "visita",
                        "offline_id": "off-1",
                    },
                ],
                "vistorias": [],
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["checkins_criados"] == 1

    def test_sync_empty(self, client):
        with patch(
            "app.routers.campo.CampoService.processar_sync",
            new_callable=AsyncMock,
            return_value={"checkins_criados": 0, "vistorias_criadas": 0, "erros": []},
        ):
            resp = client.post("/api/campo/sync", json={
                "checkins": [],
                "vistorias": [],
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["checkins_criados"] == 0
            assert data["vistorias_criadas"] == 0


class TestDadosOffline:
    def test_offline_data_success(self, client):
        with patch(
            "app.routers.campo.CampoService.gerar_pacote_offline",
            new_callable=AsyncMock,
            return_value={
                "imoveis": [{"id": "im-1"}],
                "clientes": [{"id": "cl-1"}],
                "checkins_recentes": [],
                "generated_at": "2026-02-24T12:00:00",
            },
        ):
            resp = client.get("/api/campo/offline-data")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert "imoveis" in data
            assert "clientes" in data
            assert "checkins_recentes" in data
            assert "generated_at" in data


class TestNoAuth:
    def test_no_token_checkins(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/campo/checkins")
        assert resp.status_code == 401
