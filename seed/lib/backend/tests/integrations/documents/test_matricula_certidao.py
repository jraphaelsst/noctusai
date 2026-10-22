"""`matricula_certidao` — kind (certidão vs visualização) + the certidão's own
emission date, never an act date (P5 audit B1, 2026-10).

Every fixture is SYNTHETIC: invented cartório, names, numbers and dates that
only mimic the layout of a real "Visualização de Matrícula" printout and of a
real certidão de inteiro teor.
"""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.integrations.documents import (
    TIPOS_DOCUMENTO_MATRICULA,
    CertidaoMatriculaLida,
    classificar_documento_matricula,
    ler_certidao_matricula,
)
from noctusai_lib.integrations.documents.matricula_certidao import (
    MOTIVO_ANTERIOR_AO_ULTIMO_ATO,
    MOTIVO_DIVERGENTE,
    MOTIVO_NAO_ENCONTRADA,
    MOTIVO_VISUALIZACAO,
    data_da_visualizacao,
    data_ultimo_ato,
)

ATOS = (
    "R.1/12.345 - VENDA E COMPRA - Em 10 de março de 1984. Por escritura de "
    "01/03/1984, JOAO EXEMPLO SILVA vendeu o imóvel a CARLOS FICTICIO SOUZA. Dou fé.\n"
    "R.2/12.345 - ALIENAÇÃO FIDUCIÁRIA - Em 05/06/2017. Em garantia a favor do "
    "BANCO EXEMPLO S.A.\n"
    "AV.3/12.345 - CANCELAMENTO - Em 02/02/2021. Fica cancelado o R.2.\n"
)

VISUALIZACAO = (
    "VISUALIZAÇÃO DE MATRÍCULA\n"
    "Esta visualização não tem valor de certidão.\n"
    "Oficial de Registro de Imóveis de Cidade Exemplo\n"
    "MATRÍCULA Nº 12.345\n"
    "IMÓVEL: casa 1 do Condomínio Exemplo.\n" + ATOS + "Visualização gerada em 04/03/2024 às 10:11.\n"
)

CERTIDAO = (
    "OFICIAL DE REGISTRO DE IMÓVEIS DE CIDADE EXEMPLO\n"
    "CERTIDÃO DE INTEIRO TEOR\n"
    "MATRÍCULA Nº 12.345\n"
    "IMÓVEL: casa 1.\n" + ATOS + "CERTIFICO que a presente é reprodução autêntica da matrícula "
    "nº 12.345. O referido é verdade e dou fé. Cidade Exemplo, 1º de março de 2026.\n"
    "Certidão expedida às 10:22:33 horas do dia 01/03/2026. Selo digital 1234AB.\n"
)


class TestKind:
    def test_a_visualizacao_printout_is_classified_as_such(self):
        assert classificar_documento_matricula(VISUALIZACAO)[0] == "visualizacao"

    def test_a_certidao_de_inteiro_teor_is_a_certidao(self):
        assert classificar_documento_matricula(CERTIDAO)[0] == "certidao"

    @pytest.mark.parametrize(
        "disclaimer",
        [
            "Documento para simples consulta.",
            "Este documento NÃO SUBSTITUI A CERTIDÃO.",
            "Mera vizualização, sem valor de certidão.",
        ],
    )
    def test_the_disclaimer_alone_marks_a_printout(self, disclaimer):
        texto = "MATRÍCULA Nº 12.345\n" + ATOS + disclaimer
        assert classificar_documento_matricula(texto)[0] == "visualizacao"

    def test_visualizacao_wins_over_the_word_certidao_in_its_own_disclaimer(self):
        texto = "CERTIDÃO DIGITAL? Não: visualização de matrícula sem valor de certidão.\n" + ATOS
        assert classificar_documento_matricula(texto)[0] == "visualizacao"

    def test_bare_dou_fe_in_an_act_does_not_make_a_certidao(self):
        """Act texts end with "Dou fé" too — it must not upgrade an unlabelled
        printout whose disclaimer the transcription lost."""
        assert classificar_documento_matricula("MATRÍCULA Nº 12.345\n" + ATOS) == (None, None)

    def test_an_acts_own_selo_does_not_make_a_certidao(self):
        """Deal 857: every act is signed "ESCREVENTE SELO DIGITAL Nº …"; a
        vision read that lost the disclaimer was upgraded by it."""
        texto = (
            "MATRÍCULA Nº 12.345\n" + ATOS
            + "FULANO EXEMPLO - ESCREVENTE SELO DIGITAL Nº 1234567890 R. 04\n"
        )
        assert classificar_documento_matricula(texto) == (None, None)

    def test_a_certificates_own_selo_still_marks_a_certidao(self):
        assert classificar_documento_matricula(ATOS + "Selo digital 1234AB.")[0] == "certidao"

    def test_vocabulary(self):
        assert TIPOS_DOCUMENTO_MATRICULA == ("certidao", "visualizacao")


class TestEmissionDate:
    def test_a_visualizacao_has_no_emission_date_and_says_why(self):
        """B1: the printout's first act (1984) used to be read as its emission
        date, so every deal blocked on 'certidão vencida'."""
        lida = ler_certidao_matricula(VISUALIZACAO)
        assert lida.tipo_documento_matricula == "visualizacao"
        assert lida.data_emissao is None
        assert lida.motivo == MOTIVO_VISUALIZACAO
        assert lida.data_emissao != date(1984, 3, 10)

    def test_a_certidao_emission_is_its_certification_date_never_an_act_date(self):
        lida = ler_certidao_matricula(CERTIDAO)
        assert lida.data_emissao == date(2026, 3, 1)
        assert lida.data_emissao_confianca == "alta"
        assert lida.motivo is None
        assert lida.data_ultimo_ato == date(2021, 2, 2)

    def test_the_closing_formula_is_read_when_no_labelled_emission(self):
        texto = (
            "CERTIDÃO DIGITAL\nMATRÍCULA Nº 12.345\n" + ATOS
            + "O referido é verdade e dou fé. Cidade Exemplo, 15 de abril de 2026.\n"
        )
        lida = ler_certidao_matricula(texto)
        assert lida.data_emissao == date(2026, 4, 15)
        assert lida.data_emissao_confianca == "alta"

    @pytest.mark.parametrize(
        "cidade",
        ["CIDADE EXEMPLO-SP, - ", "CIDADE EXEMPLO/SP, ", "CIDADE EXEMPLO - SP, ", "CIDADE EXEMPLO, - "],
    )
    def test_the_closing_line_tolerates_a_uf_suffix_and_a_dash_before_the_date(self, cidade):
        texto = (
            "CERTIDÃO DIGITAL\nMATRÍCULA Nº 12.345\n" + ATOS
            + "CERTIFICO E DOU FE, (PROTOCOLO NO 85.388) QUE O IMOVEL EXEMPLO. "
            "EMOLUMENTOS: R$: 45,88 TOTAL: R$: 76,98 " + cidade + "12 DE MARCO DE 2026\n"
        )
        lida = ler_certidao_matricula(texto)
        assert lida.data_emissao == date(2026, 3, 12)
        assert lida.data_emissao_confianca == "alta"

    def test_a_city_uf_date_inside_an_act_is_not_a_closing(self):
        texto = (
            "CERTIDÃO DIGITAL\nMATRÍCULA Nº 12.345\n"
            "R.3/12.345 - Em 10 de maio de 2022. CIDADE EXEMPLO-SP, 10 DE MAIO DE 2022.\n"
            "CERTIFICO E DOU FE QUE A PRESENTE E REPRODUCAO.\n"
        )
        assert ler_certidao_matricula(texto).data_emissao is None

    def test_a_labelled_emission_in_the_page_head(self):
        texto = "CERTIDÃO DE MATRÍCULA - Data da emissão: 20/05/2026\n" + ATOS
        assert ler_certidao_matricula(texto).data_emissao == date(2026, 5, 20)

    def test_an_act_citing_another_certidao_is_not_the_emission(self):
        """`certidão expedida em 01/02/2010 pela Prefeitura` inside an act is
        outside every zone — and older than the last act anyway."""
        texto = (
            "CERTIDÃO DE MATRÍCULA\nMATRÍCULA Nº 12.345\n" + ATOS
            + "AV.4/12.345 - CONSTRUÇÃO - Em 03/03/2022. À vista da certidão expedida em "
            "01/02/2010 pela Prefeitura, averba-se a construção.\n"
            + "CERTIFICO que é cópia fiel. Certidão expedida em 10/09/2026.\n"
        )
        assert ler_certidao_matricula(texto).data_emissao == date(2026, 9, 10)

    def test_no_certification_date_is_absence_not_an_act_date(self):
        lida = ler_certidao_matricula("CERTIDÃO DIGITAL\n" + ATOS + "CERTIFICO que é cópia fiel.\n")
        assert lida.data_emissao is None
        assert lida.motivo == MOTIVO_NAO_ENCONTRADA

    def test_an_emission_before_the_last_act_is_refused(self):
        lida = ler_certidao_matricula(
            "CERTIDÃO DE MATRÍCULA\n" + ATOS + "CERTIFICO. Data da emissão: 10/01/2019.\n"
        )
        assert lida.data_emissao is None
        assert lida.motivo == MOTIVO_ANTERIOR_AO_ULTIMO_ATO

    def test_two_disagreeing_labelled_emissions_are_absence(self):
        texto = (
            "CERTIDÃO DE MATRÍCULA\n" + ATOS
            + "CERTIFICO. Certidão expedida em 01/03/2026. Data da emissão: 05/03/2026.\n"
        )
        lida = ler_certidao_matricula(texto)
        assert lida.data_emissao is None
        assert lida.motivo == MOTIVO_DIVERGENTE


class TestViewDate:
    """§3 — the date the registry served a visualização (its request/print
    stamp), what the office prints as "…, emitida em <data> (Arisp)". It is
    never the emission and never an act date."""

    def test_the_generated_at_stamp_is_the_view_date(self):
        lida = ler_certidao_matricula(VISUALIZACAO)
        assert lida.data_visualizacao == date(2024, 3, 4)
        assert lida.data_emissao is None
        assert lida.motivo == MOTIVO_VISUALIZACAO

    def test_the_arisp_requester_stamp_on_every_page(self):
        estampa = "SOLICITADO POR: FULANO EXEMPLO - CPF/CNPJ: ***.123.456-** DATA:  29/06/2026 07:57:57\n"
        texto = "VISUALIZAÇÃO DE MATRÍCULA\n" + estampa + ATOS + estampa
        assert ler_certidao_matricula(texto).data_visualizacao == date(2026, 6, 29)

    def test_no_stamp_means_no_view_date_never_an_act_date(self):
        texto = "VISUALIZAÇÃO DE MATRÍCULA\nMATRÍCULA Nº 12.345\n" + ATOS
        assert ler_certidao_matricula(texto).data_visualizacao is None

    def test_a_stamp_before_the_last_act_is_refused(self):
        texto = "VISUALIZAÇÃO DE MATRÍCULA\n" + ATOS + "Consultado em 10/01/2019.\n"
        assert ler_certidao_matricula(texto).data_visualizacao is None

    def test_disagreeing_stamps_are_absence(self):
        texto = (
            "VISUALIZAÇÃO DE MATRÍCULA\n" + ATOS
            + "Visualização gerada em 04/03/2024. Data da consulta: 05/03/2024.\n"
        )
        assert ler_certidao_matricula(texto).data_visualizacao is None

    def test_the_stamp_only_in_the_text_layer_is_read_from_it(self):
        """Deal 857: the vision transcription drops the ARISP stamp printed
        as a text layer over the scan — the raw layer carries it."""
        ocr = "VISUALIZAÇÃO DE MATRÍCULA\n" + ATOS
        camada = "SOLICITADO POR: FULANO EXEMPLO - CPF/CNPJ: ***.123.456-** DATA:  29/06/2026 07:57:57"
        assert ler_certidao_matricula(ocr).data_visualizacao is None
        assert ler_certidao_matricula(ocr, texto_camada=camada).data_visualizacao == date(2026, 6, 29)

    def test_the_text_layer_never_dates_a_certidao_or_changes_its_kind(self):
        camada = "SOLICITADO POR: FULANO - DATA: 29/06/2026"
        lida = ler_certidao_matricula(CERTIDAO, texto_camada=camada)
        assert lida.tipo_documento_matricula == "certidao"
        assert lida.data_visualizacao is None
        assert lida.data_emissao == date(2026, 3, 1)

    def test_the_transcription_stamp_wins_over_the_layer(self):
        camada = "Consultado em 05/03/2024"
        assert ler_certidao_matricula(VISUALIZACAO, texto_camada=camada).data_visualizacao == date(2024, 3, 4)

    def test_a_certidao_has_no_view_date(self):
        assert ler_certidao_matricula(CERTIDAO).data_visualizacao is None

    def test_the_helper_takes_the_floor(self):
        assert data_da_visualizacao("Visualização gerada em 04/03/2024", date(2025, 1, 1)) is None
        assert data_da_visualizacao("Visualização gerada em 04/03/2024") == date(2024, 3, 4)


class TestExternalCandidate:
    """An LLM's emission answer is only trusted when it clears the same
    chronology floor."""

    def test_an_act_date_from_outside_is_refused(self):
        lida = ler_certidao_matricula("CERTIDÃO DIGITAL\n" + ATOS)
        assert not lida.aceita_data_externa(date(1984, 3, 10))
        assert lida.aceita_data_externa(date(2026, 3, 1))

    def test_an_external_date_equal_to_the_last_act_is_refused(self):
        lida = ler_certidao_matricula("CERTIDÃO DIGITAL\n" + ATOS)
        assert not lida.aceita_data_externa(date(2021, 2, 2))
        assert lida.aceita_data_externa(date(2021, 2, 3))

    def test_a_visualizacao_accepts_no_external_date(self):
        assert not ler_certidao_matricula(VISUALIZACAO).aceita_data_externa(date(2026, 3, 1))

    def test_none_is_never_accepted(self):
        assert not CertidaoMatriculaLida().aceita_data_externa(None)


def test_data_ultimo_ato_is_the_latest_registration():
    assert data_ultimo_ato(ATOS) == date(2021, 2, 2)
    assert data_ultimo_ato("") is None
