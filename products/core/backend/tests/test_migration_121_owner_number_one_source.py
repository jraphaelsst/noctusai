"""Migration 121: the agents hand-off number is copied INTO core's owner recipients (one owner number, in core)."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "owner_number_one_source")
FLAT = " ".join(SQL.split())


def test_copies_from_the_existing_agents_row_never_a_literal_number():
    assert not re.search(r"\+[1-9][0-9]{7,14}'", SQL.replace("^\\+[1-9][0-9]{7,14}$", ""))  # no hard-coded number
    assert "agents.runtime_settings" in FLAT and "numero_fallback_atendimento" in FLAT


def test_guarded_when_agents_schema_is_absent_and_idempotent():
    assert "to_regclass('agents.runtime_settings') IS NULL" in FLAT
    assert "ON CONFLICT (numero) DO NOTHING" in FLAT


def test_inserts_an_active_attributed_recipient_into_core():
    assert "INSERT INTO public.notification_owner_recipients" in FLAT
    assert "alterado_por" in FLAT and "alterado_em" in FLAT and "true" in FLAT.lower()
