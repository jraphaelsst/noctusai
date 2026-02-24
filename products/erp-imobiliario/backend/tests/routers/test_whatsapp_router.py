"""
Tests for the WhatsApp messaging integration router.
Covers config status, send message, send property card, and message history.
"""
import pytest
from unittest.mock import patch, AsyncMock


class TestWhatsAppConfig:
    def test_config_status(self, client):
        with patch(
            "app.routers.whatsapp.get_whatsapp_config_from_env",
        ) as mock_config_fn:
            from app.services.whatsapp_service import WhatsAppConfig
            mock_config_fn.return_value = WhatsAppConfig(
                api_token=None,
                phone_number_id=None,
            )
            resp = client.get("/api/whatsapp/config")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["configured"] is False
            assert data["dry_run"] is True

    def test_config_status_configured(self, client):
        with patch(
            "app.routers.whatsapp.get_whatsapp_config_from_env",
        ) as mock_config_fn:
            from app.services.whatsapp_service import WhatsAppConfig
            mock_config_fn.return_value = WhatsAppConfig(
                api_token="test-token",
                phone_number_id="12345",
            )
            resp = client.get("/api/whatsapp/config")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["configured"] is True
            assert data["api_token_set"] is True
            assert data["phone_number_id_set"] is True


class TestEnviarMensagem:
    def test_send_message_dry_run(self, client):
        client._mock_supabase.set_table_data("whatsapp_messages", [])
        with patch(
            "app.routers.whatsapp.get_whatsapp_config_from_env",
        ) as mock_config_fn, patch(
            "app.routers.whatsapp.send_message",
            new_callable=AsyncMock,
            return_value={
                "message_id": "dry_run_5511999999999",
                "status": "sent",
                "phone": "5511999999999",
                "dry_run": True,
            },
        ):
            from app.services.whatsapp_service import WhatsAppConfig
            mock_config_fn.return_value = WhatsAppConfig()

            resp = client.post("/api/whatsapp/send", json={
                "phone": "11999999999",
                "message": "Ola, tudo bem?",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["status"] == "sent"
            assert data["dry_run"] is True

    def test_send_message_with_cliente_id(self, client):
        client._mock_supabase.set_table_data("whatsapp_messages", [])
        with patch(
            "app.routers.whatsapp.get_whatsapp_config_from_env",
        ) as mock_config_fn, patch(
            "app.routers.whatsapp.send_message",
            new_callable=AsyncMock,
            return_value={
                "message_id": "dry_run_5511888888888",
                "status": "sent",
                "phone": "5511888888888",
                "dry_run": True,
            },
        ):
            from app.services.whatsapp_service import WhatsAppConfig
            mock_config_fn.return_value = WhatsAppConfig()

            resp = client.post("/api/whatsapp/send", json={
                "phone": "11888888888",
                "message": "Mensagem para cliente",
                "cliente_id": "c1",
            })
            assert resp.status_code == 200

    def test_send_message_missing_phone(self, client):
        resp = client.post("/api/whatsapp/send", json={
            "message": "Ola",
        })
        assert resp.status_code == 422

    def test_send_message_missing_message(self, client):
        resp = client.post("/api/whatsapp/send", json={
            "phone": "11999999999",
        })
        assert resp.status_code == 422

    def test_send_message_empty_message(self, client):
        resp = client.post("/api/whatsapp/send", json={
            "phone": "11999999999",
            "message": "",
        })
        assert resp.status_code == 422

    def test_send_message_phone_too_short(self, client):
        resp = client.post("/api/whatsapp/send", json={
            "phone": "123",
            "message": "Ola",
        })
        assert resp.status_code == 422


class TestEnviarImovel:
    def test_send_property_card(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "titulo_anuncio": "Apartamento 3 quartos",
            "cidade": "Sao Paulo",
            "bairro": "Jardins",
            "valor": 500000,
            "quartos": 3,
            "area_privativa": 120,
        })
        client._mock_supabase.set_table_data("whatsapp_messages", [])
        with patch(
            "app.routers.whatsapp.get_whatsapp_config_from_env",
        ) as mock_config_fn, patch(
            "app.routers.whatsapp.send_property_card",
            new_callable=AsyncMock,
            return_value={
                "message_id": "dry_run_5511999999999",
                "status": "sent",
                "phone": "5511999999999",
                "dry_run": True,
                "formatted_message": "Apartamento 3 quartos\n...",
            },
        ):
            from app.services.whatsapp_service import WhatsAppConfig
            mock_config_fn.return_value = WhatsAppConfig()

            resp = client.post("/api/whatsapp/send-property", json={
                "phone": "11999999999",
                "imovel_id": "a1",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["status"] == "sent"
            assert "formatted_message" in data

    def test_send_property_not_found(self, client):
        client._mock_supabase.set_table_data("ativos", None)
        with patch(
            "app.routers.whatsapp.get_whatsapp_config_from_env",
        ) as mock_config_fn:
            from app.services.whatsapp_service import WhatsAppConfig
            mock_config_fn.return_value = WhatsAppConfig()

            resp = client.post("/api/whatsapp/send-property", json={
                "phone": "11999999999",
                "imovel_id": "nonexistent",
            })
            assert resp.status_code == 404

    def test_send_property_missing_phone(self, client):
        resp = client.post("/api/whatsapp/send-property", json={
            "imovel_id": "a1",
        })
        assert resp.status_code == 422

    def test_send_property_missing_imovel_id(self, client):
        resp = client.post("/api/whatsapp/send-property", json={
            "phone": "11999999999",
        })
        assert resp.status_code == 422

    def test_send_property_with_mensagem_adicional(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "casa",
            "titulo_anuncio": "Casa linda",
            "cidade": "SP",
            "valor": 800000,
        })
        client._mock_supabase.set_table_data("whatsapp_messages", [])
        with patch(
            "app.routers.whatsapp.get_whatsapp_config_from_env",
        ) as mock_config_fn, patch(
            "app.routers.whatsapp.send_property_card",
            new_callable=AsyncMock,
            return_value={
                "message_id": "dry_run_5511999999999",
                "status": "sent",
                "phone": "5511999999999",
                "dry_run": True,
                "formatted_message": "Casa linda\n...",
            },
        ), patch(
            "app.routers.whatsapp.send_message",
            new_callable=AsyncMock,
            return_value={"status": "sent"},
        ):
            from app.services.whatsapp_service import WhatsAppConfig
            mock_config_fn.return_value = WhatsAppConfig()

            resp = client.post("/api/whatsapp/send-property", json={
                "phone": "11999999999",
                "imovel_id": "a1",
                "mensagem_adicional": "Essa casa e perfeita para voce!",
            })
            assert resp.status_code == 200


class TestHistoricoMensagens:
    def test_history_success(self, client):
        with patch(
            "app.routers.whatsapp.get_message_history",
            return_value={
                "messages": [
                    {"id": "m1", "phone": "5511999999999", "message": "Ola", "direction": "sent"},
                    {"id": "m2", "phone": "5511999999999", "message": "Oi", "direction": "received"},
                ],
                "total": 2,
            },
        ):
            resp = client.get("/api/whatsapp/history/11999999999")
            assert resp.status_code == 200

    def test_history_empty(self, client):
        with patch(
            "app.routers.whatsapp.get_message_history",
            return_value={
                "messages": [],
                "total": 0,
            },
        ):
            resp = client.get("/api/whatsapp/history/11888888888")
            assert resp.status_code == 200

    def test_history_pagination(self, client):
        with patch(
            "app.routers.whatsapp.get_message_history",
            return_value={
                "messages": [],
                "total": 0,
            },
        ):
            resp = client.get("/api/whatsapp/history/11999999999?page=2&page_size=10")
            assert resp.status_code == 200
