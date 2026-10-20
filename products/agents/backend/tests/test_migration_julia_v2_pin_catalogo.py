"""Structural pins for migration 040 (Julia v2 A-RT2). The behaviour runs on a real Postgres in the chain replay
(`noctus.dev.migration_replay`); these keep the intent honest."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[1]
M40 = migration_sql(ROOT, "julia_v2_pin_catalogo")


def test_the_pin_may_target_a_published_or_archived_standard_never_a_draft():
    assert "NOT IN ('publicada', 'arquivada')" in M40
    assert "guard_agent_version_qualificacao_pin" in M40


def test_a_draft_inherits_the_pin_before_the_guard_runs():
    assert "agent_versions_inherit_qualificacao" in M40
    # triggers fire in name order: the inheriting one must sort before the guard
    assert "agent_versions_inherit_qualificacao" < "guard_agent_version_qualificacao_pin"
    assert "NEW.status = 'rascunho'" in M40 and "based_on_version_id" in M40


def test_catalogue_tables_are_service_role_only():
    for t in ("catalogo_agentes", "catalogo_capacidades"):
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in M40
        assert re.search(rf"REVOKE ALL ON agents\.{t} FROM PUBLIC, anon, authenticated", M40)
    assert not re.search(r"GRANT\s+[A-Z, ]+\s+ON\s+agents\.catalogo", M40)


def test_status_pagina_row_for_the_catalogue_nav_and_no_write_grant():
    assert re.search(r"\('agentes-catalogo',\s*'desenvolvimento'\)", M40)
    assert "ON CONFLICT (nome_pagina) DO NOTHING" in M40
    # 036's lockdown stays intact: this file grants nothing on status_pagina
    assert not re.search(r"(GRANT|REVOKE)[^;]*status_pagina", M40)
