"""The two boards' configuration: roles, defaults, and their SQL twins."""
import re
from pathlib import Path

from noctusai_lib.testing import MockSupabaseClient

from app.pipelines import (
    COMERCIAL_PADRAO,
    ESTEIRA_PADRAO,
    PIPELINE_COMERCIAL,
    PIPELINE_ESTEIRA,
    garantir_etapas_padrao,
)

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def test_migration_017_seeds_exactly_the_python_esteira_defaults():
    """017 backfills `tarefa.etapa_id` by slug against these rows — a drift
    between the SQL list and ESTEIRA_PADRAO would strand tarefas."""
    sql = (MIGRATIONS / "017_igig_pipeline.sql").read_text(encoding="utf-8")
    linhas = re.findall(
        r"\('(\w+)',\s*'([^']+)',\s*'(\w+)',\s*(\d+),\s*(NULL|'\w+')\)", sql
    )
    assert [
        (slug, label, cor, int(pos), None if papel == "NULL" else papel.strip("'"))
        for slug, label, cor, pos, papel in linhas
    ] == [(s.slug, s.label, s.cor, i, s.papel) for i, s in enumerate(ESTEIRA_PADRAO)]


def test_every_role_is_in_the_papel_check():
    sql = (MIGRATIONS / "017_igig_pipeline.sql").read_text(encoding="utf-8")
    check = re.search(r"papel\s+TEXT CHECK \(papel IN \(([^)]*)\)\)", sql).group(1)
    no_banco = {v.strip().strip("'") for v in check.split(",")}
    assert set(PIPELINE_COMERCIAL.stage_roles) | set(PIPELINE_ESTEIRA.stage_roles) == no_banco


def test_each_default_set_carries_its_roles_exactly_once():
    assert [s.papel for s in COMERCIAL_PADRAO if s.papel] == ["fechado"]
    assert [s.papel for s in ESTEIRA_PADRAO if s.papel] == ["aprovacao_cliente", "agendado"]


def test_defaults_are_not_reseeded_over_an_orgs_own_configuration():
    """An org that retired every stage made a choice — no silent re-seed."""
    db = MockSupabaseClient(schema="igig")
    db.table("pipeline_stages").insert({
        "id": "s1", "org_id": "o1", "pipeline": "comercial", "slug": "unica",
        "label": "Única", "cor": "primary", "posicao": 0, "papel": None, "ativo": False,
    }).execute()
    garantir_etapas_padrao(db, PIPELINE_COMERCIAL, "o1")
    assert len(db.table("pipeline_stages")._data) == 1


def test_defaults_are_per_pipeline_and_per_org():
    db = MockSupabaseClient(schema="igig")
    garantir_etapas_padrao(db, PIPELINE_COMERCIAL, "o1")
    garantir_etapas_padrao(db, PIPELINE_ESTEIRA, "o1")
    garantir_etapas_padrao(db, PIPELINE_COMERCIAL, "o2")
    linhas = db.table("pipeline_stages")._data
    assert len(linhas) == 2 * len(COMERCIAL_PADRAO) + len(ESTEIRA_PADRAO)
