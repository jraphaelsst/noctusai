"""Migration `julia_staff_protecao_bloqueio` (298): what the SQL promises is what the services write -- the roles, the limit defaults and
ranges (the UI form is built from them), the blocklist vocabulary -- the three tables are backend-only, the backfill keeps every
authorized number authorized, and re-applying is safe."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.services import julia_protecao_service as prot
from app.services import julia_staff_service as staff

SQL = migration_sql(Path(__file__).resolve().parents[2], "julia_staff_protecao_bloqueio")  # by NAME: a renumber is safe


def test_the_roles_match_the_service_vocabulary():
    m = re.search(r"papel\s+text\s+NOT NULL CHECK \(papel IN \(([^)]*)\)\)", SQL)
    assert m and tuple(re.findall(r"'([a-z]+)'", m.group(1))) == staff.PAPEIS


def test_every_limit_default_and_range_is_the_service_constant():
    for chave, (lo, hi) in prot.FAIXAS.items():
        m = re.search(rf"{chave}\s+integer\s+NOT NULL DEFAULT (\d+)\s+CHECK \({chave} BETWEEN (\d+) AND (\d+)\)", SQL)
        assert m, chave
        assert (int(m.group(2)), int(m.group(3))) == (lo, hi), chave
        assert int(m.group(1)) == prot.PADRAO[chave], chave
    assert re.search(r"bloqueio_auto_ativo\s+boolean\s+NOT NULL DEFAULT true", SQL) and prot.PADRAO["bloqueio_auto_ativo"] is True
    assert f"char_length(prompt_documento_lead) BETWEEN {prot.PROMPT_MIN} AND {prot.PROMPT_MAX}" in SQL


def test_the_blocklist_vocabulary_and_invariants():
    gatilhos = re.search(r"gatilho\s+IN \('manual', ([^)]*)\)", SQL)
    assert gatilhos and tuple(re.findall(r"'([a-z_]+)'", gatilhos.group(1))) == prot.GATILHOS_AUTO
    assert f"BETWEEN 1 AND {prot.MOTIVO_MAX}" in SQL
    assert "julia_numeros_bloqueados_auto_expira" in SQL and "origem <> 'automatico' OR expira_em IS NOT NULL" in SQL
    assert "CREATE UNIQUE INDEX IF NOT EXISTS julia_numeros_bloqueados_ativo_uk" in SQL and "WHERE ativo" in SQL


def test_a_staff_entry_must_be_identifiable_and_a_number_is_unique_per_org():
    assert "julia_staff_identificavel" in SQL and "telefone IS NOT NULL OR user_id IS NOT NULL" in SQL
    assert "CREATE UNIQUE INDEX IF NOT EXISTS julia_staff_org_telefone_uk" in SQL and "(org_id, telefone)" in SQL


def test_it_is_idempotent_forward_only_and_backend_only():
    assert SQL.count("CREATE TABLE IF NOT EXISTS") == 3 and "ON CONFLICT" in SQL
    assert not re.search(r"\bDROP (TABLE|COLUMN)\b", SQL)
    for t in ("julia_staff", "julia_protecao_config", "julia_numeros_bloqueados"):
        assert f"'{t}'" in SQL
    assert "ENABLE ROW LEVEL SECURITY" in SQL and "TO service_role" in SQL and "REVOKE ALL" in SQL
    assert not re.search(r"TO authenticated", SQL)
    assert "SECURITY DEFINER" not in SQL.replace("NO SECURITY DEFINER", "")


def test_the_backfill_keeps_every_authorized_phone_as_an_operator():
    assert "FROM social_wiring.whatsapp_connections" in SQL and "authorized_numbers" in SQL and "'operador'" in SQL


def test_the_two_pages_are_registered_like_the_leads_page():
    assert "'julia_equipe_whatsapp'" in SQL and "'julia_protecao'" in SQL
    assert "origem.nome_pagina = 'julia_leads'" in SQL and "ON CONFLICT (nome_pagina) DO NOTHING" in SQL
