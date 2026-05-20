"""Tests for intake_monitor_router — read-only conversation/flow monitor.

Redis is the external IO boundary; we inject a minimal in-memory fake
through the router's own ``_redis_client`` seam (the analog of the
seed Fake/Real factory pattern — we exercise router logic, not a
mocked-out internal). Auth + Supabase come from the shared ``client``
fixture (MockSupabaseClient). MessageStore reads resolve to empty via
the mock, exercising the best-effort message-fetch path.
"""
from __future__ import annotations

import json

import pytest

from app.routers import intake_monitor_router as mod


class FakeRedis:
    """Just enough Redis for the monitor: scan_iter / get / delete."""

    def __init__(self, store: dict[str, str]):
        self._store = dict(store)

    def scan_iter(self, match: str, count: int = 100):
        # Only the prefix-glob form the router uses.
        prefix = match.rstrip("*")
        return [k for k in self._store if k.startswith(prefix)]

    def get(self, key: str):
        return self._store.get(key)

    def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


def _pending(state: str, code: str = "ONE9967", **extra) -> str:
    base = {
        "product_code": code,
        "drive_url": "https://drive.google.com/drive/folders/abc",
        "state": state,
    }
    base.update(extra)
    return json.dumps(base)


@pytest.fixture
def fake_redis_with(monkeypatch):
    def _install(store: dict[str, str]):
        fr = FakeRedis(store)
        # mod._redis_client is a module-level factory function (the
        # production DI seam analogous to _resolve_core_db in
        # therapy-platform/ai_pipeline.py per KB § PATTERNS/di-test-seam.md).
        # Substituting the seam IS the blessed test pattern; Real-DI
        # follow-up = social-wiring-settings-di-rewrite (Depends-able).
        monkeypatch.setattr(mod, "_redis_client", lambda: fr)  # self-patch-ok: di-seam-substitute
        return fr

    return _install


class TestListConversations:
    def test_lists_and_orders_non_idle_first(self, client, fake_redis_with):
        fake_redis_with(
            {
                "whatsapp:conv:+5511111111111": _pending("idle"),
                "whatsapp:conv:+5522222222222": _pending("awaiting_confirmation"),
                "whatsapp:active_uploads:+5522222222222": "1",
            }
        )
        resp = client.get("/api/whatsapp/intake/conversations")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 2
        # Non-idle surfaces first.
        assert data[0]["state"] == "awaiting_confirmation"
        assert data[0]["session_id"] == "+5522222222222"
        assert data[0]["active_uploads"] == 1
        assert data[0]["product_code"] == "ONE9967"
        assert data[1]["state"] == "idle"

    def test_skips_unparseable_state(self, client, fake_redis_with):
        fake_redis_with(
            {
                "whatsapp:conv:+5511111111111": "{not valid json",
                "whatsapp:conv:+5533333333333": _pending("processing"),
            }
        )
        resp = client.get("/api/whatsapp/intake/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "+5533333333333"

    def test_empty_when_no_state(self, client, fake_redis_with):
        fake_redis_with({})
        resp = client.get("/api/whatsapp/intake/conversations")
        assert resp.status_code == 200
        assert resp.json() == []


class TestConversationDetail:
    def test_returns_state_and_empty_messages(self, client, fake_redis_with):
        fake_redis_with(
            {"whatsapp:conv:+5544444444444": _pending("awaiting_video_choice")}
        )
        resp = client.get(
            "/api/whatsapp/intake/conversations/+5544444444444"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["conversation"]["state"] == "awaiting_video_choice"
        assert body["conversation"]["session_id"] == "+5544444444444"
        assert isinstance(body["messages"], list)

    def test_404_when_no_live_state(self, client, fake_redis_with):
        fake_redis_with({})
        resp = client.get("/api/whatsapp/intake/conversations/+59999")
        assert resp.status_code == 404

    def test_message_limit_validation(self, client, fake_redis_with):
        fake_redis_with(
            {"whatsapp:conv:+5544444444444": _pending("processing")}
        )
        resp = client.get(
            "/api/whatsapp/intake/conversations/+5544444444444?message_limit=999"
        )
        assert resp.status_code == 422


class TestCancel:
    def test_cancel_clears_state(self, client, fake_redis_with):
        fr = fake_redis_with(
            {"whatsapp:conv:+5566666666666": _pending("awaiting_confirmation")}
        )
        resp = client.post(
            "/api/whatsapp/intake/conversations/+5566666666666/cancel"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "session_id": "+5566666666666",
            "cleared": True,
        }
        assert "whatsapp:conv:+5566666666666" not in fr._store

    def test_cancel_absent_reports_not_cleared(self, client, fake_redis_with):
        fake_redis_with({})
        resp = client.post(
            "/api/whatsapp/intake/conversations/+50000/cancel"
        )
        assert resp.status_code == 200
        assert resp.json()["cleared"] is False
