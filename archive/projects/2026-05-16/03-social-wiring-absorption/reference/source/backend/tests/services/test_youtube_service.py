"""Tests for youtube_service — focus on pure-logic helpers (no network)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.credential_store import CredentialStore
from app.services.youtube_service import (
    YOUTUBE_SCOPES,
    YouTubeService,
    YouTubeServiceError,
    _bundle_to_credentials,
    _credentials_to_bundle,
    _parse_published_at,
    _video_item_to_summary,
)
from cryptography.fernet import Fernet


class TestCredentialsBundleRoundTrip:
    def test_bundle_to_credentials_carries_token_fields(self):
        bundle = {
            "access_token": "ya29.X",
            "refresh_token": "1//RT",
            "expires_at": "2026-05-06T13:00:00+00:00",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": YOUTUBE_SCOPES,
        }
        creds = _bundle_to_credentials(bundle, "cid", "csecret")
        assert creds.token == "ya29.X"
        assert creds.refresh_token == "1//RT"
        assert creds.client_id == "cid"
        assert creds.client_secret == "csecret"
        assert creds.token_uri == "https://oauth2.googleapis.com/token"
        # google-auth keeps expiry naive — we strip tz on the way in.
        assert creds.expiry is not None
        assert creds.expiry.tzinfo is None

    def test_credentials_to_bundle_serialises_expiry(self):
        creds = MagicMock()
        creds.token = "tok"
        creds.refresh_token = "rt"
        creds.expiry = datetime(2026, 5, 6, 13, 0, 0)
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.scopes = YOUTUBE_SCOPES
        bundle = _credentials_to_bundle(creds)
        assert bundle["access_token"] == "tok"
        assert bundle["refresh_token"] == "rt"
        # naive expiry gets normalised to UTC ISO string.
        assert bundle["expires_at"].endswith("+00:00")

    def test_malformed_expiry_falls_back_to_expired(self):
        bundle = {
            "access_token": "x",
            "refresh_token": "rt",
            "expires_at": "garbage-not-iso",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": YOUTUBE_SCOPES,
        }
        creds = _bundle_to_credentials(bundle, "cid", "csecret")
        # Should not raise — credential_store wraps the failure in
        # CredentialStoreError, but YouTube path treats malformed as
        # expired so the refresh kicks in.
        assert creds.expiry is not None


class TestVideoItemMapping:
    def test_full_video_item_extracts_subset(self):
        item = {
            "id": "abc123",
            "snippet": {
                "title": "Test Video",
                "description": "A description",
                "publishedAt": "2026-05-01T10:00:00Z",
                "thumbnails": {
                    "high": {"url": "https://img.example/high.jpg"},
                    "medium": {"url": "https://img.example/medium.jpg"},
                },
                "tags": ["tag1", "tag2"],
                "categoryId": "22",
            },
            "statistics": {
                "viewCount": "1500",
                "likeCount": "42",
                "commentCount": "7",
            },
            "status": {"privacyStatus": "public"},
            "contentDetails": {"duration": "PT3M45S"},
        }
        summary = _video_item_to_summary(item)
        assert summary.video_id == "abc123"
        assert summary.title == "Test Video"
        assert summary.thumbnail_url == "https://img.example/high.jpg"
        assert summary.view_count == 1500
        assert summary.like_count == 42
        assert summary.comment_count == 7
        assert summary.privacy_status == "public"
        assert summary.duration == "PT3M45S"
        assert summary.tags == ["tag1", "tag2"]

    def test_missing_thumbnails_yields_empty_url(self):
        item = {
            "id": "x",
            "snippet": {"title": "t", "publishedAt": "2026-01-01T00:00:00Z"},
            "statistics": {},
            "status": {},
            "contentDetails": {},
        }
        summary = _video_item_to_summary(item)
        assert summary.thumbnail_url == ""

    def test_picks_max_resolution_thumbnail(self):
        item = {
            "id": "x",
            "snippet": {
                "title": "t",
                "publishedAt": "2026-01-01T00:00:00Z",
                "thumbnails": {
                    "default": {"url": "low.jpg"},
                    "medium": {"url": "mid.jpg"},
                    "maxres": {"url": "best.jpg"},
                },
            },
            "statistics": {},
            "status": {},
            "contentDetails": {},
        }
        summary = _video_item_to_summary(item)
        assert summary.thumbnail_url == "best.jpg"

    def test_missing_published_at_yields_epoch(self):
        item = {
            "id": "x",
            "snippet": {"title": "t"},
            "statistics": {},
            "status": {},
            "contentDetails": {},
        }
        summary = _video_item_to_summary(item)
        assert summary.published_at == datetime.fromtimestamp(0, tz=timezone.utc)


class TestParsePublishedAt:
    def test_iso_z_suffix_resolves_to_utc(self):
        result = _parse_published_at("2026-05-06T12:00:00Z")
        assert result.tzinfo is not None
        assert result.tzinfo.utcoffset(result).total_seconds() == 0


class TestYouTubeServiceConstruction:
    def test_missing_credentials_raises(self):
        store = CredentialStore(MagicMock(), Fernet.generate_key().decode())
        with pytest.raises(YouTubeServiceError):
            YouTubeService(
                client_id="",
                client_secret="",
                redirect_uri="http://localhost/cb",
                credential_store=store,
            )
