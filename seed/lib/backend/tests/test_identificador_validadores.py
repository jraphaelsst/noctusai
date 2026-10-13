"""Standalone identifier validators (owner rule 2026-10-13: validation only
ACCEPTS or FLAGS — a check digit the document does not print is never
computed and appended). Fixtures are invented or the RFB's own published
example."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.primitives import identificador as idf


class TestRne:
    @pytest.mark.parametrize("valor", ["W-573.678-Z", "W573678Z", "W573678-Z", "w-573.678-z"])
    def test_printed_shapes_are_accepted_as_printed(self, valor: str) -> None:
        r = idf.validar_rne(valor)
        assert r.valido and r.canonico == "W573678-Z"
        assert r.partes == {"letra": "W", "dv": "Z"}

    @pytest.mark.parametrize("valor", ["W573678ZDIREX", "573678-Z", "W57367-Z", "WW573678Z", ""])
    def test_off_mask_is_refused(self, valor: str) -> None:
        assert not idf.validar_rne(valor).valido

    def test_no_check_digit_is_ever_appended(self) -> None:
        assert not idf.validar_rne("W573678").valido


class TestMatriculaRcpn:
    # CNS 119917 · acervo 02 · 55 · 1975 · livro B(2) · 00012 · fl 034 · termo 0001234 · DV 31
    OK = "11991702551975200012034000123431"

    def test_well_formed_casamento(self) -> None:
        r = idf.validar_matricula_rcpn(self.OK, tipo_certidao="casamento", data_emissao=date(2024, 1, 5))
        assert r.valido and r.motivo == "ok" and r.avisos == ()
        assert r.partes["ano"] == "1975" and r.partes["tipo_livro"] == "2"
        assert r.canonico == "119917 02 55 1975 2 00012 034 0001234 31"

    def test_positions_9_10_must_be_55(self) -> None:
        bad = self.OK[:8] + "44" + self.OK[10:]
        assert idf.validar_matricula_rcpn(bad).motivo == "nao_rcpn"

    def test_tipo_livro_must_match_the_certificate(self) -> None:
        r = idf.validar_matricula_rcpn(self.OK, tipo_certidao="nascimento")
        assert not r.valido and r.motivo == "tipo_livro_incompativel"

    def test_ano_after_emission_is_refused(self) -> None:
        r = idf.validar_matricula_rcpn(self.OK, data_emissao=date(1970, 1, 1))
        assert r.motivo == "ano_posterior_a_emissao"

    def test_dv_mismatch_is_only_a_soft_warning(self) -> None:
        r = idf.validar_matricula_rcpn(self.OK[:-2] + "00")
        assert r.valido and r.avisos == ("dv_nao_confere",)
        assert r.canonico.endswith(" 00")  # kept as printed, never corrected

    @pytest.mark.parametrize("valor,motivo", [("123", "tamanho"), ("1199170255197520001203400012343X", "caracteres_invalidos")])
    def test_shape_refusals(self, valor: str, motivo: str) -> None:
        assert idf.validar_matricula_rcpn(valor).motivo == motivo


class TestCnhRegistro:
    @pytest.mark.parametrize("valor", ["12345678900", "00000001795", "98765432109"])
    def test_valid(self, valor: str) -> None:
        r = idf.validar_cnh_registro(valor)
        assert r.valido and r.avisos == ()
        assert idf.ler("cnh", valor).cabe  # same answer as the registry reader

    def test_dv1_mismatch_is_hard(self) -> None:
        assert idf.validar_cnh_registro("12345678910").motivo == "dv_invalido"

    def test_dv2_mismatch_hard_when_remainder_ge_2(self) -> None:
        assert not idf.validar_cnh_registro("00000001796").valido

    def test_dv2_mismatch_only_warns_when_dv1_remainder_lt_2(self) -> None:
        # 100000001 has dv1 remainder 1 -> dv1 = 0; the valid DV2 is 8.
        assert idf.validar_cnh_registro("10000000108").avisos == ()
        r = idf.validar_cnh_registro("10000000105")
        assert r.valido and r.avisos == ("dv2_variante",)

    def test_wrong_length(self) -> None:
        assert idf.validar_cnh_registro("1234567890").motivo == "tamanho"


class TestCnpjAlfanumerico:
    def test_rfb_published_example(self) -> None:
        r = idf.validar_cnpj("12.ABC.345/01DE-35")
        assert r.valido and r.canonico == "12.ABC.345/01DE-35"

    def test_letters_in_base_bad_dv(self) -> None:
        assert idf.validar_cnpj("12ABC34501DE36").motivo == "dv_invalido"

    def test_letters_in_dv_positions_refused(self) -> None:
        assert not idf.validar_cnpj("12ABC34501DE3A").valido

    def test_numeric_still_valid(self) -> None:
        assert idf.validar_cnpj("11.222.333/0001-81").valido


class TestCreci:
    @pytest.mark.parametrize(
        "valor,canon,pessoa",
        [
            ("12345-F", "12345-F", "fisica"),
            ("12345J", "12345-J", "juridica"),
            ("CRECI/SP 12345-F", "12345-F/SP", "fisica"),
            ("123456-J/SP", "123456-J/SP", "juridica"),
        ],
    )
    def test_accepted(self, valor: str, canon: str, pessoa: str) -> None:
        r = idf.validar_creci(valor)
        assert r.valido and r.canonico == canon and r.partes["pessoa"] == pessoa

    def test_f_or_j_is_never_inferred(self) -> None:
        assert idf.validar_creci("12345").motivo == "sem_tipo"
        assert idf.validar_creci("CRECI/SP 12345").motivo == "sem_tipo"

    def test_other_suffix_refused(self) -> None:
        assert idf.validar_creci("12345-X").motivo == "tipo_invalido"

    def test_too_many_digits(self) -> None:
        assert not idf.validar_creci("1234567-F").valido
