"""Shape-detector unit tests — synthetic rows mimicking the 3 shapes the
detector empirically resolves the 29 real sheets to (see
``importer/shape_detector.py``'s module docstring for why this is 3, not
the "5 shapes" impression in the brief: several sheets differ only in
header-row TEXT, which this detector never reads)."""
from __future__ import annotations

from datetime import date

from app.modules.leads.importer.shape_detector import (
    detect_shape,
    is_blank,
    is_header_like,
    is_phone_or_email,
)


def _row(*values, width=9):
    padded = list(values) + [None] * (width - len(values))
    return tuple(padded)


class TestRowClassification:
    def test_header_row_data_literal(self):
        assert is_header_like(("DATA", "CODIGO", "ORIGEM")) is True

    def test_header_row_codigo_literal(self):
        assert is_header_like(("Data ", "CODIGO", None)) is True

    def test_data_row_is_not_header_like(self):
        row = _row(date(2026, 7, 1), "ONE1234 Foo", "ZAP", "NOVO", "Cliente", "11999998888")
        assert is_header_like(row) is False

    def test_blank_row(self):
        assert is_blank(_row()) is True

    def test_non_blank_row(self):
        assert is_blank(_row(date(2026, 7, 1))) is False

    def test_phone_like(self):
        assert is_phone_or_email(" 11 99874.5536") is True

    def test_email_like(self):
        assert is_phone_or_email("a@b.com") is True

    def test_short_string_not_phone(self):
        assert is_phone_or_email("ZAP") is False

    def test_non_string_not_phone(self):
        assert is_phone_or_email(date(2026, 7, 1)) is False


class TestDetectShape:
    def test_shape_with_novo_retorno_and_tier(self):
        # JULHO_26-style: date, codigo, origem, NOVO/RETORNO, cliente,
        # contato, corretor, tier, obs.
        rows = [
            _row(date(2026, 7, 1), "ONE1 X", "SENSEYS", "NOVO", "Alice", "11999998888", "RENATA", "SIMPLES", "obs")
            for _ in range(10)
        ]
        shape = detect_shape(rows)
        assert shape.novo_retorno_idx == 3
        assert shape.cliente_idx == 4
        assert shape.contato_idx == 5
        assert shape.corretor_idx == 6
        assert shape.tier_idx == 7

    def test_shape_without_novo_retorno_with_tier(self):
        # JAN_2026/DEZEMBRO_2025-style: date, codigo, origem, cliente,
        # contato, corretor, tier, obs.
        rows = [
            _row(date(2026, 1, 2), "ONE1 X", "SENSEYS", "Alice", "11999998888", "CINDY", "SIMPLES", "obs")
            for _ in range(10)
        ]
        shape = detect_shape(rows)
        assert shape.novo_retorno_idx is None
        assert shape.cliente_idx == 3
        assert shape.contato_idx == 4
        assert shape.corretor_idx == 5
        assert shape.tier_idx == 6

    def test_shape_without_novo_retorno_without_tier(self):
        # 2024-era sheets: date, codigo, origem, cliente, contato,
        # corretor — no tier column at all.
        rows = [
            _row(date(2024, 4, 1), "ONE1", "SITE", "Luana", "11994177427", "PRISCILA")
            for _ in range(10)
        ]
        shape = detect_shape(rows)
        assert shape.novo_retorno_idx is None
        assert shape.cliente_idx == 3
        assert shape.contato_idx == 4
        assert shape.corretor_idx == 5
        assert shape.tier_idx is None

    def test_rare_second_contact_column_does_not_win(self):
        # The ABRIL_24 anomaly: a handful of rows carry a SECOND phone
        # further right (col 8) — must not outrank the real, high-volume
        # contato column at col 4 (this is exactly the count-vs-fraction
        # bug the detector's docstring describes finding).
        rows = [
            _row(date(2024, 4, 1), "ONE1", "SITE", "Luana", "11994177427", "PRISCILA")
            for _ in range(75)
        ]
        rows += [
            _row(
                date(2024, 4, 1), "ONE2", "OLX", "Daniel", "11997726549", "WILSON",
                None, "Second", "11991567513",
            )
            for _ in range(5)
        ]
        shape = detect_shape(rows)
        assert shape.contato_idx == 4
