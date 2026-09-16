"""Prompt versioning: changing a template's text REQUIRES bumping its
version. The pins below fail on an unbumped edit — update the version
AND the pin together."""

from __future__ import annotations

from decimal import Decimal

import pytest

from noctusai_lib.domain.photo_editing.prompts import (
    ALL_PROMPTS,
    EVALUATOR_SCHEMA,
    ModelMetrics,
    render_edit_prompt,
    render_evaluator_prompt,
    render_note_writer_prompt,
    render_rule_proposer_prompt,
    render_style_guide_prompt,
)
from noctusai_lib.domain.photo_editing.types import EditType, ReferencePair, Room

PINS = {
    "fotos.edit@v1": "44639a21a0b6",
    "fotos.avaliar@v1": "9373e2ff284e",
    "fotos.guia_estilo@v1": "75a771dc7c1b",
    "fotos.propor_regras@v1": "51e709e5d312",
    "fotos.nota_modelo@v1": "7dcda361e723",
}


def test_every_prompt_is_pinned_to_its_version() -> None:
    assert {p.ref: p.sha256[:12] for p in ALL_PROMPTS} == PINS


def test_prompt_ids_are_unique() -> None:
    ids = [p.prompt_id for p in ALL_PROMPTS]
    assert len(ids) == len(set(ids)) == 5


def test_edit_prompt_is_canonical_order_and_pt_br() -> None:
    a = render_edit_prompt([EditType.CEU, EditType.COR_LUZ], guia_texto="G", guia_sha256="f" * 64)
    b = render_edit_prompt([EditType.COR_LUZ, EditType.CEU], guia_texto="G", guia_sha256="f" * 64)
    assert a.text == b.text
    assert a.text.index("Corrigir cor") < a.text.index("Substituir o céu")
    assert "Não altere a arquitetura" in a.text
    assert "Mobiliar" not in a.text
    assert a.ref == "fotos.edit@v1"


def test_edit_prompt_requires_a_type() -> None:
    with pytest.raises(ValueError):
        render_edit_prompt([], guia_texto="G", guia_sha256="x" * 64)


def test_evaluator_prompt_carries_the_strict_schema() -> None:
    r = render_evaluator_prompt([EditType.DECLUTTER], guia_texto="Guia X")
    assert r.response_schema is EVALUATOR_SCHEMA
    assert EVALUATOR_SCHEMA["additionalProperties"] is False
    assert "Guia X" in r.text and "Remover objetos" in r.text


def test_style_guide_prompt_lists_pairs_in_order() -> None:
    pairs = [
        ReferencePair(id="r1", antes_url="a1", depois_url="d1", comodo=Room.SALA,
                      criado_por="u", tipos_edicao=(EditType.COR_LUZ,), nota="clara"),
        ReferencePair(id="r2", antes_url="a2", depois_url="d2", comodo=Room.FACHADA, criado_por="u"),
    ]
    text = render_style_guide_prompt(pairs).text
    assert "Par 1: cômodo sala; edições: cor_luz — nota: clara" in text
    assert "Par 2: cômodo fachada; edições: sem tipo" in text
    with pytest.raises(ValueError):
        render_style_guide_prompt([])


def test_rule_proposer_prompt_numbers_comments() -> None:
    text = render_rule_proposer_prompt(["céu falso", "móvel sumiu"], ["Não escurecer"]).text
    assert "1. céu falso\n2. móvel sumiu" in text
    assert "- Não escurecer" in text
    assert "(nenhuma)" in render_rule_proposer_prompt(["x"], []).text
    with pytest.raises(ValueError):
        render_rule_proposer_prompt([], [])


def test_note_writer_prompt_formats_metrics() -> None:
    text = render_note_writer_prompt(
        ModelMetrics("gpt-image-2.5-sunburst", 12, Decimal("0.75"), Decimal("8.1"), Decimal("0.123456"))
    ).text
    assert "75.0%" in text and "8.10" in text and "0.1235" in text
