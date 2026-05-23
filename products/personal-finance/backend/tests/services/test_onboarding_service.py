"""Unit tests for `app.services.onboarding_service`.

Covers:
  - PF_DEFAULT_CATEGORIAS shape (19 rows, expected breakdown by tipo).
  - `seed_default_categories` — inserts on first call, no-op on second.
  - `ensure_pf_personal_org` — wraps seed helper with PF name template,
    threads org_id through to category seeding.
"""
from __future__ import annotations

import asyncio

from app.services.onboarding_service import (
    PF_DEFAULT_CATEGORIAS,
    ensure_pf_personal_org,
    seed_default_categories,
)
from noctusai_lib.testing import MockSupabaseClient


def _run(coro):
    return asyncio.run(coro)


class TestDefaultCategoriasShape:
    def test_count_is_nineteen(self):
        assert len(PF_DEFAULT_CATEGORIAS) == 19

    def test_breakdown_by_tipo(self):
        tipos = [r["tipo"] for r in PF_DEFAULT_CATEGORIAS]
        assert tipos.count("despesa") == 14
        assert tipos.count("receita") == 4
        assert tipos.count("transferencia") == 1

    def test_every_row_has_required_fields(self):
        for row in PF_DEFAULT_CATEGORIAS:
            assert {"nome", "tipo", "cor", "icone"} <= set(row.keys())
            assert row["cor"].startswith("#") and len(row["cor"]) == 7

    def test_all_nomes_unique(self):
        nomes = [r["nome"] for r in PF_DEFAULT_CATEGORIAS]
        assert len(nomes) == len(set(nomes))


class TestSeedDefaultCategories:
    def test_inserts_19_rows_for_fresh_org(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("categorias", [])  # no existing system seeds

        inserted = _run(seed_default_categories(db, "org-1"))

        assert inserted == 19
        payloads = db.table("categorias").inserted_payloads
        assert len(payloads) == 19
        assert all(p["org_id"] == "org-1" for p in payloads)
        assert all(p["is_sistema"] is True for p in payloads)
        assert {p["nome"] for p in payloads} == {r["nome"] for r in PF_DEFAULT_CATEGORIAS}

    def test_idempotent_when_already_seeded(self):
        db = MockSupabaseClient(validate_schema=False)
        # Simulate already-seeded org — at least one is_sistema row exists.
        # `org_id` must equal the org being seeded ("org-2") because the
        # idempotency pre-check filters `.eq("org_id", org_id).eq("is_sistema", True)`.
        db.set_table_data("categorias", [{"id": "cat-1", "org_id": "org-2", "is_sistema": True}])

        inserted = _run(seed_default_categories(db, "org-2"))

        assert inserted == 0
        # No inserts triggered.
        assert db.table("categorias").inserted_payloads == []


class TestEnsurePfPersonalOrg:
    def test_creates_org_with_pf_template_and_seeds_categorias(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("noctus_users", [])
        db.set_table_data("organizations", [])
        db.set_table_data("categorias", [])

        org_id = _run(
            ensure_pf_personal_org(db, "u-1", "alice@example.com")
        )

        assert org_id
        # Org row created with PF template.
        orgs = db.table("organizations").inserted_payloads
        assert len(orgs) == 1
        assert orgs[0]["nome"] == "Pessoal — alice@example.com"
        assert orgs[0]["is_personal"] is True
        # noctus_users row provisioned.
        users = db.table("noctus_users").inserted_payloads
        assert len(users) == 1
        assert users[0]["org_id"] == org_id
        # 19 categorias seeded for the new org.
        cats = db.table("categorias").inserted_payloads
        assert len(cats) == 19
        assert all(c["org_id"] == org_id for c in cats)

    def test_returns_existing_org_without_re_seeding(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data(
            "noctus_users",
            [{"id": "u-2", "email": "b@x.com", "org_id": "org-existing"}],
        )
        # `org_id` matches the existing org so the idempotency pre-check
        # (`.eq("org_id", "org-existing").eq("is_sistema", True)`) finds the
        # row and skips re-seeding.
        db.set_table_data(
            "categorias", [{"id": "cat-x", "org_id": "org-existing", "is_sistema": True}]
        )

        org_id = _run(ensure_pf_personal_org(db, "u-2", "b@x.com"))

        assert org_id == "org-existing"
        # No org or noctus_users inserts.
        assert db.table("organizations").inserted_payloads == []
        assert db.table("noctus_users").inserted_payloads == []
        # No re-seed of categorias either.
        assert db.table("categorias").inserted_payloads == []
