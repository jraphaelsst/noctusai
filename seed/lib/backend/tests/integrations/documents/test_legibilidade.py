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
    def test_cpf_label_with_failed_check_digits_flags(self):
        texto = "CPF: 111.222.333-44\n"
        resultado = avaliar_legibilidade(texto)
        assert resultado.status is LegibilidadeStatus.COMPROMETIDA
        assert "cpf_invalido" in resultado.motivos

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
