"""Tests for the seed `whatsapp_admin` standard router.

Scope: `/api/whatsapp/connection` (status), `/connection/qr`,
`/connection/restart`, `/connection/logout`, `/connection/webhook` —
happy path + auth boundary.

Test-data strategy: drive the FakeWahaClient by leaving
``settings.waha_base_url = None`` so ``get_whatsapp_client()`` returns the
in-memory deterministic Fake (the configured-vs-not seam the factory
already uses in production) — no monkey-patching of our own code. The
stateful session-machine behaviour is covered exhaustively by the
FakeWahaClient unit tests; here we assert router wiring + boundary DTOs.

Auth-boundary test raises from ``deps.get_current_user`` (the external
auth seam) — patching there is fine; patching router logic would not be.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_seed.whatsapp_admin_router import create_whatsapp_admin_router


def _settings(base_url=None):
    s = MagicMock()
    s.waha_base_url = base_url
    s.waha_api_key = None
    s.waha_session = "default"
    return s


def _authed_deps(fake_deps):
    user = MagicMock()
    user.id = "user-1"
    fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
    return fake_deps


def _client(deps, settings):
    app = FastAPI()
    app.include_router(create_whatsapp_admin_router(deps, settings))
    return TestClient(app)


class TestConnectionStatus:
    def test_unconfigured_fake_reports_scan_qr_unpaired(self, fake_deps):
        client = _client(_authed_deps(fake_deps), _settings())
        resp = client.get(
            "/api/whatsapp/connection", headers={"Authorization": "Bearer t"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["status"] == "SCAN_QR_CODE"
        assert body["paired"] is False
        assert body["session"] == "default"

    def test_auth_boundary_blocks_unauthenticated(self, fake_deps):
        fake_deps.get_current_user = AsyncMock(
            side_effect=HTTPException(status_code=401)
        )
        client = _client(fake_deps, _settings())
        resp = client.get("/api/whatsapp/connection")
        assert resp.status_code == 401


class TestQr:
    def test_qr_returns_base64_png_when_scannable(self, fake_deps):
        import base64

        client = _client(_authed_deps(fake_deps), _settings())
        resp = client.get(
            "/api/whatsapp/connection/qr",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["scannable"] is True
        assert body["status"] == "SCAN_QR_CODE"
        assert base64.b64decode(body["png_base64"]).startswith(
            b"\x89PNG\r\n\x1a\n"
        )



class TestLifecycle:
    def test_restart_returns_status_dto(self, fake_deps):
        client = _client(_authed_deps(fake_deps), _settings())
        resp = client.post(
            "/api/whatsapp/connection/restart",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        assert resp.json()["session"] == "default"

    def test_logout_returns_status_dto(self, fake_deps):
        client = _client(_authed_deps(fake_deps), _settings())
        resp = client.post(
            "/api/whatsapp/connection/logout",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "SCAN_QR_CODE"

    def test_configure_webhook_echoes_url_and_events(self, fake_deps):
        client = _client(_authed_deps(fake_deps), _settings())
        resp = client.post(
            "/api/whatsapp/connection/webhook",
            headers={"Authorization": "Bearer t"},
            json={
                "url": "http://app:8010/api/whatsapp/webhook",
                "events": ["message", "session.status"],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["url"] == "http://app:8010/api/whatsapp/webhook"
        assert body["events"] == ["message", "session.status"]

    def test_webhook_uses_default_events_when_omitted(self, fake_deps):
        client = _client(_authed_deps(fake_deps), _settings())
        resp = client.post(
            "/api/whatsapp/connection/webhook",
            headers={"Authorization": "Bearer t"},
            json={"url": "http://app:8010/api/whatsapp/webhook"},
        )
        assert resp.status_code == 200
        assert "message" in resp.json()["events"]
