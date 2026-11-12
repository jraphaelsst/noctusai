"""Q2: a section declares RULES; readiness reads the rule, layers union them, the stores refuse unknown ones."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
from noctusai_lib.testing.migrations import migration_sql

from app.stores.studio_definitions import (
    SectionInput,
    SectionRecord,
    _as_section_input,
    _validate_bundle,
    _validate_section,
)
from app.studio.camadas import apensar_secoes
from app.studio.regras_secao import REGRA_DISCORDAR, REGRAS_SECAO, uniao, validar_regras
from app.studio.models import SectionData
from app.schemas.studio_geracao import SecaoGerada

PRODUCT_BACKEND = Path(__file__).resolve().parents[3]


def _rec(chave: str, conteudo: str = "texto", regras: tuple[str, ...] = (), ativo: bool = True) -> SectionRecord:
    return SectionRecord(
        id=uuid4(), org_id=uuid4(), version_id=uuid4(), chave=chave, titulo=chave, ordem=1, conteudo=conteudo,
        ativo=ativo, created_at=None, updated_at=None, regras=regras,  # type: ignore[arg-type]
    )


def test_closed_list_and_validation():
    assert REGRA_DISCORDAR in REGRAS_SECAO
    assert validar_regras([REGRA_DISCORDAR, REGRA_DISCORDAR]) == (REGRA_DISCORDAR,)
    with pytest.raises(ValueError, match="Regra de seção desconhecida: x"):
        validar_regras(["x"])


def test_child_merged_onto_parent_keeps_the_parents_rules_and_gains_the_childs():
    pai = [_rec("honestidade", "pai", (REGRA_DISCORDAR,))]
    filho = [_rec("honestidade", "filho", ())]
    (m,) = apensar_secoes(pai, filho)
    assert m.regras == (REGRA_DISCORDAR,) and "filho" in m.conteudo
    # child-only rule is added, never duplicated
    (m2,) = apensar_secoes([_rec("a", "p", ())], [_rec("a", "f", (REGRA_DISCORDAR,))])
    assert m2.regras == (REGRA_DISCORDAR,)
    assert uniao((REGRA_DISCORDAR,), (REGRA_DISCORDAR,)) == (REGRA_DISCORDAR,)


def test_a_blank_child_does_not_drop_the_parents_rules():
    (m,) = apensar_secoes([_rec("honestidade", "pai", (REGRA_DISCORDAR,))], [_rec("honestidade", "  ", ())])
    assert m.regras == (REGRA_DISCORDAR,)


def test_fake_store_round_trips_rules_and_refuses_unknown():
    sec = SectionInput(chave="honestidade", titulo="H", ordem=1, conteudo="x", regras=(REGRA_DISCORDAR,))
    assert _as_section_input({"chave": "a", "titulo": "A", "regras": [REGRA_DISCORDAR]}).regras == (REGRA_DISCORDAR,)
    assert sec.regras == (REGRA_DISCORDAR,)
    with pytest.raises(ValueError, match="desconhecida"):
        _validate_section(SectionInput(chave="a", titulo="A", ordem=1, regras=("nao-existe",)))
    with pytest.raises(ValueError, match="desconhecida"):
        _validate_bundle([_as_section_input({"chave": "a", "titulo": "A", "regras": ["nao-existe"]})], [])


def test_bundle_models_carry_the_rules():
    assert SectionData(id=None, chave="a", titulo="A", ordem=1, conteudo="x", regras=(REGRA_DISCORDAR,)).regras
    assert SecaoGerada(chave="honestidade", titulo="H", conteudo="x", regras=[REGRA_DISCORDAR]).regras == [REGRA_DISCORDAR]
    assert SecaoGerada(chave="honestidade", titulo="H", conteudo="x").regras == []


class TestMigrationShape:
    sql = migration_sql(PRODUCT_BACKEND, "secao_regras")

    def test_adds_the_column_idempotently(self):
        assert re.search(r"ADD COLUMN IF NOT EXISTS regras TEXT\[\] NOT NULL DEFAULT '\{\}'", self.sql)

    def test_backfill_is_guarded_so_running_twice_is_harmless(self):
        assert "NOT ('discordar-com-respeito' = ANY(regras))" in self.sql
        assert "array_append(regras, 'discordar-com-respeito')" in self.sql

    def test_backfill_lifts_the_immutability_guard_only_around_itself(self):
        sql = self.sql
        off = sql.index("DISABLE TRIGGER guard_agent_prompt_sections_immutable")
        upd = sql.index("array_append(regras")
        on = sql.index("ENABLE TRIGGER guard_agent_prompt_sections_immutable")
        assert off < upd < on

    def test_write_paths_carry_the_column(self):
        for fn in ("replace_draft_sections", "create_agent_draft", "replace_draft_bundle"):
            assert f"FUNCTION agents.{fn}(" in self.sql
        assert self.sql.count("regras") > 10
