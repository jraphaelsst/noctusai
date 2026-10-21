"""Structural pins for migration 042 (a lead that asks to stop is never dropped silently). The behaviour runs on a
real Postgres in the chain replay (`mcp/noctusai/tests/test_agents_lead_opt_out_on_replay.py`); these keep the intent
honest against the Python side and the security posture (lead data is service-role only)."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.stores.threads import NOTIFICACAO_STATUS, OPT_OUT_MENSAGEM_MAX, OPT_OUT_MOTIVO_MAX, OPT_OUT_ORIGENS

ROOT = Path(__file__).resolve().parents[1]
M42 = migration_sql(ROOT, "julia_v2_lead_opt_out_eventos")
SIG = "UUID, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, UUID, UUID, UUID"


def test_the_table_is_service_role_only():
    assert "ALTER TABLE agents.lead_opt_out_eventos ENABLE ROW LEVEL SECURITY" in M42
    assert re.search(r'ON agents\.lead_opt_out_eventos\s+FOR ALL TO service_role', M42)
    assert "REVOKE ALL ON agents.lead_opt_out_eventos FROM PUBLIC, anon, authenticated" in M42


def test_the_vocabularies_and_caps_match_the_python_side():
    for v in OPT_OUT_ORIGENS + NOTIFICACAO_STATUS:
        assert f"'{v}'" in M42, v
    assert f"BETWEEN 1 AND {OPT_OUT_MOTIVO_MAX}" in M42 and f"<= {OPT_OUT_MENSAGEM_MAX}" in M42


def test_the_rpc_keeps_the_old_call_shape_and_is_service_role_only():
    flat = " ".join(M42.split())
    assert "DROP FUNCTION IF EXISTS agents.registrar_opt_out(UUID, TEXT, TEXT, TIMESTAMPTZ)" in flat
    assert f"REVOKE ALL ON FUNCTION agents.registrar_opt_out({SIG}) FROM PUBLIC, anon, authenticated" in flat
    assert f"GRANT EXECUTE ON FUNCTION agents.registrar_opt_out({SIG}) TO service_role" in flat
    for default in ("p_origem TEXT DEFAULT 'integracao'", "p_motivo TEXT DEFAULT NULL", "p_mensagem_lead TEXT DEFAULT NULL"):
        assert default in flat


def test_the_event_is_written_in_the_same_function_as_the_opt_out_and_the_lead_row_is_locked_first():
    assert M42.index("FOR UPDATE") < M42.index("INSERT INTO agents.lead_opt_out_eventos")
    assert M42.index("UPDATE agents.lead_refs SET opt_out_em") < M42.index("INSERT INTO agents.lead_opt_out_eventos")


def test_an_erased_lead_takes_its_events_with_it():
    assert "lead_ref_id UUID NOT NULL REFERENCES agents.lead_refs(id) ON DELETE CASCADE" in M42
