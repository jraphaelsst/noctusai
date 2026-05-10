"""
Real-DB RLS smoke tests for the AdConnect identity foundation
(migration `002_adconnect_identity.sql`).

Skips automatically when Supabase credentials aren't set (see
`conftest.py`). When credentials are present, these tests:

  1. Insert a distributor row under a brand-org (service-role bypass).
  2. Confirm the row is queryable via service-role.
  3. Cleanup deletes the row + the brand-org via the session-scoped
     `test_brand_org` fixture.

These tests exercise the schema + service-role bypass path. RLS-as-user
tests (distributor user A cannot see distributor B's row, brand owner
sees all) require an authed Supabase JWT for a test user — the harness
to mint those is shared with `products/erp-imobiliario/backend/tests/realdb/`
and will land in Phase 2 when the catalog routers need it. For now we
verify schema correctness + insert path.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


def test_distributor_insert_under_brand_org(adconnect_db, test_brand_org, cleanup):
    """Service-role can insert a distributor row tied to a brand org."""
    cnpj = f"00.000.000/0001-{uuid.uuid4().hex[:2]}"
    row = (
        adconnect_db.table("distributors")
        .insert({
            "org_id": test_brand_org["id"],
            "cnpj": cnpj,
            "nome": "Distribuidora Teste RLS",
            "endereco_uf": "SP",
        })
        .execute()
        .data[0]
    )
    cleanup.append(("distributors", row["id"]))
    assert row["org_id"] == test_brand_org["id"]
    assert row["status"] == "ativo"
    assert row["tier"] == "STARTER"


def test_distributor_cnpj_unique(adconnect_db, test_brand_org, cleanup):
    """The CNPJ unique constraint blocks duplicates."""
    cnpj = f"99.999.999/0001-{uuid.uuid4().hex[:2]}"
    first = (
        adconnect_db.table("distributors")
        .insert({"org_id": test_brand_org["id"], "cnpj": cnpj, "nome": "First"})
        .execute()
        .data[0]
    )
    cleanup.append(("distributors", first["id"]))

    with pytest.raises(Exception):
        adconnect_db.table("distributors").insert({
            "org_id": test_brand_org["id"],
            "cnpj": cnpj,
            "nome": "Duplicate",
        }).execute()


def test_membership_role_constraint(adconnect_db, test_brand_org, core_db, cleanup):
    """The role check constraint rejects unknown roles."""
    cnpj = f"11.111.111/0001-{uuid.uuid4().hex[:2]}"
    dist = (
        adconnect_db.table("distributors")
        .insert({"org_id": test_brand_org["id"], "cnpj": cnpj, "nome": "Role Check"})
        .execute()
        .data[0]
    )
    cleanup.append(("distributors", dist["id"]))

    # Create a user_id that exists in noctus_users so FK passes.
    email = f"adconnect-rls-{uuid.uuid4().hex[:8]}@realdb.test"
    user_resp = core_db.auth.admin.create_user({
        "email": email,
        "password": f"TestPass!{uuid.uuid4().hex[:8]}",
        "email_confirm": True,
        "user_metadata": {"org_id": test_brand_org["id"]},
    })
    user_id = user_resp.user.id

    try:
        with pytest.raises(Exception):
            adconnect_db.table("distributor_memberships").insert({
                "user_id": user_id,
                "distributor_id": dist["id"],
                "role": "PHARAOH",  # not in CHECK list
            }).execute()
    finally:
        try:
            core_db.auth.admin.delete_user(user_id)
        except Exception:
            pass
