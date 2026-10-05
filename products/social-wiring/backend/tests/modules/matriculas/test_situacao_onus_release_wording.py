"""situacao_onus: a release act worded "liberacao"/"quitada" that CITES the
encumbrance by number releases it (invented matrícula; 2026-10-05 study)."""
from __future__ import annotations

import pytest

from app.modules.matriculas import estrutura_service as es
from app.modules.matriculas.preenchimento_service import derivar_situacao_onus

AF = "R-3 - Alienação fiduciária em favor do Banco Exemplo S.A."


def _situacao(cancelamento: str):
    texto = AF + "\n" + cancelamento
    atos = [
        {"id": "a3", "ordem": 0, "kind": "R", "numero": 3, "char_inicio": 0, "char_fim": len(AF)},
        {"id": "a4", "ordem": 1, "kind": "AV", "numero": 4,
         "char_inicio": len(AF) + 1, "char_fim": len(texto)},
    ]
    return derivar_situacao_onus(atos, {}, es.sugerir(texto, atos, {})["onus"])


@pytest.mark.parametrize("frase", [
    "AV-4 - Consta a LIBERAÇÃO da alienação fiduciária registrada sob o R-3, por quitação.",
    "AV-4 - Em virtude da quitação, fica liberado o imóvel da alienação fiduciária do R-3.",
])
def test_release_wording_citing_the_act_releases_it(frase):
    assert _situacao(frase) == "livre"


def test_release_wording_without_a_citation_never_proposes_the_released_af():
    # Unlinked: indeterminate or livre-by-nothing, but NEVER "alienacao_fiduciaria"
    # contradicting a confirmed `livre`.
    assert _situacao("AV-4 - Em virtude da quitação, fica liberado o imóvel.") != "alienacao_fiduciaria"


def test_a_compra_e_venda_with_quitacao_stays_the_titulo():
    texto = "R-5 - COMPRA E VENDA. O vendedor dá plena quitação do preço (cf. R-3)."
    atos = [{"id": "a5", "ordem": 0, "kind": "R", "numero": 5, "char_inicio": 0, "char_fim": len(texto)}]
    sug = es.sugerir(texto, atos, {})
    assert sug["titulo_aquisitivo"] is not None and sug["titulo_aquisitivo"]["ato_id"] == "a5"
