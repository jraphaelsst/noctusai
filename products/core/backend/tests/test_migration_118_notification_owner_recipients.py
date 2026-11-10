"""Migration 118 (owner-notice recipients): shape, tier, service-role-only, events written by trigger."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "notification_owner_recipients")
FLAT = " ".join(SQL.split())
TABLES = ("notification_owner_recipients", "notification_owner_recipient_events")


def test_platform_tier_and_service_role_only():
    for t in TABLES:
        assert f"COMMENT ON TABLE public.{t} IS 'tier:platform'" in FLAT
        assert f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY" in FLAT
        assert f"REVOKE ALL ON public.{t} FROM PUBLIC, anon, authenticated" in FLAT
    assert not re.search(r"GRANT [A-Z, ]+ ON [\w.]+ TO (anon|authenticated|PUBLIC)", FLAT)
    assert not re.search(r"CREATE POLICY[^;]+TO (anon|authenticated)", FLAT)


def test_number_is_e164_and_unique():
    assert r"CHECK (numero ~ '^\+[1-9][0-9]{7,14}$')" in FLAT
    assert "UNIQUE (numero)" in FLAT


def test_events_enum_and_same_transaction_trigger():
    assert "CHECK (evento IN ('adicionado', 'ativado', 'desativado', 'removido'))" in FLAT
    assert "AFTER INSERT OR UPDATE OR DELETE ON public.notification_owner_recipients" in FLAT
    for ev in ("'adicionado'", "'removido'", "'ativado'", "'desativado'"):
        assert ev in FLAT
    assert "BEFORE UPDATE OR DELETE ON public.notification_owner_recipient_events" in FLAT


def test_events_carry_no_phone_number():
    ddl = re.search(r"CREATE TABLE IF NOT EXISTS public\.notification_owner_recipient_events \((.*?)\);", FLAT)
    assert ddl and "numero" not in ddl.group(1)


def test_no_security_definer_function():
    assert "SECURITY DEFINER" not in FLAT.upper()
