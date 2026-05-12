"""SELECT-predicate filtering regression tests for `MockSupabaseClient`.

Closes the gap surfaced 2026-05-11: `MockSelectBuilder.execute()` returned
ALL seeded rows regardless of `.eq/.in_/.is_/.gt/.lt/.like/etc` predicates.
UPDATE / DELETE paths already filtered via `_row_matches_predicates` +
`_PREDICATE_EVALUATORS`; the SELECT path did not — silently masking ~43 latent
test bugs across 7 products that asserted on filtered counts.

The fix wires `MockSelectBuilder._filtered_rows()` through `execute()`,
mirroring the UPDATE/DELETE filter semantics:

    - Empty predicate list → return all rows (PostgREST match-all)
    - One+ predicates AND-conjoin
    - Response-queue path is unchanged (queue wins; predicate filter
      suppressed, same shape as the UPDATE/DELETE propagation contract)
    - Operators with literal evaluators: eq/neq/in_/gt/lt/gte/lte/is_/like/
      ilike/contains
    - Operators that accumulate as match-all (debug log, no filtering):
      or_/fts/text_search/filter/overlaps/contained_by

`match({col: val})` is decomposed to literal eq predicates at record time,
so it does filter literally even though `match` is not in the evaluator map.

Companion: project `projects/mock-supabase-select-predicate-filter/`.
"""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Literal-evaluator coverage — one test per operator with a hit + miss row
# ---------------------------------------------------------------------------


def test_select_eq_filters_to_matching_rows():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "done"},
            {"id": "a3", "status": "waiting"},
        ],
    )

    result = db.table("appointments").select("*").eq("status", "waiting").execute()

    ids = sorted(r["id"] for r in result.data)
    assert ids == ["a1", "a3"]


def test_select_neq_filters_out_matching_rows():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "appointments",
        [
            {"id": "a1", "status": "waiting"},
            {"id": "a2", "status": "done"},
            {"id": "a3", "status": "waiting"},
        ],
    )

    result = db.table("appointments").select("*").neq("status", "waiting").execute()

    ids = [r["id"] for r in result.data]
    assert ids == ["a2"]


def test_select_in_filters_to_membership():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "tier": "gold"},
            {"id": "x2", "tier": "silver"},
            {"id": "x3", "tier": "bronze"},
        ],
    )

    result = db.table("items").select("*").in_("tier", ["gold", "bronze"]).execute()

    ids = sorted(r["id"] for r in result.data)
    assert ids == ["x1", "x3"]


def test_select_is_filters_by_identity():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "deleted_at": None},
            {"id": "x2", "deleted_at": "2026-01-01"},
            {"id": "x3", "deleted_at": None},
        ],
    )

    result = db.table("items").select("*").is_("deleted_at", None).execute()

    ids = sorted(r["id"] for r in result.data)
    assert ids == ["x1", "x3"]


def test_select_gt_lt_gte_lte_filter_by_comparison():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "amount": 10},
            {"id": "x2", "amount": 20},
            {"id": "x3", "amount": 30},
        ],
    )

    # gt → strict greater
    r_gt = db.table("items").select("*").gt("amount", 10).execute()
    assert sorted(r["id"] for r in r_gt.data) == ["x2", "x3"]

    # New builder per call — the in-memory list is shared, predicates are not.
    r_lt = db.table("items").select("*").lt("amount", 30).execute()
    assert sorted(r["id"] for r in r_lt.data) == ["x1", "x2"]

    r_gte = db.table("items").select("*").gte("amount", 20).execute()
    assert sorted(r["id"] for r in r_gte.data) == ["x2", "x3"]

    r_lte = db.table("items").select("*").lte("amount", 20).execute()
    assert sorted(r["id"] for r in r_lte.data) == ["x1", "x2"]


def test_select_like_case_sensitive_wildcards():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "name": "Alpha"},
            {"id": "x2", "name": "alpha"},
            {"id": "x3", "name": "Beta"},
        ],
    )

    # `%` → any-substring; case-sensitive
    result = db.table("items").select("*").like("name", "Al%").execute()

    ids = [r["id"] for r in result.data]
    assert ids == ["x1"]


def test_select_ilike_case_insensitive_wildcards():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "name": "Alpha"},
            {"id": "x2", "name": "alpha"},
            {"id": "x3", "name": "Beta"},
        ],
    )

    result = db.table("items").select("*").ilike("name", "AL%").execute()

    ids = sorted(r["id"] for r in result.data)
    assert ids == ["x1", "x2"]


def test_select_contains_list_subset_and_dict_subset():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "tags": ["red", "blue"], "meta": {"a": 1, "b": 2}},
            {"id": "x2", "tags": ["red"], "meta": {"a": 1}},
            {"id": "x3", "tags": ["green"], "meta": {"a": 2}},
        ],
    )

    r_list = db.table("items").select("*").contains("tags", ["red"]).execute()
    assert sorted(r["id"] for r in r_list.data) == ["x1", "x2"]

    r_dict = db.table("items").select("*").contains("meta", {"a": 1}).execute()
    assert sorted(r["id"] for r in r_dict.data) == ["x1", "x2"]


# ---------------------------------------------------------------------------
# Miss + empty-predicates edge cases
# ---------------------------------------------------------------------------


def test_select_with_no_predicates_returns_every_row():
    db = MockSupabaseClient(validate_schema=False)
    seed = [
        {"id": "x1", "status": "a"},
        {"id": "x2", "status": "b"},
    ]
    db.set_table_data("items", seed)

    result = db.table("items").select("*").execute()

    # Snapshot semantics — the returned list contains every seed row but is
    # not the same list object (no shared-mutation surprise via response.data).
    assert sorted(r["id"] for r in result.data) == ["x1", "x2"]


def test_select_no_match_returns_empty_list():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "a"},
            {"id": "x2", "status": "b"},
        ],
    )

    result = db.table("items").select("*").eq("status", "nope").execute()

    assert result.data == []


# ---------------------------------------------------------------------------
# Combined predicates — AND-conjunction
# ---------------------------------------------------------------------------


def test_select_combined_predicates_and_conjoin():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "active", "amount": 10},
            {"id": "x2", "status": "active", "amount": 20},
            {"id": "x3", "status": "archived", "amount": 30},
            {"id": "x4", "status": "active", "amount": 30},
        ],
    )

    result = (
        db.table("items")
        .select("*")
        .eq("status", "active")
        .gte("amount", 20)
        .execute()
    )

    ids = sorted(r["id"] for r in result.data)
    assert ids == ["x2", "x4"]


# ---------------------------------------------------------------------------
# .single() / .maybe_single() interaction with predicate filtering
# ---------------------------------------------------------------------------


def test_select_single_returns_first_filtered_row():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "a"},
            {"id": "x2", "status": "b"},
            {"id": "x3", "status": "b"},
        ],
    )

    result = (
        db.table("items").select("*").eq("status", "b").single().execute()
    )

    assert isinstance(result.data, dict)
    assert result.data["id"] == "x2"


def test_select_single_with_zero_matches_returns_falsey_empty():
    """`MockSupabaseResponse.__init__` normalizes None → `[]` (`data or []`).

    So `.single()` with zero filtered matches surfaces as falsey-empty rather
    than literal None — the existing module contract. Tests that depend on
    "no row" should check truthiness, not `is None`. UPDATE/DELETE share this
    behavior at `MockFilterBuilder.execute` and `_do_execute`.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "a"},
        ],
    )

    result = (
        db.table("items").select("*").eq("status", "nope").single().execute()
    )

    # Falsey-empty — the established cross-builder contract.
    assert not result.data


# ---------------------------------------------------------------------------
# Response-queue override — queue wins, predicate filter suppressed
# ---------------------------------------------------------------------------


def test_select_response_queue_wins_over_predicate_filter():
    """Queued response is dictated regardless of the literal seed/predicate.

    Mirrors the UPDATE/DELETE propagation-suppression contract: when a queue
    is set, the queue dictates the response shape, so tests can simulate
    error / empty / surprise responses without seeding the data layer.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "a"},
            {"id": "x2", "status": "b"},
        ],
    )
    # Override queue. After set_table_data the table is built fresh, so set
    # the queue AFTER seeding (set_table_data drops the existing builder).
    db.set_sequential_responses(
        "items",
        [MockSupabaseResponse(data=[{"id": "queued-only"}])],
    )

    # `.eq("status", "z")` would normally filter to zero rows; queue wins.
    result = db.table("items").select("*").eq("status", "z").execute()

    assert result.data == [{"id": "queued-only"}]


# ---------------------------------------------------------------------------
# Unknown-op match-all fallback (or_, fts, text_search, filter, overlaps,
# contained_by) — accumulated as predicates but evaluate match-all
# ---------------------------------------------------------------------------


def test_select_or_predicate_falls_back_to_match_all():
    """`or_` records as a synthetic predicate but evaluates as match-all.

    No PostgREST-expression parser exists; the contract is documented at
    `_PREDICATE_EVALUATORS` — unsupported ops return every row + debug log.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "a"},
            {"id": "x2", "status": "b"},
        ],
    )

    result = (
        db.table("items").select("*").or_("status.eq.never,status.eq.also-never").execute()
    )

    # Match-all fallback — both rows survive even though no row matches the
    # literal expression. Tests opting in via log-capture can see the debug.
    ids = sorted(r["id"] for r in result.data)
    assert ids == ["x1", "x2"]


def test_select_fts_text_search_filter_overlaps_contained_by_all_match_all():
    """All five unsupported ops accumulate predicates + return every row."""
    seed = [
        {"id": "x1", "txt": "hello", "tags": ["a"]},
        {"id": "x2", "txt": "world", "tags": ["b"]},
    ]

    for op_call in (
        lambda b: b.fts("txt", "hello"),
        lambda b: b.text_search("txt", "hello"),
        lambda b: b.filter("txt", "eq", "hello"),
        lambda b: b.overlaps("tags", ["a"]),
        lambda b: b.contained_by("tags", ["a", "b", "c"]),
    ):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("items", [dict(r) for r in seed])
        builder = db.table("items").select("*")
        builder = op_call(builder)
        result = builder.execute()

        # Match-all fallback — both rows survive.
        ids = sorted(r["id"] for r in result.data)
        assert ids == ["x1", "x2"], f"op produced wrong fallback: {ids}"


# ---------------------------------------------------------------------------
# Write-then-filter — INSERT propagation + SELECT predicate compose
# ---------------------------------------------------------------------------


def test_select_after_insert_then_filter_sees_only_matching_inserted_row():
    """Closes the AdConnect-pattern verification gap: insert-then-select-with-eq.

    Before the fix, insert propagation worked but `.eq()` was ignored on
    SELECT, so this assertion would have included the second inserted row.
    """
    db = MockSupabaseClient(validate_schema=False)
    tbl = db.table("appointments")
    tbl.insert({"id": "a1", "status": "waiting"}).execute()
    tbl.insert({"id": "a2", "status": "done"}).execute()

    result = tbl.select("*").eq("status", "waiting").execute()

    ids = [r["id"] for r in result.data]
    assert ids == ["a1"]


def test_select_match_decomposes_to_eq_and_filters():
    """`match({col: val})` is decomposed to `eq` predicates at record time, so
    it filters literally even though `match` is not in `_PREDICATE_EVALUATORS`.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "a", "tier": "gold"},
            {"id": "x2", "status": "a", "tier": "silver"},
            {"id": "x3", "status": "b", "tier": "gold"},
        ],
    )

    result = (
        db.table("items").select("*").match({"status": "a", "tier": "gold"}).execute()
    )

    ids = [r["id"] for r in result.data]
    assert ids == ["x1"]


def test_select_filter_returns_snapshot_not_shared_reference():
    """`response.data` is a fresh list, so accidentally mutating it doesn't
    leak into subsequent SELECT calls. Mirrors the safety contract
    `MockRequestBuilder.__init__` provides via the deep-copy of seeded data.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "items",
        [
            {"id": "x1", "status": "a"},
            {"id": "x2", "status": "b"},
        ],
    )

    first = db.table("items").select("*").execute()
    first.data.append({"id": "intruder"})

    second = db.table("items").select("*").execute()

    ids = sorted(r["id"] for r in second.data)
    assert ids == ["x1", "x2"]
