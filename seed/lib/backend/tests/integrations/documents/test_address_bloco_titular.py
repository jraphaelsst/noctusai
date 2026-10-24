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
