"""
Role-gate contract for /api/dimob/* — erp-financial-surfaces-role-gate.

Locked role tuple: ("platform_admin", "owner", "admin", "contador").
DIMOB is fiscal-tier — "manager" is intentionally EXCLUDED; "contador"
is intentionally INCLUDED (accountants must be able to preview and
generate DIMOB).

Reads (/preview, /validate) write to log_action as the aggregate-shape
audit. /generate already had log_action — preserved.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _set_role(client, role: str | None):
    user = client._mock_supabase.auth.get_user.return_value.user
    md = dict(user.user_metadata or {})
    if role is None:
        md.pop("erp_role", None)
    else:
        md["erp_role"] = role
    # DIMOB router calls get_org_id which reads user_metadata.org_id
    md.setdefault("org_id", "org-test-123")
    user.user_metadata = md


def _seed_empty(client):
    sb = client._mock_supabase
    sb.set_table_data("profiles", [])
    sb.set_table_data("clientes", [])
    sb.set_table_data("contratos_locacao", [])


class TestAllowedRoles:
    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "contador"])
    def test_preview_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/dimob/preview?ano=2025")
        assert resp.status_code == 200, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "contador"])
    def test_validate_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/dimob/validate?ano=2025")
        assert resp.status_code == 200, f"role={role} body={resp.text}"


class TestForbiddenRoles:
    @pytest.mark.parametrize("role", ["corretor", "manager", "user", None])
    def test_preview_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/dimob/preview?ano=2025")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "manager", "user", None])
    def test_validate_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/dimob/validate?ano=2025")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "manager", "user", None])
    def test_generate_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.post("/api/dimob/generate?ano=2025")
        assert resp.status_code == 403, f"role={role} body={resp.text}"


class TestReadAuditLog:
    """Aggregate-shape reads write log_action. Patches the router-module
    re-export (matches the existing `test_matriculas_router.py` pattern)."""

    def test_preview_writes_audit_log(self, client):
        _set_role(client, "contador")
        _seed_empty(client)
        mock_log = MagicMock()
        with patch("app.routers.dimob.log_action", mock_log):
            resp = client.get("/api/dimob/preview?ano=2025")
        assert resp.status_code == 200
        assert mock_log.called, "log_action must be invoked on /preview"
        call_args = [c.args for c in mock_log.call_args_list]
        assert any(
            ("ler" in args and "dimob_preview" in args) for args in call_args
        ), f"unexpected log_action calls: {call_args}"

    def test_validate_writes_audit_log(self, client):
        _set_role(client, "contador")
        _seed_empty(client)
        mock_log = MagicMock()
        with patch("app.routers.dimob.log_action", mock_log):
            resp = client.get("/api/dimob/validate?ano=2025")
        assert resp.status_code == 200
        assert mock_log.called, "log_action must be invoked on /validate"
        call_args = [c.args for c in mock_log.call_args_list]
        assert any(
            ("ler" in args and "dimob_validate" in args) for args in call_args
        ), f"unexpected log_action calls: {call_args}"
