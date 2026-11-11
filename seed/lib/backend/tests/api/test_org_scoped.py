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
    m = _mock()
    c = _client(m)
    c.table("things").update({"name": "x"}).eq("id", "2").execute()
    c.table("things").delete().eq("id", "2").execute()
    assert {r["id"] for r in m.table("things").select("*").execute().data} == {"1", "2"}
    assert [r["name"] for r in m.table("things").select("*").eq("id", "2").execute().data] == ["b1"]


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


# -- F1: an upsert may never move another tenant's row ------------------------------------------------------------
def test_upsert_without_the_org_in_on_conflict_is_refused():
    c = _client()
    with pytest.raises(OrgScopeViolation):
        c.table("things").upsert({"id": "2", "name": "takeover"}).execute()  # no on_conflict: ON CONFLICT (id) DO UPDATE
    with pytest.raises(OrgScopeViolation):
        c.table("things").upsert({"id": "2"}, on_conflict="id").execute()
    with pytest.raises(OrgScopeViolation):
        c.table("things").upsert({"id": "2"}, on_conflict="k,date").execute()


def test_insert_with_upsert_true_is_refused():
    with pytest.raises(OrgScopeViolation):
        _client().table("things").insert({"id": "2"}, upsert=True).execute()


def test_upsert_with_a_composite_org_key_or_ignore_duplicates_passes():
    m = _mock()
    c = _client(m)
    c.table("things").upsert({"id": "9", "k": 1}, on_conflict="org_id,k").execute()
    c.table("things").upsert({"id": "10"}, on_conflict=" org_id , id ").execute()
    c.table("things").upsert({"id": "11"}, on_conflict="org_id,id", ignore_duplicates=True).execute()
    assert [r["org_id"] for r in m.table("things").select("*").eq("id", "9").execute().data] == [ORG_A]


# -- F5: no embeds -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cols", ["*, parents(*)", "id, p:parents(id)", "id, parents!inner(id)", "id::text"])
def test_select_refuses_embeds_aliases_and_casts(cols):
    with pytest.raises(OrgScopeViolation):
        _client().table("things").select(cols)


def test_the_wrapped_client_is_not_reachable_by_attribute():
    c = _client()
    for name in ("_inner", "inner", "client", "_client", "_raw"):
        with pytest.raises(AttributeError):
            getattr(c, name)


# -- F9: one parent query per distinct (column, parent), however many rows -----------------------------------------
class _Counting(MockSupabaseClient):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.selects: list[str] = []

    def table(self, name):
        self.selects.append(name)
        return super().table(name)


def test_bulk_insert_checks_each_distinct_parent_once():
    m = _Counting(validate_schema=False, schema="t")
    m.set_table_data("things", [])
    m.set_table_data("parents", [{"id": "pa", "org_id": ORG_A}])
    c = _client(m)
    c.table("things").insert([{"id": str(i), "parent_id": "pa"} for i in range(50)]).execute()
    assert m.selects.count("parents") == 1


# -- reference validators (ids that live outside the schema) -------------------------------------------------------
def test_reference_validator_refuses_ids_it_does_not_vouch_for():
    seen = []

    def vouch(ids):
        seen.append(set(ids))
        return {i for i in ids if i == "u-mine"}

    c = OrgScopedClient(_mock(), ORG_A, reference_validators={"things": {"owner_id": vouch}})
    c.table("things").insert({"id": "20", "owner_id": "u-mine"}).execute()
    c.table("things").insert({"id": "21", "owner_id": None}).execute()
    with pytest.raises(ForeignReferenceError):
        c.table("things").insert({"id": "22", "owner_id": "u-other-org"}).execute()
    with pytest.raises(ForeignReferenceError):
        c.table("things").update({"owner_id": "u-other-org"}).eq("id", "1").execute()
    assert seen[0] == {"u-mine"}


# -- round 3 ---------------------------------------------------------------------------------------------------------
def test_select_judges_every_positional_column_argument():
    """postgrest-py joins all positional columns: an embed in the SECOND argument is still an embed."""
    c = _client()
    for args in (("id", "x(*)"), ("id", "p:parents(id)"), ("id", "name", "parents!inner(id)")):
        with pytest.raises(OrgScopeViolation):
            c.table("things").select(*args)
    with pytest.raises(OrgScopeViolation):
        c.table("things").select(columns="id, x(*)")
    c.table("things").select("id", "name").execute()  # plain columns still pass


def test_the_table_builder_is_not_reachable():
    t = _client().table("things")
    for name in ("_inner", "inner", "builder", "_builder"):
        with pytest.raises(AttributeError):
            getattr(t, name)


def test_ignore_duplicates_does_not_waive_the_org_in_on_conflict():
    """DO NOTHING on a global key is an existence oracle and lets one tenant block another's insert."""
    c = _client()
    with pytest.raises(OrgScopeViolation):
        c.table("things").upsert({"id": "2"}, ignore_duplicates=True).execute()
    with pytest.raises(OrgScopeViolation):
        c.table("things").upsert({"id": "2"}, on_conflict="id", ignore_duplicates=True).execute()
    c.table("things").upsert({"id": "12"}, on_conflict="org_id,id", ignore_duplicates=True).execute()
