"""Golden tests: the seed calculator reproduces the owner's SIMEC 1.0
workbooks number for number.

Expected values in ``golden/*_golden.json`` were produced by evaluating the
workbooks' OWN formulas (DADOS S–Z, PAINEL rows 6–17) over the fixture rows —
see ``golden/generate_golden.py``. Nothing here was computed by the code
under test.

The workbook is filled by hand, so every metric it has a column for is
"available" there. Our Instagram default marks ``duration_s`` unavailable
(the Graph API does not return it); the golden config flips it back on via
an override — which also exercises the override layer.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from noctusai_lib.domain.content_performance import (
    Reading,
    compute_panel,
    evaluate_readings,
    load_default_config,
    merge_overrides,
)

GOLDEN = Path(__file__).resolve().parent / "golden"
STRUCTURAL = {"published_at", "collected_at", "content_id", "topic", "format",
              "window", "source", "note"}
TOL = 1e-12


def _config(platform: str):
    base = load_default_config(platform)
    if platform == "instagram":
        return merge_overrides(base, {"metrics": {"duration_s": {"available": True}}},
                               "golden-manual-entry")
    return base


def _reading(inputs: dict) -> Reading:
    def d(v):
        return date.fromisoformat(v) if v else None

    return Reading(
        content_id=inputs["content_id"],
        published_at=d(inputs["published_at"]),
        collected_at=d(inputs["collected_at"]),
        window=inputs["window"],
        format=inputs["format"],
        topic=inputs["topic"],
        source=inputs["source"],
        note=inputs["note"],
        values={k: v for k, v in inputs.items() if k not in STRUCTURAL},
    )


def _load(platform: str) -> dict:
    return json.loads((GOLDEN / f"{platform}_golden.json").read_text(encoding="utf-8"))


def _eq(actual, expected) -> bool:
    if expected is None or actual is None:
        return actual is expected
    return abs(actual - expected) <= TOL


@pytest.mark.parametrize("platform", ["instagram", "tiktok"])
def test_rows_match_workbook_dados(platform):
    golden = _load(platform)
    config = _config(platform)
    results = evaluate_readings([_reading(c["inputs"]) for c in golden["cases"]], config)
    mismatches = []
    for i, (case, res) in enumerate(zip(golden["cases"], results)):
        exp = case["expected"]
        assert res.status.value == exp["status"], (i, case["inputs"], res.status)
        assert _eq(res.age_days, exp["age_days"]), (i, res.age_days, exp["age_days"])
        for key, want in exp.items():
            if key in ("status", "age_days"):
                continue
            got = res.indicators[key].value
            if not _eq(got, want):
                mismatches.append((i, key, got, want))
    assert not mismatches, mismatches


@pytest.mark.parametrize("platform", ["instagram", "tiktok"])
def test_panel_matches_workbook_painel(platform):
    golden = _load(platform)
    config = _config(platform)
    results = evaluate_readings([_reading(c["inputs"]) for c in golden["cases"]], config)
    panel = compute_panel(results, config)
    mismatches = []
    for window, lines in golden["panel"].items():
        for key, want in lines.items():
            got = panel[window][key].value
            if not _eq(got, want):
                mismatches.append((window, key, got, want))
    assert not mismatches, mismatches


def test_golden_covers_every_validation_state():
    states = {c["expected"]["status"] for c in _load("instagram")["cases"]}
    assert states == {"ok", "incompleto", "data_invalida", "fora_da_janela", "duplicado"}


def test_without_the_override_duration_is_nao_disponivel_never_a_number():
    """Same rows on the real Instagram default: tempo/duração is reported as
    'não disponível' everywhere (the API has no duration) — never estimated."""
    golden = _load("instagram")
    config = load_default_config("instagram")
    results = evaluate_readings([_reading(c["inputs"]) for c in golden["cases"]], config)
    assert all(r.indicators["tempo_medio_duracao"].status.value == "nao_disponivel"
               for r in results if r.indicators)
    panel = compute_panel(results, config)
    cell = panel["7d"]["media_tempo_medio_duracao"]
    assert cell.value is None and cell.status.value == "nao_disponivel"
    # The rest of the panel is unaffected.
    assert panel["7d"]["media_taxa_interacao"].value == pytest.approx(
        golden["panel"]["7d"]["media_taxa_interacao"], abs=TOL)
