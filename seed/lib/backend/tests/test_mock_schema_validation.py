"""Unit tests for MockSupabaseClient schema validation (Phase 2 wiring).

Covers:
  - Every filter method raises MockSchemaError on invalid column (red path)
  - Every filter method returns self on valid column (green path / chainable)
  - Bare-tablename → public coercion
  - .schema("foo").from_("bar") binds correctly
  - .select("col1,col2") validates each
  - .insert/.update/.upsert payload keys validated (Q3)
  - validate_schema=False (default) preserves the old blind-spot behavior
  - Unknown-table → no raise (Q4 WARN+skip)
  - `or_` complex-expression skipped (known limitation)
"""
from __future__ import annotations

import pytest

from noctusai_lib.testing import (
    MockSchemaError,
    MockSupabaseClient,
    set_cache_for_tests,
    reset_cache,
)


@pytest.fixture(autouse=True)
def schema_cache():
    set_cache_for_tests(
        {
            "therapy.session_summary_versions": {
                "id",
                "session_record_id",
                "track",
                "version_number",
                "summary",
                "key_points",
                "tags",
                "source",
                "observation_snapshot_ids",
                "created_at",
            },
            "therapy.session_records": {
                "id",
                "appointment_id",
                "combined_transcript_text",
                "therapist_notes_private",
                "total_segments",
                "ai_generated_at",
                "audio_deleted_at",
                "created_at",
            },
            "public.notifications": {
                "id",
                "user_id",
                "org_id",
                "type",
                "title",
                "message",
                "metadata",
                "read",
                "created_at",
            },
        }
    )
    yield
    reset_cache()


# ---------------------------------------------------------------------------
# Default behavior (validate_schema=False) — no validation, old behavior preserved
# ---------------------------------------------------------------------------


def test_default_validate_schema_true_raises_on_invalid_col():
    """Phase 4 flipped default → True. Tests that want to opt OUT must pass
    `validate_schema=False` explicitly (and should document why in a comment)."""
    client = MockSupabaseClient()  # default validate_schema=True
    with pytest.raises(MockSchemaError):
        client.schema("therapy").from_("session_summary_versions").delete().eq(
            "session_id", "abc"
        ).execute()


def test_explicit_opt_out_still_works():
    """Products with schema drift still need the escape hatch."""
    client = MockSupabaseClient(validate_schema=False)
    client.schema("therapy").from_("session_summary_versions").delete().eq(
        "session_id", "abc"
    ).execute()
    # No raise → test passes.


# ---------------------------------------------------------------------------
# The compliance-audit silent-fail now surfaces loudly
# ---------------------------------------------------------------------------


def test_compliance_audit_silent_fail_is_caught():
    """This is the archetypal bug the project closes. lgpd_service.py did:
        client.schema('therapy').from_('session_summary_versions')
              .delete().eq('session_id', sid).execute()
    where `session_id` does not exist. Old mock accepted it silently;
    validator now raises."""
    client = MockSupabaseClient(validate_schema=True)
    with pytest.raises(MockSchemaError) as excinfo:
        client.schema("therapy").from_("session_summary_versions").delete().eq(
            "session_id", "abc"
        ).execute()
    err = excinfo.value
    assert err.table == "session_summary_versions"
    assert err.invalid_column == "session_id"
    assert err.schema == "therapy"
    assert "session_record_id" in err.valid_columns


def test_compliance_audit_second_silent_fail_is_caught():
    """session_summary_versions has no 'therapist_id' either (another lgpd_service bug)."""
    client = MockSupabaseClient(validate_schema=True)
    with pytest.raises(MockSchemaError):
        client.schema("therapy").from_("session_summary_versions").delete().eq(
            "therapist_id", "abc"
        ).execute()


# ---------------------------------------------------------------------------
# Valid column → chainable, no raise
# ---------------------------------------------------------------------------


def test_valid_column_eq_returns_chainable():
    client = MockSupabaseClient(validate_schema=True)
    result = (
        client.schema("therapy")
        .from_("session_summary_versions")
        .delete()
        .eq("session_record_id", "abc")
        .execute()
    )
    assert result.data == []  # default empty data, no data set


# ---------------------------------------------------------------------------
# Every filter method, parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,args",
    [
        ("eq", ("bad_col", "v")),
        ("neq", ("bad_col", "v")),
        ("in_", ("bad_col", ["a"])),
        ("gt", ("bad_col", 1)),
        ("lt", ("bad_col", 1)),
        ("gte", ("bad_col", 1)),
        ("lte", ("bad_col", 1)),
        ("ilike", ("bad_col", "%x%")),
        ("like", ("bad_col", "%x%")),
        ("is_", ("bad_col", None)),
        ("contains", ("bad_col", [1])),
        ("contained_by", ("bad_col", [1])),
        ("overlaps", ("bad_col", [1])),
        ("fts", ("bad_col", "term")),
        ("text_search", ("bad_col", "term")),
        ("filter", ("bad_col", "eq", "v")),
    ],
)
def test_every_filter_method_raises_on_invalid_col(method, args):
    client = MockSupabaseClient(validate_schema=True)
    q = (
        client.schema("therapy")
        .from_("session_summary_versions")
        .select("*")
    )
    with pytest.raises(MockSchemaError):
        getattr(q, method)(*args)


def test_match_dict_raises_on_bad_key():
    client = MockSupabaseClient(validate_schema=True)
    q = client.schema("therapy").from_("session_summary_versions").select("*")
    with pytest.raises(MockSchemaError):
        q.match({"bad_col": "v"})


def test_match_dict_accepts_valid_keys():
    client = MockSupabaseClient(validate_schema=True)
    q = client.schema("therapy").from_("session_summary_versions").select("*")
    q.match({"session_record_id": "abc", "track": "base"}).execute()


def test_order_on_invalid_column_raises():
    client = MockSupabaseClient(validate_schema=True)
    q = client.schema("therapy").from_("session_summary_versions").select("*")
    with pytest.raises(MockSchemaError):
        q.order("bad_col")


def test_order_on_valid_column_ok():
    client = MockSupabaseClient(validate_schema=True)
    client.schema("therapy").from_("session_summary_versions").select("*").order(
        "version_number", desc=True
    ).execute()


# ---------------------------------------------------------------------------
# .select("col1,col2") validates each
# ---------------------------------------------------------------------------


def test_select_with_comma_list_validates_each():
    client = MockSupabaseClient(validate_schema=True)
    with pytest.raises(MockSchemaError) as excinfo:
        client.schema("therapy").from_("session_summary_versions").select(
            "id, session_record_id, bogus"
        )
    assert excinfo.value.invalid_column == "bogus"


def test_select_star_passes():
    client = MockSupabaseClient(validate_schema=True)
    client.schema("therapy").from_("session_summary_versions").select("*").execute()


def test_select_valid_cols_pass():
    client = MockSupabaseClient(validate_schema=True)
    client.schema("therapy").from_("session_summary_versions").select(
        "id, session_record_id, track"
    ).execute()


def test_select_with_joined_shape_skips_validation():
    """PostgREST nested selects like 'id, sessions!inner(id,ref)' have
    complex shapes; we don't attempt to parse the join — bail."""
    client = MockSupabaseClient(validate_schema=True)
    # Must not raise even though "therapy.something_weird(id)" isn't validatable.
    client.schema("therapy").from_("session_summary_versions").select(
        "id, sessions!inner(id)"
    ).execute()


def test_select_star_plus_join_does_not_treat_star_as_column():
    """Regression for core `.select('*, products(*)')` pattern — star IS a
    valid sentinel even when mixed with a join projection."""
    client = MockSupabaseClient(validate_schema=True)
    # public.notifications does not have a column literally named `*`; parser
    # must recognize the star + join shape and bail.
    client.from_("notifications").select("*, products(*)").execute()
    client.from_("notifications").select("*, products(*), organizations(*)").execute()


# ---------------------------------------------------------------------------
# Payload-key validation on insert/update/upsert (Q3)
# ---------------------------------------------------------------------------


def test_insert_payload_keys_validated():
    client = MockSupabaseClient(validate_schema=True)
    with pytest.raises(MockSchemaError) as excinfo:
        client.schema("therapy").from_("session_records").insert(
            {"id": "abc", "therapist_id": "xyz"}  # therapist_id not on this table
        )
    assert excinfo.value.invalid_column == "therapist_id"
    assert excinfo.value.operation == "insert"


def test_insert_valid_payload_ok():
    client = MockSupabaseClient(validate_schema=True)
    client.schema("therapy").from_("session_records").insert(
        {"id": "abc", "appointment_id": "xyz"}
    ).execute()


def test_insert_batch_payload_validates_each_row():
    client = MockSupabaseClient(validate_schema=True)
    with pytest.raises(MockSchemaError):
        client.schema("therapy").from_("session_records").insert(
            [
                {"id": "abc", "appointment_id": "xyz"},  # valid
                {"id": "def", "patient_id": "bad"},  # invalid key
            ]
        )


def test_update_payload_validated():
    client = MockSupabaseClient(validate_schema=True)
    with pytest.raises(MockSchemaError):
        client.schema("therapy").from_("session_records").update(
            {"bogus_field": "v"}
        ).eq("id", "abc")


def test_upsert_payload_validated():
    client = MockSupabaseClient(validate_schema=True)
    with pytest.raises(MockSchemaError):
        client.schema("therapy").from_("session_records").upsert(
            {"bogus": "v"}
        )


# ---------------------------------------------------------------------------
# Bare tablename → public coercion
# ---------------------------------------------------------------------------


def test_bare_tablename_uses_public_schema():
    client = MockSupabaseClient(validate_schema=True)
    # `public.notifications` has `user_id` but not `patient_id`.
    with pytest.raises(MockSchemaError) as excinfo:
        client.from_("notifications").select("*").eq("patient_id", "abc")
    assert excinfo.value.schema == "public"
    # Valid column works:
    client.from_("notifications").select("*").eq("user_id", "abc").execute()


# ---------------------------------------------------------------------------
# Unknown-table fallback (Q4 WARN+skip)
# ---------------------------------------------------------------------------


def test_unknown_table_does_not_raise():
    """Table not in cache → validator silently skips (Q4 WARN+skip).
    The compliance audit's SECOND class of bug (typo'd table name) is out
    of scope here — this project closes COLUMNS, not TABLES."""
    client = MockSupabaseClient(validate_schema=True)
    # notarealtable doesn't exist in cache
    client.schema("therapy").from_("notarealtable").select("*").eq(
        "any_col", "v"
    ).execute()


# ---------------------------------------------------------------------------
# Tier 1.5 G4 — strict_unknown_tables=True opt-in
# ---------------------------------------------------------------------------


class TestStrictUnknownTables:
    """When strict_unknown_tables=True, unknown-table queries raise instead
    of WARN+skip. Opt-in for products that have completed schema-drift
    reconciliation; default stays False to preserve existing behavior."""

    def test_default_off_preserves_warn_skip(self):
        """Default mode unchanged: unknown table → silent skip."""
        from noctusai_lib.testing import MockSupabaseClient
        client = MockSupabaseClient(validate_schema=True)
        # nonexistent table → no raise
        client.schema("therapy").from_("imaginary_table").select("*").eq(
            "x", "v"
        ).execute()

    def test_strict_on_unknown_table_raises_unknown_table_error(self):
        from noctusai_lib.testing import (
            MockSupabaseClient, MockUnknownTableError,
        )
        client = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True)
        with pytest.raises(MockUnknownTableError) as excinfo:
            client.schema("therapy").from_("imaginary_table").select("*").eq(
                "x", "v"
            )
        err = excinfo.value
        assert err.table == "imaginary_table"
        assert err.schema == "therapy"
        assert "does not exist in any migration file" in str(err)

    def test_strict_unknown_table_subclasses_schema_error(self):
        """`except MockSchemaError` must catch `MockUnknownTableError` too."""
        from noctusai_lib.testing import MockSchemaError, MockSupabaseClient
        client = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True)
        with pytest.raises(MockSchemaError):
            client.schema("therapy").from_("imaginary_table").select("*").eq(
                "x", "v"
            )

    def test_strict_known_table_still_works_normally(self):
        """Strict mode does not change behavior for known tables."""
        from noctusai_lib.testing import MockSupabaseClient
        client = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True)
        # therapy.session_records IS in the cache (test fixture above)
        client.schema("therapy").from_("session_records").select("*").eq(
            "appointment_id", "abc"
        ).execute()

    def test_strict_known_table_still_catches_bad_column(self):
        """Strict mode + known table + bad column → still MockSchemaError."""
        from noctusai_lib.testing import MockSchemaError, MockSupabaseClient
        client = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True)
        with pytest.raises(MockSchemaError):
            client.schema("therapy").from_("session_records").select("*").eq(
                "no_such_col", "v"
            )

    def test_strict_select_on_unknown_table_raises(self):
        """`.select("*")` on an unknown table also raises in strict mode."""
        from noctusai_lib.testing import MockSupabaseClient, MockUnknownTableError
        client = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True)
        with pytest.raises(MockUnknownTableError):
            client.schema("therapy").from_("imaginary_table").select("*")

    def test_strict_insert_on_unknown_table_raises(self):
        from noctusai_lib.testing import MockSupabaseClient, MockUnknownTableError
        client = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True)
        with pytest.raises(MockUnknownTableError):
            client.schema("therapy").from_("imaginary_table").insert({"foo": "bar"})

    def test_strict_propagates_through_schema_chain(self):
        """`.schema(name).from_(table)` must carry the flag."""
        from noctusai_lib.testing import MockSupabaseClient, MockUnknownTableError
        client = MockSupabaseClient(validate_schema=True, strict_unknown_tables=True)
        # .schema('public') chain inherits strict mode
        with pytest.raises(MockUnknownTableError):
            client.schema("public").from_("imaginary_table").select("*")


# ---------------------------------------------------------------------------
# or_ expression — known limitation, should not false-positive
# ---------------------------------------------------------------------------


def test_or_complex_expression_skipped():
    client = MockSupabaseClient(validate_schema=True)
    # PostgREST or_ expression: should not attempt validation.
    client.schema("therapy").from_("session_records").select("*").or_(
        "id.eq.abc,appointment_id.eq.xyz"
    ).execute()


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


def test_error_message_lists_valid_columns():
    client = MockSupabaseClient(validate_schema=True)
    try:
        client.schema("therapy").from_("session_summary_versions").delete().eq(
            "session_id", "abc"
        ).execute()
        assert False, "expected MockSchemaError"
    except MockSchemaError as exc:
        msg = str(exc)
        assert "therapy.session_summary_versions" in msg
        assert "session_id" in msg
        # The valid-column list names the real column the caller probably meant:
        assert "session_record_id" in msg


# ---------------------------------------------------------------------------
# Chaining preserved
# ---------------------------------------------------------------------------


def test_filter_methods_still_chainable():
    client = MockSupabaseClient(validate_schema=True)
    q = (
        client.schema("therapy")
        .from_("session_summary_versions")
        .select("*")
        .eq("session_record_id", "abc")
        .neq("track", "base")
        .order("version_number", desc=True)
        .limit(10)
    )
    result = q.execute()
    assert result.data == []
