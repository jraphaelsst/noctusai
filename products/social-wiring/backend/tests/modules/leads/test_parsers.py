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
        # Upper-cased since migration 062 — see TestParseCodigoIsCanonical.
        assert parse_codigo("One9922 - Nativo Clube - Km 29") == (
            "ONE9922",
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
        # A one-letter prefix is still matched, and now canonicalised.
        codigo, _, _ = parse_codigo("a3282 Pousada dos Bandeirantes - Km 23")
        assert codigo == "A3282"

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
        assert codigo == "ONE7326"
        assert emp == "Rolleboise"
        assert reg  # non-empty best-effort remainder, never silently dropped


class TestParseContato:
    """`contato_norm` is CANONICAL E.164 since migration 037.

    It used to be bare digits (`11998745536`), which never compared equal to
    the same person's `+5511998745536` arriving from a Meta campaign — the
    whole reason the platform now has one phone format.
    """

    def test_phone_with_dots_and_spaces(self):
        norm, tipo = parse_contato(" 11 99874.5536")
        assert tipo == "telefone"
        assert norm == "+5511998745536"

    def test_email(self):
        norm, tipo = parse_contato("gilbertospinelli@gmail.com")
        assert tipo == "email"
        assert norm == "gilbertospinelli@gmail.com"

    def test_dash_formatted_phone(self):
        norm, tipo = parse_contato("11-99937.2647")
        assert tipo == "telefone"
        assert norm == "+5511999372647"

    def test_already_canonical_is_a_fixed_point(self):
        # A re-import of a sheet the importer already normalized must not
        # mutate the value a second time.
        assert parse_contato("+5511999372647") == ("+5511999372647", "telefone")

    def test_campaign_shape_matches_sheet_shape(self):
        # THE point of the change: two intake paths, one string.
        from_sheet, _ = parse_contato("11-99937.2647")
        from_campaign, _ = parse_contato("+5511999372647")
        assert from_sheet == from_campaign

    def test_unparseable_phone_keeps_its_type_but_has_no_norm(self):
        # 8-digit legacy mobile: `normalize_phone` refuses to invent the ninth
        # digit, so nothing may key on it — but it IS a phone, and typing it
        # `desconhecido` would hide it from the filter a human would use to
        # find and fix it. The original survives in `ParsedRow.contato`.
        assert parse_contato("11 9999-9999") == (None, "telefone")

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


class TestParseCodigoIsCanonical:
    """Pins the migration-062 contract: the parser upper-cases.

    `_CODIGO_RE` matches `[A-Za-z]`, and `parse_codigo` used to return the
    match verbatim. `One10107` was therefore stored as typed and never
    joined `imoveis.codigo` (`ONE10107`) — 6057 rows on the live tenant
    carried a lowercase character and 2406 leads silently failed to
    resolve.

    The Python side and `social_wiring.canonicalize_lead_codigo_imovel()`
    MUST agree: the trigger is BEFORE INSERT, so a disagreement means the
    API echoes one value while the DB holds another. That is the same
    contract `parse_contato` keeps with `canonicalize_lead_contato()`.
    """

    def test_lowercase_prefix_is_upper_cased(self):
        codigo, _, _ = parse_codigo("one10107")
        assert codigo == "ONE10107"

    def test_mixed_case_prefix_is_upper_cased(self):
        codigo, _, _ = parse_codigo("One10107")
        assert codigo == "ONE10107"

    def test_already_upper_is_unchanged(self):
        codigo, _, _ = parse_codigo("ONE10107")
        assert codigo == "ONE10107"

    def test_case_variants_converge_on_one_value(self):
        """The whole point: every spelling collapses to one join key."""
        variants = ["ONE10107", "One10107", "one10107", "oNe10107"]
        assert {parse_codigo(v)[0] for v in variants} == {"ONE10107"}

    def test_two_letter_prefix_converges(self):
        assert {parse_codigo(v)[0] for v in ["CA0190", "Ca0190", "ca0190"]} == {"CA0190"}

    def test_canonicalisation_does_not_disturb_the_remainder(self):
        """Only the código is folded — the free text keeps its own case."""
        codigo, emp, reg = parse_codigo("one9922 - Nativo Clube - Km 29")
        assert codigo == "ONE9922"
        assert emp == "Nativo Clube"
        assert reg == "Km 29"

    def test_matches_what_the_sql_trigger_would_produce(self):
        """`upper(btrim(...))` is the trigger body; mirror it exactly."""
        for raw in ["one10107", "One10107", "ONE10107", "cA4350"]:
            codigo, _, _ = parse_codigo(raw)
            assert codigo == raw.strip().upper()
