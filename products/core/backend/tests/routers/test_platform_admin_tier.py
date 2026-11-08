"""The platform-admin tier of core's API: `/api/admin/*` is platform-only and says so the same way everywhere.

Exercises the REAL `get_current_admin` dependency (the conftest `client` fixtures replace it wholesale, so
they cannot prove its verdict): an org owner/admin whose `noctus_users.role` is not `admin` is refused with a
strict 403 + code `platform_admin_required`; a missing token is a strict 401.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app import dependencies


def _db_with_role(role):
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.single.return_value
    chain.execute.return_value = SimpleNamespace(data={"role": role} if role is not None else None)
    return db


def _run(role, *, authorization="Bearer t"):
    async def _user(_authorization):
        return SimpleNamespace(id="u1"), "tok"

    with patch.object(dependencies, "get_current_user", _user), \
         patch.object(dependencies, "get_admin_client", lambda: _db_with_role(role)):
        return asyncio.run(dependencies.get_current_admin(authorization, None, None))


@pytest.mark.parametrize("role", ["manager", "member", "viewer", "owner", "marketing", None])
def test_non_platform_role_is_refused_with_the_canonical_403(role):
    # `manager`/`owner` are the org-admin shapes: an org admin is NOT a platform admin.
    with pytest.raises(HTTPException) as exc:
        _run(role)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "platform_admin_required"


def test_platform_admin_passes():
    user, token = _run("admin")
    assert user.id == "u1" and token == "tok"


def test_missing_token_is_a_strict_401():
    async def _no_user(authorization):
        raise HTTPException(status_code=401, detail="Token ausente")

    with patch.object(dependencies, "get_current_user", _no_user):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(dependencies.get_current_admin(None, None, None))
    assert exc.value.status_code == 401


def test_openapi_lists_no_platform_admin_paths():
    """`/api/admin/*` stays out of the public schema (the org-tier spend read moved to /api/orgs/{id}/llm-spend)."""
    from app.main import app

    leaked = [p for p in app.openapi()["paths"] if p.startswith("/api/admin")]
    assert leaked == []
    assert "/api/orgs/{org_id}/llm-spend" in app.openapi()["paths"]


def test_org_tier_spend_read_is_not_under_the_admin_prefix(client):
    resp = client.get("/api/orgs/11111111-1111-1111-1111-111111111111/llm-spend")
    assert resp.status_code == 403
