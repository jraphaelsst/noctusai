"""Guard tests for the validator's FALSE-POSITIVE / FALSE-NEGATIVE fixes
(2026-10-06 diagnosis of the 10 scored deals). Each fix is pinned in BOTH
directions: the benign twin passes, the true twin still fails. Every string is
invented."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comparador  # noqa: E402
from test_comparador_dois_niveis import _BASE, _troca  # noqa: E402

LAC = comparador.MARCADOR_LACUNA


def _com_objeto(paragrafos, texto_imovel):
    """`_BASE` with the IMÓVEL quote replaced."""
    out = list(paragrafos)
    i = next(k for k, p in enumerate(out) if p.startswith("IMÓVEL:"))
    out[i] = texto_imovel
    return out


_IMOVEL_REF = (
    "IMÓVEL: casa nº 54, com área privativa de 80,50m2, confrontando pela frente com a rua 1 e por 2 lados com o lote vizinho. "
    "Imóvel devidamente cadastrado pela Prefeitura Municipal de Cidade Exemplo sob nº 23253.41.85.0055.00.000 e caracterizado na "
    "Matrícula Nº 12.345 do 1º Cartório de Registro de Imóveis de Cidade Exemplo."
)


class TestInscricaoCadastral:
    def test_separators_and_zero_groups_are_layout(self):
        gerado = _com_objeto(_BASE, _IMOVEL_REF.replace("23253.41.85.0055.00.000", "23253-41-85-0055-00-000"))
        ref = _com_objeto(_BASE, _IMOVEL_REF)
        assert comparador.pontuar(ref, gerado).veredito == "aprovado"

    def test_a_wrong_inscricao_still_fails(self):
        ref = _com_objeto(_BASE, _IMOVEL_REF)
        gerado = _com_objeto(_BASE, _IMOVEL_REF.replace("23253.41.85.0055.00.000", "23253.41.85.0056.00.000"))
        card = comparador.pontuar(ref, gerado)
        assert card.veredito == "reprovado"

    def test_a_second_inscricao_labelled_area_maior_is_an_observation(self):
        ref = _com_objeto(_BASE, _IMOVEL_REF)
        gerado = _com_objeto(_BASE, _IMOVEL_REF + " CADASTRO IMOBILIÁRIO: nº 23253.41.85.0002.0 (área maior).")
        card = comparador.pontuar(ref, gerado)
        assert card.veredito == "aprovado_com_observacoes", card.motivos()

    def test_the_second_inscricao_does_not_excuse_a_wrong_first_one(self):
        ref = _com_objeto(_BASE, _IMOVEL_REF)
        gerado = _com_objeto(
            _BASE,
            _IMOVEL_REF.replace("23253.41.85.0055.00.000", "23253.41.85.0099.00.000")
            + " CADASTRO IMOBILIÁRIO: nº 23253.41.85.0002.0 (área maior).",
        )
        assert comparador.pontuar(ref, gerado).veredito == "reprovado"


class TestNumeraisDescritivosDoImovel:
    def test_a_boundary_street_number_is_the_registrys_wording(self):
        ref = _com_objeto(_BASE, _IMOVEL_REF)
        gerado = _com_objeto(_BASE, _IMOVEL_REF.replace("rua 1 e por 2 lados", "Rua I e por dois lados"))
        assert comparador.pontuar(ref, gerado).veredito == "aprovado_com_observacoes"

    def test_the_units_own_number_stays_material(self):
        ref = _com_objeto(_BASE, _IMOVEL_REF)
        gerado = _com_objeto(_BASE, _IMOVEL_REF.replace("casa nº 54", "casa nº 55"))
        assert comparador.pontuar(ref, gerado).veredito == "reprovado"

    def test_an_area_stays_material(self):
        ref = _com_objeto(_BASE, _IMOVEL_REF)
        gerado = _com_objeto(_BASE, _IMOVEL_REF.replace("80,50m2", "80,60m2"))
        assert comparador.pontuar(ref, gerado).veredito == "reprovado"


class TestParcelasEnumeradasNaMora:
    _MORA = "CLÁUSULA SÉTIMA – DA MORA E DO INADIMPLEMENTO"

    def _com_mora(self, texto):
        return _BASE[:-4] + [self._MORA, texto] + _BASE[-4:]

    def test_a_citation_of_the_parcelas_by_number_is_not_a_term(self):
        ref = self._com_mora("Em atraso das parcelas 1 (um), 2 (dois), e 3 (três) do preço, multa de 2% (dois por cento).")
        gerado = self._com_mora("Em atraso de qualquer das parcelas do preço, multa de 2% (dois por cento).")
        assert comparador.pontuar(ref, gerado).veredito == "aprovado_com_observacoes"

    def test_a_different_multa_still_fails_that_clause(self):
        ref = self._com_mora("Em atraso das parcelas 1 (um), 2 (dois), e 3 (três) do preço, multa de 2% (dois por cento).")
        gerado = self._com_mora("Em atraso de qualquer das parcelas do preço, multa de 5% (cinco por cento).")
        assert comparador.pontuar(ref, gerado).veredito == "reprovado"


_PREAMBULO_REF = (
    "De um lado, FULANO DE TAL, brasileiro, casado, portador da cédula de identidade RG 12.345.678-SSP-SP e inscrito no CPF sob nº "
    "111.444.777-35, e de outro lado, BELTRANA EXEMPLO, brasileira, solteira, portadora da cédula de identidade RG 23.456.789-SSP-SP e "
    "inscrita no CPF sob nº 529.982.247-25, residente na Avenida Modelo, nº 20."
)


class TestMarcadoresDeLacunaNaQualificacao:
    def _com_preambulo(self, texto):
        out = list(_BASE)
        out[1] = texto
        return out

    def test_a_nationality_gap_does_not_hide_a_different_party_name(self):
        ref = self._com_preambulo(_PREAMBULO_REF)
        gerado = self._com_preambulo(_PREAMBULO_REF.replace("BELTRANA EXEMPLO, brasileira", f"OUTRA PESSOA, {LAC}"))
        card = comparador.pontuar(ref, gerado)
        assert card.veredito == "reprovado"
        assert any(m.startswith("mat_parte_nome") for m in card.motivos()), card.motivos()

    def test_a_name_that_is_itself_a_gap_is_still_a_gap_not_a_failure(self):
        ref = self._com_preambulo(_PREAMBULO_REF)
        gerado = self._com_preambulo(_PREAMBULO_REF.replace("BELTRANA EXEMPLO, brasileira", f"{LAC}, brasileira"))
        card = comparador.pontuar(ref, gerado)
        assert not any(m.startswith("mat_parte_nome") for m in card.motivos()), card.motivos()

    def test_the_issuer_gap_marker_does_not_absorb_a_second_wrong_rg(self):
        """`RG [[LACUNA]]-[[LACUNA]]` is ONE missing RG (number + issuer). The issuer
        marker used to absorb the NEXT missing RG, hiding a wrong printed one."""
        ref = self._com_preambulo(_PREAMBULO_REF)
        gerado = self._com_preambulo(
            _PREAMBULO_REF.replace("RG 12.345.678-SSP-SP", "RG 1234568-SSP-SP").replace(
                "RG 23.456.789-SSP-SP", f"RG {LAC}-{LAC}"
            )
        )
        card = comparador.pontuar(ref, gerado)
        assert card.veredito == "reprovado"
        assert card.resumo()["numeros_materiais_por_tipo"].get("rg", 0) >= 1

    def test_a_lone_issuer_gap_with_the_number_printed_absorbs_nothing(self):
        ref = self._com_preambulo(_PREAMBULO_REF)
        gerado = self._com_preambulo(_PREAMBULO_REF.replace("RG 23.456.789-SSP-SP", f"RG 23.456.789-{LAC}"))
        card = comparador.pontuar(ref, gerado)
        assert card.veredito == "incompleto", card.motivos()


class TestPosseSemPrazoComDataFixa:
    _POSSE_REF = "A posse será transmitida aos compradores em 15 de outubro de 2026, livre de pessoas e coisas."

    def test_the_day_count_sentinel_is_the_same_gap_as_a_missing_fixed_date(self):
        gerado = _troca(
            _BASE, self._POSSE_REF, f"A posse será transmitida aos compradores em até {comparador.INTEIRO_LACUNA} dias, livre de pessoas e coisas."
        )
        card = comparador.pontuar(_BASE, gerado)
        assert card.veredito == "incompleto", card.motivos()

    def test_a_printed_wrong_date_still_fails(self):
        gerado = _troca(_BASE, "em 15 de outubro de 2026", "em 20 de outubro de 2026")
        assert comparador.pontuar(_BASE, gerado).veredito == "reprovado"


class TestRomanosEmNomesDeVia:
    """Deal 867 (2026-10-06): the matrícula transcribes `Rua I`, the signed
    contract prints `Rua 1` — one fact. Scope: a Roman numeral right after a
    street-type word ONLY. `Anexo I` / `Bloco I` / `Torre I` stay strict (a
    bloco/anexo number is the unit's identity and is compared as written)."""

    def test_extraction_reads_both_spellings_as_one_token(self):
        for romano, arabico in (("Rua I", "Rua 1"), ("Alameda III", "Alameda 3"),
                                ("Av. IV", "Av. 4"), ("Travessa IX", "Travessa 9"),
                                ("quadra XII", "quadra 12")):
            assert comparador.extrair_numeros(romano) == comparador.extrair_numeros(arabico), romano

    def test_a_different_number_is_still_a_different_token(self):
        assert comparador.extrair_numeros("Rua 2") != comparador.extrair_numeros("Rua 1")
        assert comparador.extrair_numeros("Rua II") != comparador.extrair_numeros("Rua 1")

    def test_not_after_a_street_word_nothing_changes(self):
        for texto in ("Anexo I", "Bloco I", "Torre II", "Eu, I, declaro"):
            assert comparador.romanos_de_via_para_arabicos(texto) == texto
        # a street NAME that merely starts with those letters is untouched
        assert comparador.romanos_de_via_para_arabicos("Rua Itapeva") == "Rua Itapeva"
        assert comparador.romanos_de_via_para_arabicos("Rua das Flores") == "Rua das Flores"

    def test_rua_i_vs_rua_1_in_the_objeto_clause_is_not_a_missing_number(self):
        imovel = (
            "IMÓVEL: casa nº 54, situada na Rua {via}, nº 20, com área privativa de 80,50m2, "
            "caracterizado na Matrícula Nº 12.345 do 1º Cartório de Registro de Imóveis de Cidade Exemplo."
        )
        ref = _com_objeto(_BASE, imovel.format(via="1"))
        gerado = _com_objeto(_BASE, imovel.format(via="I"))
        assert comparador.pontuar(ref, gerado).veredito != "reprovado"
        assert comparador.pontuar(gerado, ref).veredito != "reprovado"

    def test_rua_2_vs_rua_1_is_still_material(self):
        imovel = (
            "IMÓVEL: casa nº 54, situada na Rua {via}, nº 20, com área privativa de 80,50m2, "
            "caracterizado na Matrícula Nº 12.345 do 1º Cartório de Registro de Imóveis de Cidade Exemplo."
        )
        ref = _com_objeto(_BASE, imovel.format(via="1"))
        assert comparador.pontuar(ref, _com_objeto(_BASE, imovel.format(via="2"))).veredito == "reprovado"
        assert comparador.pontuar(ref, _com_objeto(_BASE, imovel.format(via="II"))).veredito == "reprovado"
