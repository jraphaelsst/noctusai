"""The offer catalogue is DATA of the qualification standard (``parametros.catalogo``) and a tag of each lead event
(``lead_imovel_eventos.catalogo``). Structural pins of the migration, the closed set the engine validates, and the
round trip through the store and the API view."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_sql

from app.catalogos import CATALOGOS
from app.qualificacao import engine
from app.qualificacao.lead_store import FakeLeadQualificacaoStore
from app.qualificacao.models import EventoImovel, ParametrosDef
from app.qualificacao.schemas import ParametrosIn, versao_out
from app.qualificacao.store import FakePadraoStore
from tests.qualificacao.fixture_v1 import versao_v1
from tests.qualificacao.harness import ADMIN

BACKEND = Path(__file__).resolve().parents[2]
SQL = migration_sql(BACKEND, "catalogo_opcoes")


class TestMigration:
    def test_it_is_forward_only_and_idempotent(self):
        assert "ADD COLUMN IF NOT EXISTS catalogo TEXT NULL" in SQL
        assert "ADD COLUMN IF NOT EXISTS catalogo TEXT NOT NULL DEFAULT 'imoveis_sw'" in SQL
        assert not re.search(r"\bDROP (TABLE|COLUMN)\b", SQL)

    def test_existing_rows_stay_the_real_estate_catalogue_and_the_standard_names_none_by_default(self):
        assert "agents.lead_imovel_eventos ADD COLUMN IF NOT EXISTS catalogo TEXT NOT NULL DEFAULT 'imoveis_sw'" in SQL
        assert "agents.qualificacao_parametros ADD COLUMN IF NOT EXISTS catalogo TEXT NULL" in SQL

    def test_both_columns_are_shape_checked(self):
        for tabela in ("qualificacao_parametros", "lead_imovel_eventos"):
            assert f"ADD CONSTRAINT {tabela}_catalogo_check" in SQL
        assert SQL.count("char_length(catalogo) <= 64") == 2

    def test_cloning_a_version_copies_the_catalogue(self):
        corpo = SQL[SQL.index("CREATE OR REPLACE FUNCTION agents.criar_rascunho_qualificacao"):]
        alvo = re.search(r"INSERT INTO agents\.qualificacao_parametros\s*\(([^)]*)\)\s*SELECT([^;]*?)FROM", corpo)
        assert alvo is not None
        colunas = [c.strip() for c in alvo.group(1).split(",")]
        copiadas = [c.strip() for c in alvo.group(2).split(",")]
        assert "catalogo" in colunas and "catalogo" in copiadas
        # 080 re-declared it first: this re-declaration keeps its column (chain-wide: test_criar_rascunho_copia_parametros)
        assert "max_retomadas_seguidas" in colunas and "max_retomadas_seguidas" in copiadas

    def test_the_renames_are_left_as_a_named_destination(self):
        assert "NOC-REMEDIATE[codigo-opcao-rename]" in SQL


class TestEngineValidation:
    @pytest.mark.parametrize("chave", [None, *CATALOGOS])
    def test_a_known_catalogue_or_none_publishes(self, chave):
        v = versao_v1()
        v = replace(v, parametros=replace(v.parametros, catalogo=chave))
        assert not [e for e in engine.validar_versao(v) if e["path"] == "parametros.catalogo"]

    def test_an_unknown_catalogue_is_refused_naming_the_closed_set(self):
        v = versao_v1()
        erros = engine.validar_versao(replace(v, parametros=replace(v.parametros, catalogo="inventado")))
        (erro,) = [e for e in erros if e["path"] == "parametros.catalogo"]
        assert erro["code"] == "parametro_invalido" and "imoveis_sw" in str(erro)


class TestRoundTrip:
    def test_the_standard_keeps_its_catalogue_through_the_store_and_the_api_view(self):
        padroes = FakePadraoStore()
        padrao = padroes.criar_padrao("sdr-base", "SDR", None)
        vid = padroes.criar_rascunho(padrao.id, "v1", None)
        padroes.salvar_parametros(vid, ParametrosIn(minimo_para_ofertar={"todos": []}, catalogo="fixture").to_def())
        padroes.publicar(vid, ADMIN)
        assert padroes.obter_versao(vid).parametros.catalogo == "fixture"
        assert versao_out(padroes.obter_versao(vid))["parametros"]["catalogo"] == "fixture"

    def test_a_standard_that_names_none_says_none(self):
        assert ParametrosDef(minimo_para_ofertar={}).catalogo is None
        assert ParametrosIn(minimo_para_ofertar={}).to_def().catalogo is None


class TestEventsCarryTheirCatalogue:
    def test_an_event_defaults_to_the_real_estate_catalogue(self):
        assert EventoImovel("A", "oferecido").catalogo == "imoveis_sw"

    def test_the_fake_store_keeps_the_tag(self):
        from uuid import uuid4

        s, org, lead = FakeLeadQualificacaoStore(), uuid4(), uuid4()
        s.adicionar_evento(org, lead, agent_id=uuid4(), thread_id=None, evento=EventoImovel("A", "oferecido", catalogo="fixture"))
        assert [e.catalogo for e in s.listar_eventos(org, lead)] == ["fixture"]

    def test_the_real_store_writes_the_column_only_for_another_catalogue(self):
        """A real-estate row is written EXACTLY as before 081 (so the image may run before the column exists)."""
        from uuid import uuid4

        from app.qualificacao.lead_store import SupabaseLeadQualificacaoStore as LeadQualificacaoStore

        escritas: list[dict] = []

        class _T:
            def insert(self, row):
                escritas.append(dict(row))
                return self

            def execute(self):
                class R:
                    data = [{**escritas[-1], "id": str(uuid4()), "created_at": "2026-11-11T00:00:00+00:00"}]
                return R

        class _C:
            def schema(self, _s): return self
            def table(self, _t): return _T()

        store = LeadQualificacaoStore(_C())
        for cat in ("imoveis_sw", "fixture"):
            store.adicionar_evento(uuid4(), uuid4(), agent_id=uuid4(), thread_id=None,
                                   evento=EventoImovel("A", "oferecido", catalogo=cat))
        assert "catalogo" not in escritas[0] and escritas[1]["catalogo"] == "fixture"
