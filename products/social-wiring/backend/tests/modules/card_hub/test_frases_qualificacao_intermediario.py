"""`frases.qualificacao_intermediario` — pure unit, no DB, no fixtures.

Regression for the 2026-09-23 e2e-harness finding: `Intermediario` carries
no `genero` column (neither `atendimento_intermediarios` migration 108 nor
`lead_corretores` migration 025 has one — unlike `clientes.genero`, which
feeds `Pessoa`'s own gender-agreed qualification via `concordancia.
normalizar_genero`), so the PF branch hardcoded the masculine "corretor de
imóveis inscrito" regardless of the actual person's gender. Confirmed
against real production data: contract 08 (the office's own human-typed
reference for a real, signed deal) qualifies a female corretora as
"corretora ... inscrita", while the generator's persisted render for the
SAME deal said "corretor ... inscrito" for her — a reproducible wrong-gender
defect, not a reference-contract stylistic deviation.
"""
from __future__ import annotations

from app.modules.card_hub.contrato_gerador import frases
from app.modules.card_hub.contrato_gerador.dados import Endereco, Intermediario


def _intermediario(**overrides) -> Intermediario:
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        corretor_id=None,
        nome="RENATA DIAS GONÇALVES",
        creci="274.956",
        tipo="percentual",
        valor=None,
        pessoa_tipo="pf",
        documento="17146716821",
        endereco=Endereco(),
    )
    base.update(overrides)
    return Intermediario(**base)


def test_pf_intermediario_qualificacao_is_gender_neutral():
    """No `genero` fact exists for an intermediário — the noun must never
    assert one. `nacionalidade_flex`'s own "brasileiro(a)" is this file's
    established convention for exactly this situation."""
    texto = frases.qualificacao_intermediario(_intermediario())
    assert "corretor(a) de imóveis inscrito(a) no" in texto
    assert "corretor de imóveis inscrito" not in texto
    assert "corretora de imóveis inscrita" not in texto


def test_pf_intermediario_qualificacao_still_carries_documento_e_creci():
    it = _intermediario(creci="274.956")
    texto = frases.qualificacao_intermediario(it)
    assert "RENATA DIAS GONÇALVES" in texto
    assert "171.467.168-21" in texto  # CPF formatted via `documento()`
    assert "com inscrição no CRECI sob o nº 274.956" in texto


def test_pj_intermediario_qualificacao_unaffected():
    """The PJ branch never mentioned "corretor" at all — this fix must not
    touch it."""
    it = _intermediario(
        nome="ONE CONSULTORIA IMOBILIÁRIA LTDA",
        pessoa_tipo="pj",
        documento="40479637000127",
        creci=None,
    )
    texto = frases.qualificacao_intermediario(it)
    assert texto.startswith("ONE CONSULTORIA IMOBILIÁRIA LTDA, pessoa jurídica inscrita no CNPJ")
    assert "corretor" not in texto
