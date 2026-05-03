"""Unit tests for noctusai_lib.notifications field mapping.

Pure functions; no DB, no network. The mapper is the boundary between
core's English notification schema and every product's Portuguese API.
"""
from noctusai_lib.domain.notifications import (
    map_notification_to_pt,
    map_notification_from_pt,
)


class TestMapNotificationToPt:
    def test_renames_english_keys_to_portuguese(self):
        record = {"type": "invite", "title": "Hello", "message": "Hi", "read": False}
        out = map_notification_to_pt(record)
        assert out["tipo"] == "invite"
        assert out["titulo"] == "Hello"
        assert out["mensagem"] == "Hi"
        assert out["is_read"] is False

    def test_passes_through_unknown_keys(self):
        record = {"id": "abc", "created_at": "2026-04-21", "custom": 42}
        out = map_notification_to_pt(record)
        assert out["id"] == "abc"
        assert out["created_at"] == "2026-04-21"
        assert out["custom"] == 42

    def test_extracts_link_from_metadata_dict(self):
        out = map_notification_to_pt({"metadata": {"link": "/inbox/1"}})
        assert out["link"] == "/inbox/1"

    def test_link_is_none_when_metadata_missing(self):
        out = map_notification_to_pt({"id": "x"})
        assert out["link"] is None

    def test_link_is_none_when_metadata_is_not_a_dict(self):
        out = map_notification_to_pt({"metadata": "not-a-dict"})
        assert out["link"] is None

    def test_link_is_none_when_metadata_dict_has_no_link_key(self):
        out = map_notification_to_pt({"metadata": {"other": "value"}})
        assert out["link"] is None

    def test_empty_record_still_sets_link_key(self):
        out = map_notification_to_pt({})
        assert "link" in out
        assert out["link"] is None


class TestMapNotificationFromPt:
    def test_renames_portuguese_keys_to_english(self):
        data = {"tipo": "invite", "titulo": "Hi", "mensagem": "M", "is_read": True}
        out = map_notification_from_pt(data)
        assert out["type"] == "invite"
        assert out["title"] == "Hi"
        assert out["message"] == "M"
        assert out["read"] is True

    def test_passes_through_unknown_keys(self):
        out = map_notification_from_pt({"user_id": "u-1", "extra": 9})
        assert out["user_id"] == "u-1"
        assert out["extra"] == 9

    def test_round_trip_preserves_known_fields(self):
        original = {"type": "t", "title": "ti", "message": "msg", "read": False}
        pt = map_notification_to_pt(original)
        pt.pop("link", None)  # round-trip doesn't re-synthesize metadata
        back = map_notification_from_pt(pt)
        assert back == original
