"""F82 (2026-10-24, prod): the holder's address comes from the holder's block.

A gas bill (OCR) prints the customer twice — the window-envelope block and a
customer box — and the utility's OWN sender block ("Remetente: Companhia de
Gás …, CEP <another> - <bairro> - <city> - SP"). The reader took the sender's
CEP and city for the customer. Every fixture here is synthetic (invented
names, streets and CEPs) but keeps that layout: two customer blocks plus a
remetente block with a different CEP and city.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.address import caixa_logradouro, find_endereco

#: Envelope block (CEP + city) + labelled customer box (no CEP in it) +
#: the sender's one-line block with its own labelled CEP — the triggering
#: shape. The two street reads disagree by one OCR letter.
CONTA_GAS_ROTULADA = """\
Nota Fiscal / Conta Gás
CICRANO DE EXEMPLO
EST MUNICIPAL VALE DOURADO 512 APTO 33
06700-100 ITAPECERICA SP
Código do Usuário: 11223344
Vencimento: 10/10/2026  Total a pagar: R$ 91,20
Cliente: CICRANO DE EXEMPLO
Endereço: EST MUNICIPAL VALE DORADO 512
APTO 33 ITAPECERICA
Remetente: Companhia de Gás do Exemplo, Rua Bom Retiro, 975 - CEP 04100-200 - Vila Exemplo - São Paulo - SP
"""

#: Same bill, no labels at all — both customer blocks are bare lines.
CONTA_GAS_ENVELOPE = """\
Nota Fiscal / Conta Gás
CICRANO DE EXEMPLO
EST MUNICIPAL VALE DOURADO 512 APTO 33
06700-100 ITAPECERICA SP
Código do Usuário 11223344
Remetente: Companhia de Gás do Exemplo, Rua Bom Retiro, 975 - CEP 04100-200 - Vila Exemplo - São Paulo - SP
CICRANO DE EXEMPLO
EST MUNICIPAL VALE DORADO 512
APTO 33 ITAPECERICA
"""


class TestTheSendersBlockIsNeverTheHolders:
    def test_labelled_bill_takes_cep_and_city_from_the_holders_block(self):
        r = find_endereco(CONTA_GAS_ROTULADA)
        assert r.cep == "06700-100"
        assert r.cidade == "ITAPECERICA"
        assert r.uf == "SP"
        assert r.numero == "512"
        assert r.complemento == "APTO 33"
        assert r.titular == "CICRANO DE EXEMPLO"

    def test_envelope_only_bill_reads_the_holder_not_nothing(self):
        r = find_endereco(CONTA_GAS_ENVELOPE)
        assert (r.cep, r.cidade, r.uf) == ("06700-100", "ITAPECERICA", "SP")
        assert r.numero == "512"

    def test_a_remetente_label_alone_on_its_line_opens_the_senders_block(self):
        texto = (
            "FULANA EXEMPLAR\n"
            "R DAS AMOREIRAS 77\n"
            "13010-110 CAMPINAS SP\n"
            "\n"
            "Remetente:\n"
            "Distribuidora Exemplo\n"
            "Av das Industrias, 1000\n"
            "CEP 04100-200 - SAO PAULO - SP\n"
        )
        r = find_endereco(texto)
        assert (r.cep, r.cidade) == ("13010-110", "CAMPINAS")

    def test_a_labelled_cep_outside_the_streets_block_is_not_taken_when_another_cep_exists(self):
        """No issuer marker at all: a far labelled CEP and a second CEP
        elsewhere — the labelled street's block printed none of them, so
        neither is guessed; the envelope block reading the same street
        supplies the locality."""
        texto = (
            "BELTRANO EXEMPLO\n"
            "R DAS AMOREIRAS 77\n"
            "13010-110 CAMPINAS SP\n"
            "\n"
            "Endereço: R DAS AMOREIRAS 77\n"
            "\n"
            "Pague em qualquer lotérica\n"
            "Rua Qualquer, 5 - CEP 04100-200 - SAO PAULO - SP\n"
        )
        r = find_endereco(texto)
        assert (r.cep, r.cidade) == ("13010-110", "CAMPINAS")


class TestTheStreetAsMostReadsPrintIt:
    def test_a_tie_keeps_the_read_of_the_block_the_cep_came_from(self):
        # Envelope (with the CEP) reads DOURADO, the labelled box DORADO.
        r = find_endereco(CONTA_GAS_ROTULADA)
        assert r.logradouro == "Estrada Municipal Vale Dourado"

    def test_the_majority_spelling_wins_over_the_chosen_one(self):
        texto = CONTA_GAS_ENVELOPE.replace(
            "EST MUNICIPAL VALE DOURADO 512 APTO 33", "EST MUNICIPAL VALE DORADO 512 APTO 33"
        ) + "EST MUNICIPAL VALE DOURADO 512\nEST MUNICIPAL VALE DOURADO 512\n"
        r = find_endereco(texto)
        assert r.logradouro == "Estrada Municipal Vale Dourado"

    def test_agreeing_reads_stay_alta(self):
        texto = CONTA_GAS_ROTULADA.replace("VALE DORADO", "VALE DOURADO")
        r = find_endereco(texto)
        assert r.logradouro == "Estrada Municipal Vale Dourado"
        assert r.confianca == "alta"

    def test_disagreeing_reads_are_baixa(self):
        assert find_endereco(CONTA_GAS_ROTULADA).confianca == "baixa"


class TestLogradouroCasing:
    def test_type_expansion_never_leaves_a_mixed_case_street(self):
        assert caixa_logradouro("Estrada MUNICIPAL DO EMBU") == "Estrada Municipal do Embu"

    def test_a_mixed_case_read_is_untouched(self):
        assert caixa_logradouro("Rua das Flores") == "Rua das Flores"
        assert caixa_logradouro("Rua XV de Novembro") == "Rua XV de Novembro"

    def test_roman_numerals_digits_and_quadra_codes_keep_their_print(self):
        assert caixa_logradouro("Rua XV DE NOVEMBRO") == "Rua XV de Novembro"
        assert caixa_logradouro("SQN 308 BLOCO C") == "SQN 308 Bloco C"

    def test_a_street_named_after_a_connector_keeps_its_last_letter(self):
        assert caixa_logradouro("RUA E") == "Rua E"


class TestAnExistingGoodComprovanteIsUnchanged:
    def test_a_light_bill_envelope_block_still_reads_the_same(self):
        texto = (
            "ENEL DISTRIBUICAO EXEMPLO S.A.\n"
            "Rua Atica, 673 - CEP 04634-042 - SAO PAULO - SP\n"
            "CNPJ 61.695.227/0001-93\n"
            "\n"
            "MARIA APARECIDA DE SOUZA\n"
            "RUA DAS FLORES 123 AP 45\n"
            "JARDIM PAULISTA\n"
            "01234-567 SAO PAULO SP\n"
        )
        r = find_endereco(texto)
        assert r.partes() == {
            "cep": "01234-567",
            "logradouro": "Rua das Flores",
            "numero": "123",
            "complemento": "AP 45",
            "bairro": "JARDIM PAULISTA",
            "cidade": "SAO PAULO",
            "uf": "SP",
        }
        assert r.confianca == "baixa"


#: F82 round 2: the SHAPE the production vision read actually returns for
#: this bill class (line order, labels, noise) — every value invented. The
#: holder's CEP sits under a combined `CEP/Cidade:` label; the sender's
#: block and the utility's own "segunda via" block both print another CEP;
#: the holder's street is printed twice, both labelled.
CONTA_GAS_OCR_REAL = """\
[descrição da imagem] GASEXEMPLO: virtual.gasexemplo.com.br

Nota Fiscal / Conta Gás:
Destinatário: CICRANO DE EXEMPLO
Endereço: EST MUNICIPAL VALE DOURADO 512 APTO 33
CEP/Cidade: 06700-100 ITAPECERICA SP
Código de barras: -1234567890000 1234567890A000SACOB
Tarefa: 1234
Mês de Referência: jul/2026
Vencimento: 29.07.2026

Orientação e apoio ao Cliente:
Gás 24h: 08000 000 000

Remetente: Companhia de Gás do Exemplo
Endereço remetente: Rua Bom Retiro, 975 - CEP 04100-200 - Vila Exemplo - São Paulo - SP

Para uso do Correio
Data: / /

GASEXEMPLO (segunda via):
Razão social: Companhia de Gás do Exemplo
Endereço: Rua Bom Retiro, 975 - CEP 04100-200 - Vila Exemplo - São Paulo - SP
CNPJ: 00.000.000/0006-00 - Insc. Estadual 000.000.000.000

Cliente: CICRANO DE EXEMPLO
Código do cliente: 12345678
Endereço: EST MUNICIPAL VALE DOURADO 512 APTO 33 ITAPECERICA
CPF/CNPJ: 000000000-00 /

Vencimento: 29.07.2026
Valor a pagar (R$): 99,79
"""


class TestTheRealOcrShape:
    def test_reads_the_holders_address_off_the_real_layout(self):
        r = find_endereco(CONTA_GAS_OCR_REAL)
        assert r.partes() == {
            "cep": "06700-100",
            "logradouro": "Estrada Municipal Vale Dourado",
            "numero": "512",
            "complemento": "APTO 33",
            "bairro": None,
            "cidade": "ITAPECERICA",
            "uf": "SP",
        }
        assert r.titular == "CICRANO DE EXEMPLO"
        assert r.confianca == "alta"

    def test_the_combined_cep_cidade_label_is_a_labelled_cep(self):
        r = find_endereco(
            "Endereço: R DAS AMOREIRAS 77\nCEP / Município: 13010-110 CAMPINAS SP\n"
        )
        assert (r.cep, r.cidade, r.uf) == ("13010-110", "CAMPINAS", "SP")

    def test_a_one_letter_ocr_slip_in_one_of_three_copies_loses_the_vote(self):
        texto = CONTA_GAS_OCR_REAL.replace(
            "Endereço: EST MUNICIPAL VALE DOURADO 512 APTO 33\n",
            "Endereço: EST MUNICIPAL VALE DORADO 512 APTO 33\n",
        ) + "EST MUNICIPAL VALE DOURADO 512\n"
        assert find_endereco(texto).logradouro == "Estrada Municipal Vale Dourado"


#: The OTHER shape the same vision rung returns for this bill on a re-read
#: (run-to-run variance): no labels at all, every holder line ending in a
#: dangling "key: value" colon, the sender's block bare under "Remetente:".
CONTA_GAS_OCR_DOIS_PONTOS = """\
[descrição da imagem] NOTA FISCAL / CONTA GÁS: 
CICRANO DE EXEMPLO: 
EST MUNICIPAL VALE DOURADO 512 APTO 33: 
06700-100 ITAPECERICA SP: 
-123456789000001234567890A000SACOB: 
Tarefa: 1234
Vencimento: 29.07.2026

Remetente: Companhia de Gás do Exemplo
Rua Bom Retiro, 975 - CEP 04100-200 - Vila Exemplo - São Paulo - SP

Companhia de Gás do Exemplo: 
Rua Bom Retiro, 975 - CEP 04100-200 - Vila Exemplo - São Paulo - SP
CNPJ: 00.000.0000006-00 - Insc. Estadual 000.000.000.000

CICRANO DE EXEMPLO: 
Código do cliente: 12345678
EST MUNICIPAL VALE DOURADO 512 APTO 33 ITAPECERICA: 
CPF/CNPJ: 000000000-00 /
"""


def test_the_dangling_colon_shape_reads_the_holder_too():
    r = find_endereco(CONTA_GAS_OCR_DOIS_PONTOS)
    assert r.partes() == {
        "cep": "06700-100",
        "logradouro": "Estrada Municipal Vale Dourado",
        "numero": "512",
        "complemento": "APTO 33",
        "bairro": None,
        "cidade": "ITAPECERICA",
        "uf": "SP",
    }
    assert r.titular == "CICRANO DE EXEMPLO"


def test_the_double_spaced_shape_reads_the_holder_too():
    """A third re-read of the same bill came back with a blank line after
    every line — no two lines of the holder's block adjacent."""
    texto = "\n\n".join(l for l in CONTA_GAS_OCR_REAL.splitlines() if l.strip()) + "\n"
    r = find_endereco(texto)
    assert (r.cep, r.cidade, r.uf, r.numero) == ("06700-100", "ITAPECERICA", "SP", "512")
    assert r.logradouro == "Estrada Municipal Vale Dourado"


def test_a_bare_name_above_a_spelled_out_codigo_do_cliente_is_the_titular():
    texto = (
        "Endereço: R DAS AMOREIRAS 77\n"
        "CEP/Cidade: 13010-110 CAMPINAS SP\n"
        "\n"
        "FULANA EXEMPLAR\n"
        "Código do cliente: 12345\n"
    )
    assert find_endereco(texto).titular == "FULANA EXEMPLAR"


def test_the_copys_trailing_city_is_never_the_bairro():
    """A re-read labelled only the SECOND copy ("… 512 APTO 33 ITAPECERICA");
    the locality came from the envelope block — the trailing token is the
    city, never a bairro."""
    texto = (
        "Nota Fiscal / Conta Gás:\n"
        "CICRANO DE EXEMPLO\n"
        "EST MUNICIPAL VALE DOURADO 512 APTO 33\n"
        "CEP: 06700-100 ITAPECERICA SP\n"
        "Vencimento: 29.07.2026\n"
        "\n"
        "Remetente: Companhia de Gás do Exemplo\n"
        "Rua Bom Retiro, 975 - CEP 04100-200 - Vila Exemplo - São Paulo - SP\n"
        "\n"
        "Cliente: CICRANO DE EXEMPLO\n"
        "Código do cliente: 12345678\n"
        "Endereço: EST MUNICIPAL VALE DOURADO 512 APTO 33 ITAPECERICA\n"
    )
    r = find_endereco(texto)
    assert (r.cep, r.cidade, r.bairro, r.complemento) == ("06700-100", "ITAPECERICA", None, "APTO 33")
