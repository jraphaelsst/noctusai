"""
Role-gate contract for /api/impostos/* — erp-financial-surfaces-role-gate.

Locked role tuple: ("platform_admin", "owner", "admin", "contador").
Impostos is fiscal-tier — "manager" is intentionally EXCLUDED; "contador"
is intentionally INCLUDED.

Aggregate read /resumo writes to log_action.
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
    user.user_metadata = md


def _seed_empty(client):
    client._mock_supabase.set_table_data("impostos", [])


class TestAllowedRoles:
    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "contador"])
    def test_list_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/impostos")
        assert resp.status_code == 200, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "contador"])
    def test_resumo_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/impostos/resumo")
        assert resp.status_code == 200, f"role={role} body={resp.text}"


class TestForbiddenRoles:
    @pytest.mark.parametrize("role", ["corretor", "manager", "user", None])
    def test_list_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/impostos")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "manager", "user", None])
    def test_resumo_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/impostos/resumo")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "manager", "user"])
    def test_get_by_id_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/impostos/some-id")
        assert resp.status_code == 403, f"role={role} body={resp.text}"


class TestReadAuditLog:
    """Aggregate-shape reads write log_action. Patches the router-module
    re-export (matches the existing `test_matriculas_router.py` pattern)."""

    def test_resumo_writes_audit_log(self, client):
        _set_role(client, "contador")
        _seed_empty(client)
        mock_log = MagicMock()
        with patch("app.routers.impostos.log_action", mock_log):
            resp = client.get("/api/impostos/resumo")
        assert resp.status_code == 200
        assert mock_log.called, "log_action must be invoked on /resumo"
        call_args = [c.args for c in mock_log.call_args_list]
        assert any(
            ("ler" in args and "impostos_resumo" in args) for args in call_args
        ), f"unexpected log_action calls: {call_args}"
