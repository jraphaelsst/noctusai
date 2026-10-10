"""Geração migration (the shared ``cs_geracao`` file) + the taxonomies it is generated from.

The migration is located by NAME (``migration_path``), never by number: a number in a test filename
or path breaks the moment a parallel session renumbers it (compliance gate).
"""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path

from app.modules.media_creation import geracao_taxonomias as tax

_BACKEND = Path(__file__).resolve().parents[3]
SQL = migration_path(_BACKEND, "cs_geracao").read_text(encoding="utf-8")


class TestTaxonomies:
    def test_counts_match_the_contract(self):
        assert (len(tax.NICHOS), len(tax.PROFISSOES), len(tax.FORMATOS_VIDEO), len(tax.TREINAMENTOS)) == (28, 102, 15, 5)
        assert len(tax.GATILHOS) == 7 and len(tax.TONS) == 6
        assert tax.CRIATIVIDADE == ("essencial", "equilibrado", "explorador")

    def test_ids_are_unique_and_formatos_are_1_to_15(self):
        assert len(tax.NICHO_IDS) == 28 and len(tax.PROFISSAO_IDS) == 102
        assert sorted(tax.FORMATO_IDS) == list(range(1, 16))
        assert [o for o, _, _ in tax.TREINAMENTOS] == [1, 2, 3, 4, 5]

    def test_verbatim_anchors(self):
        assert dict(tax.NICHOS)[26] == "Imobiliário"
        assert dict(tax.PROFISSOES)[82] == "Corretor de Imóveis"
        assert tax.FORMATOS_VIDEO[0][1] == "Lista de Valor Prático" and tax.FORMATOS_VIDEO[14][1] == "Websérie"
        assert tax.TREINAMENTOS[0][1] == "Como preencher a Bio"

    def test_gatilho_slugs_match_the_migration_check(self):
        check = re.search(r"gatilho\s+TEXT CHECK \(gatilho IN \(([^)]*)\)\)", SQL)
        assert check is not None
        assert set(re.findall(r"'([a-z]+)'", check.group(1))) == tax.GATILHO_SLUGS

    def test_seed_sql_is_deterministic_and_escapes_quotes(self):
        assert tax.seed_sql() == tax.seed_sql()
        assert tax._q("d'água") == "'d''água'"


class TestMigration:
    def test_carries_the_generated_seed_verbatim(self):
        assert tax.seed_sql() in SQL

    def test_seed_does_not_overwrite_admin_owned_columns(self):
        treinos = tax.seed_sql().split("INSERT INTO social_wiring.cs_treinamentos")[1]
        assert "video_url" not in treinos and "ativo" not in treinos.split("ON CONFLICT")[1]

    def test_every_table_has_rls_enabled(self):
        tables = re.findall(r"CREATE TABLE IF NOT EXISTS social_wiring\.(\w+)", SQL)
        assert len(tables) == 13, tables
        for t in tables:
            assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in SQL, t
            assert f'"{t}_service_role"' in SQL, t

    def test_chat_and_memory_tables_are_private_to_their_user(self):
        for t in ("cs_chat_conversas", "cs_memorias", "cs_chat_mensagens"):
            policy = SQL.split(f'CREATE POLICY "{t}_own_user"')[1].split("DROP POLICY")[0]
            assert "auth.uid()" in policy, t
            assert f'"{t}_select_own_org"' not in SQL

    def test_org_scoped_tables_use_the_217_policy_shape(self):
        for t in ("cs_headline_lotes", "cs_headlines", "cs_roteiros"):
            assert f'"{t}_select_own_org"' in SQL and f'"{t}_write_own_org"' in SQL, t

    def test_library_tables_are_read_only_for_the_browser_role(self):
        """M3: 001's `GRANT ALL ... TO authenticated` must not leave the library writable from PostgREST."""
        tables = ("cs_perfis_monitorados", "cs_virais", "cs_biblioteca_referencias")
        for t in tables:
            assert f'"{t}_select_own_org"' in SQL and f'CREATE POLICY "{t}_write_own_org"' not in SQL, t
        revoke = re.search(r"REVOKE INSERT, UPDATE, DELETE[^;]*;", SQL)
        grant = re.search(r"GRANT SELECT\s+ON ([^;]*?)\s+TO authenticated;", SQL)
        assert revoke and grant
        for t in tables:
            assert f"social_wiring.{t}" in revoke.group(0) and f"social_wiring.{t}" in grant.group(1), t
        assert "FROM authenticated" in revoke.group(0)
        assert "inativo_desde" in SQL.split("CREATE TABLE IF NOT EXISTS social_wiring.cs_virais")[0]

    def test_bucket_is_private_and_the_ten_pages_are_registered(self):
        assert "VALUES ('sw-biblioteca', 'sw-biblioteca', false)" in SQL
        keys = re.findall(r"\('(media-creation-[a-z-]+)', 'desenvolvimento'\)", SQL)
        assert len(keys) == len(set(keys)) == 10

    def test_one_active_manual_batch_per_user_index(self):
        assert re.search(
            r"cs_headline_lotes \(created_by\)\s+WHERE status IN \('criando', 'processando'\) AND origem <> 'sugestao_auto'",
            SQL,
        )

    def test_voice_quota_function_counts_only_voice_rows(self):
        fn = SQL.split("FUNCTION social_wiring.reservar_transcricao(")[1].split("$fn$;")[0]
        counters = [s for s in re.findall(r"SELECT .*?;", fn, flags=re.S) if "FROM social_wiring.transcricoes" in s]
        assert len(counters) == 6
        assert all("origem = 'usuario'" in s for s in counters), counters

    def test_library_quota_function_counts_only_library_rows(self):
        fn = SQL.split("FUNCTION social_wiring.reservar_transcricao_biblioteca(")[1].split("$fn$;")[0]
        counters = [s for s in re.findall(r"SELECT .*?;", fn, flags=re.S) if "FROM social_wiring.transcricoes" in s]
        assert len(counters) == 3 and all("origem = 'biblioteca'" in s for s in counters)
        assert "'biblioteca_viral'" in fn and "> 180" in fn
        revoke = SQL.split("REVOKE EXECUTE ON FUNCTION social_wiring.reservar_transcricao_biblioteca")[1]
        assert "FROM PUBLIC, anon, authenticated" in revoke.split(";")[0]

    def test_is_idempotent_and_guarded(self):
        assert "Migration 229 requires" in SQL
        assert not re.search(r"CREATE TABLE (?!IF NOT EXISTS)", SQL)
        assert "DROP TABLE" not in SQL
