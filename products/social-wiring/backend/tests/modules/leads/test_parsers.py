"""Parser unit tests — date / código / contato / retorno-prefix. Every
fixture is SYNTHESIZED (no real workbook rows — never commit real client
data), covering the shapes + edge cases documented in
``leads-module-PROJECT.md`` §3.
"""
from __future__ import annotations

from datetime import date, datetime

from app.modules.leads.importer.parsers import (
    looks_like_date_value,
    parse_codigo,
    parse_contato,
    parse_date_cell,
    strip_retorno_prefix,
)


class TestParseDateCell:
    def test_datetime_object(self):
        assert parse_date_cell(datetime(2026, 7, 1)) == date(2026, 7, 1)

    def test_date_object(self):
        assert parse_date_cell(date(2026, 7, 1)) == date(2026, 7, 1)

    def test_dd_mm_yy_string(self):
        # ABRIL_24-style: "01.04.24" -> 2024-04-01
        assert parse_date_cell("01.04.24") == date(2024, 4, 1)

    def test_dd_mm_yyyy_string(self):
        assert parse_date_cell("19.03.2024") == date(2024, 3, 19)

    def test_excel_serial_float(self):
        # Standard Excel epoch (date(1899,12,30)); cross-checked against
        # the well-known reference point serial 45658 == 2025-01-01.
        assert parse_date_cell(45658.0) == date(2025, 1, 1)

    def test_unparseable_string_returns_none(self):
        assert parse_date_cell("not a date") is None

    def test_invalid_calendar_date_returns_none(self):
        # 31.02.24 — February never has 31 days.
        assert parse_date_cell("31.02.24") is None

    def test_none_returns_none(self):
        assert parse_date_cell(None) is None

    def test_out_of_range_serial_returns_none(self):
        assert parse_date_cell(1.0) is None


class TestLooksLikeDateValue:
    def test_datetime(self):
        assert looks_like_date_value(datetime(2026, 7, 1)) is True

    def test_dd_mm_yy_string(self):
        assert looks_like_date_value("01.04.24") is True

    def test_plausible_serial(self):
        assert looks_like_date_value(45658.0) is True

    def test_header_text_is_not_date_like(self):
        assert looks_like_date_value("DATA") is False

    def test_none_is_not_date_like(self):
        assert looks_like_date_value(None) is False


class TestParseCodigo:
    def test_space_separated_no_regiao(self):
        assert parse_codigo("ONE10180 Jardim Ester ") == ("ONE10180", "Jardim Ester", None)

    def test_dash_separated_with_regiao(self):
        assert parse_codigo("One9922 - Nativo Clube - Km 29") == (
            "One9922",
            "Nativo Clube",
            "Km 29",
        )

    def test_space_before_dash_before_regiao(self):
        assert parse_codigo("ONE9622 Bosque dos Manacás - Km 21") == (
            "ONE9622",
            "Bosque dos Manacás",
            "Km 21",
        )

    def test_exclusividade_prefix_stripped(self):
        assert parse_codigo("EXCLUSIVIDADE ONE8868 Bosque dos Manacás - Km 21 ") == (
            "ONE8868",
            "Bosque dos Manacás",
            "Km 21",
        )

    def test_locacao_prefix_stripped(self):
        codigo, emp, reg = parse_codigo("LOCAÇÃO ONE1234 Some Place")
        assert codigo == "ONE1234"
        assert emp == "Some Place"

    def test_lowercase_a_prefix(self):
        codigo, _, _ = parse_codigo("a3282 Pousada dos Bandeirantes - Km 23")
        assert codigo == "a3282"

    def test_ca_prefix(self):
        codigo, emp, _ = parse_codigo("CA4350 - SÃO PAULOII")
        assert codigo == "CA4350"
        assert emp == "SÃO PAULOII"

    def test_bare_codigo_no_rest(self):
        assert parse_codigo("ONE7196") == ("ONE7196", None, None)

    def test_unparseable_returns_all_none(self):
        assert parse_codigo("INTERESSE NA REGIÃO") == (None, None, None)

    def test_none_returns_all_none(self):
        assert parse_codigo(None) == (None, None, None)

    def test_composite_codigo_keeps_first_token(self):
        codigo, emp, reg = parse_codigo(
            "One7326 - Rolleboise - Km 22 - Ca1003 - Miolo Granja Viana - Km 23"
        )
        assert codigo == "One7326"
        assert emp == "Rolleboise"
        assert reg  # non-empty best-effort remainder, never silently dropped


class TestParseContato:
    def test_phone_with_dots_and_spaces(self):
        norm, tipo = parse_contato(" 11 99874.5536")
        assert tipo == "telefone"
        assert norm == "11998745536"

    def test_email(self):
        norm, tipo = parse_contato("gilbertospinelli@gmail.com")
        assert tipo == "email"
        assert norm == "gilbertospinelli@gmail.com"

    def test_dash_formatted_phone(self):
        norm, tipo = parse_contato("11-99937.2647")
        assert tipo == "telefone"
        assert norm == "11999372647"

    def test_blank_is_desconhecido(self):
        assert parse_contato("") == (None, "desconhecido")

    def test_none_is_desconhecido(self):
        assert parse_contato(None) == (None, "desconhecido")

    def test_short_digit_string_is_desconhecido(self):
        # Fewer than 8 digits — not a plausible phone number.
        assert parse_contato("1234") == (None, "desconhecido")


class TestStripRetornoPrefix:
    def test_retorno_prefix_stripped(self):
        name, is_retorno = strip_retorno_prefix("Retorno Paula ")
        assert name == "Paula"
        assert is_retorno is True

    def test_uppercase_retorno_prefix(self):
        name, is_retorno = strip_retorno_prefix("RETORNO LUZENI")
        assert name == "LUZENI"
        assert is_retorno is True

    def test_no_prefix_passthrough(self):
        name, is_retorno = strip_retorno_prefix("Juliana")
        assert name == "Juliana"
        assert is_retorno is False

    def test_none_passthrough(self):
        assert strip_retorno_prefix(None) == (None, False)

    def test_retorno_with_colon(self):
        name, is_retorno = strip_retorno_prefix("Retorno: Marisa Bregues")
        assert name == "Marisa Bregues"
        assert is_retorno is True
