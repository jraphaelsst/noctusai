"""`ensure_default_stages` — lazy per-org default stage seeding."""
from __future__ import annotations

from noctusai_lib.domain.pipeline import (
    PipelineConfig,
    StageDefault,
    ensure_default_stages,
    list_stages,
)
from noctusai_lib.testing.mocks import MockSupabaseClient

CFG = PipelineConfig(
    pipeline="demo",
    card_table="cards",
    value_field="valor",
    entity_label="card",
    entity_kind="card",
    stage_roles=("fim",),
)
DEFAULTS = (
    StageDefault("a", "A", "primary"),
    StageDefault("b", "B", "success", "fim"),
)


def _db():
    return MockSupabaseClient(schema="x")


def test_seeds_when_the_pipeline_has_no_rows():
    db = _db()
    assert ensure_default_stages(db, CFG, DEFAULTS, org_id="o1") is True
    rows = list_stages(db, CFG, org_id="o1")
    assert [(r["slug"], r["posicao"], r["papel"]) for r in rows] == [("a", 0, None), ("b", 1, "fim")]
    assert all(r["org_id"] == "o1" and r["pipeline"] == "demo" and r["ativo"] for r in rows)


def test_idempotent():
    db = _db()
    ensure_default_stages(db, CFG, DEFAULTS, org_id="o1")
    assert ensure_default_stages(db, CFG, DEFAULTS, org_id="o1") is False
    assert len(db.table(CFG.stages_table)._data) == 2


def test_inactive_rows_count_as_configured():
    db = _db()
    db.table(CFG.stages_table).insert({
        "id": "s1", "org_id": "o1", "pipeline": "demo", "slug": "only",
        "label": "Only", "cor": "primary", "posicao": 0, "papel": None, "ativo": False,
    }).execute()
    assert ensure_default_stages(db, CFG, DEFAULTS, org_id="o1") is False
    assert len(db.table(CFG.stages_table)._data) == 1


def test_per_org_and_per_pipeline():
    db = _db()
    ensure_default_stages(db, CFG, DEFAULTS, org_id="o1")
    ensure_default_stages(db, CFG, DEFAULTS, org_id="o2")
    assert len(db.table(CFG.stages_table)._data) == 4
