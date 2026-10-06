"""Structural tests for the SECURITY DEFINER EXECUTE lockdown migrations
(core 061 + per-product siblings). No database needed."""
from __future__ import annotations

from pathlib import Path

import pytest

PRODUCTS = Path(__file__).resolve().parents[3]

MIGRATIONS = {
    "core": ("061_secdef_execute_lockdown.sql", ("public", "core")),
    "social-wiring": ("209_secdef_execute_lockdown.sql", ("social_wiring",)),
    "community": ("016_secdef_execute_lockdown.sql", ("community",)),
    "academia-de-reciclagem": ("014_secdef_execute_lockdown.sql", ("academia_de_reciclagem",)),
    "store": ("010_secdef_execute_lockdown.sql", ("store",)),
    "agents": ("019_secdef_execute_lockdown.sql", ("agents",)),
    "igig": ("037_secdef_execute_lockdown.sql", ("igig",)),
    # Inactive-product schemas (owner-authorized 2026-10-06; grants only).
    "erp-imobiliario": ("049_secdef_execute_lockdown.sql", ("erp", "imobi_scheduling", "media_scheduling")),
    "therapy-platform": ("017_secdef_execute_lockdown.sql", ("therapy",)),
    "orbity": ("018_secdef_execute_lockdown.sql", ("orbity",)),
    "core-pilates": ("063_secdef_execute_lockdown_pilates.sql", ("pilates",)),
}


def _sql(product: str) -> str:
    return (PRODUCTS / product.removesuffix("-pilates") / "backend" / "migrations" / MIGRATIONS[product][0]).read_text(encoding="utf-8")


@pytest.mark.parametrize("product", sorted(MIGRATIONS))
def test_revokes_secdef_from_callers_and_grants_service_role(product: str) -> None:
    sql = _sql(product)
    assert "p.prosecdef" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql
    for schema in MIGRATIONS[product][1]:
        assert f"'{schema}'" in sql


@pytest.mark.parametrize("product", sorted(MIGRATIONS))
def test_no_untyped_empty_array_literal(product: str) -> None:
    # Postgres cannot type a bare `ARRAY[]` (42P18) — it failed 4 of these
    # migrations against prod on 2026-10-06 while every structural test passed.
    import re
    assert not re.search(r"ARRAY\[\](?!::)", _sql(product))


@pytest.mark.parametrize("product", sorted(MIGRATIONS))
def test_rls_helpers_kept_by_derivation(product: str) -> None:
    sql = _sql(product)
    assert "'pg_policy'::regclass" in sql and "'pg_attrdef'::regclass" in sql
    assert "deptype = 'e'" in sql  # extension members skipped


@pytest.mark.parametrize("product", sorted(MIGRATIONS))
def test_default_privileges_hardened(product: str) -> None:
    sql = _sql(product)
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA" in sql
    assert "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated" in sql


def test_core_explicit_keep_list_names_rls_helpers() -> None:
    sql = _sql("core")
    for fn in ("current_org_id", "current_user_org_id", "current_org_role", "current_user_id",
               "is_customer", "current_customer_org_id", "is_platform_admin"):
        assert f"'{fn}'" in sql
    assert "'fotos_lote_visivel'" in _sql("social-wiring")
    c = _sql("community")
    assert "'eh_equipe'" in c and "'meu_membro_id'" in c


def test_secdef_probe_registered() -> None:
    import sys
    sys.path.insert(0, str(PRODUCTS.parent / "mcp" / "noctusai"))
    from tools.noctus.dev.verify_db_guards import DEFAULT_REGISTRY

    probe = next(p for p in DEFAULT_REGISTRY if p.guard_name == "secdef_execute_lockdown")
    assert probe.kind == "state_assertion"
    assert "has_function_privilege('anon'" in probe.sql
    assert "'igig'" in probe.sql
