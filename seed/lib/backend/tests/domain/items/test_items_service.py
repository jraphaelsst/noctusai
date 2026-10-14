"""Item + category services: CRUD, SKU uniqueness per org, fiscal normalisation, search, archive, isolation."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.items import ItemsConfig, categories, items
from noctusai_lib.domain.items.errors import ItemsError
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, EAN13, mk_item


def err(exc: pytest.ExceptionInfo) -> tuple[int, str]:
    return exc.value.status_code, exc.value.code


def test_create_applies_defaults_and_canonical_fiscal_forms(s):
    row = items.create_item(s, {
        "sku": "ab-1", "name": "  Parafuso  ", "ncm": "7318.15.00", "cest": "01.001.00",
        "cfop_default": "5.102", "origem": "0", "gtin": EAN13, "cost_cents": 150, "price_cents": 300,
    })
    assert row["sku"] == "AB-1" and row["name"] == "Parafuso"
    assert (row["item_type"], row["unit"], row["is_active"]) == ("goods", "UN", True)
    assert (row["ncm"], row["cest"], row["cfop_default"], row["origem"], row["gtin"]) == ("73181500", "0100100", "5102", 0, EAN13)
    assert items.get_item(s, row["id"])["id"] == row["id"]


@pytest.mark.parametrize("field, value, code", [
    ("ncm", "123", "ncm_invalido"), ("cest", "12", "cest_invalido"), ("cfop_default", "4102", "cfop_invalido"),
    ("origem", 9, "origem_invalida"), ("gtin", "7891000100104", "gtin_invalido"), ("sku", "a b", "sku_invalido"),
])
def test_invalid_fiscal_field_is_422_with_its_code(s, field, value, code):
    with pytest.raises(ItemsError) as e:
        mk_item(s, **{field: value})
    assert err(e) == (422, code) and e.value.details["field"] in (field, "cfop_default", "sku")


def test_unknown_unit_item_type_and_negative_money_refused(s):
    for over in ({"unit": "XX"}, {"item_type": "gadget"}, {"cost_cents": -1}, {"weight_g": -5}):
        with pytest.raises(ItemsError) as e:
            mk_item(s, **over)
        assert e.value.status_code == 422


def test_sku_unique_per_org_case_insensitive_and_scoped_to_org(s, s_b):
    mk_item(s, "dup-1")
    with pytest.raises(ItemsError) as e:
        mk_item(s, "DUP-1")
    assert err(e) == (409, "sku_duplicado")
    mk_item(s_b, "DUP-1")  # another org: unaffected
    other = mk_item(s, "dup-2")
    with pytest.raises(ItemsError) as e:
        items.update_item(s, other["id"], {"sku": "Dup-1"})
    assert err(e) == (409, "sku_duplicado")
    assert items.update_item(s, other["id"], {"sku": "dup-2"})["sku"] == "DUP-2"  # own sku is not a clash


def test_update_patches_only_given_fields_and_clears_nullables(s):
    row = mk_item(s, ncm="73181500", price_cents=500)
    out = items.update_item(s, row["id"], {"name": "Novo", "ncm": None, "price_cents": None})
    assert out["name"] == "Novo" and out["ncm"] is None and out["price_cents"] is None
    stored = items.get_item(s, row["id"])
    assert stored["name"] == "Novo" and stored["ncm"] is None and stored["sku"] == row["sku"]
    assert items.update_item(s, row["id"], {}) == stored


def test_update_refuses_nulling_a_required_field(s):
    row = mk_item(s)
    for field in ("name", "unit", "item_type", "cost_cents", "sku", "is_active"):
        with pytest.raises(ItemsError) as e:
            items.update_item(s, row["id"], {field: None})
        assert err(e) == (422, "campo_obrigatorio")


def test_archive_and_unarchive_are_idempotent_and_filterable(s):
    a, b = mk_item(s, "A"), mk_item(s, "B")
    assert items.set_active(s, a["id"], False)["is_active"] is False
    assert items.set_active(s, a["id"], False)["is_active"] is False
    assert [r["sku"] for r in items.list_items(s, active=True)[0]] == ["B"]
    assert [r["sku"] for r in items.list_items(s, active=False)[0]] == ["A"]
    assert items.set_active(s, a["id"], True)["is_active"] is True
    assert {r["sku"] for r in items.list_items(s)[0]} == {"A", "B"} and b


def test_search_term_can_never_inject_postgrest_syntax():
    from noctusai_lib.domain.items._common import like_term

    assert like_term('ac"me, (x).y%_*\\') == "%ac%me% %x%y%"
    assert like_term("A.B") == "%A%B%"
    assert like_term("  par-1 ") == "%par-1%"
    assert not any(ch in like_term('a"b,c(d)e*f\\g:h') for ch in ',()"*\\:')


def test_filters_and_pagination(s):
    # NOTE: the mock evaluates PostgREST `or()` as match-all, so `q` is proven accepted + bounded here,
    # and the pattern text is pinned by `like_term` above; the eq/in_ filters ARE evaluated.
    mk_item(s, "PAR-1", name="Parafuso sextavado")
    mk_item(s, "POR-1", name="Porca", gtin=EAN13)
    mk_item(s, "SRV-1", name="Instalação", item_type="service", unit="H")
    names = lambda **kw: [r["sku"] for r in items.list_items(s, **kw)[0]]
    assert names(item_type="service") == ["SRV-1"]
    assert sorted(names()) == ["PAR-1", "POR-1", "SRV-1"]
    assert items.list_items(s, q='ac"me, (x).y')[1] <= 3
    rows, total, page, size = items.list_items(s, page=2, page_size=2)
    assert (len(rows), total, page, size) == (1, 3, 2, 2)
    with pytest.raises(ItemsError):
        items.list_items(s, item_type="gadget")


def test_category_filter_includes_descendants(s):
    root = categories.create_category(s, {"name": "Ferragens"})
    child = categories.create_category(s, {"name": "Parafusos", "parent_id": root["id"]})
    mk_item(s, "A", category_id=child["id"])
    mk_item(s, "B", category_id=root["id"])
    mk_item(s, "C")
    assert {r["sku"] for r in items.list_items(s, category_id=root["id"])[0]} == {"A", "B"}
    assert {r["sku"] for r in items.list_items(s, category_id=child["id"])[0]} == {"A"}


def test_category_must_belong_to_the_org(s, s_b):
    foreign = categories.create_category(s_b, {"name": "Alheia"})
    with pytest.raises(ItemsError) as e:
        mk_item(s, category_id=foreign["id"])
    assert err(e) == (422, "referencia_invalida")
    with pytest.raises(NotFoundError):
        items.list_items(s, category_id=foreign["id"])


def test_org_isolation_reads_and_writes(s, s_b):
    row = mk_item(s, "ISO-1")
    with pytest.raises(NotFoundError):
        items.get_item(s_b, row["id"])
    with pytest.raises(NotFoundError):
        items.update_item(s_b, row["id"], {"name": "x"})
    with pytest.raises(NotFoundError):
        items.set_active(s_b, row["id"], False)
    assert items.list_items(s_b)[1] == 0
    assert items.get_item(s, row["id"])["name"] == row["name"]


def test_extra_item_types_are_the_vertical_seam(db):
    vs = type(items)  # noqa: F841 (module handle only)
    from noctusai_lib.domain.items._common import Scope

    scope = Scope(db, ItemsConfig(schema=CFG.schema, extra_item_types=("procedure",)), "o1")
    assert items.create_item(scope, {"sku": "P1", "name": "Consulta", "item_type": "procedure"})["item_type"] == "procedure"
    with pytest.raises(ItemsError):
        items.create_item(Scope(db, CFG, "o1"), {"sku": "P2", "name": "x", "item_type": "procedure"})
    with pytest.raises(ValueError):
        ItemsConfig(schema="x", extra_item_types=("goods",))
    with pytest.raises(ValueError):
        ItemsConfig(schema="x", extra_item_types=("Bad-Type",))


# ── categories ──


def test_category_tree_duplicates_cycles_and_delete_rules(s, s_b):
    root = categories.create_category(s, {"name": "Raiz"})
    kid = categories.create_category(s, {"name": "Filha", "parent_id": root["id"]})
    with pytest.raises(ItemsError) as e:
        categories.create_category(s, {"name": "raiz"})
    assert err(e) == (409, "categoria_duplicada")
    categories.create_category(s, {"name": "Filha"})  # same name, different level
    categories.create_category(s_b, {"name": "Raiz"})  # other org
    with pytest.raises(ItemsError) as e:
        categories.update_category(s, root["id"], {"parent_id": kid["id"]})
    assert err(e) == (422, "categoria_ciclo")
    with pytest.raises(ItemsError) as e:
        categories.delete_category(s, root["id"])
    assert err(e) == (409, "categoria_em_uso")
    mk_item(s, category_id=kid["id"])
    with pytest.raises(ItemsError) as e:
        categories.delete_category(s, kid["id"])
    assert err(e) == (409, "categoria_em_uso")
    assert categories.category_paths(s)[kid["id"]] == "Raiz > Filha"
    empty = categories.create_category(s, {"name": "Vazia"})
    categories.delete_category(s, empty["id"])
    with pytest.raises(NotFoundError):
        categories.get_category(s, empty["id"])
    with pytest.raises(NotFoundError):
        categories.update_category(s_b, root["id"], {"name": "x"})
    renamed = categories.update_category(s, root["id"], {"name": "Raiz 2", "is_active": False})
    assert renamed["name"] == "Raiz 2" and renamed["is_active"] is False
