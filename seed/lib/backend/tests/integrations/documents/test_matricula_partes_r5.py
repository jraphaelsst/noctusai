"""Real-deal replay R5 (2026-10-23): a venda e compra that merely REFERENCES a
prior cessão, and a cessão whose cedentes' qualification carries legal text.
EVERY name and number is invented; only the LAYOUT is real."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents import extrair_detalhes_ato, nome_de_parte_valido

R3 = (
    "R.3/ 21.748 - BARUERI, 15 de janeiro de 1985. Pela mesma escritura mencionada na "
    "averbação nº 02, acima,- os proprietários FULANO ORIGEM EXEMPLO, e sua mulher "
    "FULANA ORIGEM EXEMPLO, retro qualificados, TRANSMITIRAM definitivamente, por venda "
    "e compra, o imóvel desta matrícula, à CICRANO ADQUIRENTE EXEMPLO, casado com "
    "BELTRANA ADQUIRENTE EXEMPLO, supra qualificados pelo preço ajustado de CR$ 10.000.000, "
    "com as condições da escritura, ficando cumprido e sem mais efeito o compromisso "
    "objeto da averbação nº 01, e por consequência a cessão de direitos objeto da "
    "averbação nº 02, supra."
)

AV2 = (
    "AV.2/ 21.748 - BARUERI, 15 de janeiro de 1985. Pela escritura pública lavrada aos "
    "28/12/84, às fls. 396/399, do livro 198, nas notas do Tabelião de Carapicuiba, desta "
    "comarca, os compromissários compradores, EDUARDO ALVORADA EXEMPLO,- RG. 5.002.617 e "
    "CIC/MF. nº 663.268.778/49, brasileiro, engenheiro, e sua mulher FERNANDA ALVORADA "
    "EXEMPLO, RG. sob nº 5.385.920-SP e CIC/MF. nº 769.754.878/04, brasileira,- pedagoga, "
    "casados no regime da comunhão de bens, antes da Lei nº 6515/77, residentes na Rua "
    "Exemplo, 10, CEDERAM E TRANS- FERIRAM todos os seus direitos e obrigações decorrentes "
    "do compromisso de venda e compra, averbado sob o nº 01, retro, à CICRANO ADQUIRENTE "
    "EXEMPLO, RG 1.111.111 brasileiro, engenheiro, casado no regime da comunhão de bens, "
    "antes da Lei 6515/77, com a senhora BELTRANA ADQUIRENTE EXEMPLO, brasileira, "
    "pedagoga."
)


def test_r5_1_a_sale_referencing_a_cession_stays_a_sale():
    d = extrair_detalhes_ato(R3)
    assert d.natureza == "compra_e_venda"
    assert [p.nome for p in d.adquirentes][0] == "CICRANO ADQUIRENTE EXEMPLO"


def test_r5_2_cessao_transmitentes_and_spouse():
    d = extrair_detalhes_ato(AV2)
    assert d.natureza == "cessao_direitos"
    assert [p.nome for p in d.transmitentes] == ["EDUARDO ALVORADA EXEMPLO", "FERNANDA ALVORADA EXEMPLO"]
    nomes = {p.nome for p in d.adquirentes}
    assert nomes == {"CICRANO ADQUIRENTE EXEMPLO", "BELTRANA ADQUIRENTE EXEMPLO"}


@pytest.mark.parametrize("n", ["antes da Lei nº", "Lei nº", "regime da comunhão", "antes da Lei"])
def test_r5_2_legal_text_is_never_a_name(n):
    assert not nome_de_parte_valido(n)
