"""Direct tests for `MockRequestBuilder` payload-tracking attributes:
`inserted_payloads` (existing) and `updated_payloads` (new 2026-05-03).

Both expose the same shape: a per-table list of dicts captured in call
order, mirroring what production code passed to `.insert(...)` /
`.update(...)`. Tests across products read these to assert write
side-effects without monkey-patching the helper that issued the call
(per `feedback_no_monkeypatching_in_tests`).
"""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient


def test_inserted_payloads_captures_single_dict():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"id": "a1", "status": "waiting"}).execute()
    assert db.table("appointments").inserted_payloads == [
        {"id": "a1", "status": "waiting"}
    ]


def test_inserted_payloads_captures_list_of_dicts():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert(
        [{"id": "a1"}, {"id": "a2"}]
    ).execute()
    assert db.table("appointments").inserted_payloads == [
        {"id": "a1"},
        {"id": "a2"},
    ]


def test_updated_payloads_captures_single_dict():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").update({"status": "cancelled"}).eq("id", "a1").execute()
    assert db.table("appointments").updated_payloads == [{"status": "cancelled"}]


def test_updated_payloads_captures_multiple_calls_in_order():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").update({"status": "cancelled"}).eq("id", "a1").execute()
    db.table("appointments").update({"status": "waiting"}).eq("id", "a2").execute()
    assert db.table("appointments").updated_payloads == [
        {"status": "cancelled"},
        {"status": "waiting"},
    ]


def test_updated_payloads_captures_list_of_dicts():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").update(
        [{"status": "x"}, {"status": "y"}]
    ).eq("id", "a1").execute()
    assert db.table("appointments").updated_payloads == [
        {"status": "x"},
        {"status": "y"},
    ]


def test_inserted_and_updated_payloads_are_independent():
    db = MockSupabaseClient(validate_schema=False)
    db.table("appointments").insert({"id": "a1"}).execute()
    db.table("appointments").update({"status": "cancelled"}).eq("id", "a1").execute()
    builder = db.table("appointments")
    assert builder.inserted_payloads == [{"id": "a1"}]
    assert builder.updated_payloads == [{"status": "cancelled"}]


def test_updated_payloads_starts_empty():
    db = MockSupabaseClient(validate_schema=False)
    assert db.table("appointments").updated_payloads == []
