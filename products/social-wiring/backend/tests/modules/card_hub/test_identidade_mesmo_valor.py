"""`_mesmo_valor` — "different string" is not "different fact".

Live finding 2026-09-23: re-extracting real certidões de casamento opened
conflicts `Divorciado(a)` (a legacy human-typed spelling) vs `divorciado` (the
extractor's canonical token) — the same fact, asked of a human twice.
"""
import pytest

from app.modules.card_hub.identidade_extracao_service import _mesmo_valor


@pytest.mark.parametrize(
    "a,b",
    [
        ("Divorciado(a)", "divorciado"),
        ("CASADA", "casado"),
        ("Viúvo(a)", "viuvo"),
        ("solteiro", "solteiro"),
    ],
)
def test_estado_civil_legacy_spelling_is_the_same_fact(a, b):
    assert _mesmo_valor("estado_civil", a, b)


@pytest.mark.parametrize(
    "a,b",
    [
        ("Divorciado(a)", "casado"),
        ("solteiro", "uniao_estavel"),
    ],
)
def test_estado_civil_different_status_is_a_conflict(a, b):
    assert not _mesmo_valor("estado_civil", a, b)


def test_estado_civil_unknown_spelling_falls_back_to_text_compare():
    # An unmapped value is never guessed at — it only matches itself.
    assert _mesmo_valor("estado_civil", "amasiado", "amasiado")
    assert not _mesmo_valor("estado_civil", "amasiado", "casado")
