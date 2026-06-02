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
    def test_list_no_longer_requires_youtube_creds(self, client, override_settings):
        """GET /api/videos now reads directly from youtube_videos (RLS-bounded Supabase);
        it does NOT instantiate a YouTubeService — so missing encryption_key / YouTube
        creds no longer produce 503 on the list path. The 503 now fires only on sync.
        Regression-guard: assert 200 (empty catalog) not 503."""
        override_settings(
            encryption_key="",
            youtube_client_id="cid",
            youtube_client_secret="csecret",
        )
        resp = client.get("/api/videos")
        # 200 with empty items (mock Supabase returns no rows)
        assert resp.status_code == 200, resp.text

    def test_sync_missing_encryption_key_returns_503(self, client, override_settings):
        """POST /api/videos/sync resolves account via integration_account_service,
        which requires an encryption_key — 503 on missing key."""
        override_settings(
            encryption_key="",
            youtube_client_id="cid",
            youtube_client_secret="csecret",
        )
        resp = client.post("/api/videos/sync")
        assert resp.status_code == 503, resp.text


class TestListLimitValidation:
    def test_limit_above_100_rejected(self, client, override_settings):
        override_settings(**_YT_COMPLETE)
        resp = client.get("/api/videos?limit=500")
        # FastAPI Query(le=100) → 422 with "less_than_equal" in detail.
        assert resp.status_code == 422, resp.text

    def test_limit_zero_rejected(self, client, override_settings):
        override_settings(**_YT_COMPLETE)
        resp = client.get("/api/videos?limit=0")
        assert resp.status_code == 422, resp.text


class TestListUnauthenticated:
    def test_list_requires_auth(self, client):
        resp = client.raw().get("/api/videos")
        assert resp.status_code in (401, 403), resp.text


class TestGetVideoNotInCache:
    def test_unknown_id_returns_404(self, client, override_settings):
        override_settings(**_YT_COMPLETE)
        resp = client.get("/api/videos/ghost-video-id-xyz")
        # The mock supabase client returns no rows by default.
        assert resp.status_code == 404, resp.text
        assert "sync" in resp.text.lower()


class TestSyncUnauthenticated:
    def test_sync_requires_auth(self, client):
        resp = client.raw().post("/api/videos/sync")
        assert resp.status_code in (401, 403), resp.text
