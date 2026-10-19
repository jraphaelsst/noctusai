"""Migration `julia_v2_espelhos`: the mirror columns, `estagio_minimo`, and the default opening message as DATA.

The mock DB derives its schema from the migrations, so the columns the code writes exist only because that migration declares them; this
file pins the rest of what the SQL promises (idempotent, forward-only, the seeded row carries the placeholders and no persona
name, no text of it lives in code).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql

from app.services import julia_aviso_service as aviso
from tests.support.julia_world import MENSAGEM_INICIAL_MIGRACAO, ORG_ID, World

SQL = migration_sql(Path(__file__).resolve().parents[2], "julia_v2_espelhos")  # by NAME: a renumber on integrate is safe


def test_the_seeded_default_message_is_the_one_the_tests_use_and_names_no_persona():
    m = re.search(r"VALUES \(\s*'mensagem_inicial',\s*'((?:[^']|'')*)'\s*\)", SQL)
    assert m, "the default opening message is not seeded as a row"
    texto = m.group(1).replace("''", "'")
    assert texto == MENSAGEM_INICIAL_MIGRACAO
    assert {"{agente}", "{empresa}", "{link}"} <= set(re.findall(r"\{[a-z]+\}", texto))
    assert "Julia" not in texto  # the agent's name comes from agents' status at send time


def test_it_is_idempotent_and_never_overwrites_an_edited_text():
    assert "ON CONFLICT (chave) DO NOTHING" in SQL
    assert SQL.count("ADD COLUMN IF NOT EXISTS") == 5
    assert "CREATE TABLE IF NOT EXISTS social_wiring.julia_textos_padrao" in SQL
    assert not re.search(r"\bDROP (TABLE|COLUMN)\b", SQL)  # forward-only: the retired columns go one release later


def test_the_estagio_and_estado_columns_are_shape_checked():
    assert "julia_envio_regras_estagio_minimo_forma" in SQL and "whatsapp_chats_agente_estado_valido" in SQL
    assert "'ativo', 'pausado', 'concluido', 'encerrado', 'transferido'" in SQL


def test_the_platform_default_table_is_service_role_only():
    assert "ENABLE ROW LEVEL SECURITY" in SQL and "TO service_role" in SQL
    assert "TO authenticated" not in SQL.split("julia_textos_padrao")[-1]


def test_no_default_text_for_the_opening_message_lives_in_code():
    assert not hasattr(aviso, "MENSAGEM_INICIAL_PADRAO")


class TestTextoPadrao:
    def test_a_new_org_notice_is_seeded_from_the_row(self):
        w = World()
        row = aviso.obter_ou_criar(w.sw, w.core, ORG_ID)
        assert row["mensagem_inicial"] == MENSAGEM_INICIAL_MIGRACAO

    def test_an_edited_row_is_what_new_orgs_get(self):
        w = World()
        w.sw.set_table_data("julia_textos_padrao", [{"chave": "mensagem_inicial", "conteudo": "Olá, sou {agente} da {empresa}. {link}"}])
        assert aviso.obter_ou_criar(w.sw, w.core, ORG_ID)["mensagem_inicial"] == "Olá, sou {agente} da {empresa}. {link}"

    def test_a_missing_row_is_a_503_never_a_fallback_string(self):
        from noctusai_lib.primitives.exceptions import AppException

        w = World()
        w.sw.set_table_data("julia_textos_padrao", [])
        with pytest.raises(AppException) as e:
            aviso.obter_ou_criar(w.sw, w.core, ORG_ID)
        assert (e.value.code, e.value.status_code) == ("texto_padrao_ausente", 503)
