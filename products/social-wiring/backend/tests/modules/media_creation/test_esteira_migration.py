"""Esteira migration (the shared ``cs_esteira`` file) + the config it is generated from.

Located by NAME (``migration_path``), never by number.
"""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_path

from app.config import settings
from app.modules.media_creation import esteira_config as cfg

_BACKEND = Path(__file__).resolve().parents[3]
SQL = migration_path(_BACKEND, "cs_esteira").read_text(encoding="utf-8")
_BEGIN = "-- BEGIN GENERATED card_hub(post)\n"
_END = "\n-- END GENERATED"


class TestGeneratedCardHub:
    def test_generated_section_is_exactly_the_generators_output(self):
        body = SQL.split(_BEGIN, 1)[1].split(_END, 1)[0]
        assert body.rstrip("\n") == cfg.gerar_migration_card_hub().rstrip("\n"), (
            "the GENERATED card_hub(post) section drifted from esteira_config.gerar_migration_card_hub -- "
            "regenerate it, never hand-edit"
        )

    def test_hub_binds_the_post_and_the_equipe(self):
        assert cfg.CS_POST_HUB.entity_table == "cs_posts"
        assert cfg.CS_POST_HUB.member_source.table == "cs_equipe"
        assert cfg.CS_POST_HUB.bucket == "sw-esteira"
        assert "bucket_id = 'sw-esteira'" in SQL

    def test_no_identity_document_types(self):
        assert [t[0] for t in cfg.ESTEIRA_DOC_TIPOS] == ["referencia", "outro"]
        assert all(t[3] is False for t in cfg.ESTEIRA_DOC_TIPOS)


class TestPipeline:
    def test_seven_default_stages_with_unique_roles(self):
        slugs = [s.slug for s in cfg.ESTEIRA_PADRAO]
        assert slugs == ["ideacao", "headline_roteiro", "gravacao", "edicao", "pronto", "postado", "bloqueado_cancelado"]
        roles = [s.papel for s in cfg.ESTEIRA_PADRAO if s.papel]
        assert sorted(roles) == sorted(cfg.PIPELINE_ESTEIRA.stage_roles) and len(set(roles)) == 3

    def test_api_roles_match_the_widened_papel_check(self):
        check = re.search(r"pipeline_stages_papel_check\s+CHECK \(papel IN \(([^)]*)\)\)", SQL)
        assert check is not None
        assert set(re.findall(r"'([a-z_]+)'", check.group(1))) >= set(cfg.PIPELINE_ESTEIRA.stage_roles)

    def test_pipeline_checks_widened_on_both_tables(self):
        for name in ("pipeline_stages_pipeline_check", "pipeline_movimentos_pipeline_check"):
            assert f"{name}\n  CHECK (pipeline IN ('funil', 'processos_venda', 'esteira'))" in SQL


class TestPostShape:
    def test_composite_fks_null_only_their_own_column(self):
        assert "FOREIGN KEY (headline_id, marca_id) REFERENCES social_wiring.cs_headlines (id, marca_id)" in SQL
        assert "ON DELETE SET NULL (headline_id)" in SQL
        assert "FOREIGN KEY (roteiro_id, marca_id) REFERENCES social_wiring.cs_roteiros (id, marca_id)" in SQL
        assert "ON DELETE SET NULL (roteiro_id)" in SQL
        assert "UNIQUE (id, marca_id)" in SQL

    def test_one_post_per_headline_and_roteiro(self):
        assert "cs_posts_headline_uq\n    ON social_wiring.cs_posts (headline_id) WHERE headline_id IS NOT NULL" in SQL
        assert "cs_posts_roteiro_uq\n    ON social_wiring.cs_posts (roteiro_id) WHERE roteiro_id IS NOT NULL" in SQL

    def test_stage_delete_is_restricted(self):
        assert "etapa_id              UUID NOT NULL REFERENCES social_wiring.pipeline_stages (id) ON DELETE RESTRICT" in SQL

    def test_new_tables_have_the_229_rls_shape(self):
        for t in ("cs_posts", "cs_equipe"):
            assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in SQL
            for suffix in ("select_own_org", "write_own_org", "service_role"):
                assert f'"{t}_{suffix}"' in SQL, (t, suffix)

    def test_batch_remembers_its_post(self):
        assert "ADD COLUMN IF NOT EXISTS post_id UUID REFERENCES social_wiring.cs_posts (id) ON DELETE SET NULL" in SQL

    def test_rebind_rpc_is_service_role_only(self):
        assert "cs_rebind_roteiro(p_org uuid, p_post uuid, p_old uuid, p_new uuid)" in SQL
        assert "REVOKE EXECUTE ON FUNCTION social_wiring.cs_rebind_roteiro(uuid, uuid, uuid, uuid)\n    FROM PUBLIC, anon, authenticated" in SQL

    def test_status_pagina_rows(self):
        assert "('media-creation-esteira', 'desenvolvimento'" in SQL
        assert "media_creation'" not in SQL.replace("media-creation", ""), "241 must not touch the legacy page row (A-3 does, wave 3)"


def test_legendas_cap_is_finite():
    assert settings.legendas_dia_usuario == 40
