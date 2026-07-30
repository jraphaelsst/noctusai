"""Canonical phone format — the contract every product now depends on.

The interesting cases here are the REFUSALS. Anyone can normalize
"(11) 99457-3387"; the value of this module is that it declines to invent
a ninth digit or to accept a 7-digit subscriber, because both would
produce a number that looks right in a table and can never be dialed.
"""
from __future__ import annotations

import pytest

from noctusai_lib.primitives.phone import (
    format_phone,
    is_valid_phone,
    normalize_phone,
    phone_digits,
)

CANONICAL = "+5511994573387"


class TestNormalizeEveryObservedSpelling:
    """Each of these is a real shape found in the live DB or in a product's
    intake path on 2026-07-30. They MUST all collapse to one string."""

    @pytest.mark.parametrize(
        "raw",
        [
            "+5511994573387",   # Meta Lead-Ads (already canonical)
            "5511994573387",    # WAHA chat id, suffix stripped
            "11994573387",      # workbook import, digits-only
            "11 99457.3387",    # workbook import, as stored today
            "(11) 99457-3387",  # ERP form input
            "+55 11 99457-3387",
            "011994573387",     # long-distance trunk prefix
            "  11994573387  ",
        ],
    )
    def test_collapses_to_canonical(self, raw: str) -> None:
        assert normalize_phone(raw) == CANONICAL

    def test_landline_eight_digit_subscriber(self) -> None:
        assert normalize_phone("(11) 3216-5498") == "+551132165498"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("11995735128.0", "+5511995735128"),   # live row, Excel float artifact
            ("11995735128.00", "+5511995735128"),
            ("+5511995735128.0", "+5511995735128"),
        ],
    )
    def test_excel_float_suffix_is_stripped(self, raw: str, expected: str) -> None:
        # Excel reads the phone column as a number and stringifies it back with
        # a fractional part. 547 live rows landed that way; the ".0" is a
        # spreadsheet artifact, not a digit.
        assert normalize_phone(raw) == expected

    def test_area_code_55_is_not_mistaken_for_the_country_code(self) -> None:
        # DDD 55 is Santa Maria/RS. "5532165498" is a NATIONAL number, not
        # a country-coded one — reading the leading "55" as Brazil would
        # leave "32165498" behind, which is not a valid national number, so
        # the shape test rejects that reading and keeps the whole string.
        assert normalize_phone("5532165498") == "+555532165498"


class TestRefusesRatherThanGuesses:
    @pytest.mark.parametrize(
        "raw",
        [
            "+55115072510",   # 7-digit subscriber — live malformed row
            "1199457",        # too short
            "119999999",      # 9-digit legacy mobile missing the 9th digit
            "não informado",
            "",
            "   ",
            None,
            "0",
        ],
    )
    def test_returns_none(self, raw: str | None) -> None:
        assert normalize_phone(raw) is None
        assert is_valid_phone(raw) is False

    def test_float_suffix_does_not_rescue_an_invalid_number(self) -> None:
        # The strip is only ever accepted when what remains is VALID. An
        # 8-digit legacy mobile with a float suffix is still an 8-digit legacy
        # mobile, and must not be rescued into a plausible-looking wrong one.
        assert normalize_phone("11 9793.0") is None

    def test_a_separator_dot_is_not_a_float_suffix(self) -> None:
        # "11 99457.3387" uses the dot as a SEPARATOR — the digits already
        # form a valid number, so the first reading wins and the second never
        # runs.
        assert normalize_phone("11 99457.3387") == CANONICAL

    def test_never_prefixes_a_nine_onto_a_legacy_mobile(self) -> None:
        # São Paulo's 2012 migration added a 9th digit. Deciding WHICH
        # 8-digit numbers were mobiles is a guess; a wrong guess silently
        # writes a stranger's number into a customer record.
        assert normalize_phone("11 9999-9999") is None


class TestInternationalPassThrough:
    def test_explicit_plus_non_brazilian_is_trusted(self) -> None:
        assert normalize_phone("+14155552671") == "+14155552671"

    def test_explicit_plus_brazilian_is_still_shape_checked(self) -> None:
        # The "+" asserts international, but a +55 claim is one we CAN
        # verify, so a malformed Brazilian number is refused even with it.
        assert normalize_phone("+5511507251") is None

    def test_beyond_e164_envelope_is_refused(self) -> None:
        assert normalize_phone("+1234567890123456") is None  # 16 digits


class TestWhatsAppSeam:
    def test_phone_digits_drops_the_plus(self) -> None:
        assert phone_digits("(11) 99457-3387") == "5511994573387"

    def test_chat_id_composition(self) -> None:
        assert f"{phone_digits('11994573387')}@c.us" == "5511994573387@c.us"

    def test_junk_cannot_become_a_chat_id(self) -> None:
        assert phone_digits("não informado") is None


class TestFormatIsTheDisplaySeam:
    def test_valid_renders_canonical(self) -> None:
        assert format_phone("11 99457.3387") == CANONICAL

    def test_malformed_is_shown_not_hidden(self) -> None:
        # A number the user can see is wrong is fixable; a blank field
        # hides that we hold bad data.
        assert format_phone("+55115072510") == "+55115072510"

    def test_explicit_fallback_wins_for_malformed(self) -> None:
        assert format_phone("lixo", fallback="—") == "—"

    def test_empty_stays_empty(self) -> None:
        assert format_phone(None) is None
        assert format_phone("   ") is None


class TestIdempotence:
    """A row normalized by the backfill and then re-normalized on the next
    write must not drift — otherwise every save mutates the record."""

    @pytest.mark.parametrize("raw", ["11994573387", "+5511994573387", "(11) 3216-5498"])
    def test_normalize_is_a_fixed_point(self, raw: str) -> None:
        once = normalize_phone(raw)
        assert once is not None
        assert normalize_phone(once) == once
