"""Static checks for core's browser-grant lockdown migration (104).

No live database: the SQL is asserted structurally. The migration's own final
DO block RAISEs on any remaining anon/authenticated grant when it is applied."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "products/core/backend/migrations"
SQL = migration_sql(MIGRATIONS, "public_browser_grants_service_only")
FLAT = " ".join(SQL.split())
CODE = "\n".join(l for l in SQL.splitlines() if not l.lstrip().startswith("--"))
CODE_FLAT = " ".join(CODE.split())


def test_default_privileges_are_revoked_for_postgres():
    for obj in ("TABLES", "SEQUENCES"):
        assert (f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON {obj} "
                "FROM anon, authenticated") in CODE_FLAT


def test_supabase_admin_defaults_never_fail_the_deploy():
    block = CODE_FLAT[CODE_FLAT.index("FOR ROLE supabase_admin") - 200:]
    assert "EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE" in block


def test_every_public_relation_loses_browser_grants_but_not_finance():
    assert "REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated" in CODE_FLAT
    assert "c.relname NOT LIKE 'fin\\_%'" in CODE_FLAT
    assert "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated" in CODE_FLAT


def test_nothing_is_granted_back_to_the_browser():
    # Step 1: the browser reads no core public table; only service_role is granted.
    for m in re.finditer(r"GRANT [^;]*? TO ([^;]*);", CODE_FLAT):
        assert not re.search(r"\b(anon|authenticated|PUBLIC)\b", m.group(1)), m.group(0)


def test_products_is_not_recreated_and_loses_read_all():
    assert 'DROP POLICY IF EXISTS "products_read_all" ON public.products' in CODE_FLAT
    assert not re.search(r"(CREATE|ALTER) TABLE[^;]*public\.products\b", CODE_FLAT)
    assert not re.search(r"CREATE POLICY[^;]*ON public\.products\b", CODE_FLAT)


def test_every_touched_table_declares_a_tier():
    assert "COMMENT ON TABLE public.%I IS %L" in CODE_FLAT
    tiers = dict(re.findall(r"\('([a-z_]+)','(platform|org|service|public)'\)", CODE))
    for t in ("products", "noctus_users", "plans", "plan_prices", "organizations", "notifications"):
        assert t in tiers, t
    assert not any(t.startswith("fin_") for t in tiers)
    assert tiers["products"] == "platform"


def test_final_assertion_guards_grants_policy_and_noctus_users():
    assert "has_any_column_privilege('authenticated'" in CODE_FLAT
    assert "RAISE EXCEPTION '104: public relation(s) still reachable by anon/authenticated" in CODE_FLAT
    assert "RAISE EXCEPTION '104: products_read_all still present'" in CODE_FLAT
    assert "RAISE EXCEPTION '104: noctus_users has a browser UPDATE policy'" in CODE_FLAT


def test_no_migration_gives_authenticated_an_update_policy_on_noctus_users():
    """`noctus_users.role` is the platform-admin gate: the browser must never write it."""
    pat = re.compile(r"CREATE POLICY\s+\"?(\w+)\"?\s+ON\s+(?:public\.)?noctus_users\b([^;]*);", re.I | re.S)
    offenders = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        for name, body in pat.findall(f.read_text(encoding="utf-8")):
            b = " ".join(body.split()).upper()
            writes = re.search(r"\bFOR (UPDATE|ALL)\b", b) or "FOR " not in b
            browser = re.search(r"\bTO\b[^;]*\b(AUTHENTICATED|ANON|PUBLIC)\b", b) or " TO " not in f" {b} "
            if writes and browser:
                offenders.append(f"{f.name}:{name}")
    assert not offenders, offenders
