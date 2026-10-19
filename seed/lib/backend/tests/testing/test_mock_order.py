"""`.order()` sorts like PostgREST: stable, NULLs largest by default, keys compose."""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient


def _db(rows):
    db = MockSupabaseClient()
    db.set_table_data("t", rows)
    return db


def _ids(q):
    return [r["id"] for r in q.execute().data]


ROWS = [
    {"id": "a", "k": 2, "g": "x"},
    {"id": "b", "k": None, "g": "x"},
    {"id": "c", "k": 1, "g": "y"},
    {"id": "d", "k": 2, "g": "y"},
    {"id": "e", "k": None, "g": "y"},
]


def test_asc_default_nulls_last_stable():
    assert _ids(_db(ROWS).table("t").select("*").order("k")) == ["c", "a", "d", "b", "e"]


def test_desc_default_nulls_first_stable():
    assert _ids(_db(ROWS).table("t").select("*").order("k", desc=True)) == ["b", "e", "a", "d", "c"]


def test_nullsfirst_override():
    assert _ids(_db(ROWS).table("t").select("*").order("k", nullsfirst=True)) == ["b", "e", "c", "a", "d"]
    assert _ids(_db(ROWS).table("t").select("*").order("k", desc=True, nullsfirst=False)) == ["a", "d", "c", "b", "e"]


def test_multiple_orders_compose_first_is_primary():
    q = _db(ROWS).table("t").select("*").order("g").order("k", desc=True)
    assert _ids(q) == ["b", "a", "e", "d", "c"]


def test_order_applies_before_limit_and_single():
    assert _ids(_db(ROWS).table("t").select("*").order("k").limit(2)) == ["c", "a"]
    row = _db(ROWS).table("t").select("*").order("k", desc=True).limit(1).execute().data
    assert row[0]["id"] == "b"


def test_order_respects_filters():
    q = _db(ROWS).table("t").select("*").eq("g", "y").order("k", desc=True)
    assert _ids(q) == ["e", "d", "c"]
