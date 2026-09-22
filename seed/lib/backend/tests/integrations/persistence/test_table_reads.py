"""`noctusai_lib.integrations.persistence.table_reads` — the lifted
org-scoped PostgREST read helpers. Each helper's body is a defence against a
limit invisible at the call site; these tests exercise the limit itself."""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.integrations.persistence import table_reads as tr
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG = str(uuid4())


def _db(rows):
    db = MockSupabaseClient(validate_schema=False, schema="x")
    db.set_table_data("t", rows)
    return db


class TestBatched:
    def test_chunks_at_the_url_safe_size(self):
        chunks = list(tr.batched(list(range(450))))
        assert [len(c) for c in chunks] == [200, 200, 50]

    def test_empty(self):
        assert list(tr.batched([])) == []


class TestPagedRows:
    def test_reads_past_the_1000_row_cap(self):
        rows = [{"id": f"{i:05d}", "org_id": ORG} for i in range(2500)]
        assert len(tr.paged_rows(_db(rows), "t", ORG)) == 2500

    def test_is_org_scoped_and_eq_filtered(self):
        rows = [
            {"id": "1", "org_id": ORG, "k": "a"},
            {"id": "2", "org_id": ORG, "k": "b"},
            {"id": "3", "org_id": str(uuid4()), "k": "a"},
        ]
        assert [r["id"] for r in tr.paged_rows(_db(rows), "t", ORG, eq_filters={"k": "a"})] == ["1"]

    def test_refine_applies_extra_filter_shapes(self):
        rows = [{"id": "1", "org_id": ORG, "deleted_at": None}, {"id": "2", "org_id": ORG, "deleted_at": "x"}]
        got = tr.paged_rows(_db(rows), "t", ORG, refine=lambda q: q.is_("deleted_at", "null"))
        assert [r["id"] for r in got] == ["1"]

    def test_a_keyless_table_pages_on_its_own_key(self):
        rows = [{"tag_id": f"{i:04d}", "org_id": ORG} for i in range(1200)]
        got = tr.paged_rows(_db(rows), "t", ORG, order_col="tag_id", id_key="tag_id")
        assert len(got) == 1200


class TestInBatchedRows:
    def test_batches_and_pages(self):
        rows = [{"id": f"{i:05d}", "org_id": ORG} for i in range(700)]
        ids = [r["id"] for r in rows] + ["missing"]
        assert len(tr.in_batched_rows(_db(rows), "t", ORG, "id", ids)) == 700

    def test_no_ids_no_query(self):
        assert tr.in_batched_rows(None, "t", ORG, "id", []) == []


class TestActors:
    def _core(self):
        core = MockSupabaseClient(validate_schema=False, schema="public")
        core.set_table_data("noctus_users", [
            {"id": "u1", "nome": "Ana", "email": "a@x"},
            {"id": "u2", "nome": None, "email": "b@x"},
        ])
        return core

    def test_resolves_names_falling_back_to_email(self):
        got = tr.resolve_actors(self._core(), {"u1", "u2", None, ""})
        assert got == {"u1": {"id": "u1", "nome": "Ana"}, "u2": {"id": "u2", "nome": "b@x"}}

    def test_no_ids_no_query(self):
        assert tr.resolve_actors(None, set()) == {}

    def test_actor_of_an_unresolved_id_keeps_the_id(self):
        assert tr.actor({}, "u9") == {"id": "u9", "nome": None}
        assert tr.actor({}, None) is None

    def test_actor_resolver_reads_the_client_per_call(self):
        """Never captured at construction — a swapped core client is seen."""
        clients = [self._core()]
        resolve = tr.actor_resolver(lambda: clients[-1])
        assert resolve({"u1"})["u1"]["nome"] == "Ana"
        empty = MockSupabaseClient(validate_schema=False, schema="public")
        empty.set_table_data("noctus_users", [])
        clients.append(empty)
        assert resolve({"u1"}) == {}
