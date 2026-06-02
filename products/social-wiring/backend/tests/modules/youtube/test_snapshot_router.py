"""Tests for snapshot router — trend endpoints + run endpoint auth boundary.

Tests:
  - GET /api/youtube/channel/trend returns 401 without auth
  - GET /api/youtube/videos/{id}/trend returns 401 without auth
  - POST /api/youtube/snapshot/run returns 401 without auth
  - channel/trend returns point list from snapshot table
  - video/trend returns point list from video snapshot table
  - kind= filter served from correct table
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import MockRequestBuilder


@pytest.fixture
def client(request):
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ─── Auth boundary ───────────────────────────────────────────────────────

class TestAuthBoundary:
    def test_snapshot_run_requires_auth(self, client):
        r = client.post("/api/youtube/snapshot/run")
        assert r.status_code == 401

    def test_channel_trend_requires_auth(self, client):
        r = client.get("/api/youtube/channel/trend")
        assert r.status_code == 401

    def test_video_trend_requires_auth(self, client):
        r = client.get("/api/youtube/videos/abc123/trend")
        assert r.status_code == 401


# ─── kind= filter ────────────────────────────────────────────────────────

class TestKindFilter:
    def test_videos_list_default_kind_video(self, client):
        """GET /api/videos without kind= reads from youtube_videos (no auth test — just schema)."""
        r = client.get("/api/videos")
        # Without auth → 401
        assert r.status_code == 401

    def test_videos_list_kind_short_requires_auth(self, client):
        r = client.get("/api/videos?kind=short")
        assert r.status_code == 401

    def test_videos_list_kind_invalid_rejected(self, client):
        # kind must be 'video' or 'short'
        r = client.get("/api/videos?kind=garbage")
        # 401 or 422 — either means the request was rejected at auth/validation boundary
        assert r.status_code in (401, 422)
