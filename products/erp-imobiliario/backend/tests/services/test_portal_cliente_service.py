"""
Unit tests for PortalClienteService — token generation/validation, dashboard data scoping.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_with_record(record):
    """Return a MockSupabaseClient whose default query returns *record*."""
    return MockSupabaseClient(data=record)


# ---------------------------------------------------------------------------
# gerar_token
# ---------------------------------------------------------------------------

class TestGerarToken:

    def test_token_is_string(self):
        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(MockSupabaseClient(), "user-1")

        token = svc.gerar_token()

        assert isinstance(token, str)

    def test_token_is_url_safe(self):
        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(MockSupabaseClient(), "user-1")

        token = svc.gerar_token()

        # URL-safe tokens use only alphanumeric, '-', and '_'
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', token)

    def test_token_has_sufficient_length(self):
        """secrets.token_urlsafe(32) produces at least 32 characters."""
        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(MockSupabaseClient(), "user-1")

        token = svc.gerar_token()

        assert len(token) >= 32

    def test_tokens_are_unique(self):
        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(MockSupabaseClient(), "user-1")

        tokens = {svc.gerar_token() for _ in range(50)}

        assert len(tokens) == 50


# ---------------------------------------------------------------------------
# validar_token
# ---------------------------------------------------------------------------

class TestValidarToken:

    def test_invalid_token_raises_403(self):
        """A token not found in the DB should raise HTTPException 403."""
        db = MockSupabaseClient(data=None)

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        with pytest.raises(HTTPException) as exc_info:
            svc.validar_token("nonexistent-token")

        assert exc_info.value.status_code == 403
        assert "inválido" in exc_info.value.detail.lower() or "revogado" in exc_info.value.detail.lower()

    def test_valid_non_expired_token(self):
        """A valid active token with future expiration should return the record."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        record = {
            "id": "pa-1",
            "token": "valid-token",
            "ativo": True,
            "data_expiracao": future,
            "cliente_id": "c-1",
        }
        db = _make_db_with_record(record)

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.validar_token("valid-token")

        assert result["id"] == "pa-1"

    def test_expired_token_raises_403(self):
        """A token whose data_expiracao is in the past should raise 403."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        record = {
            "id": "pa-1",
            "token": "expired-token",
            "ativo": True,
            "data_expiracao": past,
            "cliente_id": "c-1",
        }
        db = _make_db_with_record(record)

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        with pytest.raises(HTTPException) as exc_info:
            svc.validar_token("expired-token")

        assert exc_info.value.status_code == 403
        assert "expirado" in exc_info.value.detail.lower()

    def test_token_without_expiration_is_valid(self):
        """A token with no data_expiracao should be accepted."""
        record = {
            "id": "pa-1",
            "token": "no-expire",
            "ativo": True,
            "data_expiracao": None,
            "cliente_id": "c-1",
        }
        db = _make_db_with_record(record)

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.validar_token("no-expire")

        assert result["id"] == "pa-1"


# ---------------------------------------------------------------------------
# get_dashboard
# ---------------------------------------------------------------------------

class TestGetDashboard:

    def test_returns_all_sections(self):
        db = MockSupabaseClient()
        db.set_table_data("contratos", [{"id": "c1"}])
        db.set_table_data("lancamentos", [{"id": "l1"}])
        db.set_table_data("documentos", [{"id": "d1"}])

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.get_dashboard("client-1")

        assert "contratos" in result
        assert "financeiro" in result
        assert "documentos" in result

    def test_empty_data_returns_empty_lists(self):
        db = MockSupabaseClient(data=[])

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.get_dashboard("client-1")

        assert result["contratos"] == []
        assert result["financeiro"] == []
        assert result["documentos"] == []


# ---------------------------------------------------------------------------
# get_financeiro
# ---------------------------------------------------------------------------

class TestGetFinanceiro:

    def test_returns_list(self):
        db = MockSupabaseClient(data=[{"id": "l1", "valor": 100}])

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.get_financeiro("client-1")

        assert isinstance(result, list)

    def test_empty_returns_empty_list(self):
        db = MockSupabaseClient(data=[])

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.get_financeiro("client-1")

        assert result == []


# ---------------------------------------------------------------------------
# get_chamados
# ---------------------------------------------------------------------------

class TestGetChamados:

    def test_returns_list(self):
        db = MockSupabaseClient(data=[{"id": "ch1"}])

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.get_chamados("client-1", "pa-1")

        assert isinstance(result, list)

    def test_empty_returns_empty_list(self):
        db = MockSupabaseClient(data=[])

        from app.services.portal_cliente_service import PortalClienteService
        svc = PortalClienteService(db)

        result = svc.get_chamados("client-1", "pa-1")

        assert result == []
