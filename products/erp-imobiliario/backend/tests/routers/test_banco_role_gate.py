"""
Role-gate contract for /api/banco/* — erp-financial-surfaces-role-gate.

Locked role tuple: ("platform_admin", "owner", "admin", "manager").
Banco is general-financial-tier — "contador" intentionally EXCLUDED;
"manager" intentionally INCLUDED (cash-flow visibility).

Aggregate reads /extratos and /conciliacao write to log_action.
Per-id /retorno/{remessa_id} stays un-logged (low-exfiltration single
record).
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
    sb = client._mock_supabase
    sb.set_table_data("extratos_bancarios", [])
    sb.set_table_data("movimentacoes_bancarias", [])
    sb.set_table_data("remessas", [])


class TestAllowedRoles:
    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "manager"])
    def test_list_extratos_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/banco/extratos")
        assert resp.status_code == 200, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["platform_admin", "owner", "admin", "manager"])
    def test_conciliacao_allowed_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/banco/conciliacao")
        assert resp.status_code == 200, f"role={role} body={resp.text}"


class TestForbiddenRoles:
    @pytest.mark.parametrize("role", ["corretor", "contador", "user", None])
    def test_list_extratos_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/banco/extratos")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "contador", "user", None])
    def test_conciliacao_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/banco/conciliacao")
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "contador", "user"])
    def test_retorno_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.get("/api/banco/retorno/rem-some-id")
        # 403 from gate, never 404 — gate fires BEFORE the lookup.
        assert resp.status_code == 403, f"role={role} body={resp.text}"

    @pytest.mark.parametrize("role", ["corretor", "contador", "user"])
    def test_importar_forbidden_for_role(self, client, role):
        _set_role(client, role)
        _seed_empty(client)
        resp = client.post("/api/banco/importar", json={
            "banco": "001",
            "movimentacoes": [
                {"data": "2026-03-01", "descricao": "x", "valor": 1.0, "tipo": "credito"},
            ],
        })
        assert resp.status_code == 403, f"role={role} body={resp.text}"


class TestReadAuditLog:
    """Aggregate-shape reads write log_action. Patches the router-module
    re-export (matches the existing `test_matriculas_router.py` pattern)."""

    def test_extratos_writes_audit_log(self, client):
        _set_role(client, "admin")
        _seed_empty(client)
        mock_log = MagicMock()
        with patch("app.routers.banco.log_action", mock_log):
            resp = client.get("/api/banco/extratos")
        assert resp.status_code == 200
        assert mock_log.called, "log_action must be invoked on /extratos"
        call_args = [c.args for c in mock_log.call_args_list]
        assert any(
            ("ler" in args and "banco_extratos" in args) for args in call_args
        ), f"unexpected log_action calls: {call_args}"

    def test_conciliacao_writes_audit_log(self, client):
        _set_role(client, "admin")
        _seed_empty(client)
        mock_log = MagicMock()
        with patch("app.routers.banco.log_action", mock_log):
            resp = client.get("/api/banco/conciliacao")
        assert resp.status_code == 200
        assert mock_log.called, "log_action must be invoked on /conciliacao"
        call_args = [c.args for c in mock_log.call_args_list]
        assert any(
            ("ler" in args and "banco_conciliacao" in args) for args in call_args
        ), f"unexpected log_action calls: {call_args}"
