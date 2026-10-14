"""CSV export / import: injection safety, exact money, validate-everything-first, update semantics, round trip."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.items import categories, csv_io, items
from noctusai_lib.domain.items.errors import ItemsError

from .conftest import EAN13, mk_item


def imp(s, text: str, **kw):
    return csv_io.import_items_csv(s, text.encode("utf-8"), **kw)


def rows(s):
    return {r["sku"]: r for r in items.list_items(s, page_size=100)[0]}


@pytest.mark.parametrize("raw, cents", [("12,50", 1250), ("1.234,56", 123456), ("1234.56", 123456), ("0", 0), ("R$ 3,00", 300), ("7", 700)])
def test_parse_money_is_exact(raw, cents):
    assert csv_io.parse_money_cents(raw) == cents


@pytest.mark.parametrize("raw", ["-1", "1.234", "abc", "1,234", "nan", "inf", ""])
def test_parse_money_refuses_ambiguous_or_bad(raw):
    with pytest.raises(ValueError):
        csv_io.parse_money_cents(raw)


def test_csv_safe_neutralises_formula_leads():
    assert csv_io.csv_safe("=1+1") == "'=1+1" and csv_io.csv_safe("@x") == "'@x" and csv_io.csv_safe("ok") == "ok"
    assert csv_io.csv_safe(None) == ""


def test_import_creates_with_defaults_and_canonical_forms(s):
    out = imp(s, f"sku;name;unit;ncm;gtin;cost;origem\nab-1;Alfa;kg;7318.15.00;{EAN13};1.234,56;2\n")
    assert out == {"created": 1, "updated": 0, "dry_run": False}
    r = rows(s)["AB-1"]
    assert (r["unit"], r["ncm"], r["gtin"], r["cost_cents"], r["origem"], r["item_type"], r["is_active"]) == ("KG", "73181500", EAN13, 123456, 2, "goods", True)


def test_import_is_all_or_nothing_and_reports_every_problem(s):
    mk_item(s, "EXIST")
    with pytest.raises(ItemsError) as e:
        imp(s, "sku,name,ncm,cost\nOK-1,Bom,,1\nBAD 1,x,,\nOK-2,Ruim,123,\nEXIST,Dup,,\nOK-1,Repetido,,\nOK-3,,,\n")
    err = e.value
    assert (err.status_code, err.code) == (422, "importacao_invalida")
    found = {(x["line"], x["field"], x["code"]) for x in err.details["errors"]}
    assert found == {
        (3, "sku", "sku_invalido"), (4, "ncm", "ncm_invalido"), (5, "sku", "sku_duplicado"),
        (6, "sku", "sku_duplicado"), (7, "name", "campo_obrigatorio"),
    }
    assert set(rows(s)) == {"EXIST"}  # nothing from the file was written, not even the valid rows


def test_import_dry_run_writes_nothing(s):
    assert imp(s, "sku,name\nA,Alfa\nB,Beta\n", dry_run=True) == {"created": 2, "updated": 0, "dry_run": True}
    assert rows(s) == {}


def test_import_update_existing_blank_cell_keeps_value(s):
    mk_item(s, "U-1", name="Antigo", ncm="73181500", cost_cents=500)
    with pytest.raises(ItemsError):
        imp(s, "sku,name\nU-1,Novo\n")  # existing SKU without update_existing is a row error
    out = imp(s, "sku,name,ncm,cost,price\nU-1,Novo,,,9.90\nN-1,Novo item,,,\n", update_existing=True)
    assert out == {"created": 1, "updated": 1, "dry_run": False}
    r = rows(s)["U-1"]
    assert (r["name"], r["ncm"], r["cost_cents"], r["price_cents"]) == ("Novo", "73181500", 500, 990)


def test_import_header_rules(s):
    for text, fragment in (
        ("sku\nA\n", "obrigatórias"), ("sku,name,color\nA,x,red\n", "desconhecidas"), ("sku,name,sku\nA,x,A\n", "repete"), ("", "vazio"),
    ):
        with pytest.raises(ItemsError) as e:
            imp(s, text)
        assert e.value.status_code == 422 and fragment in e.value.message
    with pytest.raises(ItemsError) as e:
        csv_io.import_items_csv(s, b"x" * (csv_io.MAX_IMPORT_BYTES + 1))
    assert e.value.status_code == 413


def test_import_category_by_path_must_exist(s, s_b):
    root = categories.create_category(s, {"name": "Ferragens"})
    kid = categories.create_category(s, {"name": "Parafusos", "parent_id": root["id"]})
    categories.create_category(s_b, {"name": "Alheia"})
    imp(s, 'sku,name,category\nA,Alfa,"ferragens >  Parafusos"\n')
    assert rows(s)["A"]["category_id"] == kid["id"]
    for path in ("Inexistente", "Alheia"):
        with pytest.raises(ItemsError) as e:
            imp(s, f"sku,name,category\nB,Beta,{path}\n")
        assert e.value.details["errors"][0]["code"] == "categoria_inexistente"


def test_import_row_cap(s):
    body = "sku,name\n" + "".join(f"S{i},n\n" for i in range(csv_io.MAX_IMPORT_ROWS + 1))
    with pytest.raises(ItemsError) as e:
        imp(s, body)
    assert "limite" in e.value.message and rows(s) == {}


def test_export_is_bom_crlf_exact_money_and_injection_safe(s):
    root = categories.create_category(s, {"name": "Raiz"})
    mk_item(s, "E-1", name="=cmd|' /C calc'!A0", cost_cents=123456, price_cents=1, gtin=EAN13, category_id=root["id"], ncm="73181500")
    raw = csv_io.items_csv(s)
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    lines = text.split("\r\n")
    assert lines[0] == ",".join(csv_io.ITEM_CSV_COLUMNS)
    assert "'=cmd" in lines[1] and "1234.56" in lines[1] and "0.01" in lines[1] and ",Raiz," in lines[1] and "73181500" in lines[1]


def test_export_refuses_instead_of_truncating(s):
    mk_item(s, "A")
    mk_item(s, "B")
    with pytest.raises(ItemsError) as e:
        csv_io.items_csv(s, max_rows=1)
    assert (e.value.status_code, e.value.code) == (422, "exportacao_grande_demais")


def test_export_walks_every_page(s):
    for i in range(205):
        items.create_item(s, {"sku": f"P{i:03d}", "name": f"Item {i}"})
    text = csv_io.items_csv(s).decode("utf-8-sig")
    assert len([l for l in text.split("\r\n") if l]) == 206


def test_round_trip_export_then_import_reproduces_the_catalog(s, s_b):
    root = categories.create_category(s, {"name": "Raiz"})
    mk_item(s, "R-1", name="Um, com vírgula", description="linha\ncom quebra", unit="CX", item_type="asset",
            category_id=root["id"], ncm="73181500", cest="0100100", cfop_default="5102", origem=1, gtin=EAN13,
            cost_cents=1999, price_cents=2999, weight_g=10, length_mm=1, width_mm=2, height_mm=3, is_active=False)
    exported = csv_io.items_csv(s)
    # same file into a fresh org: its category does not exist there, so create the same tree first.
    categories.create_category(s_b, {"name": "Raiz"})
    assert csv_io.import_items_csv(s_b, exported) == {"created": 1, "updated": 0, "dry_run": False}
    a, b = rows(s)["R-1"], rows(s_b)["R-1"]
    skip = {"id", "org_id", "category_id", "created_at", "updated_at"}
    assert {k: v for k, v in a.items() if k not in skip} == {k: v for k, v in b.items() if k not in skip}
