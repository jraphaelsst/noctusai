"""`find_cartorio` / `find_inscricao_municipal` — the cartório heading and the
CADASTRO MUNICIPAL block of a certidão de matrícula.

Every name, number and city below is invented; the SHAPES are the real ones
seen on signed certidões (ridigital two-column scans, digital text-layer
certidões, split two-line headings).
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.matricula_cabecalho import (
    find_cartorio,
    find_inscricao_municipal,
)

RIDIGITAL = (
    "================================================\n"
    "Valide aqui este documento\n"
    "Mat. 3917 - Página 1/3 - PROT. 445566\n"
    "CNM: 12345678\n"
    "LIVRO Nº 2 - REGISTRO\n"
    "GERAL\n"
    "—matrícula—\n"
    "3917\n"
    "OFICIAL DE REGISTRO DE IMÓVEIS\n"
    "DA COMARCA DE SÃO PAULO/SP\n"
    "\n"
    "IMÓVEL: Um lote de terreno sob o nº 7 da quadra B.\n"
    "CADASTRO MUNICIPAL: Contribuinte nº 123.456.7-8.\n"
    "REGISTRO ANTERIOR: R-5/M-12.345 do Registro de Imóveis de Osasco/SP.\n"
    "R-1/3917 - Em 10 de março de 2001, venda e compra.\n"
    "Documento gerado oficialmente pelo Registro de Imóveis via www.ridigital.org.br\n"
)


class TestFindCartorio:
    def test_split_two_line_heading_is_joined(self):
        valor, conf, _ = find_cartorio(RIDIGITAL)
        assert valor == "OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE SÃO PAULO/SP"
        assert conf == "alta"

    def test_single_line_ordinal_heading(self):
        texto = (
            "1º Oficial de Registro de Imóveis de Cotia - SP\n"
            "MATRÍCULA Nº 45.678 — FICHA 01\n"
            "IMÓVEL: Apartamento 12.\n"
        )
        valor, conf, _ = find_cartorio(texto)
        assert valor == "1º Oficial de Registro de Imóveis de Cotia - SP"
        assert conf == "alta"

    def test_prefix_line_above_is_joined(self):
        texto = "2º OFICIAL DE\nREGISTRO DE IMÓVEIS DE CAMPINAS\nIMÓVEL: Casa.\n"
        valor, conf, _ = find_cartorio(texto)
        assert valor == "2º OFICIAL DE REGISTRO DE IMÓVEIS DE CAMPINAS"
        assert conf == "alta"

    def test_body_mention_of_another_registry_is_never_read(self):
        """REGISTRO ANTERIOR names the PREVIOUS registry — a different cartório."""
        texto = (
            "MATRÍCULA Nº 1.234\n"
            "IMÓVEL: Casa.\n"
            "REGISTRO ANTERIOR: matrícula 9 do 3º Registro de Imóveis de Osasco.\n"
        )
        assert find_cartorio(texto) == (None, "nenhuma", None)

    def test_ridigital_furniture_is_not_a_cartorio(self):
        texto = (
            "Documento gerado oficialmente pelo Registro de Imóveis via www.ridigital.org.br\n"
            "IMÓVEL: Casa.\n"
        )
        assert find_cartorio(texto)[0] is None

    def test_two_different_headings_is_absence(self):
        texto = (
            "1º Registro de Imóveis de Barueri\n"
            "2º Registro de Imóveis de Barueri\n"
            "IMÓVEL: Casa.\n"
        )
        assert find_cartorio(texto) == (None, "nenhuma", None)

    def test_repeated_identical_heading_still_agrees(self):
        texto = (
            "CARTÓRIO DE REGISTRO DE IMÓVEIS DE CARAPICUÍBA\n"
            "Cartório de Registro de Imóveis de Carapicuíba\n"
            "IMÓVEL: Casa.\n"
        )
        valor, conf, _ = find_cartorio(texto)
        assert conf == "alta"
        assert valor == "CARTÓRIO DE REGISTRO DE IMÓVEIS DE CARAPICUÍBA"

    def test_legacy_markup_does_not_hide_the_heading_end_or_leak_into_value(self):
        texto = (
            "**1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA**\n"
            "**IMÓVEL:** Casa.\n"
            "R-1/10 - venda do Registro de Imóveis de Itu.\n"
        )
        valor, conf, _ = find_cartorio(texto)
        assert valor == "1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA"
        assert conf == "alta"

    def test_empty(self):
        assert find_cartorio("") == (None, "nenhuma", None)


class TestFindInscricaoMunicipal:
    def test_contribuinte_number(self):
        assert find_inscricao_municipal("Contribuinte nº 123.456.7-8.") == (
            "123.456.7-8",
            "alta",
        )

    def test_long_dotted_inscricao(self):
        assert find_inscricao_municipal(
            "Inscrição cadastral 23222.44.55.0100.00.000"
        ) == ("23222.44.55.0100.00.000", "alta")

    def test_area_maior_is_only_a_suggestion(self):
        valor, conf = find_inscricao_municipal(
            "Contribuinte 012.345.0067-1, em área maior."
        )
        assert (valor, conf) == ("012.345.0067-1", "baixa")

    def test_several_numbers_is_baixa_first_wins(self):
        valor, conf = find_inscricao_municipal(
            "Contribuintes 111.222.333-4 e 555.666.777-8."
        )
        assert (valor, conf) == ("111.222.333-4", "baixa")

    def test_short_numbers_are_not_an_inscricao(self):
        assert find_inscricao_municipal("Lote 7, quadra 12.") == (None, "nenhuma")

    def test_nao_consta(self):
        assert find_inscricao_municipal("Não consta.") == (None, "nenhuma")
