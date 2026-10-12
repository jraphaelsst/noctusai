"""`datas_ptbr` — the shared printed-date reader (normalized text in)."""
from datetime import date

from noctusai_lib.integrations.documents.datas_ptbr import MESES, data_valida, datas_no_texto


def test_both_shapes_in_position_order():
    norm = "EM 1O DE MARCO DE 2026 E DEPOIS 05/04/2026, POR FIM 06.04.2026"
    assert [d for _i, _f, d in datas_no_texto(norm)] == [
        date(2026, 3, 1), date(2026, 4, 5), date(2026, 4, 6),
    ]


def test_impossible_day_is_skipped_not_repaired():
    assert datas_no_texto("31/02/2026 E 30 DE FEVEREIRO DE 2026") == []
    assert data_valida(2026, 2, 31) is None


def test_window_is_respected():
    norm = "01/01/2026 X 02/02/2026"
    assert [d for _i, _f, d in datas_no_texto(norm, desde=11)] == [date(2026, 2, 2)]


def test_month_table_is_complete():
    assert sorted(MESES.values()) == list(range(1, 13))
