"""
Unit tests for WhatsApp Service — phone normalization, message formatting, dry-run mode.
"""
import pytest

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# _normalize_phone
# ---------------------------------------------------------------------------

class TestNormalizePhone:

    def test_international_format_with_spaces_and_dashes(self):
        from app.services.whatsapp_service import _normalize_phone
        assert _normalize_phone("+55 11 91234-5678") == "5511912345678"

    def test_zero_prefix_landline_style(self):
        from app.services.whatsapp_service import _normalize_phone
        assert _normalize_phone("011912345678") == "5511912345678"

    def test_ddd_and_number_only(self):
        from app.services.whatsapp_service import _normalize_phone
        assert _normalize_phone("11912345678") == "5511912345678"

    def test_already_international(self):
        from app.services.whatsapp_service import _normalize_phone
        assert _normalize_phone("5511912345678") == "5511912345678"

    def test_parentheses_format(self):
        from app.services.whatsapp_service import _normalize_phone
        assert _normalize_phone("(11) 91234-5678") == "5511912345678"

    def test_short_number_gets_country_code(self):
        from app.services.whatsapp_service import _normalize_phone
        # 8-digit local number with DDD
        assert _normalize_phone("1191234567") == "551191234567"

    def test_zero_only_prefix_stripped(self):
        from app.services.whatsapp_service import _normalize_phone
        assert _normalize_phone("021987654321") == "5521987654321"


# ---------------------------------------------------------------------------
# _format_currency
# ---------------------------------------------------------------------------

class TestFormatCurrency:

    def test_basic_value(self):
        from app.services.whatsapp_service import _format_currency
        assert _format_currency(1500.50) == "R$ 1.500,50"

    def test_round_value(self):
        from app.services.whatsapp_service import _format_currency
        assert _format_currency(1000.00) == "R$ 1.000,00"

    def test_large_value(self):
        from app.services.whatsapp_service import _format_currency
        assert _format_currency(1500000.00) == "R$ 1.500.000,00"

    def test_zero(self):
        from app.services.whatsapp_service import _format_currency
        assert _format_currency(0) == "R$ 0,00"

    def test_cents_only(self):
        from app.services.whatsapp_service import _format_currency
        assert _format_currency(0.99) == "R$ 0,99"

    def test_negative_value(self):
        from app.services.whatsapp_service import _format_currency
        result = _format_currency(-500.00)
        assert "500" in result


# ---------------------------------------------------------------------------
# _build_property_message
# ---------------------------------------------------------------------------

class TestBuildPropertyMessage:

    def test_full_property_data(self):
        from app.services.whatsapp_service import _build_property_message

        imovel = {
            "titulo_anuncio": "Apartamento de Luxo",
            "tipo_imovel": "apartamento",
            "finalidade": "venda",
            "valor": 850000.0,
            "bairro": "Jardins",
            "cidade": "São Paulo",
            "estado": "SP",
            "quartos": 3,
            "suites": 1,
            "banheiros": 2,
            "vagas": 2,
            "area_privativa": 120,
        }

        msg = _build_property_message(imovel)

        assert "*Apartamento de Luxo*" in msg
        assert "Apartamento" in msg
        assert "Venda" in msg
        assert "R$ 850.000,00" in msg
        assert "Jardins" in msg
        assert "São Paulo" in msg
        assert "3 quartos" in msg
        assert "1 suites" in msg
        assert "2 vagas" in msg
        assert "120m2" in msg

    def test_minimal_data_uses_default_title(self):
        from app.services.whatsapp_service import _build_property_message

        msg = _build_property_message({})
        assert "*Imovel Disponivel*" in msg

    def test_long_description_truncated(self):
        from app.services.whatsapp_service import _build_property_message

        imovel = {
            "descricao_seo": "A" * 500,
        }
        msg = _build_property_message(imovel)

        # Description should be truncated to 297 + "..."
        assert "..." in msg

    def test_condominio_shown(self):
        from app.services.whatsapp_service import _build_property_message

        msg = _build_property_message({"condominio_nome": "Residencial Park"})
        assert "Residencial Park" in msg

    def test_tour_virtual_shown(self):
        from app.services.whatsapp_service import _build_property_message

        msg = _build_property_message({"tour_virtual_url": "https://tour.example.com"})
        assert "https://tour.example.com" in msg

    def test_iptu_shown(self):
        from app.services.whatsapp_service import _build_property_message

        msg = _build_property_message({"iptu": 2400.0})
        assert "IPTU" in msg
        assert "2.400,00" in msg


# ---------------------------------------------------------------------------
# WhatsAppConfig
# ---------------------------------------------------------------------------

class TestWhatsAppConfig:

    def test_not_configured_when_no_token(self):
        from app.services.whatsapp_service import WhatsAppConfig

        config = WhatsAppConfig(api_token=None, phone_number_id="123")
        assert config.is_configured is False

    def test_not_configured_when_no_phone_id(self):
        from app.services.whatsapp_service import WhatsAppConfig

        config = WhatsAppConfig(api_token="token-abc", phone_number_id=None)
        assert config.is_configured is False

    def test_not_configured_when_both_missing(self):
        from app.services.whatsapp_service import WhatsAppConfig

        config = WhatsAppConfig()
        assert config.is_configured is False

    def test_configured_when_both_set(self):
        from app.services.whatsapp_service import WhatsAppConfig

        config = WhatsAppConfig(api_token="token-abc", phone_number_id="12345")
        assert config.is_configured is True

    def test_send_url(self):
        from app.services.whatsapp_service import WhatsAppConfig

        config = WhatsAppConfig(
            api_token="tok", phone_number_id="999", api_version="v18.0"
        )
        assert config.send_url == "https://graph.facebook.com/v18.0/999/messages"

    def test_headers(self):
        from app.services.whatsapp_service import WhatsAppConfig

        config = WhatsAppConfig(api_token="my-secret-token")
        assert config.headers["Authorization"] == "Bearer my-secret-token"
        assert config.headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# send_message (dry-run mode)
# ---------------------------------------------------------------------------

class TestSendMessage:

    @pytest.mark.asyncio
    async def test_dry_run_when_not_configured(self):
        from app.services.whatsapp_service import send_message, WhatsAppConfig

        config = WhatsAppConfig()  # Not configured
        result = await send_message(
            phone="11912345678",
            message="Olá, tudo bem?",
            config=config,
        )

        assert result["dry_run"] is True
        assert result["status"] == "sent"
        assert "5511912345678" in result["phone"]
        assert result["message_id"].startswith("dry_run_")

    @pytest.mark.asyncio
    async def test_dry_run_normalizes_phone(self):
        from app.services.whatsapp_service import send_message, WhatsAppConfig

        config = WhatsAppConfig()
        result = await send_message(
            phone="+55 21 99999-0000",
            message="Test",
            config=config,
        )

        assert result["phone"] == "5521999990000"


# ---------------------------------------------------------------------------
# send_property_card (dry-run mode)
# ---------------------------------------------------------------------------

class TestSendPropertyCard:

    @pytest.mark.asyncio
    async def test_dry_run_includes_formatted_message(self):
        from app.services.whatsapp_service import send_property_card, WhatsAppConfig

        config = WhatsAppConfig()  # Not configured
        imovel = {
            "titulo_anuncio": "Cobertura Duplex",
            "tipo_imovel": "cobertura",
            "valor": 2000000.0,
            "cidade": "Rio de Janeiro",
            "bairro": "Leblon",
            "quartos": 4,
        }

        result = await send_property_card(
            phone="21988887777",
            imovel_data=imovel,
            config=config,
        )

        assert result["dry_run"] is True
        assert "formatted_message" in result
        assert "*Cobertura Duplex*" in result["formatted_message"]
        assert "R$ 2.000.000,00" in result["formatted_message"]
        assert "Leblon" in result["formatted_message"]

    @pytest.mark.asyncio
    async def test_dry_run_returns_sent_status(self):
        from app.services.whatsapp_service import send_property_card, WhatsAppConfig

        config = WhatsAppConfig()
        result = await send_property_card(
            phone="11999990000",
            imovel_data={"tipo_imovel": "casa"},
            config=config,
        )

        assert result["status"] == "sent"


# ---------------------------------------------------------------------------
# send_via_waha (consumes seed WahaClient via get_whatsapp_client factory)
# ---------------------------------------------------------------------------

class TestSendViaWaha:
    """ERP's `send_via_waha` delegates HTTP transport to the seed
    `noctusai_lib.integrations.whatsapp.WahaClient`. Tests patch the seed's
    `WahaClient.send_text` (external integration boundary) — never the
    product's `send_via_waha` itself."""

    @pytest.mark.asyncio
    async def test_not_configured_returns_failed(self):
        """No row in `whatsapp_config` → fail envelope, never touches the lib."""
        from app.services.whatsapp_service import send_via_waha

        db = MockSupabaseClient()
        db.set_table_data("whatsapp_config", [])

        result = await send_via_waha(db, "11912345678", "hello")

        assert result["status"] == "failed"
        assert result["error"] == "WAHA not configured"
        assert result["phone"] == "11912345678"

    @pytest.mark.asyncio
    async def test_dry_run_when_no_waha_url(self):
        """Config row exists but `waha_api_url` is empty → dry_run envelope."""
        from app.services.whatsapp_service import send_via_waha

        db = MockSupabaseClient()
        db.set_table_data("whatsapp_config", [{
            "provider": "waha",
            "is_active": True,
            "waha_api_url": "",
            "waha_api_key": "",
            "waha_session_name": "default",
        }])

        result = await send_via_waha(db, "11912345678", "hello")

        assert result["dry_run"] is True
        assert result["status"] == "sent"
        assert result["message_id"] == "dry_run_11912345678"

    @pytest.mark.asyncio
    async def test_success_delegates_to_seed_client(self, monkeypatch):
        """Successful send: patch `httpx.AsyncClient` at the external HTTP
        boundary inside the seed `WahaClient`; ERP-side normalization +
        envelope preserved. Pattern mirrors seed's own client tests."""
        from unittest.mock import AsyncMock, MagicMock
        import httpx
        from app.services.whatsapp_service import send_via_waha
        from noctusai_lib.integrations.whatsapp import client as waha_client_module

        captured_post: dict = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"id": "waha-msg-42"})

        async def fake_post(path, json=None, headers=None):
            captured_post["path"] = path
            captured_post["json"] = json
            captured_post["headers"] = headers
            return mock_response

        fake_async_client = AsyncMock()
        fake_async_client.post = fake_post
        fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
        fake_async_client.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(
            waha_client_module.httpx,
            "AsyncClient",
            lambda **_: fake_async_client,
        )

        db = MockSupabaseClient()
        db.set_table_data("whatsapp_config", [{
            "provider": "waha",
            "is_active": True,
            "waha_api_url": "http://waha.local:3000",
            "waha_api_key": "secret-key",
            "waha_session_name": "erp-session",
        }])

        result = await send_via_waha(db, "11912345678", "Olá")

        # Envelope assertions (status + ID + phone).
        assert result["status"] == "sent"
        assert result["message_id"] == "waha-msg-42"
        assert result["phone"] == "5511912345678"  # ERP-side BR country-code prepend

        # Verify the seed client built the right payload + headers.
        assert captured_post["path"] == "/api/sendText"
        assert captured_post["json"] == {
            "session": "erp-session",
            "chatId": "5511912345678@c.us",
            "text": "Olá",
        }
        assert captured_post["headers"]["X-Api-Key"] == "secret-key"
        assert captured_post["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_seed_client_exception_returns_failed(self, monkeypatch):
        """When seed `WahaClient.send_text` raises (HTTPStatusError or other),
        ERP surfaces the legacy `{status: failed, error: ...}` envelope."""
        from unittest.mock import AsyncMock, MagicMock
        import httpx
        from app.services.whatsapp_service import send_via_waha
        from noctusai_lib.integrations.whatsapp import client as waha_client_module

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500 Internal Server Error", request=MagicMock(), response=mock_response,
            ),
        )

        fake_async_client = AsyncMock()
        fake_async_client.post = AsyncMock(return_value=mock_response)
        fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
        fake_async_client.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(
            waha_client_module.httpx,
            "AsyncClient",
            lambda **_: fake_async_client,
        )

        db = MockSupabaseClient()
        db.set_table_data("whatsapp_config", [{
            "provider": "waha",
            "is_active": True,
            "waha_api_url": "http://waha.local:3000",
            "waha_api_key": "secret-key",
            "waha_session_name": "default",
        }])

        result = await send_via_waha(db, "11912345678", "test")

        assert result["status"] == "failed"
        assert result["message_id"] is None
        assert "500" in result["error"]
        assert result["phone"] == "5511912345678"
