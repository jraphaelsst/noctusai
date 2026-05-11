"""
Unit tests for ``app.services._bulk.bulk_lookup``.

Exercises the four return shapes + edge cases:
- scalar return (default ``value_cols="name"``)
- dict return (multi-col)
- empty ids short-circuit
- falsy/duplicate id filtering
- custom ``key_col``
- integration with the canonical ``MockSupabaseClient`` (seed-real-data,
  per "no monkey-patching" rule).
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services._bulk import bulk_lookup


def _client():
    return MockSupabaseClient(validate_schema=False, schema="therapy")


class TestBulkLookupScalar:
    def test_returns_id_to_scalar_map(self):
        db = _client()
        db.set_table_data("clinics", [
            {"id": "c1", "name": "Alpha"},
            {"id": "c2", "name": "Beta"},
        ])
        result = bulk_lookup(db, "clinics", ["c1", "c2"], value_cols="name")
        assert result == {"c1": "Alpha", "c2": "Beta"}

    def test_multiple_ids_all_resolve(self):
        db = _client()
        db.set_table_data("clinics", [
            {"id": "c1", "name": "Alpha"},
            {"id": "c2", "name": "Beta"},
            {"id": "c3", "name": "Gamma"},
        ])
        result = bulk_lookup(
            db, "clinics", ["c1", "c2", "c3"], value_cols="name",
        )
        assert result == {"c1": "Alpha", "c2": "Beta", "c3": "Gamma"}

    def test_missing_value_col_is_none(self):
        db = _client()
        db.set_table_data("clinics", [
            {"id": "c1"},  # no name column
        ])
        result = bulk_lookup(db, "clinics", ["c1"], value_cols="name")
        assert result == {"c1": None}


class TestBulkLookupDict:
    def test_returns_id_to_col_dict(self):
        db = _client()
        db.set_table_data("messages", [
            {"id": "m1", "content": "hello", "message_type": "text"},
            {"id": "m2", "content": "world", "message_type": "system"},
        ])
        result = bulk_lookup(
            db, "messages", ["m1", "m2"],
            value_cols=["content", "message_type"],
        )
        assert result == {
            "m1": {"content": "hello", "message_type": "text"},
            "m2": {"content": "world", "message_type": "system"},
        }

    def test_missing_col_is_none_in_dict(self):
        db = _client()
        db.set_table_data("messages", [
            {"id": "m1", "content": "hello"},  # no message_type
        ])
        result = bulk_lookup(
            db, "messages", ["m1"],
            value_cols=["content", "message_type"],
        )
        assert result == {"m1": {"content": "hello", "message_type": None}}


class TestBulkLookupEdgeCases:
    def test_empty_ids_short_circuits_to_empty_dict(self):
        db = _client()
        # No table data needed — should never hit the DB.
        result = bulk_lookup(db, "clinics", [], value_cols="name")
        assert result == {}

    def test_all_falsy_ids_short_circuits(self):
        db = _client()
        result = bulk_lookup(db, "clinics", [None, "", None], value_cols="name")
        assert result == {}

    def test_falsy_ids_filtered_out(self):
        db = _client()
        db.set_table_data("clinics", [
            {"id": "c1", "name": "Alpha"},
        ])
        result = bulk_lookup(
            db, "clinics", [None, "c1", "", "c1"],
            value_cols="name",
        )
        # Duplicates collapsed; falsy filtered.
        assert result == {"c1": "Alpha"}

    def test_no_matching_rows_returns_empty_dict(self):
        db = _client()
        db.set_table_data("clinics", [])
        result = bulk_lookup(db, "clinics", ["c1"], value_cols="name")
        assert result == {}


class TestBulkLookupKeyCol:
    def test_custom_key_col(self):
        db = _client()
        db.set_table_data("therapist_profiles", [
            {"user_id": "u1", "display_name": "Dr. A"},
            {"user_id": "u2", "display_name": "Dr. B"},
        ])
        result = bulk_lookup(
            db, "therapist_profiles", ["u1", "u2"],
            key_col="user_id", value_cols="display_name",
        )
        assert result == {"u1": "Dr. A", "u2": "Dr. B"}

    def test_custom_key_col_dict_shape(self):
        db = _client()
        db.set_table_data("therapist_profiles", [
            {"user_id": "u1", "display_name": "Dr. A", "specialty": "CBT"},
        ])
        result = bulk_lookup(
            db, "therapist_profiles", ["u1"],
            key_col="user_id",
            value_cols=["display_name", "specialty"],
        )
        assert result == {"u1": {"display_name": "Dr. A", "specialty": "CBT"}}
