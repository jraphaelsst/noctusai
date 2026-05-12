"""
Tests for the AdConnect Distributors Router (Phase 2 — Supabase-backed).

Covers:
  • GET /distributors        — admin lists all in org; non-admin → 403.
  • GET /distributors/me     — current user's distributor (via JWT distributorId
                                or via membership lookup).
  • GET /distributors/{id}   — admin: any in org; user: own only.

Distributor PII is LGPD-flagged at the auth.py invitation flow (Phase 1
Engineer A); this router is read-only so no LGPD writes happen here.

Auth fixture pattern (Phase 1 of `adconnect-test-conftest-distributor-binding`):
the conftest's mock auth.get_user IGNORES bearer-token bytes — `_admin_headers()`
/ `_customer_headers()` are decorative. The role + distributor_id MUST be bound
on the mock via `bind_adconnect_user(...)` (or the `as_admin` / `as_customer`
fixtures) before the request.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from tests.conftest import (
    ORG_ID_BRAND as ORG_ID,
    OTHER_ORG_ID,
    DIST_A_ID,
    DIST_B_ID,
    bind_adconnect_user,
)


# Token content is decorative — `MockSupabaseClient.auth.get_user` is patched
# to return a fixed MockUser regardless of the bearer-token bytes (see
# `tests/conftest.py` docstring). Any HS256-signed header parses cleanly;
# the secret is a local literal because the canonical auth path uses the
# seed's `make_get_current_user` factory (Supabase-backed), not a custom
# JWT verifier.
_JWT_SECRET = "test-only-decorative-secret"


def _make_token(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(body, _JWT_SECRET, algorithm="HS256")


def _admin_headers(org_id: str = ORG_ID) -> dict[str, str]:
    tok = _make_token({"sub": "user-admin", "role": "admin", "org_id": org_id})
    return {"Authorization": f"Bearer {tok}"}


def _customer_headers(distributor_id: str = DIST_A_ID, *, org_id: str = ORG_ID) -> dict[str, str]:
    tok = _make_token({
        "sub": f"user-{distributor_id}",
        "role": "customer",
        "distributorId": distributor_id,
        "org_id": org_id,
    })
    return {"Authorization": f"Bearer {tok}"}


def _seed_distributors(mock_sb, *, distributors: list[dict] | None = None, memberships: list[dict] | None = None):
    distributors = distributors if distributors is not None else _default_distributors()
    memberships = memberships if memberships is not None else []
    mock_sb.set_table_data("distributors", distributors)
    mock_sb.set_table_data("distributor_memberships", memberships)


def _default_distributors() -> list[dict]:
    return [
        {
            "id": DIST_A_ID,
            "org_id": ORG_ID,
            "cnpj": "11.111.111/0001-11",
            "nome": "Distribuidor A",
            "endereco_cidade": "São Paulo",
            "endereco_uf": "SP",
            "status": "ativo",
            "tier": "STARTER",
        },
        {
            "id": DIST_B_ID,
            "org_id": ORG_ID,
            "cnpj": "22.222.222/0001-22",
            "nome": "Distribuidor B",
            "endereco_cidade": "Rio de Janeiro",
            "endereco_uf": "RJ",
            "status": "ativo",
            "tier": "MASTER",
        },
    ]


# ---------------------------------------------------------------------------
# GET /distributors
# ---------------------------------------------------------------------------


class TestListDistributors:
    def test_list_as_admin_returns_all_in_org(self, client):
        _seed_distributors(client.mock_supabase)
        bind_adconnect_user(client, role="admin", distributor_id=None)
        r = client.raw().get("/distributors", headers=_admin_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2
        assert {d["nome"] for d in data} == {"Distribuidor A", "Distribuidor B"}

    def test_list_as_non_admin_rejected(self, client):
        _seed_distributors(client.mock_supabase)
        bind_adconnect_user(client, role="customer", distributor_id=DIST_A_ID)
        r = client.raw().get("/distributors", headers=_customer_headers(DIST_A_ID))
        assert r.status_code == 403

    def test_list_unauthenticated_rejected(self, client):
        r = client.raw().get("/distributors")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /distributors/me
# ---------------------------------------------------------------------------


class TestMeEndpoint:
    def test_me_returns_distributor_for_customer_with_jwt_distributor_id(self, client):
        _seed_distributors(client.mock_supabase, distributors=[_default_distributors()[0]])
        bind_adconnect_user(client, role="customer", distributor_id=DIST_A_ID)
        r = client.raw().get("/distributors/me", headers=_customer_headers(DIST_A_ID))
        assert r.status_code == 200
        assert r.json()["id"] == DIST_A_ID

    def test_me_admin_without_distributor_id_returns_401(self, client):
        # Admin's user_metadata has no distributor_id → 401 (admin uses GET /
        # instead). Mock has no memberships either, so the fallback path also fails.
        _seed_distributors(client.mock_supabase, memberships=[])
        bind_adconnect_user(client, role="admin", distributor_id=None)
        r = client.raw().get("/distributors/me", headers=_admin_headers())
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /distributors/{id}
# ---------------------------------------------------------------------------


class TestGetDistributor:
    def test_get_admin_can_fetch_any_in_org(self, client):
        _seed_distributors(
            client.mock_supabase,
            distributors=[_default_distributors()[1]],  # only B
        )
        bind_adconnect_user(client, role="admin", distributor_id=None)
        r = client.raw().get(f"/distributors/{DIST_B_ID}", headers=_admin_headers())
        assert r.status_code == 200
        assert r.json()["nome"] == "Distribuidor B"

    def test_get_customer_can_fetch_own(self, client):
        _seed_distributors(
            client.mock_supabase,
            distributors=[_default_distributors()[0]],  # only A
        )
        bind_adconnect_user(client, role="customer", distributor_id=DIST_A_ID)
        r = client.raw().get(
            f"/distributors/{DIST_A_ID}",
            headers=_customer_headers(DIST_A_ID),
        )
        assert r.status_code == 200
        assert r.json()["nome"] == "Distribuidor A"

    def test_get_customer_cannot_fetch_other_distributor(self, client):
        # Customer B tries to read distributor A's row → 403.
        _seed_distributors(
            client.mock_supabase,
            distributors=[_default_distributors()[0]],  # the row IS A
        )
        # Customer's user_metadata has distributor_id=DIST_B_ID; they request DIST_A_ID.
        bind_adconnect_user(client, role="customer", distributor_id=DIST_B_ID)
        r = client.raw().get(
            f"/distributors/{DIST_A_ID}",
            headers=_customer_headers(DIST_B_ID),
        )
        assert r.status_code == 403

    def test_get_admin_from_other_org_cannot_see(self, client):
        # Admin from a different org → 403.
        _seed_distributors(
            client.mock_supabase,
            distributors=[_default_distributors()[0]],
        )
        bind_adconnect_user(client, role="admin", distributor_id=None, org_id=OTHER_ORG_ID)
        r = client.raw().get(
            f"/distributors/{DIST_A_ID}",
            headers=_admin_headers(org_id=OTHER_ORG_ID),
        )
        assert r.status_code == 403

    def test_get_not_found(self, client):
        _seed_distributors(client.mock_supabase, distributors=[])
        bind_adconnect_user(client, role="admin", distributor_id=None)
        r = client.raw().get(
            "/distributors/nonexistent-id",
            headers=_admin_headers(),
        )
        assert r.status_code == 404
