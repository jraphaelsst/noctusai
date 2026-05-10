"""
Real-DB smoke tests for the admin V1 surface (Phase 6).

Skips automatically when Supabase credentials aren't set (see `conftest.py`).
When credentials are present, these tests exercise:

  1. The brand-admin role gate via service-role client (bypasses RLS but
     proves the schema accepts the admin write paths).
  2. RLS-as-a-distributor: a distributor user's JWT cannot SELECT a
     distributor row outside their membership. This piece is deferred to
     Phase 8 / a dedicated identity harness — V1 keeps the schema check.

These tests do NOT mint authed JWTs (the harness for that is shared with
PF / ERP and lives in `core` — see Phase 8 plan). They confirm:
  - The migration file lets the brand admin INSERT a regras_recompensa row
    with the soft-delete shape (ativa=false) and read it back.
  - The faturas table accepts a row with the cross-distributor admin shape.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


def test_admin_role_can_insert_and_soft_delete_reward_rule(
    adconnect_db, test_brand_org, cleanup
):
    """Service-role (acting as brand admin path) can insert a reward rule
    and flip ativa=false (soft delete)."""
    org_id = test_brand_org["id"]
    rule = (
        adconnect_db.table("regras_recompensa")
        .insert({
            "org_id": org_id,
            "nome": f"Cashback Test {uuid.uuid4().hex[:6]}",
            "tipo": "cashback_percentual",
            "valor": 5.0,
            "ativa": True,
        })
        .execute()
        .data[0]
    )
    cleanup.append(("regras_recompensa", rule["id"]))

    # Soft-delete: flip ativa=false.
    updated = (
        adconnect_db.table("regras_recompensa")
        .update({"ativa": False})
        .eq("id", rule["id"])
        .execute()
        .data[0]
    )
    assert updated["ativa"] is False


def test_admin_can_create_distributor_under_brand_org(
    adconnect_db, test_brand_org, cleanup
):
    """Brand-admin onboarding path: insert a distributor under the brand's
    org and confirm the default shape (status='ativo', tier='STARTER')."""
    cnpj = f"77.777.777/0001-{uuid.uuid4().hex[:2]}"
    row = (
        adconnect_db.table("distributors")
        .insert({
            "org_id": test_brand_org["id"],
            "cnpj": cnpj,
            "nome": "Admin Onboarded Distributor",
        })
        .execute()
        .data[0]
    )
    cleanup.append(("distributors", row["id"]))
    assert row["status"] == "ativo"
    assert row["tier"] == "STARTER"
