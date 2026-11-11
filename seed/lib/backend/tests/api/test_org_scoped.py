"""OrgScopedClient: every query is bound to one org; cross-org writes and foreign references are refused."""
from __future__ import annotations

import pytest

from noctusai_lib.api.org_scoped import ForeignReferenceError, OrgScopedClient, OrgScopeViolation
from noctusai_lib.testing import MockSupabaseClient

ORG_A = "00000000-0000-4000-8000-00000000000a"
ORG_B = "00000000-0000-4000-8000-00000000000b"


def _mock() -> MockSupabaseClient:
    m = MockSupabaseClient(validate_schema=False, schema="t")
    m.set_table_data("things", [
        {"id": "1", "org_id": ORG_A, "name": "a1"},
        {"id": "2", "org_id": ORG_B, "name": "b1"},
    ])
    m.set_table_data("parents", [{"id": "pa", "org_id": ORG_A}, {"id": "pb", "org_id": ORG_B}])
    return m


def _client(m=None, org=ORG_A) -> OrgScopedClient:
    return OrgScopedClient(m or _mock(), org, foreign_keys={"things": {"parent_id": "parents"}})


def test_select_only_sees_own_org():
    rows = _client().table("things").select("*").execute().data
    assert [r["id"] for r in rows] == ["1"]


def test_select_by_foreign_id_is_not_found():
    assert _client().table("things").select("*").eq("id", "2").execute().data == []


def test_update_and_delete_cannot_touch_other_org():
    c = _client()
    c.table("things").update({"name": "x"}).eq("id", "2").execute()
    c.table("things").delete().eq("id", "2").execute()
    assert {r["id"] for r in c._inner.table("things").select("*").execute().data} == {"1", "2"}
    assert [r["name"] for r in c._inner.table("things").select("*").eq("id", "2").execute().data] == ["b1"]


def test_insert_stamps_org_and_refuses_other_org():
    m = _mock()
    c = _client(m)
    c.table("things").insert({"id": "3", "name": "n"}).execute()
    assert m.table("things").inserted_payloads[-1]["org_id"] == ORG_A
    with pytest.raises(OrgScopeViolation):
        c.table("things").insert({"id": "4", "org_id": ORG_B}).execute()
    with pytest.raises(OrgScopeViolation):
        c.table("things").upsert([{"id": "5"}, {"id": "6", "org_id": ORG_B}]).execute()


def test_update_refuses_rehoming_the_org():
    with pytest.raises(OrgScopeViolation):
        _client().table("things").update({"org_id": ORG_B}).eq("id", "1").execute()


def test_foreign_reference_must_belong_to_same_org():
    c = _client()
    c.table("things").insert({"id": "7", "parent_id": "pa"}).execute()  # own org: fine
    c.table("things").insert({"id": "8", "parent_id": None}).execute()  # null: fine
    with pytest.raises(ForeignReferenceError) as e:
        c.table("things").insert({"id": "9", "parent_id": "pb"}).execute()  # other org's parent
    assert e.value.status_code == 422
    with pytest.raises(ForeignReferenceError):
        c.table("things").update({"parent_id": "pb"}).eq("id", "1").execute()


def test_rpc_schema_and_auth_are_not_exposed():
    c = _client()
    for name in ("rpc", "schema", "auth", "storage"):
        with pytest.raises(AttributeError):
            getattr(c, name)


def test_needs_a_real_org_id():
    for bad in (None, "", "not-a-uuid"):
        with pytest.raises(ValueError):
            OrgScopedClient(_mock(), bad)
