"""Tests for videos_router — boundary validation + 503-on-config-gap.

Full pipeline tests live in test_video_cache_service.py; here we just
verify the router wires correctly and rejects bad inputs at the
FastAPI layer."""
from __future__ import annotations


_ENC_KEY = "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg="

_YT_COMPLETE = dict(
    encryption_key=_ENC_KEY,
    youtube_client_id="cid",
    youtube_client_secret="csecret",
)


class TestListConfigGaps:
    def test_missing_encryption_key_returns_503(self, client, settings_override):
        settings_override(
            encryption_key="",
            youtube_client_id="cid",
            youtube_client_secret="csecret",
        )
        resp = client.get("/api/videos")
        assert resp.status_code == 503, resp.text
        assert "encryption_key" in resp.text.lower()

    def test_missing_youtube_creds_returns_503(self, client, settings_override):
        settings_override(
            encryption_key=_ENC_KEY,
            youtube_client_id="",
            youtube_client_secret="",
        )
        resp = client.get("/api/videos")
        assert resp.status_code == 503, resp.text
        assert "youtube_client" in resp.text.lower()


class TestListLimitValidation:
    def test_limit_above_100_rejected(self, client, settings_override):
        settings_override(**_YT_COMPLETE)
        resp = client.get("/api/videos?limit=500")
        # FastAPI Query(le=100) → 422 with "less_than_equal" in detail.
        assert resp.status_code == 422, resp.text

    def test_limit_zero_rejected(self, client, settings_override):
        settings_override(**_YT_COMPLETE)
        resp = client.get("/api/videos?limit=0")
        assert resp.status_code == 422, resp.text


class TestListUnauthenticated:
    def test_list_requires_auth(self, client):
        resp = client.raw().get("/api/videos")
        assert resp.status_code in (401, 403), resp.text


class TestGetVideoNotInCache:
    def test_unknown_id_returns_404(self, client, settings_override):
        settings_override(**_YT_COMPLETE)
        resp = client.get("/api/videos/ghost-video-id-xyz")
        # The mock supabase client returns no rows by default.
        assert resp.status_code == 404, resp.text
        assert "sync" in resp.text.lower()


class TestSyncUnauthenticated:
    def test_sync_requires_auth(self, client):
        resp = client.raw().post("/api/videos/sync")
        assert resp.status_code in (401, 403), resp.text
