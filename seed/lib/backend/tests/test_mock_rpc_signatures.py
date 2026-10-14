"""`MockSupabaseClient.rpc` resolves like PostgREST: by argument NAME against the migration-declared signatures.

Regression: inventory `stock.py` sent `p_org_id` while every function declares `p_org`; the mock ignored argument
names, so every suite was green while every inventory write answered PGRST202 in production.
"""
from __future__ import annotations

import pytest
from postgrest.exceptions import APIError

from noctusai_lib.testing import _schema_cache
from noctusai_lib.testing.migration_parser import parse_function_sql
from noctusai_lib.testing.mocks import MockSupabaseClient

SQL = """
CREATE OR REPLACE FUNCTION rpcx.do_thing(p_org UUID, p_row JSONB, p_note TEXT DEFAULT NULL, OUT x int) RETURNS JSONB
LANGUAGE plpgsql AS $fn$ BEGIN RETURN '{}'::jsonb; END; $fn$;
CREATE FUNCTION rpcx.over(a int) RETURNS int LANGUAGE sql AS 'select 1';
CREATE FUNCTION rpcx.over(a int, b numeric(10,2) = 2) RETURNS int LANGUAGE sql AS 'select 1';
"""


@pytest.fixture
def db():
    prev = _schema_cache.set_functions_for_tests(parse_function_sql(SQL))
    yield MockSupabaseClient(validate_schema=True, schema="rpcx")
    _schema_cache.set_functions_for_tests(prev, merge=False)


def test_parser_splits_params_required_and_overloads():
    sigs = parse_function_sql(SQL)
    assert sigs["rpcx.do_thing"] == [{"params": {"p_org", "p_row", "p_note"}, "required": {"p_org", "p_row"}}]
    assert sorted(sorted(s["required"]) for s in sigs["rpcx.over"]) == [["a"], ["a"]]


def test_declared_names_resolve(db):
    db.rpc("do_thing", {"p_org": "o", "p_row": {}}).execute()
    db.rpc("do_thing", {"p_org": "o", "p_row": {}, "p_note": "n"}).execute()
    db.rpc("over", {"a": 1, "b": 2}).execute()


def test_misnamed_argument_is_pgrst202(db):
    with pytest.raises(APIError) as err:
        db.rpc("do_thing", {"p_org_id": "o", "p_row": {}})
    assert err.value.code == "PGRST202"


def test_missing_required_argument_is_pgrst202(db):
    with pytest.raises(APIError) as err:
        db.rpc("do_thing", {"p_org": "o"})
    assert err.value.code == "PGRST202"


def test_unknown_function_is_pgrst202(db):
    with pytest.raises(APIError) as err:
        db.rpc("no_such_fn", {})
    assert err.value.code == "PGRST202"


def test_function_seeded_by_the_test_without_a_signature_is_judged_on_nothing(db):
    db.set_rpc_data("canned", {"status": "ok"})
    assert db.rpc("canned", {"whatever": 1}).execute().data == {"status": "ok"}


def test_validation_off_keeps_the_lenient_shape():
    MockSupabaseClient(validate_schema=False, schema="rpcx").rpc("anything", {"x": 1})


def test_default_public_mock_resolves_a_product_schema_function_by_bare_name():
    """A mock left on the default `public` stands in for a product's schema-pinned client
    (social-wiring `cs_rebind_roteiro` lives in `social_wiring`) — still judged by names."""
    prev = _schema_cache.set_functions_for_tests(parse_function_sql(SQL))
    try:
        pub = MockSupabaseClient(validate_schema=True)
        pub.rpc("do_thing", {"p_org": "o", "p_row": {}}).execute()
        with pytest.raises(APIError) as err:
            pub.rpc("do_thing", {"p_org_id": "o", "p_row": {}})
        assert err.value.code == "PGRST202"
        with pytest.raises(APIError):
            pub.rpc("no_such_fn", {})
    finally:
        _schema_cache.set_functions_for_tests(prev, merge=False)
