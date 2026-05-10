"""Write-propagation tests for `MockSupabaseClient`.

Closes the gap surfaced N=4 by AdConnect MVP (cart, orders, sellout, rewards
routers). Before this fix, INSERT / UPDATE / DELETE on a table did NOT mutate
the in-memory SELECT seed, so a router that did
`db.table(t).insert(...).execute(); db.table(t).select(...).execute()` would
not see its own write. Tests had to pre-seed the post-write state via
`set_table_data(...)` or `MockSupabaseClient(initial_state={...})`, masking
SELECT-after-INSERT bugs in the consumer code.

Companion project: `projects/mock-supabase-write-propagation/`.
"""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# INSERT propagation
# ---------------------------------------------------------------------------


def test_insert_then_select_returns_inserted_row():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"id": "a1", "status": "waiting"}).execute()

    result = db.table("appointments").select("*").execute()

    assert result.data == [{"id": "a1", "status": "waiting"}]


def test_insert_appends_auto_id_visible_in_subsequent_select():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"status": "waiting"}).execute()

    result = db.table("appointments").select("*").execute()

    assert len(result.data) == 1
    assert result.data[0]["status"] == "waiting"
    # Auto-id assigned by the mock.
    assert result.data[0]["id"] == "mock-appointments-1"


def test_insert_list_payload_propagates_all_rows():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert(
        [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]
    ).execute()

    result = db.table("appointments").select("*").execute()

    ids = sorted(r["id"] for r in result.data)
    assert ids == ["a1", "a2", "a3"]


def test_insert_preserves_seeded_rows_and_appends():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [{"id": "a0", "status": "done"}],
    )
    db.table("appointments").insert({"id": "a1", "status": "waiting"}).execute()

    result = db.table("appointments").select("*").execute()

    ids = sorted(r["id"] for r in result.data)
    assert ids == ["a0", "a1"]


def test_insert_inserted_payloads_still_holds_raw_payload():
    """Backwards-compat: tests reading inserted_payloads see the raw dict
    (no auto-id), matching the documented contract.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"status": "waiting"}).execute()

    builder = db.table("appointments")
    assert builder.inserted_payloads == [{"status": "waiting"}]


def test_insert_response_data_includes_auto_id():
    """Backwards-compat: production code reading `result.data[0]['id']`
    still works.
    """
    db = MockSupabaseClient(validate_schema=False)
    result = db.table("appointments").insert({"status": "waiting"}).execute()

    assert result.data[0]["id"] == "mock-appointments-1"


def test_insert_with_response_queue_skips_propagation():
    """When a response queue is set, the queue dictates the result and the
    write does NOT propagate (lets tests simulate insert-failure without
    accidentally seeding the SELECT side too).
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_sequential_responses(
        "appointments",
        [MockSupabaseResponse(data=[])],  # simulate insert returning no rows
    )

    db.table("appointments").insert({"id": "a1"}).execute()

    # The queue intercepted execute(); SELECT is on a separate code path
    # (un-queued, since we only queued one response). Propagation must NOT
    # have occurred — otherwise tests asserting "insert failed → table empty"
    # would silently break.
    select_result = db.table("appointments").select("*").execute()
    assert select_result.data == []


# ---------------------------------------------------------------------------
# UPDATE propagation
# ---------------------------------------------------------------------------


def test_update_eq_mutates_matching_row_in_place():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "waiting"},
        ],
    )

    db.table("appointments").update({"status": "done"}).eq("id", "a1").execute()
    result = db.table("appointments").select("*").execute()

    rows_by_id = {r["id"]: r for r in result.data}
    assert rows_by_id["a1"]["status"] == "done"
    assert rows_by_id["a2"]["status"] == "waiting"


def test_update_returns_mutated_rows_in_response():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "waiting"},
        ],
    )

    response = (
        db.table("appointments")
        .update({"status": "done"})
        .eq("id", "a1")
        .execute()
    )

    assert isinstance(response, MockSupabaseResponse)
    assert response.error is None
    assert len(response.data) == 1
    assert response.data[0]["id"] == "a1"
    assert response.data[0]["status"] == "done"


def test_update_after_insert_propagates_through_select():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"id": "a1", "status": "waiting"}).execute()
    db.table("appointments").update({"status": "done"}).eq("id", "a1").execute()

    result = db.table("appointments").select("*").execute()

    assert result.data == [{"id": "a1", "status": "done"}]


def test_update_with_no_filters_mutates_all_rows():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "waiting"},
        ],
    )

    db.table("appointments").update({"status": "done"}).execute()
    result = db.table("appointments").select("*").execute()

    assert all(r["status"] == "done" for r in result.data)


def test_update_in_filter_matches_membership():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "waiting"},
            {"id": "a3", "status": "waiting"},
        ],
    )

    db.table("appointments").update({"status": "done"}).in_(
        "id", ["a1", "a3"]
    ).execute()
    result = db.table("appointments").select("*").execute()

    rows_by_id = {r["id"]: r for r in result.data}
    assert rows_by_id["a1"]["status"] == "done"
    assert rows_by_id["a2"]["status"] == "waiting"
    assert rows_by_id["a3"]["status"] == "done"


def test_update_updated_payloads_still_holds_raw_payload():
    """Backwards-compat: `updated_payloads` still receives the raw payload."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("appointments", [{"id": "a1", "status": "waiting"}])
    db.table("appointments").update({"status": "done"}).eq("id", "a1").execute()

    assert db.table("appointments").updated_payloads == [{"status": "done"}]


def test_update_with_response_queue_skips_propagation():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("appointments", [{"id": "a1", "status": "waiting"}])
    db.set_sequential_responses(
        "appointments",
        [MockSupabaseResponse(data=[])],
    )

    db.table("appointments").update({"status": "done"}).eq("id", "a1").execute()
    # Queue intercepted execute(); _data not mutated.
    # SELECT here will pull from the queue too (it's empty after one consume).
    # We assert via the unmutated _data on the cached builder:
    builder = db.table("appointments")
    assert builder._data[0]["status"] == "waiting"


# ---------------------------------------------------------------------------
# DELETE propagation
# ---------------------------------------------------------------------------


def test_delete_eq_removes_matching_row():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "waiting"},
        ],
    )

    db.table("appointments").delete().eq("id", "a1").execute()
    result = db.table("appointments").select("*").execute()

    assert len(result.data) == 1
    assert result.data[0]["id"] == "a2"


def test_delete_returns_removed_rows_in_response():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "waiting"},
        ],
    )

    response = db.table("appointments").delete().eq("id", "a1").execute()

    assert len(response.data) == 1
    assert response.data[0]["id"] == "a1"


def test_delete_in_filter_removes_membership():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1"},
            {"id": "a2"},
            {"id": "a3"},
        ],
    )

    db.table("appointments").delete().in_("id", ["a1", "a3"]).execute()
    result = db.table("appointments").select("*").execute()

    assert len(result.data) == 1
    assert result.data[0]["id"] == "a2"


def test_delete_no_filters_wipes_table():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [{"id": "a1"}, {"id": "a2"}],
    )

    db.table("appointments").delete().execute()
    result = db.table("appointments").select("*").execute()

    assert result.data == []


def test_delete_after_insert_round_trip():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"id": "a1", "status": "waiting"}).execute()
    db.table("appointments").insert({"id": "a2", "status": "waiting"}).execute()
    db.table("appointments").delete().eq("id", "a1").execute()

    result = db.table("appointments").select("*").execute()
    assert len(result.data) == 1
    assert result.data[0]["id"] == "a2"


def test_delete_with_response_queue_skips_propagation():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("appointments", [{"id": "a1"}])
    db.set_sequential_responses(
        "appointments",
        [MockSupabaseResponse(data=[])],
    )

    db.table("appointments").delete().eq("id", "a1").execute()
    builder = db.table("appointments")
    assert builder._data == [{"id": "a1"}]  # not propagated


# ---------------------------------------------------------------------------
# Compound flows (round-trips)
# ---------------------------------------------------------------------------


def test_insert_update_delete_round_trip():
    """End-to-end: insert two rows, update one, delete the other; SELECT
    reflects each step.
    """
    db = MockSupabaseClient(validate_schema=False)

    db.table("orders").insert({"id": "o1", "status": "pending"}).execute()
    db.table("orders").insert({"id": "o2", "status": "pending"}).execute()

    after_insert = db.table("orders").select("*").execute()
    assert sorted(r["id"] for r in after_insert.data) == ["o1", "o2"]

    db.table("orders").update({"status": "paid"}).eq("id", "o1").execute()

    after_update = db.table("orders").select("*").execute()
    rows_by_id = {r["id"]: r for r in after_update.data}
    assert rows_by_id["o1"]["status"] == "paid"
    assert rows_by_id["o2"]["status"] == "pending"

    db.table("orders").delete().eq("id", "o2").execute()

    after_delete = db.table("orders").select("*").execute()
    assert len(after_delete.data) == 1
    assert after_delete.data[0]["id"] == "o1"
    assert after_delete.data[0]["status"] == "paid"


# ---------------------------------------------------------------------------
# Backwards-compat regression checks (these worked pre-fix, must still work)
# ---------------------------------------------------------------------------


def test_select_only_no_writes_unchanged():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("appointments", [{"id": "a1"}, {"id": "a2"}])

    result = db.table("appointments").select("*").execute()
    assert len(result.data) == 2


def test_inserted_payloads_independent_of_propagation():
    """A test reading inserted_payloads should still see the raw dicts in
    call order — propagation does NOT alter what inserted_payloads holds.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"status": "waiting"}).execute()
    db.table("appointments").insert({"status": "done"}).execute()

    assert db.table("appointments").inserted_payloads == [
        {"status": "waiting"},
        {"status": "done"},
    ]
