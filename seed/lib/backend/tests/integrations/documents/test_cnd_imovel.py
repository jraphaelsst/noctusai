"""`cnd_imovel` — the imóvel's CND de IPTU and condomínio declaração, read
from printed text. Fixtures are SYNTHETIC, shaped after the real layouts
(GIAP "Cidadão Online" CNDs, a Secretaria de Receita CND, administradora and
associação declarações) — no real names, numbers or addresses."""
from datetime import date

import pytest

from noctusai_lib.integrations.documents.cnd_imovel import (
    LEITORES_POR_TIPO,
    NEGATIVA,
    POSITIVA,
    POSITIVA_COM_EFEITO_DE_NEGATIVA,
    ler_cnd_iptu,
    ler_declaracao_condominio,
)

GIAP_NEGATIVA = """Estado de São Paulo
CENTRO INTEGRADO TRIBUTARIO - CIT
CERTIDÃO NEGATIVA DE TRIBUTOS IMOBILIÁRIOS
CERTIDÃO NEGATIVA Nº. 123456/2026
Certificamos para os devidos fins e efeitos que NÃO CONSTAM DÉBITOS nesta municipalidade para a inscrição
Imobiliária , até a presente data.
Prefeitura do Municipio de Cotia, 11 de agosto de 2026.
FULANA DE TALProprietario:
Local: RUA EXEMPLO   Nº 10             BAIRRO TESTE  LOTE 1  QUADRA A
CEP 06700-000 COTIA SP
Ressalvando-se o direito da Fazenda Municipal de cobrar os débitos que venham a ser apurados.
Essa certidão é válida por 60 dias.
Inscrição Imobiliária: 11111.22.33.0444.00.000
Código de Autenticidade
CINAAAA0000
"""

# The positiva layout scrambles label/value order: the inscrição value lands
# under "Quadra:" before its own label.
GIAP_POSITIVA = """Estado de São Paulo
CENTRO INTEGRADO TRIBUTARIO - CIT
CERTIDÃO POSITIVA TRIBUTOS IMOBILIÁRIOS
CERTIDÃO POSITIVA Nº. 654321/2026
Quadra:
22222.33.44.0555.00.000
Certificamos para os devidos fins e efeitos que a inscrição Imobiliária abaixo descrita encontra-se EM DÉBITO com
esta Municipalidade até a presente data.
Local do Imóvel:     RUA EXEMPLO  Nº 20           AP 1
Inscrição Imobiliária:
Lote:
Proprietário: CICLANO DE TAL
Ressalvando-se o direito da Fazenda Municipal de cobrar os débitos que venham a ser apurados.
Esta certidão é válida por 60 dias
Prefeitura do Municipio de Cotia, 19 de junho de 2026.
"""

SECRETARIA_NEGATIVA = """MUNICIPIO DE EXEMPLO
SECRETARIA DE RECEITA E RENDAS
CERTIDÃO NEGATIVA DE DÉBITOS DE TRIBUTOS IMOBILIÁRIOS
CERTIDÃO IMOBILIÁRIA Nº:
INTERESSADO(A):
29000/2026
BELTRANA DE TAL
Válida por 90 (noventa) dias da data da
sua emissão.
Inscrição Cadastral N°:
Proprietário:
33333.44.55.0666.00.000
Não encontramos pendências com relação aos lançamentos
tributários e não tributários, vinculados ao Imobiliário, até a presente data.
Fica ressalvado o direito da Fazenda Pública, nos termos da Lei 2.968, de 28 de
dezembro  de  2009.
Exemplópolis , 03 de setembro de 2026.
Certidão emitida ás 10:23 horas do dia 03/09/2026 (hora e data de Brasilia)
"""


class TestCndIptu:
    def test_negativa_giap(self):
        lida = ler_cnd_iptu(GIAP_NEGATIVA)
        assert lida.numero == "123456/2026"
        assert lida.emitida_em == date(2026, 8, 11)
        assert lida.validade_dias == 60
        assert lida.validade_ate == date(2026, 10, 10)
        assert lida.resultado == NEGATIVA
        assert lida.inscricao == "11111.22.33.0444.00.000"

    def test_positiva_giap_with_scrambled_inscricao(self):
        lida = ler_cnd_iptu(GIAP_POSITIVA)
        assert lida.numero == "654321/2026"
        assert lida.emitida_em == date(2026, 6, 19)
        assert lida.validade_ate == date(2026, 8, 18)
        assert lida.resultado == POSITIVA
        assert lida.inscricao == "22222.33.44.0555.00.000"

    def test_secretaria_layout_number_after_interveniente_label(self):
        lida = ler_cnd_iptu(SECRETARIA_NEGATIVA)
        assert lida.numero == "29000/2026"
        assert lida.resultado == NEGATIVA
        assert lida.inscricao == "33333.44.55.0666.00.000"

    def test_a_law_date_is_never_the_emission(self):
        # "Lei 2.968, de 28 de dezembro de 2009" sits before the closing.
        lida = ler_cnd_iptu(SECRETARIA_NEGATIVA)
        assert lida.emitida_em == date(2026, 9, 3)
        assert lida.validade_ate == date(2026, 12, 2)

    def test_labelled_emission_alone_is_enough(self):
        texto = "CERTIDÃO NEGATIVA Nº 1000/2026\nCertidão emitida ás 09:00 horas do dia 05/01/2026"
        assert ler_cnd_iptu(texto).emitida_em == date(2026, 1, 5)

    def test_printed_validade_ate_wins_over_the_term(self):
        texto = (
            "CERTIDÃO NEGATIVA Nº 1000/2026\nCotia, 05 de janeiro de 2026.\n"
            "Válida até 01/02/2026"
        )
        lida = ler_cnd_iptu(texto)
        assert lida.validade_ate == date(2026, 2, 1)
        assert lida.validade_dias is None

    def test_term_without_an_emission_date_gives_no_validade(self):
        lida = ler_cnd_iptu("CERTIDÃO NEGATIVA Nº 1000/2026\nEssa certidão é válida por 60 dias.")
        assert lida.validade_dias == 60
        assert lida.validade_ate is None

    def test_two_different_inscricoes_are_not_guessed(self):
        texto = (
            "CERTIDÃO NEGATIVA\nInscrição Imobiliária: 11111.22.33.0444.00.000\n"
            "Inscrição anterior 99999.88.77.0666.00.000"
        )
        assert ler_cnd_iptu(texto).inscricao is None

    def test_no_label_no_inscricao(self):
        assert ler_cnd_iptu("CERTIDÃO NEGATIVA 11111.22.33.0444.00.000").inscricao is None

    def test_campos_uses_the_row_column_names(self):
        assert ler_cnd_iptu(GIAP_NEGATIVA).campos() == {
            "numero": "123456/2026",
            "emitida_em": "2026-08-11",
            "validade_ate": "2026-10-10",
            "resultado": "negativa",
            "inscricao_imobiliaria": "11111.22.33.0444.00.000",
        }

    def test_empty_text_reads_nothing(self):
        assert ler_cnd_iptu("").campos() == {}


class TestResultado:
    @pytest.mark.parametrize(
        "texto",
        [
            "CERTIDÃO POSITIVA COM EFEITOS DE NEGATIVA DE DÉBITOS",
            "Certidão positiva com efeito de negativa — débitos com exigibilidade suspensa",
        ],
    )
    def test_positiva_com_efeito_de_negativa(self, texto):
        assert ler_cnd_iptu(texto).resultado == POSITIVA_COM_EFEITO_DE_NEGATIVA

    def test_negated_debt_phrase_is_not_a_debt(self):
        assert ler_cnd_iptu("NÃO CONSTAM DÉBITOS para o imóvel").resultado == NEGATIVA

    def test_contradictory_wording_is_not_guessed(self):
        texto = "CERTIDÃO NEGATIVA\nO imóvel encontra-se EM DÉBITO com esta municipalidade"
        assert ler_cnd_iptu(texto).resultado is None

    def test_a_reservation_about_future_debts_is_not_a_debt(self):
        texto = (
            "CERTIDÃO NEGATIVA\nRessalvando-se o direito da Fazenda Municipal de cobrar "
            "os débitos que venham a ser apurados."
        )
        assert ler_cnd_iptu(texto).resultado == NEGATIVA


class TestDeclaracaoCondominio:
    """🔴 The bug this module exists for: a paid-up declaração is NEGATIVA
    (no debts). The model used to answer `positiva`."""

    @pytest.mark.parametrize(
        "texto",
        [
            "Administradora Exemplo Ltda\nvimos por meio desta, declarar a quem possa interessar, "
            "que a unidade 000078 - FULANO DE TAL está com as cotas condominiais quitadas, "
            "até a presente data.\nSÃO PAULO, 31 de Agosto de 2026",
            "CERTIDÃO NEGATIVA DE DÉBITOS\nRESIDENCIAL EXEMPLO\n... que a unidade autônoma "
            "número 000012, encontra-se em dia com o pagamento das cotas vencidas até o dia "
            "31 de agosto de 2026, razão pela qual firmamos a presente declaração.\n"
            "Cotia, 31 de agosto de 2026.",
        ],
    )
    def test_paid_up_declaracao_is_negativa_with_its_closing_date(self, texto):
        lida = ler_declaracao_condominio(texto)
        assert lida.resultado == NEGATIVA
        assert lida.emitida_em == date(2026, 8, 31)

    def test_associacao_quite_without_a_date(self):
        texto = (
            "Na qualidade de Presidente da ASSOCIAÇÃO EXEMPLO, DECLARO que o Sr(a). FULANO "
            "está quite com todas as suas taxas de manutenções até a presente data."
        )
        lida = ler_declaracao_condominio(texto)
        assert lida.resultado == NEGATIVA
        assert lida.emitida_em is None  # none printed — never invented

    def test_unit_in_arrears_is_positiva(self):
        texto = "Declaramos que a unidade 12 possui débitos em atraso.\nCotia, 01 de setembro de 2026."
        assert ler_declaracao_condominio(texto).resultado == POSITIVA

    def test_declaracao_has_no_numero_nor_inscricao(self):
        lida = ler_declaracao_condominio("CERTIDÃO NEGATIVA Nº 1/2026 Inscrição Imobiliária: 1.2.3.4")
        assert lida.numero is None and lida.inscricao is None


def test_leitores_por_tipo_covers_both_imovel_cnds():
    assert set(LEITORES_POR_TIPO) == {"cnd_iptu", "cnd_condominio"}
