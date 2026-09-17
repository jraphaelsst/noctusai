"""Tests for `app/routers/whatsapp_connections_router.py` — Slice C
(user decision 2026-09-17, "community uses social-wiring's
mechanisms"). WhatsApp is NOT paired in this slice
(`NOC-REMEDIATE[community-waha-pairing]`) — these tests assert the
MECHANISM (admin-gated CRUD + config-gap handling), not a live pairing
flow (`community_waha_base_url` stays unset, matching the fresh-clone /
not-yet-paired default).

The generic contract (paths, response shapes, status codes) is already
covered by the seed's own `seed/framework/backend/tests/routers/
test_whatsapp_connections_router.py`. These tests assert ONLY what is
product-specific: every route (not just writes — unlike api-keys, the
seed factory has no per-route admin split) is gated by `get_community_
role`, and the store is `community.whatsapp_connections`
(ENCRYPTION_KEY-gated).

Auth-boundary tests assert strict `== 401`.
"""
from __future__ import annotations

import uuid

from noctusai_lib.security.encrypted_tokens import generate_key

from app.config import settings
from tests.conftest import seed_community_role

_FAKE_ID = str(uuid.uuid4())


def _set_encryption_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", generate_key().decode())  # self-patch-ok: configuration value, not a guard


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        resp = client.raw().get("/api/whatsapp/connections")
        assert resp.status_code == 401

    def test_create_without_auth_401(self, client):
        resp = client.raw().post(
            "/api/whatsapp/connections", json={"label": "linha 1", "api_key": "x"}
        )
        assert resp.status_code == 401

    def test_status_without_auth_401(self, client):
        resp = client.raw().get(f"/api/whatsapp/connections/{_FAKE_ID}/status")
        assert resp.status_code == 401


class TestAdminGate:
    def test_moderador_cannot_list(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.get("/api/whatsapp/connections")
        assert resp.status_code == 403

    def test_moderador_cannot_create(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(
            "/api/whatsapp/connections", json={"label": "linha 1", "api_key": "x"}
        )
        assert resp.status_code == 403


class TestEncryptionGap:
    def test_list_without_encryption_key_503(self, client, monkeypatch):
        # Explicit unset — never rely on an unset ambient ENCRYPTION_KEY
        # (a dev machine's repo-root `.env` can carry one for another
        # product's tests).
        monkeypatch.setattr(settings, "encryption_key", "")  # self-patch-ok: configuration value, not a guard
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/whatsapp/connections")
        assert resp.status_code == 503


class TestListEmpty:
    def test_admin_list_empty_200(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)
        seed_community_role(client, org_role="admin")
        resp = client.get("/api/whatsapp/connections")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateWithoutWahaConfigured:
    def test_admin_create_503_when_waha_base_url_unset(self, client, monkeypatch):
        # `community_waha_base_url` empty is the current, real state
        # (no number paired yet) — the router must fail loud (503), not
        # silently create an unusable row.
        _set_encryption_key(monkeypatch)
        seed_community_role(client, org_role="admin")
        resp = client.post(
            "/api/whatsapp/connections", json={"label": "linha 1", "api_key": "waha-key"}
        )
        assert resp.status_code == 503
