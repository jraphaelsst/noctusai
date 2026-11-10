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
    assert "CHECK (evento IN ('adicionado', 'ativado', 'desativado', 'renomeado', 'removido'))" in FLAT
    assert "ator UUID NOT NULL" in FLAT
    assert "'renomeado'" in FLAT
    assert "AFTER INSERT OR UPDATE OR DELETE ON public.notification_owner_recipients" in FLAT
    for ev in ("'adicionado'", "'removido'", "'ativado'", "'desativado'"):
        assert ev in FLAT
    assert "BEFORE UPDATE OR DELETE ON public.notification_owner_recipient_events" in FLAT


def test_events_carry_no_phone_number():
    ddl = re.search(r"CREATE TABLE IF NOT EXISTS public\.notification_owner_recipient_events \((.*?)\);", FLAT)
    assert ddl and "numero" not in ddl.group(1)


def test_numero_is_immutable_by_trigger():
    assert "NEW.numero IS DISTINCT FROM OLD.numero" in FLAT
    assert "BEFORE UPDATE ON public.notification_owner_recipients" in FLAT


def test_events_cannot_be_truncated_or_written_by_service_role():
    assert "BEFORE TRUNCATE ON public.notification_owner_recipient_events FOR EACH STATEMENT" in FLAT
    assert "BEFORE TRUNCATE ON public.notification_owner_recipients FOR EACH STATEMENT" in FLAT
    assert "REVOKE ALL ON public.notification_owner_recipient_events FROM service_role" in FLAT
    assert "GRANT SELECT ON public.notification_owner_recipient_events TO service_role" in FLAT
    assert not re.search(r"GRANT (ALL|INSERT|UPDATE|DELETE|TRUNCATE)[A-Z, ]* ON public\.notification_owner_recipient_events", FLAT)
    assert ("REVOKE ALL ON SEQUENCE public.notification_owner_recipient_events_id_seq "
            "FROM PUBLIC, anon, authenticated, service_role") in FLAT


def test_only_the_definer_trigger_function_writes_events():
    m = re.search(r"FUNCTION public\.notification_owner_recipients_record_event\(\).*?LANGUAGE plpgsql SECURITY DEFINER "
                  r"SET search_path = public", FLAT)
    assert m
    assert ("REVOKE EXECUTE ON FUNCTION public.notification_owner_recipients_record_event() "
            "FROM PUBLIC, anon, authenticated, service_role") in FLAT


def test_remover_rpc_is_one_statement_with_the_actor():
    assert "FUNCTION public.remover_destinatario_dono(p_id UUID, p_ator UUID)" in FLAT
    assert "set_config('noc.ator', p_ator::text, true)" in FLAT
    assert "DELETE FROM public.notification_owner_recipients WHERE id = p_id RETURNING id INTO v_id" in FLAT
    assert "REVOKE EXECUTE ON FUNCTION public.remover_destinatario_dono(UUID, UUID) FROM PUBLIC, anon, authenticated" in FLAT
    assert "GRANT EXECUTE ON FUNCTION public.remover_destinatario_dono(UUID, UUID) TO service_role" in FLAT
