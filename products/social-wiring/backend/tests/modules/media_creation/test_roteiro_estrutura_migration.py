"""``cs_roteiros.estrutura`` migration — located by NAME, never by number.

The live refusal is proven by the ``social_wiring.cs_roteiros_estrutura_check`` GuardProbe
(``verify_db_guards``); this pins the file's shape against the prompt's own structure list.
"""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path

from app.modules.media_creation.prompts.roteiro_geracao import ESTRUTURA_PADRAO, ESTRUTURAS

_BACKEND = Path(__file__).resolve().parents[3]
SQL = migration_path(_BACKEND, "cs_roteiros_estrutura").read_text(encoding="utf-8")


class TestEstruturaMigration:
    def test_coluna_not_null_com_padrao_corestudio_e_idempotente(self):
        assert (
            "ADD COLUMN IF NOT EXISTS estrutura TEXT NOT NULL DEFAULT "
            f"'{ESTRUTURA_PADRAO}'"
        ) in SQL

    def test_check_nomeado_bate_com_as_estruturas_do_prompt(self):
        assert "DROP CONSTRAINT IF EXISTS cs_roteiros_estrutura_check" in SQL
        check = re.search(r"cs_roteiros_estrutura_check\s+CHECK \(estrutura IN \(([^)]*)\)\)", SQL)
        assert check is not None
        assert tuple(re.findall(r"'([a-z]+)'", check.group(1))) == ESTRUTURAS

    def test_guard_probe_registrado(self):
        assert "cs_roteiros_estrutura_check" in SQL and "verify_db_guards" in SQL
