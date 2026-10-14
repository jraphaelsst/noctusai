"""CSV statement parsing: caller-supplied column map, debit/credit pairs, positional fitid."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from noctusai_lib.domain.finance.csv_import import CsvColumnMap, parse_csv
from noctusai_lib.domain.finance.errors import FinanceError

ACC = "11111111-2222-3333-4444-555555555555"
CSV = (
    "Data;Histórico;Valor\n"
    "03/10/2026;PIX RECEBIDO;1.500,00\n"
    "05/10/2026;CAFE;-12,50\n"
    "05/10/2026;CAFE;-12,50\n"
).encode("utf-8")


def cmap(**over):
    return CsvColumnMap(date="Data", description="Histórico", amount="Valor", **over)


def test_named_columns_and_brazilian_numbers():
    st = parse_csv(CSV, cmap(), account_id=ACC)
    assert [(l.posted_on, l.amount_cents) for l in st.lines] == [
        (date(2026, 10, 3), 150000), (date(2026, 10, 5), -1250), (date(2026, 10, 5), -1250)]


def test_duplicate_same_day_lines_get_distinct_stable_fitids():
    a = parse_csv(CSV, cmap(), account_id=ACC)
    b = parse_csv(CSV, cmap(), account_id=ACC)
    assert len({l.fitid for l in a.lines}) == 3
    assert [l.fitid for l in a.lines] == [l.fitid for l in b.lines]


def test_fitid_depends_on_the_account():
    assert parse_csv(CSV, cmap(), account_id=ACC).lines[0].fitid != parse_csv(CSV, cmap(), account_id="x").lines[0].fitid


def test_index_columns_no_header_cp1252():
    raw = "03/10/2026,Padaria Pão,\"-1,234.50\"\n".encode("cp1252")
    st = parse_csv(raw, CsvColumnMap(date=0, description=1, amount=2, has_header=False, delimiter=",", decimal="dot"), account_id=ACC)
    assert st.lines[0].amount_cents == -123450 and st.lines[0].description == "Padaria Pão"


def test_debit_credit_pair():
    raw = b"d;h;deb;cred\n01/10/2026;A;10,00;\n02/10/2026;B;;7,00\n"
    st = parse_csv(raw, CsvColumnMap(date="d", description="h", debit="deb", credit="cred"), account_id=ACC)
    assert [l.amount_cents for l in st.lines] == [-1000, 700]


def test_missing_column_is_a_422():
    with pytest.raises(FinanceError) as e:
        parse_csv(CSV, CsvColumnMap(date="Data", description="Nope", amount="Valor"), account_id=ACC)
    assert e.value.code == "extrato_invalido"


def test_bad_date_names_the_line():
    with pytest.raises(FinanceError) as e:
        parse_csv("Data;Histórico;Valor\n31/02/2026;X;1,00\n".encode(), cmap(), account_id=ACC)
    assert "linha 1" in e.value.message


@pytest.mark.parametrize("kw", [dict(), dict(amount="a", debit="b", credit="c"), dict(debit="b"), dict(typo=1)])
def test_column_map_shape_is_strict(kw):
    with pytest.raises(ValidationError):
        CsvColumnMap(**{"date": "d", "description": "h", **kw})
