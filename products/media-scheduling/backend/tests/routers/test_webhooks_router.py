"""WAHA webhook router — sha256_hex signature verification + bypass-on-unset.

Pins the canonical 5-pin webhook compliance contract surfaced by
``noctusai_lib.security.webhook_signatures.webhook_endpoint``:
valid HMAC → 200, tampered body / wrong key → 401, missing header → 401,
unset secret + bypass=True → 200 with WARNING (early-dev only).

Filed 2026-05-09 to close the audit gap (pin #5: status-pinned tests
were missing for this receiver). See KB § PATTERNS/webhook-signatures.md.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from unittest.mock import patch

from app.config import settings


SECRET = "media-scheduling-waha-secret"


def _hmac_sha256_hex(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _ignored_payload() -> bytes:
    """A payload the receiver classifies as `WahaIgnoredEvent` → 200 ignored.

    Using an ignored event shape lets us pin signature behavior without
    needing to mock LID auth + buffer + worker. Real events take the
    deeper code path; that's covered by service-level tests.
    """
    return json.dumps({"event": "session.status", "session": "default"}).encode()


class TestWahaWebhookSignature:
    def test_valid_signature_returns_200(self, client, monkeypatch):
        monkeypatch.setattr(settings, "waha_webhook_secret", SECRET)
        body = _ignored_payload()
        resp = client.raw().post(
            "/webhooks/waha",
            content=body,
            headers={
                "X-Webhook-Hmac-SHA256": _hmac_sha256_hex(body, SECRET),
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200

    def test_tampered_body_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "waha_webhook_secret", SECRET)
        signed_body = _ignored_payload()
        sig = _hmac_sha256_hex(signed_body, SECRET)
        # Send DIFFERENT body with the original signature → 401
        resp = client.raw().post(
            "/webhooks/waha",
            content=b'{"event":"different","session":"default"}',
            headers={
                "X-Webhook-Hmac-SHA256": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_missing_signature_header_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "waha_webhook_secret", SECRET)
        resp = client.raw().post(
            "/webhooks/waha",
            content=_ignored_payload(),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "waha_webhook_secret", SECRET)
        body = _ignored_payload()
        resp = client.raw().post(
            "/webhooks/waha",
            content=body,
            headers={
                "X-Webhook-Hmac-SHA256": _hmac_sha256_hex(body, "wrong-secret"),
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 401


class TestWahaWebhookBypassWhenUnset:
    def test_unset_secret_bypasses_with_warning(self, client, monkeypatch, caplog):
        monkeypatch.setattr(settings, "waha_webhook_secret", "")
        with caplog.at_level(logging.WARNING, logger="noctusai_lib.security.webhook_signatures"):
            resp = client.raw().post(
                "/webhooks/waha",
                content=_ignored_payload(),
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200
        assert any("bypass" in r.message.lower() or "unset" in r.message.lower()
                   for r in caplog.records), "expected bypass WARNING in log"
