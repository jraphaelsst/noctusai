"""SEC hotfix 2026-10-06 — `/api/import` (admin bundle import) is pinned to the
TRUSTED org: a user context whose org differs from ``noctus_users.org_id`` is
refused (``org_mismatch``), and the bridge ignores ``user_metadata.org_id``.
"""
from __future__ import annotations

import asyncio
from uuid import NAMESPACE_OID, UUID, uuid5

import pytest
from fastapi import HTTPException
from noctusai_lib.api.auth.session.types import AuthContext

_TRUSTED_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_VICTIM_ORG = UUID("00000000-0000-4000-8000-0000000000dd")
_USER = UUID("00000000-0000-4000-8000-0000000000bb")


def _ctx(org: UUID) -> AuthContext:
    return AuthContext(
        org_id=org, caller_kind="user", user_id=_USER, scopes=[],
        raw_token="s", api_token_id=None,
    )


def _seed(client) -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(_USER), "org_id": str(_TRUSTED_ORG), "org_role": "owner"}]
    )


def test_admin_of_trusted_org_cannot_import_into_another_org(client, store, set_auth):
    _seed(client)
    set_auth(_ctx(_VICTIM_ORG))  # e.g. a bridge/session fed a forged org
    resp = client.raw().post(
        "/api/import", content=b"{}\n", headers={"content-type": "application/x-ndjson"}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "org_mismatch"


def test_legacy_bridge_takes_org_from_trusted_row_not_metadata(client):
    from app.dependencies import _legacy_jwt_resolver

    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(uuid5(NAMESPACE_OID, "test-user-123")), "org_id": str(_TRUSTED_ORG), "org_role": "owner"}]
    )
    # The shared fixture's user_metadata.org_id is a DIFFERENT (test) org.
    ctx = asyncio.new_event_loop().run_until_complete(_legacy_jwt_resolver("jwt"))
    assert ctx.org_id == _TRUSTED_ORG


def test_legacy_bridge_refuses_user_without_trusted_row(client):
    from app.dependencies import _legacy_jwt_resolver

    client.mock_supabase.set_table_data("noctus_users", [])
    with pytest.raises(HTTPException) as exc:
        asyncio.new_event_loop().run_until_complete(_legacy_jwt_resolver("jwt"))
    assert exc.value.status_code == 403
