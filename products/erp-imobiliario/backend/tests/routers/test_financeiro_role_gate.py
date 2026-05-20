"""
Role-gate contract for /api/financeiro/* — erp-financial-surfaces-role-gate.

Locked role tuple: ("platform_admin", "owner", "admin", "manager").
A "corretor" / unknown role MUST get 403; "contador" is intentionally
EXCLUDED from this surface (general financial reads are managerial, not
fiscal-tier).

Aggregate reads (/resumo, /fluxo-caixa) ALSO write to log_action — verified
here as a smoke ("at-least-once" call), not exhaustive coverage (the audit
contract itself is covered upstream).

Note: per the no-monkey-patching-our-code rule, we set role via
user.user_metadata — the same shape the runtime resolver reads. The gate
runs production code unmodified.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — set the role the same way the runtime resolver reads it.
# ---------------------------------------------------------------------------


def _set_role(client, role: str | None):
    """Set or clear erp_role on the default mock user."""
    user = client._mock_supabase.auth.get_user.return_value.user
    md = dict(user.user_metadata or {})
    if role is None:
        md.pop("erp_role", None)
    else:
        md["erp_role"] = role
    user.user_metadata = md


def _seed_empty_lancamentos(client):
    client._mock_supabase.set_table_data("lancamentos", [])


# ---------------------------------------------------------------------------
# Allowed-role coverage (200)
# ---------------------------------------------------------------------------


class TestAllowedRoles:
    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "manager"])
    def test_list_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty_lancamentos(client)
        resp = client.get("/api/financeiro")
        assert resp.status_code == 200, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "manager"])
    def test_resumo_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty_lancamentos(client)
        resp = client.get("/api/financeiro/resumo")
        assert resp.status_code == 200, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "manager"])
    def test_fluxo_caixa_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty_lancamentos(client)
        resp = client.get("/api/financeiro/fluxo-caixa")
        assert resp.status_code == 200, f"role={role} body={resp.text}"


# ---------------------------------------------------------------------------
# Forbidden-role coverage (403)
# ---------------------------------------------------------------------------


class TestForbiddenRoles:
    @pytest.mark.parametrize("role", ["corretor", "contador", "user", None])
    def test_list_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty_lancamentos(client)
        resp = client.get("/api/financeiro")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "contador", "user", None])
    def test_resumo_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty_lancamentos(client)
        resp = client.get("/api/financeiro/resumo")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "contador", "user", None])
    def test_fluxo_caixa_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty_lancamentos(client)
        resp = client.get("/api/financeiro/fluxo-caixa")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "contador", "user"])
    def test_get_by_id_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty_lancamentos(client)
        resp = client.get("/api/financeiro/some-id")
        assert resp.status_code == 403, f"role={role} body={resp.text}"


# ---------------------------------------------------------------------------
# Audit-log contract on aggregate reads
# ---------------------------------------------------------------------------


class TestReadAuditLog:
    """Aggregate-shape reads write log_action.

    The router imports `log_action` into its own module namespace via
    `from app.dependencies import log_action`, so we patch the router's
    re-export (matches the convention in `test_matriculas_router.py`).
    Patching a write side-effect at the router module boundary is one of
    the sanctioned DI-test seams — we are NOT replacing our own guards or
    business logic.
    """

    def test_resumo_writes_audit_log(self, client):
        _set_role(client, "admin")
        _seed_empty_lancamentos(client)
        mock_log = MagicMock()
        with patch("app.routers.financeiro.log_action", mock_log):
            resp = client.get("/api/financeiro/resumo")
        assert resp.status_code == 200
        assert mock_log.called, "log_action must be invoked on /resumo"
        call_args = [c.args for c in mock_log.call_args_list]
        assert any(
            ("ler" in args and "financeiro_resumo" in args) for args in call_args
        ), f"unexpected log_action calls: {call_args}"

    def test_fluxo_caixa_writes_audit_log(self, client):
        _set_role(client, "admin")
        _seed_empty_lancamentos(client)
        mock_log = MagicMock()
        with patch("app.routers.financeiro.log_action", mock_log):
            resp = client.get("/api/financeiro/fluxo-caixa")
        assert resp.status_code == 200
        assert mock_log.called, "log_action must be invoked on /fluxo-caixa"
        call_args = [c.args for c in mock_log.call_args_list]
        assert any(
            ("ler" in args and "financeiro_fluxo_caixa" in args) for args in call_args
        ), f"unexpected log_action calls: {call_args}"
