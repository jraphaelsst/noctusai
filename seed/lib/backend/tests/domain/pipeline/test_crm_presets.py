"""CrmPreset — market default funnels, org-editable; role-keyed no-op."""
from __future__ import annotations

import logging

import pytest

from noctusai_lib.domain.pipeline import (
    MARKET_PRESETS,
    CrmPreset,
    PipelineConfig,
    StageDefault,
    ensure_preset_stages,
    list_stages,
    stage_for_role,
    update_stage,
    create_stage,
    delete_stage,
)
from noctusai_lib.domain.pipeline.presets import CANONICAL_CRM_ROLES
from noctusai_lib.testing.mocks import MockSupabaseClient


def _cfg(board: str, preset: CrmPreset) -> PipelineConfig:
    return PipelineConfig(
        pipeline=board, card_table="cards", value_field="valor",
        entity_label="card", entity_kind="card", stage_roles=preset.stage_roles(board),
    )


def _db():
    return MockSupabaseClient(schema="x")


def _seeded(market: str, org: str = "o1"):
    preset = MARKET_PRESETS[market]
    cfgs = {b: _cfg(b, preset) for b in preset.pipelines}
    db = _db()
    ensure_preset_stages(db, preset, cfgs, org_id=org)
    return preset, cfgs, db


def test_today_values_pinned():
    slugs = {m: {b: [s.slug for s in st] for b, st in p.pipelines.items()} for m, p in MARKET_PRESETS.items()}
    assert slugs["real_estate"]["funil"] == [
        "qualificacao", "visitas", "proposta_recebida", "negociacao", "proposta_decisao"]
    assert len(slugs["real_estate"]["processos_venda"]) == 8
    assert slugs["saas"]["funil_noc"] == ["novo", "contatado", "qualificado", "proposta"]
    assert slugs["agency"]["comercial"] == ["novo", "contato", "qualificado", "proposta", "negociacao", "fechado"]
    assert slugs["clinic"]["leads"] == ["lead", "atendimento", "negociacao", "fechado"]


def test_seeds_lazily_and_org_edits_win():
    preset, cfgs, db = _seeded("real_estate")
    assert ensure_preset_stages(db, preset, cfgs, org_id="o1") == {"funil": False, "processos_venda": False}
    cfg = cfgs["funil"]
    rows = list_stages(db, cfg, org_id="o1")
    visitas = next(r for r in rows if r["slug"] == "visitas")
    update_stage(db, cfg, visitas["id"], {"label": "Visita agendada", "cor": "primary"}, org_id="o1")
    assert ensure_preset_stages(db, preset, cfgs, org_id="o1")["funil"] is False
    after = next(r for r in list_stages(db, cfg, org_id="o1") if r["id"] == visitas["id"])
    assert after["label"] == "Visita agendada" and after["slug"] == "visitas"  # slug immutable


def test_org_can_add_and_remove_stages():
    _, cfgs, db = _seeded("clinic")
    cfg = cfgs["leads"]
    novo = create_stage(db, cfg, {"label": "Sessão experimental", "papel": "sessao_experimental"}, org_id="o1")
    assert novo["papel"] == "sessao_experimental"
    # a role-bearing stage is guarded: release the role first (existing mechanic), then remove
    update_stage(db, cfg, novo["id"], {"papel": None}, org_id="o1")
    delete_stage(db, cfg, novo["id"], org_id="o1")
    assert all(r["slug"] != novo["slug"] for r in list_stages(db, cfg, org_id="o1"))


def test_visita_role_noop_for_org_without_it(caplog):
    # One (real estate) has Visita; Senseys (agency) does not — same feature call.
    _, re_cfgs, re_db = _seeded("real_estate")
    hit = stage_for_role(re_db, re_cfgs["funil"], "visita", org_id="o1", feature="visit_scheduled")
    assert hit is not None and hit["slug"] == "visitas"

    _, ag_cfgs, ag_db = _seeded("agency")
    with caplog.at_level(logging.INFO, logger="noctusai_lib.domain.pipeline.presets"):
        assert stage_for_role(ag_db, ag_cfgs["comercial"], "visita", org_id="o1", feature="visit_scheduled") is None
    assert "visit_scheduled" in caplog.text and "papel=visita" in caplog.text


def test_noop_when_org_removed_the_role_stage():
    _, cfgs, db = _seeded("real_estate")
    cfg = cfgs["funil"]
    row = next(r for r in list_stages(db, cfg, org_id="o1") if r["papel"] == "visita")
    update_stage(db, cfg, row["id"], {"papel": None}, org_id="o1")  # org drops the role; stage stays
    assert stage_for_role(db, cfg, "visita", org_id="o1", feature="visit_scheduled") is None
    update_stage(db, cfg, row["id"], {"papel": "visita", "ativo": True}, org_id="o1")
    update_stage(db, cfg, row["id"], {"papel": None}, org_id="o1")
    update_stage(db, cfg, row["id"], {"ativo": False}, org_id="o1")
    assert stage_for_role(db, cfg, "visita", org_id="o1", feature="visit_scheduled") is None


def test_orgs_are_isolated():
    preset, cfgs, db = _seeded("saas", "o1")
    ensure_preset_stages(db, preset, cfgs, org_id="o2")
    assert len(list_stages(db, cfgs["funil_noc"], org_id="o2")) == 4


def test_roles_validate_against_canonical_plus_market():
    for p in MARKET_PRESETS.values():
        for board in p.pipelines:
            assert set(CANONICAL_CRM_ROLES) <= set(p.stage_roles(board))
    # any org may add a market role its default funnel lacks
    assert "sessao_experimental" in MARKET_PRESETS["agency"].stage_roles("comercial")


@pytest.mark.parametrize(
    "stages",
    [
        (StageDefault("a", "A", "primary"), StageDefault("a", "A2", "primary")),
        (StageDefault("a", "A", "nope"),),
        (StageDefault("a", "A", "primary", "inexistente"),),
        (StageDefault("a", "A", "primary", "ganho"), StageDefault("b", "B", "primary", "ganho")),
        (StageDefault("Bad Slug", "A", "primary"),),
        (),
    ],
)
def test_preset_rejects_bad_data(stages):
    with pytest.raises(ValueError):
        CrmPreset(market="m", pipelines={"b": stages})


def test_missing_board_config_is_loud():
    preset = MARKET_PRESETS["real_estate"]
    with pytest.raises(ValueError, match="processos_venda"):
        ensure_preset_stages(_db(), preset, {"funil": _cfg("funil", preset)}, org_id="o1")
