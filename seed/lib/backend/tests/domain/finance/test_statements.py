"""Statement import: caps BEFORE parsing, sha256 re-import, overlap dedupe, org scope, suggestions."""
from __future__ import annotations

import json

import pytest

from noctusai_lib.domain.finance import statements

from .conftest import mk_account, mk_entry
from .recon_support import ofx1, ofx2, rh  # noqa: F401

COLS = json.dumps({"date": "Data", "description": "Histórico", "amount": "Valor"})
CSV = b"Data;Hist\xc3\xb3rico;Valor\n03/10/2026;PIX;100,00\n"


def test_caps_run_on_the_bytes_before_any_parser(rh):
    acc = mk_account(rh.s)
    # unparseable garbage: if a parser ran we would see 422 extrato_invalido, not the cap errors
    big = rh.upload(acc["id"], "x.ofx", b"x" * (statements.MAX_STATEMENT_BYTES + 1))
    assert big.status_code == 413 and big.json()["error"]["code"] == "extrato_grande_demais"
    many = rh.upload(acc["id"], "x.ofx", b"x\n" * (statements.MAX_STATEMENT_LINES + 1))
    assert many.status_code == 422 and many.json()["error"]["code"] == "extrato_linhas_demais"
    blocks = rh.upload(acc["id"], "x.ofx", b"<STMTTRN>" * (statements.MAX_STATEMENT_LINES + 1))
    assert blocks.json()["error"]["code"] == "extrato_linhas_demais"


def test_import_ofx_and_reimport_is_409_without_leaking_other_accounts(rh):
    a, b = mk_account(rh.s, "A"), mk_account(rh.s, "B")
    data = ofx1(("20261003", "100.00", "F1", "PIX"), ("20261004", "-20.00", "F2", "TARIFA"))
    first = rh.upload(a["id"], "e.ofx", data)
    assert first.status_code == 201 and first.json()["data"]["lines"] == 2
    again = rh.upload(a["id"], "e.ofx", data)
    assert again.status_code == 409 and again.json()["error"]["code"] == "extrato_ja_importado"
    assert b["id"] not in again.text
    # same bytes into ANOTHER account is a different statement
    assert rh.upload(b["id"], "e.ofx", data).status_code == 201


def test_overlapping_statement_skips_known_fitids(rh):
    acc = mk_account(rh.s)
    rh.upload(acc["id"], "1.ofx", ofx1(("20261003", "100.00", "F1", "A")))
    r = rh.upload(acc["id"], "2.ofx", ofx1(("20261003", "100.00", "F1", "A"), ("20261004", "5.00", "F2", "B")))
    d = r.json()["data"]
    assert (d["lines"], d["duplicates_skipped"]) == (1, 1)
    assert len(rh.s.rows("statement_lines")) == 2


def test_csv_requires_column_map_and_stores_duplicate_same_day_lines(rh):
    acc = mk_account(rh.s)
    r = rh.upload(acc["id"], "e.csv", CSV)
    assert r.status_code == 422 and r.json()["error"]["code"] == "mapa_de_colunas_obrigatorio"
    dup = b"Data;Hist\xc3\xb3rico;Valor\n03/10/2026;CAFE;-5,00\n03/10/2026;CAFE;-5,00\n"
    ok = rh.upload(acc["id"], "e.csv", dup, column_map=COLS)
    assert ok.status_code == 201 and ok.json()["data"]["lines"] == 2


def test_bad_column_map_json_is_422(rh):
    acc = mk_account(rh.s)
    r = rh.upload(acc["id"], "e.csv", CSV, column_map="{not json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "mapa_de_colunas_invalido"


def test_account_of_another_org_is_refused(rh):
    foreign = mk_account(rh.s_b, "Outra")
    r = rh.upload(foreign["id"], "e.ofx", ofx1(("20261003", "1.00", "F", "x")))
    assert r.status_code == 422 and r.json()["error"]["code"] == "referencia_invalida"
    assert rh.s_b.rows("statement_lines") == []


def test_xxe_statement_is_refused_and_nothing_is_stored(rh):
    acc = mk_account(rh.s)
    hostile = ofx2(("20261003", "1.00", "F", "x"), doctype='<!DOCTYPE o [<!ENTITY x SYSTEM "file:///etc/passwd">]>')
    r = rh.upload(acc["id"], "e.ofx", hostile)
    assert r.status_code == 422 and rh.s.rows("statement_imports") == []


def test_unknown_format_is_422(rh):
    acc = mk_account(rh.s)
    r = rh.upload(acc["id"], "e.pdf", b"%PDF-1.4 ...")
    assert r.json()["error"]["code"] == "extrato_formato_desconhecido"


@pytest.mark.parametrize("delta, expected", [(0, True), (3, True), (-3, True), (4, False), (-4, False)])
def test_suggestion_window_is_three_days(rh, delta, expected):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    posted = f"202610{10 + delta:02d}"
    r = rh.upload(acc["id"], "e.ofx", ofx1((posted, "100.00", "F1", "PIX")))
    line = rh.s.rows("statement_lines")[0]
    assert (line["suggested_entry_id"] == e["id"]) is expected
    assert line["match_status"] == ("suggested" if expected else "unmatched")
    assert r.json()["data"]["suggested"] == int(expected)


def test_suggestion_needs_same_amount_and_same_direction(rh):
    acc = mk_account(rh.s)
    mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    mk_entry(rh.s, direction="payable", due_date="2026-10-10", amount_cents=7000)
    rh.upload(acc["id"], "e.ofx", ofx1(("20261010", "99.99", "A", "x"), ("20261010", "-100.00", "B", "y"), ("20261010", "70.00", "C", "z")))
    assert all(l["match_status"] == "unmatched" for l in rh.s.rows("statement_lines"))


def test_two_identical_lines_never_share_one_suggestion(rh):
    acc = mk_account(rh.s)
    mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    rh.upload(acc["id"], "e.ofx", ofx1(("20261010", "100.00", "A", "x"), ("20261010", "100.00", "B", "x")))
    assert sorted(l["match_status"] for l in rh.s.rows("statement_lines")) == ["suggested", "unmatched"]


def test_listing_is_org_scoped_and_paginated(rh):
    acc = mk_account(rh.s)
    imp = rh.upload(acc["id"], "e.ofx", ofx1(("20261003", "1.00", "A", "x"), ("20261004", "2.00", "B", "y"))).json()["data"]["import"]
    r = rh.client.get(f"/api/finance/statements/{imp['id']}/lines?page_size=1", headers=rh.staff())
    assert r.status_code == 200 and len(r.json()["data"]) == 1 and r.json()["pagination"]["total"] == 2
    assert rh.client.get(f"/api/finance/statements/{imp['id']}/lines", headers=rh.admin_b).status_code == 404
