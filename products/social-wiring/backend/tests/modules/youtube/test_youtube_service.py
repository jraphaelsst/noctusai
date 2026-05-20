"""Tests for youtube_service — focus on pure-logic helpers (no network)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.youtube import VideoFull
from noctusai_lib.security.token_store import make_credential_store
from app.modules.youtube.services.youtube import (
    YOUTUBE_SCOPES,
    YouTubeService,
    YouTubeServiceError,
    _bundle_to_credentials,
    _credentials_to_bundle,
    _video_full_to_summary,
)


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


class TestVideoFullToSummary:
    """Phase 6a-youtube — projection translation from seed ``VideoFull``
    to product ``VideoSummary``. The raw-API dict mapping (the prior
    ``_video_item_to_summary`` shape) now lives at the seed
    (``_video_full_from_api`` in ``noctusai_lib.integrations.youtube.real``)
    + is covered by ``seed/lib/backend/tests/test_youtube_integration.py``."""

    def _video_full(self, **overrides) -> VideoFull:
        defaults = dict(
            id="abc123",
            title="Test Video",
            description="A description",
            channel_id="UC-owner",
            published_at=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            duration_seconds=225,
            duration_iso="PT3M45S",
            thumbnail_url="https://img.example/high.jpg",
            privacy_status="public",
            view_count=1500,
            like_count=42,
            comment_count=7,
            tags=("tag1", "tag2"),
            category_id="22",
        )
        defaults.update(overrides)
        return VideoFull(**defaults)

    def test_full_round_trip_extracts_every_field(self):
        v = self._video_full()
        summary = _video_full_to_summary(v)
        assert summary.video_id == "abc123"
        assert summary.title == "Test Video"
        assert summary.thumbnail_url == "https://img.example/high.jpg"
        assert summary.view_count == 1500
        assert summary.like_count == 42
        assert summary.comment_count == 7
        assert summary.privacy_status == "public"
        assert summary.duration == "PT3M45S"
        # Tags re-materialise as a list (seed stores a frozen tuple).
        assert summary.tags == ["tag1", "tag2"]
        assert isinstance(summary.tags, list)
        assert summary.category_id == "22"

    def test_missing_thumbnail_yields_empty_url(self):
        v = self._video_full(thumbnail_url="")
        assert _video_full_to_summary(v).thumbnail_url == ""

    def test_empty_tags_round_trip_as_empty_list(self):
        v = self._video_full(tags=())
        summary = _video_full_to_summary(v)
        assert summary.tags == []
        assert isinstance(summary.tags, list)

    def test_unknown_privacy_status_stringified(self):
        v = self._video_full(privacy_status="unknown")
        # The product VideoSummary keeps privacy as a plain string;
        # the seed `"unknown"` literal stringifies cleanly.
        assert _video_full_to_summary(v).privacy_status == "unknown"


class TestYouTubeServiceConstruction:
    def test_missing_credentials_raises(self):
        store = make_credential_store()
        with pytest.raises(YouTubeServiceError):
            YouTubeService(
                client_id="",
                client_secret="",
                redirect_uri="http://localhost/cb",
                credential_store=store,
            )
