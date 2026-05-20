"""Tests for dashboard_router — boundary validation + 503-on-config-gap.

Service-internal classifier tests live in test_dashboard_service.py
(when added). Here we exercise the FastAPI layer."""
from __future__ import annotations


_ENC_KEY = "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg="


class TestStatsConfigGap:
    def test_missing_encryption_key_returns_503(self, client, settings_override):
        settings_override(encryption_key="")
        resp = client.get("/api/dashboard/stats")
        assert resp.status_code == 503, resp.text
        assert "encryption_key" in resp.text.lower()


class TestStatsHappyPath:
    def test_returns_kpi_shape(self, client, settings_override):
        settings_override(encryption_key=_ENC_KEY)
        resp = client.get("/api/dashboard/stats")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for key in ("total_videos", "total_views", "total_likes", "total_comments"):
            assert key in data
            assert isinstance(data[key], int)


class TestTopVideosLimit:
    def test_limit_above_50_rejected(self, client, settings_override):
        settings_override(encryption_key=_ENC_KEY)
        resp = client.get("/api/dashboard/top-videos?limit=51")
        assert resp.status_code == 422

    def test_limit_zero_rejected(self, client, settings_override):
        settings_override(encryption_key=_ENC_KEY)
        resp = client.get("/api/dashboard/top-videos?limit=0")
        assert resp.status_code == 422

    def test_default_limit_returns_list(self, client, settings_override):
        settings_override(encryption_key=_ENC_KEY)
        resp = client.get("/api/dashboard/top-videos")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)


class TestRecentUploadsLimit:
    def test_limit_above_50_rejected(self, client, settings_override):
        settings_override(encryption_key=_ENC_KEY)
        resp = client.get("/api/dashboard/recent-uploads?limit=100")
        assert resp.status_code == 422

    def test_default_limit_returns_list(self, client, settings_override):
        settings_override(encryption_key=_ENC_KEY)
        resp = client.get("/api/dashboard/recent-uploads")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)


class TestUnauthenticated:
    def test_stats_requires_auth(self, client):
        resp = client.raw().get("/api/dashboard/stats")
        assert resp.status_code in (401, 403), resp.text

    def test_top_videos_requires_auth(self, client):
        resp = client.raw().get("/api/dashboard/top-videos")
        assert resp.status_code in (401, 403), resp.text

    def test_recent_uploads_requires_auth(self, client):
        resp = client.raw().get("/api/dashboard/recent-uploads")
        assert resp.status_code in (401, 403), resp.text
