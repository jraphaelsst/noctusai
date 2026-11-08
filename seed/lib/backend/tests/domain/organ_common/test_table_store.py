"""`OrgTableStore`: the Fake refuses what the DB's UNIQUE guards refuse; the Real maps ONLY 23505 to `StoreConflict`."""
from __future__ import annotations

import pytest

from noctusai_lib.domain._organ_common import (
    FakeOrgTableStore,
    StoreConflict,
    SupabaseOrgTableStore,
    TableSpec,
    UniqueKey,
    make_org_table_store,
)

SPECS = {
    "teams": TableSpec("t_teams", unique=(UniqueKey("uq_t_teams_name", ("name",)),)),
    "members": TableSpec(
        "t_members",
        unique=(UniqueKey("uq_t_members_active", ("team", "user"), where=lambda r: r.get("left") is None),),
    ),
    "goals": TableSpec(
        "t_goals",
        unique=(UniqueKey("uq_t_goals_key", ("subject", "period"), where=lambda r: r.get("period") is not None, nulls_equal=("subject",)),),
    ),
}


def test_fake_unique_is_per_org_and_null_never_collides():
    s = FakeOrgTableStore(SPECS)
    s.insert("teams", "o1", [{"name": "A"}])
    with pytest.raises(StoreConflict) as e:
        s.insert("teams", "o1", [{"name": "A"}])
    assert e.value.guard == "uq_t_teams_name"
    s.insert("teams", "o2", [{"name": "A"}])  # another org
    s.insert("teams", "o1", [{"name": None}])
    s.insert("teams", "o1", [{"name": None}])  # NULL != NULL


def test_fake_partial_and_coalesced_keys():
    s = FakeOrgTableStore(SPECS)
    s.insert("members", "o", [{"team": "t", "user": "u", "left": "2026-01-01"}])
    s.insert("members", "o", [{"team": "t", "user": "u", "left": None}])  # the past membership does not count
    with pytest.raises(StoreConflict):
        s.insert("members", "o", [{"team": "t", "user": "u", "left": None}])
    s.insert("goals", "o", [{"subject": None, "period": "p"}])
    with pytest.raises(StoreConflict):  # a NULL subject IS a key value for the goals index (COALESCE)
        s.insert("goals", "o", [{"subject": None, "period": "p"}])
    s.insert("goals", "o", [{"subject": None, "period": None}])
    s.insert("goals", "o", [{"subject": None, "period": None}])  # partial index: no period => unconstrained


def test_fake_multi_row_insert_is_atomic_and_scoped():
    s = FakeOrgTableStore(SPECS)
    with pytest.raises(StoreConflict):
        s.insert("teams", "o", [{"name": "X"}, {"name": "X"}])
    assert s.select("teams", "o") == []  # one transaction: nothing landed
    row = s.insert("teams", "o", [{"name": "Y"}])[0]
    assert s.get("teams", "other", row["id"]) is None and s.delete("teams", "other", row["id"]) is False
    assert s.update("teams", "other", row["id"], {"name": "Z"}) is None
    assert s.update("teams", "o", row["id"], {"name": "Z"})["name"] == "Z"


def test_fake_select_filters_order_and_paging():
    s = FakeOrgTableStore({"e": TableSpec("e")})
    for i, d in enumerate(["2026-01-03", "2026-01-01", "2026-01-02"]):
        s.insert("e", "o", [{"day": d, "n": i, "tag": "a" if i else None}])
    assert [r["day"] for r in s.select("e", "o", order=(("day", False),))] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert [r["day"] for r in s.select("e", "o", gte={"day": "2026-01-02"}, order=(("day", True),), limit=1)] == ["2026-01-03"]
    assert len(s.select("e", "o", is_null=("tag",))) == 1 and len(s.select("e", "o", not_null=("tag",))) == 2
    assert len(s.select("e", "o", in_={"n": [0, 2]})) == 2 and s.select("e", "o", in_={"n": []}) == []
    with pytest.raises(KeyError):
        s.select("nope", "o")


class _Client:
    """Raises on write; reads nothing. Duck-types the supabase builder chain."""

    def __init__(self, exc):
        self.exc = exc

    def table(self, name):
        return self

    def insert(self, rows):
        return self

    def update(self, body):
        return self

    def eq(self, *a):
        return self

    def execute(self):
        raise self.exc


def _unique_exc():
    exc = RuntimeError('duplicate key value violates unique constraint "uq_t_teams_name"')
    exc.code = "23505"
    return exc


def test_real_translates_only_a_unique_violation():
    store = SupabaseOrgTableStore(_Client(_unique_exc()), SPECS)
    with pytest.raises(StoreConflict) as e:
        store.insert("teams", "o", [{"name": "A"}])
    assert e.value.guard == "uq_t_teams_name"
    with pytest.raises(StoreConflict):
        store.update("teams", "o", "id1", {"name": "A"})
    with pytest.raises(RuntimeError, match="connection reset"):  # anything else propagates
        SupabaseOrgTableStore(_Client(RuntimeError("connection reset")), SPECS).insert("teams", "o", [{"name": "A"}])


def test_factory_has_no_silent_fake():
    assert isinstance(make_org_table_store(SPECS, use_fake=True), FakeOrgTableStore)
    with pytest.raises(RuntimeError):
        make_org_table_store(SPECS)
