"""Consumer half of the seed's 2026-10-13 owner rules (identidade extraction):

- an RNE arrives as its own kind (`IdentityFields.rne`, never `rg`) and is
  stored in the cliente's existing identity pair (`rg` + `rg_orgao_expedidor`)
  — typed by `clientes.identidade_tipo` (migration 193);
- a DERIVED gender (`genero_derivado=True`, a certidão's grammar) is never
  written to the cliente (`pode_persistir=False`).
"""
from __future__ import annotations

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents.conjuges import ConjugeLido
from noctusai_lib.integrations.documents.types import ExtractionConfidence, IdentityFields

ALTA = ExtractionConfidence.ALTA
BAIXA = ExtractionConfidence.BAIXA


def test_rne_maps_onto_the_identity_pair() -> None:
    f = IdentityFields(
        rne="W-573.678-Z", rne_confianca=ALTA, rne_rotulo="RG",
        rne_orgao="DIREX", identidade_tipo="rne",
    )
    lidos = svc._valores_lidos(f)
    assert lidos["rg"] == ("W-573.678-Z", "alta", "RG", True)
    assert lidos["rg_orgao_expedidor"] == ("DIREX", "alta", "RG", True)


def test_an_ordinary_rg_is_unchanged() -> None:
    f = IdentityFields(rg="52.179.965-X", rg_confianca=ALTA, rg_rotulo="RG", rg_orgao="SSP/SP", rg_orgao_confianca=ALTA)
    lidos = svc._valores_lidos(f)
    assert lidos["rg"] == ("52.179.965-X", "alta", "RG", True)
    assert lidos["rg_orgao_expedidor"] == ("SSP/SP", "alta", "RG", True)


def test_derived_gender_is_never_persisted() -> None:
    f = IdentityFields(genero="Feminino", genero_confianca=BAIXA, genero_derivado=True)
    valor, _conf, _rot, pode = svc._valores_lidos(f)["genero"]
    assert valor == "Feminino" and pode is False


def test_printed_gender_is_persisted() -> None:
    f = IdentityFields(genero="Feminino", genero_confianca=ALTA, genero_rotulo="SEXO")
    assert svc._valores_lidos(f)["genero"][3] is True


def test_other_spouse_derived_gender_is_never_persisted() -> None:
    cj = ConjugeLido(nome="JOSE EXEMPLO", genero="Masculino", genero_confianca="baixa", genero_derivado=True)
    assert svc._lidos_do_conjuge(cj, IdentityFields())["genero"][3] is False
