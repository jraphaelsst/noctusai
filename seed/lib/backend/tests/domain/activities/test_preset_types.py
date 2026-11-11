"""`CrmPreset.activity_types`: validated, deduped, and carrying the market's types as DATA (no code branch per market)."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.activities import GENERIC_ACTIVITY_TYPES, ActivitiesConfig, ActivityTypeSpec
from noctusai_lib.domain.pipeline.market_presets import AGENCY_PRESET, GENERIC_PRESET, MARKET_PRESETS, REAL_ESTATE_PRESET
from noctusai_lib.domain.pipeline.presets import CrmPreset
from noctusai_lib.domain.pipeline.defaults import StageDefault as S


def _preset(**kw):
    return CrmPreset(market="m", pipelines={"funil": (S("novo", "Novo", "secondary"),)}, **kw)


def test_a_preset_without_types_falls_back_to_the_generic_set():
    assert _preset().activity_types == ()
    assert ActivitiesConfig.for_preset("x", _preset()).default_types == GENERIC_ACTIVITY_TYPES


def test_a_repeated_type_slug_is_refused():
    with pytest.raises(ValueError, match="activity-type"):
        _preset(activity_types=(ActivityTypeSpec("a", "A"), ActivityTypeSpec("a", "B")))


@pytest.mark.parametrize("slug,kind", [("Bad Slug", "task"), ("ok", "party"), ("", "task")])
def test_a_bad_type_is_refused_at_construction(slug, kind):
    with pytest.raises(ValueError):
        ActivityTypeSpec(slug, "Label", kind)


def test_real_estate_carries_the_future_consumers_as_data_with_the_right_kinds():
    by = {t.slug: t.kind for t in REAL_ESTATE_PRESET.activity_types}
    # §4 rows Chaves / Manutenção / Campo: custody log, maintenance and field work are rows, not code
    assert by["chave_retirada"] == by["chave_devolucao"] == by["manutencao"] == "task"
    assert by["campo"] == by["visita"] == "visit"
    assert {"tarefa", "ligacao", "reuniao"} <= set(by)


def test_only_real_estate_has_a_visit_type_other_markets_use_the_generic_set():
    assert all(t.kind != "visit" for t in GENERIC_PRESET.activity_types)
    assert AGENCY_PRESET.activity_types == ()
    assert sum(1 for p in MARKET_PRESETS.values() if p.activity_types) == 1


def test_no_market_noun_lives_in_the_organ_code():
    """seed/ ships mechanics; a market's nouns arrive only as preset data (`market_presets.py`, tracked by its own remediation marker)."""
    import pathlib
    import re

    import noctusai_lib.domain.activities as pkg

    banned = re.compile(r"chave|manuten|imov|corretor|paciente|visita|campo", re.I)
    offenders = {
        f.name: sorted({m.group(0).lower() for m in banned.finditer(f.read_text(encoding="utf-8"))})
        for f in pathlib.Path(pkg.__file__).parent.glob("*.py")
    }
    assert {k: v for k, v in offenders.items() if v} == {}
