"""Tests for Mailchimp pure-function mappers.

Covers:
- ``subscriber_hash``: MD5 hash vector (normalisation, padding).
- ``parse_server_prefix``: happy-path variants + malformed key errors.
- ``template_edit_url``: URL shape.
- ``raw_to_audience`` / ``raw_to_member`` / ``raw_to_segment`` /
  ``raw_to_template`` / ``raw_to_campaign``: round-trip checks.
"""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.mailchimp.mappers import (
    parse_server_prefix,
    raw_to_audience,
    raw_to_campaign,
    raw_to_member,
    raw_to_segment,
    raw_to_template,
    subscriber_hash,
    template_edit_url,
)


# ---------------------------------------------------------------------------
# subscriber_hash
# ---------------------------------------------------------------------------


def test_hash_known_vector() -> None:
    # MD5("test@example.com") = 55502f40dc8b7c769880b10874abc9d0
    assert subscriber_hash("test@example.com") == "55502f40dc8b7c769880b10874abc9d0"


def test_hash_lowercases_before_hashing() -> None:
    assert subscriber_hash("Test@Example.COM") == subscriber_hash("test@example.com")


def test_hash_strips_whitespace() -> None:
    assert subscriber_hash("  test@example.com  ") == subscriber_hash("test@example.com")


def test_hash_uppercase_input_matches_known_vector() -> None:
    assert subscriber_hash("TEST@EXAMPLE.COM") == "55502f40dc8b7c769880b10874abc9d0"


def test_hash_is_32_hex_chars() -> None:
    h = subscriber_hash("foo@bar.com")
    assert len(h) == 32
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# parse_server_prefix
# ---------------------------------------------------------------------------


def test_parse_prefix_us6() -> None:
    assert parse_server_prefix("mytoken123-us6") == "us6"


def test_parse_prefix_eu1() -> None:
    assert parse_server_prefix("abc-eu1") == "eu1"


def test_parse_prefix_us19() -> None:
    assert parse_server_prefix("longertoken-us19") == "us19"


def test_parse_prefix_with_many_hyphens_uses_last_segment() -> None:
    # Key with multiple dashes; only the LAST segment is the dc.
    assert parse_server_prefix("abc-def-us6") == "us6"


def test_parse_prefix_raises_on_empty_string() -> None:
    with pytest.raises(ValueError, match="Malformed"):
        parse_server_prefix("")


def test_parse_prefix_raises_on_no_hyphen() -> None:
    with pytest.raises(ValueError, match="Malformed"):
        parse_server_prefix("mytoken123")


def test_parse_prefix_raises_on_trailing_hyphen() -> None:
    with pytest.raises(ValueError, match="Malformed"):
        parse_server_prefix("mytoken-")


# ---------------------------------------------------------------------------
# template_edit_url
# ---------------------------------------------------------------------------


def test_template_edit_url_shape() -> None:
    url = template_edit_url("us6", 12345)
    assert url == "https://us6.admin.mailchimp.com/templates/edit?id=12345"


def test_template_edit_url_eu1() -> None:
    url = template_edit_url("eu1", 99)
    assert url.startswith("https://eu1.admin.mailchimp.com")
    assert "?id=99" in url


# ---------------------------------------------------------------------------
# raw_to_audience
# ---------------------------------------------------------------------------


def test_raw_to_audience_extracts_fields() -> None:
    raw = {
        "id": "aud-001",
        "name": "My Audience",
        "stats": {"member_count": 42},
    }
    audience = raw_to_audience(raw)
    assert audience.id == "aud-001"
    assert audience.name == "My Audience"
    assert audience.member_count == 42
    assert audience.raw is raw


def test_raw_to_audience_missing_stats_defaults_zero() -> None:
    raw = {"id": "aud-002", "name": "Empty", "stats": {}}
    audience = raw_to_audience(raw)
    assert audience.member_count == 0


# ---------------------------------------------------------------------------
# raw_to_member
# ---------------------------------------------------------------------------


def test_raw_to_member_extracts_merge_fields() -> None:
    raw = {
        "email_address": "alice@example.com",
        "status": "subscribed",
        "merge_fields": {"FNAME": "Alice", "LNAME": "Smith"},
        "tags": [{"id": 1, "name": "vip"}],
        "vip": True,
        "last_changed": "2024-01-15T12:00:00+00:00",
    }
    member = raw_to_member(raw)
    assert member.email == "alice@example.com"
    assert member.first_name == "Alice"
    assert member.last_name == "Smith"
    assert "vip" in member.tags
    assert member.vip is True
    assert member.last_changed is not None


def test_raw_to_member_empty_tags_list() -> None:
    raw = {
        "email_address": "bob@example.com",
        "status": "unsubscribed",
        "merge_fields": {},
        "tags": [],
        "vip": False,
    }
    member = raw_to_member(raw)
    assert member.tags == []


def test_raw_to_member_string_tags_list() -> None:
    """Tags as plain strings (some older API responses use this shape)."""
    raw = {
        "email_address": "carol@example.com",
        "status": "subscribed",
        "merge_fields": {},
        "tags": ["tag-a", "tag-b"],
        "vip": False,
    }
    member = raw_to_member(raw)
    assert set(member.tags) == {"tag-a", "tag-b"}


def test_raw_to_member_null_last_changed() -> None:
    raw = {
        "email_address": "dave@example.com",
        "status": "pending",
        "merge_fields": {},
        "tags": [],
        "vip": False,
        "last_changed": None,
    }
    member = raw_to_member(raw)
    assert member.last_changed is None


# ---------------------------------------------------------------------------
# raw_to_segment
# ---------------------------------------------------------------------------


def test_raw_to_segment_extracts_fields() -> None:
    raw = {
        "id": 7,
        "name": "Segment A",
        "member_count": 5,
        "created_at": "2024-02-01T00:00:00+00:00",
        "updated_at": "2024-02-05T00:00:00+00:00",
    }
    segment = raw_to_segment(raw)
    assert segment.id == 7
    assert segment.name == "Segment A"
    assert segment.member_count == 5
    assert segment.created_at is not None
    assert segment.updated_at is not None


# ---------------------------------------------------------------------------
# raw_to_template
# ---------------------------------------------------------------------------


def test_raw_to_template_computes_edit_url() -> None:
    raw = {
        "id": 42,
        "name": "My Template",
        "category": "",
        "type": "user",
        "drag_and_drop": False,
        "thumbnail": "https://mc.example.com/thumb.png",
        "date_created": "2024-01-01T00:00:00+00:00",
        "date_edited": "2024-01-02T00:00:00+00:00",
    }
    tmpl = raw_to_template(raw, server_prefix="us6")
    assert tmpl.id == 42
    assert tmpl.edit_url == "https://us6.admin.mailchimp.com/templates/edit?id=42"
    assert tmpl.preview_image == "https://mc.example.com/thumb.png"


def test_raw_to_template_no_prefix_empty_edit_url() -> None:
    raw = {"id": 1, "name": "T", "type": "user", "drag_and_drop": False}
    tmpl = raw_to_template(raw)
    assert tmpl.edit_url == ""


# ---------------------------------------------------------------------------
# raw_to_campaign
# ---------------------------------------------------------------------------


def test_raw_to_campaign_extracts_nested_fields() -> None:
    raw = {
        "id": "camp-001",
        "web_id": 999,
        "status": "save",
        "emails_sent": 0,
        "archive_url": "https://mailchi.mp/test",
        "settings": {
            "title": "My Campaign",
            "subject_line": "Hello",
            "preview_text": "Preview",
            "from_name": "Sender",
            "reply_to": "reply@example.com",
            "template_id": 5,
        },
        "recipients": {
            "list_id": "aud-001",
            "segment_opts": {"saved_segment_id": 3},
        },
        "report_summary": {"opens": 10, "clicks": 2},
    }
    campaign = raw_to_campaign(raw)
    assert campaign.id == "camp-001"
    assert campaign.title == "My Campaign"
    assert campaign.segment_id == 3
    assert campaign.template_id == 5
    assert campaign.opens == 10
    assert campaign.clicks == 2


def test_raw_to_campaign_no_segment_opts() -> None:
    raw = {
        "id": "camp-002",
        "web_id": 0,
        "status": "sent",
        "emails_sent": 100,
        "archive_url": "",
        "settings": {
            "title": "Simple",
            "subject_line": "Hi",
            "preview_text": "",
            "from_name": "X",
            "reply_to": "x@x.com",
        },
        "recipients": {"list_id": "aud-001"},
        "report_summary": {},
    }
    campaign = raw_to_campaign(raw)
    assert campaign.segment_id is None
    assert campaign.template_id is None
    assert campaign.opens is None
    assert campaign.clicks is None
