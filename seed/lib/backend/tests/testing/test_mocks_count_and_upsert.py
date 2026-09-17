"""`count="exact"` filtering + `.upsert()` propagation — the two mock gaps
several products worked around by hand (a stale `count`, and a documented
`.upsert()` no-op forcing SELECT-then-insert-or-update).

Companion to `test_mocks.py` (SELECT-predicate filtering). Fixed 2026-09-16.
"""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient


# ---------------------------------------------------------------------------
# count="exact" — reflects the FILTERED rows, not len(table)
# ---------------------------------------------------------------------------


def test_count_exact_reflects_filtered_rows_not_whole_table():
    db = MockSupabaseClient()
    db.set_table_data("widgets", [
        {"id": "1", "org_id": "org-a"},
        {"id": "2", "org_id": "org-a"},
        {"id": "3", "org_id": "org-b"},
    ])
    result = db.table("widgets").select("id", count="exact").eq("org_id", "org-a").execute()
    assert len(result.data) == 2
    assert result.count == 2  # NOT 3 (the whole table) — the pre-fix bug


def test_count_exact_without_count_kwarg_stays_none():
    db = MockSupabaseClient()
    db.set_table_data("widgets", [{"id": "1"}])
    result = db.table("widgets").select("id").execute()
    assert result.count is None


def test_count_exact_is_independent_of_range_window():
    """Real PostgREST's count reflects the FILTER, not the pagination
    window — `.range(0, 0)` truncates `data` to 1 row but `count` still
    reports the full filtered total (5)."""
    db = MockSupabaseClient()
    db.set_table_data("widgets", [{"id": str(i), "org_id": "org-a"} for i in range(5)])
    result = (
        db.table("widgets")
        .select("id", count="exact")
        .eq("org_id", "org-a")
        .range(0, 0)
        .execute()
    )
    assert len(result.data) == 1
    assert result.count == 5


def test_count_exact_with_single_mode_still_reports_filtered_total():
    db = MockSupabaseClient()
    db.set_table_data("widgets", [
        {"id": "1", "org_id": "org-a"}, {"id": "2", "org_id": "org-a"}, {"id": "3", "org_id": "org-b"},
    ])
    result = (
        db.table("widgets").select("id", count="exact").eq("org_id", "org-a").single()
    )
    result = result.execute()
    assert result.data["id"] == "1"
    assert result.count == 2


def test_count_exact_zero_matches_is_zero_not_none():
    db = MockSupabaseClient()
    db.set_table_data("widgets", [{"id": "1", "org_id": "org-b"}])
    result = db.table("widgets").select("id", count="exact").eq("org_id", "org-a").execute()
    assert result.data == []
    assert result.count == 0


def test_count_exact_via_response_queue_is_unaffected():
    """The queue dictates the response entirely (existing contract) — a
    queued `MockSupabaseResponse(count=...)` is NOT recomputed from
    `_filtered_rows()`."""
    from noctusai_lib.testing import MockSupabaseResponse

    db = MockSupabaseClient()
    db.set_table_data("widgets", [{"id": "1", "org_id": "org-a"}])
    db.set_sequential_responses("widgets", [MockSupabaseResponse(data=[{"id": "x"}], count=99)])
    result = db.table("widgets").select("id", count="exact").eq("org_id", "org-a").execute()
    assert result.count == 99


# ---------------------------------------------------------------------------
# upsert() — insert-or-update on the conflict key
# ---------------------------------------------------------------------------


def test_upsert_inserts_when_no_conflicting_row_exists():
    db = MockSupabaseClient()
    db.set_table_data("settings", [])
    result = db.table("settings").upsert({"key": "a", "value": "1"}, on_conflict="key").execute()
    assert result.data[0]["key"] == "a" and result.data[0]["value"] == "1"
    assert result.data[0]["id"]  # auto-id, same as insert()
    assert db.table("settings").select("*").execute().data == result.data


def test_upsert_merges_into_the_conflicting_row():
    db = MockSupabaseClient()
    db.set_table_data("settings", [{"key": "a", "value": "1", "other": "untouched"}])
    result = db.table("settings").upsert({"key": "a", "value": "2"}, on_conflict="key").execute()
    assert result.data == [{"key": "a", "value": "2", "other": "untouched"}]
    rows = db.table("settings").select("*").execute().data
    assert rows == [{"key": "a", "value": "2", "other": "untouched"}]  # merged in place, not duplicated


def test_upsert_default_conflict_target_is_id():
    db = MockSupabaseClient()
    db.set_table_data("orgs", [{"id": "o1", "name": "Old"}])
    result = db.table("orgs").upsert({"id": "o1", "name": "New"}).execute()
    assert result.data == [{"id": "o1", "name": "New"}]
    assert len(db.table("orgs").select("*").execute().data) == 1


def test_upsert_composite_on_conflict_columns():
    db = MockSupabaseClient()
    db.set_table_data("campaign_days", [
        {"campaign_id": "c1", "date": "2026-09-01", "spend": 10},
    ])
    result = (
        db.table("campaign_days")
        .upsert({"campaign_id": "c1", "date": "2026-09-01", "spend": 20}, on_conflict="campaign_id,date")
        .execute()
    )
    assert result.data == [{"campaign_id": "c1", "date": "2026-09-01", "spend": 20}]
    # A different date is NOT a conflict — inserted alongside.
    result2 = (
        db.table("campaign_days")
        .upsert({"campaign_id": "c1", "date": "2026-09-02", "spend": 5}, on_conflict="campaign_id,date")
        .execute()
    )
    assert len(result2.data) == 1
    assert len(db.table("campaign_days").select("*").execute().data) == 2


def test_upsert_ignore_duplicates_leaves_conflicting_row_untouched_and_unreturned():
    db = MockSupabaseClient()
    db.set_table_data("settings", [{"key": "a", "value": "1"}])
    result = (
        db.table("settings")
        .upsert({"key": "a", "value": "2"}, on_conflict="key", ignore_duplicates=True)
        .execute()
    )
    assert result.data == []  # the conflicting row is not part of the response
    rows = db.table("settings").select("*").execute().data
    assert rows == [{"key": "a", "value": "1"}]  # untouched


def test_upsert_ignore_duplicates_still_inserts_non_conflicting_rows():
    db = MockSupabaseClient()
    db.set_table_data("settings", [{"key": "a", "value": "1"}])
    result = (
        db.table("settings")
        .upsert(
            [{"key": "a", "value": "2"}, {"key": "b", "value": "3"}],
            on_conflict="key", ignore_duplicates=True,
        )
        .execute()
    )
    assert [r["key"] for r in result.data] == ["b"]
    rows = db.table("settings").select("*").execute().data
    assert {r["key"]: r["value"] for r in rows} == {"a": "1", "b": "3"}


def test_upsert_tracks_raw_payload_in_upserted_payloads():
    db = MockSupabaseClient()
    db.set_table_data("settings", [])
    payload = {"key": "a", "value": "1"}
    db.table("settings").upsert(payload, on_conflict="key").execute()
    assert db.table("settings").upserted_payloads == [payload]


def test_upsert_list_payload_mixes_insert_and_merge():
    db = MockSupabaseClient()
    db.set_table_data("settings", [{"key": "a", "value": "1"}])
    result = (
        db.table("settings")
        .upsert([{"key": "a", "value": "2"}, {"key": "b", "value": "3"}], on_conflict="key")
        .execute()
    )
    assert {r["key"]: r["value"] for r in result.data} == {"a": "2", "b": "3"}
    rows = db.table("settings").select("*").execute().data
    assert {r["key"]: r["value"] for r in rows} == {"a": "2", "b": "3"}


def test_upsert_is_not_filterable_like_insert():
    """Real supabase-py's `.upsert()` returns a `SyncQueryRequestBuilder`
    (execute-only), same as `.insert()` — no `.eq()` chaining."""
    db = MockSupabaseClient()
    db.set_table_data("settings", [])
    builder = db.table("settings").upsert({"key": "a", "value": "1"}, on_conflict="key")
    assert not hasattr(builder, "eq")


def test_upsert_response_queue_suppresses_propagation():
    from noctusai_lib.testing import MockSupabaseResponse

    db = MockSupabaseClient()
    db.set_table_data("settings", [{"key": "a", "value": "1"}])
    db.set_sequential_responses("settings", [MockSupabaseResponse(data=[{"key": "a", "value": "queued"}])])
    result = db.table("settings").upsert({"key": "a", "value": "2"}, on_conflict="key").execute()
    assert result.data == [{"key": "a", "value": "queued"}]
    # The shared list was NOT mutated — queue wins, same contract insert()/
    # update() already document.
    assert db.table("settings")._data == [{"key": "a", "value": "1"}]
