"""Pure tests for `documents.legibilidade` — see that module's own docstring
for the measured CNH-screenshot failure this closes.
"""
from noctusai_lib.integrations.documents.legibilidade import (
    AVISO_LEITURA_COMPROMETIDA,
    LegibilidadeStatus,
    avaliar_legibilidade,
)
from noctusai_lib.integrations.documents.types import IdentityFields

#: A CPF whose check digits verify — used elsewhere in this test family as
#: the canonical "valid" example.
_CPF_VALIDO = "412.954.238-98"


class TestCleanScanStaysOk:
    """Owner directive: thresholds are conservative — a clean scan must
    never be flagged, or the banner trains people to ignore it."""

    def test_well_labelled_transcription_is_ok(self):
        texto = (
            "CARTEIRA NACIONAL DE HABILITACAO\n"
            "NOME: JOAO CARLOS PEREIRA\n"
            f"DATA DE NASCIMENTO: 12/05/1980\n"
            f"CPF: {_CPF_VALIDO}\n"
            "UF: SP\n"
            "FILIACAO: PEDRO PEREIRA E ANA PEREIRA\n"
        )
        resultado = avaliar_legibilidade(texto, nome_titular="JOAO CARLOS PEREIRA")
        assert resultado.status is LegibilidadeStatus.OK
        assert resultado.motivos == ()
        assert resultado.mensagem is None

    def test_pdf_text_layer_shape_without_colons_is_ok(self):
        """Rung 1 (PDF text layer) is not laid out `RÓTULO: valor` per
        line — the mismatch signal must find nothing to misjudge there."""
        texto = (
            "REPUBLICA FEDERATIVA DO BRASIL\n"
            "DATA DE EXPEDICAO 10/03/1995\n"
            "DATA DE NASCIMENTO 12/05/1980"
        )
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_a_single_stray_ilegivel_marker_does_not_flag(self):
        texto = (
            "NOME: JOAO CARLOS PEREIRA\n"
            f"CPF: {_CPF_VALIDO}\n"
            "DATA DE NASCIMENTO: 12/05/1980\n"
            "RG: 52.179.965-X\n"
            "PROFISSAO: (ilegivel)\n"
        )
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_nome_similar_but_not_equal_to_filiacao_does_not_flag(self):
        texto = (
            "NOME: MARIA APARECIDA PELOSI\n"
            "FILIACAO: JOSE PELOSI E MARIA APARECIDA PELOSI RANGEL\n"
        )
        resultado = avaliar_legibilidade(texto, nome_titular="MARIA APARECIDA PELOSI")
        assert resultado.status is LegibilidadeStatus.OK


class TestCampoDataInvalido:
    def test_date_label_with_non_date_value_flags(self):
        texto = "DATA DE NASCIMENTO: BRASILEROCA\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "campo_data_invalido" in resultado.motivos

    def test_date_label_marked_ilegivel_does_not_double_flag_as_mismatch(self):
        texto = "DATA DE NASCIMENTO: (ilegivel)\n"
        resultado = avaliar_legibilidade(texto)
        assert "campo_data_invalido" not in resultado.motivos


class TestCepInvalido:
    def test_cep_label_with_non_8_digit_value_flags(self):
        texto = "CEP: 99 de abril\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "cep_invalido" in resultado.motivos

    def test_cep_label_with_8_digits_is_ok(self):
        texto = "CEP: 04567-000\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK


class TestCpfInvalido:
    """P2 corpus (2026-09-28): a LONE `cpf_invalido` — nothing else wrong on
    the document — is demoted to non-comprometida (a single OCR digit slip,
    not whole-document damage). Co-occurring with any other signal, it
    still counts as normal."""

    def test_cpf_label_with_failed_check_digits_alone_stays_ok(self):
        texto = "CPF: 111.222.333-44\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK
        assert resultado.motivos == ()

    def test_cpf_label_with_failed_check_digits_plus_another_signal_flags(self):
        texto = "CPF: 111.222.333-44\nUF: XX\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert set(resultado.motivos) == {"cpf_invalido", "uf_invalida"}

    def test_cpf_label_with_valid_check_digits_is_ok(self):
        texto = f"CPF: {_CPF_VALIDO}\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_cpf_label_not_eleven_digits_is_not_a_type_mismatch(self):
        """A short/garbled run under a CPF label is `cpf.py`'s own concern
        (it already demotes it); this module only flags a full eleven-digit
        run that fails the checksum."""
        texto = "CPF: 123\n"
        resultado = avaliar_legibilidade(texto)
        assert "cpf_invalido" not in resultado.motivos

    def test_a_cnh_numero_de_registro_label_is_never_mistaken_for_a_cpf(self):
        """A CNH's own `Nº DE REGISTRO` is an 11-digit number with no CPF
        check-digit relationship — validating it AS a CPF would almost
        always fail the checksum for a reason that has nothing to do with
        legibility. The label simply does not contain `CPF`, so this check
        never runs on it at all."""
        texto = "Nº DE REGISTRO: 12345678900\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_a_cat_hab_label_is_never_mistaken_for_a_cpf(self):
        texto = "CAT HAB: AB\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK


class TestUfInvalida:
    def test_uf_label_with_invalid_value_flags(self):
        texto = "UF: XX\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "uf_invalida" in resultado.motivos

    def test_uf_label_with_valid_value_is_ok(self):
        texto = "UF: SP\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_naturalidade_label_is_never_mistaken_for_uf(self):
        texto = "NATURALIDADE: SAO PAULO\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_a_compound_label_merely_containing_the_uf_token_is_never_checked(self):
        """P2 corpus (2026-09-28) — 13/28 false alarms: a real CNH's `4c DOC
        IDENTIDADE / ÓRG EMISSOR / UF` groups three sub-fields into one
        label; `UF` being one whitespace-separated token in it does not
        make the LABEL a UF field."""
        texto = "4c DOC IDENTIDADE / ÓRG EMISSOR / UF: 12345678 SSP SP\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK


class TestCampoDataInvalidoCompostoPassa:
    """P2 corpus (2026-09-28) — 15/28 false alarms: a real CNH's date label
    is often compound (`DATA, LOCAL E UF DE NASCIMENTO`), and its value
    legitimately carries more than the date. The check is "does the value
    CONTAIN a date", not "is the value nothing but a date"."""

    def test_data_local_e_uf_de_nascimento(self):
        texto = "3 DATA, LOCAL E UF DE NASCIMENTO: 01/02/1980, COTIA, SP\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_data_e_local_de_nascimento_bilingual(self):
        texto = (
            "DATA E LOCAL DE NASCIMENTO / DATE AND PLACE OF BIRTH: "
            "01/02/1980, SAO PAULO, SP\n"
        )
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_a_date_label_with_genuinely_no_date_in_the_value_still_flags(self):
        """The fix widens the match, it does not disable the check."""
        texto = "DATA, LOCAL E UF DE NASCIMENTO: COTIA, SP\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "campo_data_invalido" in resultado.motivos


class TestEnderecoSemTexto:
    def test_address_with_no_real_word_flags(self):
        texto = "ENDERECO: 12.345.6789 - 2 via\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "endereco_sem_texto" in resultado.motivos

    def test_a_genuine_address_is_ok(self):
        texto = "ENDERECO: RUA DAS FLORES, 123\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK

    def test_ilegivel_marker_is_not_double_flagged_as_no_text(self):
        texto = "ENDERECO: (ilegivel)\n"
        resultado = avaliar_legibilidade(texto)
        assert "endereco_sem_texto" not in resultado.motivos


class TestCampoIncompativelDocumentoPessoal:
    def test_icms_marker_flags(self):
        texto = "INSCRICAO ESTADUAL DE CONTRIBUINTE DO ICMS: 12.3456789/01\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "campo_incompativel_documento_pessoal" in resultado.motivos

    def test_cnpj_shaped_number_flags(self):
        texto = "INSTITUICAO RESPONSAVEL PELO REGISTRO 12.345.678/90\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "campo_incompativel_documento_pessoal" in resultado.motivos

    def test_an_ordinary_cnh_never_flags(self):
        texto = "CARTEIRA NACIONAL DE HABILITACAO\nNOME: JOAO CARLOS PEREIRA\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.OK


class TestTextoRepetido:
    def test_a_repeated_two_word_phrase_flags(self):
        texto = "SECCAO DE SEGURANCA PUBLICA DO ESTADO DE SEGURANCA PUBLICA\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "texto_repetido" in resultado.motivos

    def test_ordinary_connector_repetition_never_flags(self):
        """`DE`/`DO` repeating is ordinary Portuguese — only a gram carrying
        at least one REAL (4+ letter) word counts."""
        texto = "ESTADO DE SAO PAULO SECRETARIA DA SEGURANCA PUBLICA\n"
        resultado = avaliar_legibilidade(texto)
        assert "texto_repetido" not in resultado.motivos

    def test_a_short_line_never_flags(self):
        texto = "UF: SP\n"
        resultado = avaliar_legibilidade(texto)
        assert "texto_repetido" not in resultado.motivos


class TestMissedRgHallucination:
    """The SECOND real hallucination the P2 corpus measurement caught this
    module missing entirely — a genuinely damaged RG scan, invented values.
    Every signal below is new (2026-09-28); together they must flag it."""

    def test_the_missed_rg_now_flags(self):
        texto = "\n".join(
            [
                "REGISTRO GERAL",
                "ENDERECO: 12.345.6789 - 2 via",
                "PAIS: MULHERES DA FAMILIA DOS SANTOS",
                "INSCRICAO ESTADUAL DE CONTRIBUINTE DO ICMS: 12.3456789/01",
                "INSTITUICAO RESPONSAVEL PELO REGISTRO 12.345.678/90",
                "SECCAO DE SEGURANCA PUBLICA DO ESTADO DE SEGURANCA PUBLICA",
            ]
        )
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "endereco_sem_texto" in resultado.motivos
        assert "campo_incompativel_documento_pessoal" in resultado.motivos
        assert "texto_repetido" in resultado.motivos


class TestAltaTaxaIlegivel:
    def test_high_share_of_ilegivel_markers_flags(self):
        texto = "\n".join(
            [
                "NOME: (ilegivel)",
                "CPF: (ilegivel)",
                f"RG: 52.179.965-X",
                "PROFISSAO: ANALISTA",
            ]
        )
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "alta_taxa_ilegivel" in resultado.motivos

    def test_low_share_of_ilegivel_markers_stays_ok(self):
        linhas = [f"CAMPO{i}: valor{i}" for i in range(10)]
        linhas[0] = "CAMPO0: (ilegivel)"
        resultado = avaliar_legibilidade("\n".join(linhas))
        assert resultado.status is LegibilidadeStatus.OK


class TestNomeIgualFiliacao:
    def test_holder_name_equal_to_mothers_flags(self):
        """The measured CNH-screenshot failure: the holder `NOME` field
        was actually the mother's `FILIAÇÃO` name."""
        texto = (
            "NOME: MARIA APARECIDA DAS DORES\n"
            "FILIACAO: JOSE DA SILVA E MARIA APARECIDA DAS DORES\n"
        )
        resultado = avaliar_legibilidade(texto, nome_titular="MARIA APARECIDA DAS DORES")
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "nome_igual_filiacao" in resultado.motivos

    def test_no_titular_hint_skips_the_check(self):
        texto = "FILIACAO: JOSE DA SILVA E MARIA APARECIDA DAS DORES\n"
        resultado = avaliar_legibilidade(texto, nome_titular=None)
        assert "nome_igual_filiacao" not in resultado.motivos


class TestMeasuredCnhScreenshotCase:
    """All three signals fire together on the actual measured transcription
    shape, and the combined message names every reason."""

    def test_combined_signals(self):
        texto = (
            "CNH DIGITAL\n"
            "NOME: MARIA APARECIDA DAS DORES\n"
            "DATA DE NASCIMENTO: BRASILEROCA\n"
            f"CPF: {_CPF_VALIDO}\n"
            "CEP: 99 de abril\n"
            "FILIACAO: JOSE DA SILVA E MARIA APARECIDA DAS DORES\n"
        )
        resultado = avaliar_legibilidade(texto, nome_titular="MARIA APARECIDA DAS DORES")
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert set(resultado.motivos) == {
            "campo_data_invalido",
            "cep_invalido",
            "nome_igual_filiacao",
        }
        assert resultado.mensagem is not None


class TestIdentityFieldsLeituraComprometida:
    def test_true_when_aviso_carries_the_code(self):
        fields = IdentityFields(aviso=AVISO_LEITURA_COMPROMETIDA)
        assert fields.leitura_comprometida is True

    def test_true_when_joined_with_another_code(self):
        fields = IdentityFields(aviso=f"titulares_multiplos+{AVISO_LEITURA_COMPROMETIDA}")
        assert fields.leitura_comprometida is True

    def test_false_when_absent(self):
        fields = IdentityFields(aviso="titulares_multiplos")
        assert fields.leitura_comprometida is False

    def test_false_when_aviso_is_none(self):
        fields = IdentityFields()
        assert fields.leitura_comprometida is False
