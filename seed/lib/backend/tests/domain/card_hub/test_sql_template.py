"""`card_hub_migration` — parity with the tables the lifted code was written
against, plus the conventions every emitted table must carry."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.domain.card_hub import card_hub_migration
from noctusai_lib.domain.card_hub.sql import DEFAULT_DOCUMENTO_TIPOS
from noctusai_lib.testing.migration_parser import parse_files, parse_sql
from tests.domain.card_hub.conftest import lead_config, sw_config

_REPO = Path(__file__).resolve().parents[6]
_SW_MIGRATIONS = _REPO / "products" / "social-wiring" / "backend" / "migrations"
_SW_CARD_HUB_FILES = ("056_card_hub_core.sql", "057_card_hub_documentos.sql", "083_cliente_checklist_extras.sql")


def _noop(ids):
    return {}


#: 057 seeds `'RG -- retenção ...'` / `'CPF -- retenção ...'` descriptions,
#: and `noctusai_lib.testing.migration_parser._strip_line_comments` is not
#: string-literal-aware — it eats from `--` to end of line, closing quote
#: included, so the NEXT table in that file (`cliente_documento_acessos`) never
#: reaches the schema map. Its columns, verbatim from 057's CREATE TABLE:
_PARSER_BLIND_TABLES = {
    "social_wiring.cliente_documento_acessos": {
        "id", "org_id", "documento_id", "usuario_id", "acao", "created_at",
    },
}


class TestSocialWiringParity:
    def test_template_columns_equal_sw_056_057_083(self):
        """For social-wiring's config, every table the template emits has
        EXACTLY the columns 056 + 057 + 083 created — no more, no fewer — and
        the template emits every table those files did."""
        files = [_SW_MIGRATIONS / name for name in _SW_CARD_HUB_FILES]
        assert all(f.is_file() for f in files), files
        sw = {**parse_files(files), **_PARSER_BLIND_TABLES}
        generated = parse_sql(card_hub_migration(sw_config(_noop), "social_wiring"))
        assert generated == sw

    def test_the_parser_blind_spot_is_still_there(self):
        """`_PARSER_BLIND_TABLES` is a hand-kept literal ONLY because the
        mock's migration parser cannot see it; the day the parser learns to
        skip `--` inside string literals, this fails and the literal must go
        (the parsed columns then take over the parity check above)."""
        sw = parse_files([_SW_MIGRATIONS / name for name in _SW_CARD_HUB_FILES])
        assert not set(_PARSER_BLIND_TABLES) & set(sw)

    def test_parity_covers_every_card_hub_table(self):
        generated = parse_sql(card_hub_migration(sw_config(_noop), "social_wiring"))
        cfg = sw_config(_noop)
        expected = {f"social_wiring.{getattr(cfg.tables, n)}" for n in (
            "notas", "tags", "tag_links", "membros", "lembretes", "checklists", "checklist_itens",
            "checklist_extras", "documentos", "documento_tipos", "documento_acessos",
        )} | {"social_wiring.clientes"}
        assert set(generated) == expected


class TestConventions:
    @pytest.fixture
    def ddl(self):
        return card_hub_migration(lead_config(_noop), "crm")

    def test_search_path_prelude(self, ddl):
        assert "SET search_path = crm, public;" in ddl

    def test_every_table_has_rls_and_the_service_role_bypass(self, ddl):
        tables = re.findall(r"CREATE TABLE IF NOT EXISTS crm\.(\w+)", ddl)
        assert len(tables) == 11
        for t in tables:
            assert f"ALTER TABLE crm.{t} ENABLE ROW LEVEL SECURITY;" in ddl, t
            assert f'CREATE POLICY "service_role_bypass" ON crm.{t} FOR ALL TO service_role' in ddl, t

    def test_org_tables_use_the_subquery_org_predicate(self, ddl):
        assert 'CREATE POLICY "lead_notas_select_own_org" ON crm.lead_notas FOR SELECT TO authenticated\n  USING (org_id = (SELECT public.current_org_id()));' in ddl

    def test_one_descricao_per_card_is_a_db_constraint(self, ddl):
        assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_lead_notas_one_descricao" in ddl
        assert "WHERE tipo = 'descricao' AND deleted_at IS NULL;" in ddl

    def test_bucket_is_private_and_object_rls_keys_on_org_first_segment(self, ddl):
        assert "VALUES ('crm-documentos', 'crm-documentos', false)" in ddl
        assert "(storage.foldername(name))[1] = (SELECT public.current_org_id())::text" in ddl
        # Bucket-qualified names: two products' hubs must not replace each other's policies.
        assert 'CREATE POLICY "crm-documentos_storage_select" ON storage.objects' in ddl
        assert '"service_role_bypass" ON storage.objects' not in ddl

    def test_access_log_has_no_authenticated_write_policy(self, ddl):
        policies = re.findall(r'CREATE POLICY "[^"]+" ON crm\.lead_documento_acessos FOR (\w+) TO (\w+)', ddl)
        assert sorted(policies) == [("ALL", "service_role"), ("SELECT", "authenticated")]

    def test_no_stage_fk_without_a_stage_table(self, ddl):
        assert "pipeline_stages" not in ddl
        assert "etapa_id    UUID," in ddl

    def test_entity_datas_are_opt_out(self, ddl):
        assert "data_entrega" not in ddl
        assert "ADD COLUMN IF NOT EXISTS data_entrega" in card_hub_migration(sw_config(_noop), "social_wiring")

    def test_default_catalogue_withholds_identity_types_and_ships_outro(self, ddl):
        by_tipo = {row[0]: row for row in DEFAULT_DOCUMENTO_TIPOS}
        assert by_tipo["outro"][4] is True
        assert all(row[4] is False for row in DEFAULT_DOCUMENTO_TIPOS if row[3])
        assert "ON CONFLICT (tipo_documento) DO NOTHING;" in ddl
        assert "INSERT INTO crm.lead_documento_tipos" not in card_hub_migration(
            lead_config(_noop), "crm", documento_tipos=()
        )

    def test_idempotent_shapes(self, ddl):
        assert "CREATE TABLE crm." not in ddl  # always IF NOT EXISTS
        for name in re.findall(r'CREATE POLICY "([^"]+)" ON (\S+)', ddl):
            assert f'DROP POLICY IF EXISTS "{name[0]}" ON {name[1]};' in ddl, name

    def test_empty_schema_is_refused(self):
        with pytest.raises(ValueError):
            card_hub_migration(lead_config(_noop), " ")
