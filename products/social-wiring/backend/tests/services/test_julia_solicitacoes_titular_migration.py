"""Migration `julia_solicitacoes_titular`: what the SQL promises is what the service writes (tipos, statuses, deadline column),
the table is backend-only, and re-applying is safe."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.services import julia_solicitacoes_titular_service as sol

SQL = migration_sql(Path(__file__).resolve().parents[2], "julia_solicitacoes_titular")  # by NAME: a renumber is safe


def _lista(coluna: str) -> tuple[str, ...]:
    m = re.search(rf"{coluna}\s+text\s+NOT NULL[^,]*?CHECK \({coluna} IN \(([^)]*)\)\)", SQL, re.S)
    assert m, coluna
    return tuple(re.findall(r"'([a-z_]+)'", m.group(1)))


def test_tipo_and_status_match_the_service_vocabulary():
    assert _lista("tipo") == sol.TIPOS
    assert _lista("status") == sol.STATUS


def test_the_record_carries_the_deadline_the_excerpt_cap_and_the_decision_columns():
    for col in ("prazo_em", "recebida_em", "decidido_por", "decidido_em", "motivo_decisao", "trecho_lead", "contato_id", "org_id"):
        assert re.search(rf"\b{col}\b", SQL), col
    assert "char_length(trecho_lead) <= 500" in SQL


def test_it_is_idempotent_forward_only_and_backend_only():
    assert "CREATE TABLE IF NOT EXISTS" in SQL and "ON CONFLICT (nome_pagina) DO NOTHING" in SQL
    assert not re.search(r"\bDROP (TABLE|COLUMN)\b", SQL)
    assert "ENABLE ROW LEVEL SECURITY" in SQL and "TO service_role" in SQL
    assert "REVOKE ALL ON social_wiring.julia_solicitacoes_titular FROM anon, authenticated" in SQL
    assert not re.search(r"TO authenticated", SQL)


def test_the_opt_outs_page_is_registered():
    assert "'julia_opt_outs'" in SQL
