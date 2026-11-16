"""The note we leave in Vista's internal observations (`ObsVenda`/`ObsLocacao`): insertion cases (owner 2026-11-04)."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.integrations.vista.observacoes import campo_obs, compor_campos, inserir_linha, montar_linha

L = "04/11/26 Proprietário informa via WhatsApp: valor de venda 900 → 850. confirmou. (NoctusAI)"
HOJE = date(2026, 11, 4)


def test_log_present_the_line_goes_before_the_first_dated_line_and_the_header_is_untouched():
    atual = "Lote 3 Quadra 4\nMPM 1267\nPP Fulano 11 99999-0000\n18/09/26 MPM informa Venda SUSPENSA em 11/09/2026. (Tami)\n22/08/26 Cindy informa alterações de valores. (Tami)"
    out = inserir_linha(atual, L).split("\n")
    assert out[:3] == atual.split("\n")[:3] and out[3] == L and out[4].startswith("18/09/26") and len(out) == 6


@pytest.mark.parametrize("variante", ["10/10/2026 - texto (CY)", "10/10/26: texto", "10/10/26 X informa y. (Z)"])
def test_the_dated_line_variants_are_all_detected(variante):
    assert inserir_linha(f"Cabeçalho\n{variante}", L).split("\n") == ["Cabeçalho", L, variante]


def test_no_log_header_only_appends_after_the_header_with_one_blank_line():
    assert inserir_linha("Lote 3 Quadra 4\nMPM 1267", L) == f"Lote 3 Quadra 4\nMPM 1267\n\n{L}"
    assert inserir_linha("Lote 3\nMPM 1267\n", L) == f"Lote 3\nMPM 1267\n\n{L}"  # trailing newline: still one blank line


@pytest.mark.parametrize("vazio", [None, "", "  \n "])
def test_an_empty_field_becomes_just_the_line(vazio):
    assert inserir_linha(vazio, L) == L


def test_crlf_is_normalised_and_a_log_only_field_gets_the_line_on_top():
    assert inserir_linha("10/10/26 a. (b)\r\n01/09/26 c. (d)", L).split("\n") == [L, "10/10/26 a. (b)", "01/09/26 c. (d)"]


def test_the_line_is_one_line_with_no_phone_or_email_and_follows_the_pattern():
    linha = montar_linha(fonte="Proprietário", canal="WhatsApp", campo="valor de venda", antes="900000", depois="850000",
                         motivo="falou com fulano@x.com no 11 98888-7777\nde novo", autor="NoctusAI", conversa_url="https://sw.test/c?x=1", hoje=HOJE)
    assert "\n" not in linha and "@" not in linha and "98888" not in linha
    assert linha == ("04/11/26 Proprietário informa via WhatsApp: valor de venda 900000 → 850000. "
                     "falou com [e-mail] no [telefone] de novo. Conversa: https://sw.test/c?x=1 (NoctusAI)")


def test_reason_and_author_are_required():
    for motivo, autor in (("", "a"), ("  ", "a"), ("m", ""), (None, None)):
        with pytest.raises(ValueError):
            montar_linha(fonte="f", canal="c", campo="k", antes=1, depois=2, motivo=motivo, autor=autor)


def test_finalidade_picks_the_field_and_compor_uses_the_current_values():
    assert campo_obs("venda") == "ObsVenda" and campo_obs("locacao") == "ObsLocacao" and campo_obs("aluguel") == "ObsLocacao"
    with pytest.raises(ValueError):
        campo_obs("troca")
    campos, linha = compor_campos({"ValorLocacao": "3000"}, {"ValorLocacao": "2500", "ObsLocacao": "Cab\n01/01/26 a. (b)"}, finalidade="locacao",
                                  fonte="Prop", canal="WA", motivo="m", autor="N", hoje=HOJE)
    assert campos["ValorLocacao"] == "3000" and campos["ObsLocacao"].split("\n") == ["Cab", linha, "01/01/26 a. (b)"] and "ValorLocacao 2500 → 3000" in linha
    assert "ObsVenda" not in campos
