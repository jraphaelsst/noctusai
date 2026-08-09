"""
Tests for the webhook router skeleton — pins the canonical contract
surfaced by ``noctusai_lib.security.webhook_signatures``:

  - valid signature           → 200
  - tampered body / wrong key → 401
  - missing headers           → 401
  - unset secret + bypass=True → 200 with WARNING (early-dev only)
  - invalid JSON body         → 400

Every assertion pins ``response.status_code`` per the keeper-detector
rule (``check_test_status_assertion``). The helpers mirror what the
live Resend receiver at
``products/social-wiring/backend/app/modules/email_marketing/routers/webhooks.py``
exercises, so the new product can copy the shape verbatim.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from app.config import settings


SECRET_BYTES = b"igig-webhook-secret-bytes"
SECRET_B64 = base64.b64encode(SECRET_BYTES).decode("ascii")
SVIX_ID = "msg_test_1"
SVIX_TS = "1700000000"


def _svix_sig(body: bytes) -> str:
    """Compute a valid Svix-protocol v1 signature for ``body``."""
    payload = f"{SVIX_ID}.{SVIX_TS}.{body.decode()}".encode("utf-8")
    sig = base64.b64encode(hmac.new(SECRET_BYTES, payload, hashlib.sha256).digest()).decode("ascii")
    return f"v1,{sig}"


class TestWebhookSignatureVerification:
    """The canonical webhook_endpoint(...) dep enforces signatures."""

    def test_valid_signature_returns_200(self, client, monkeypatch):
        monkeypatch.setattr(settings, "example_webhook_secret", SECRET_B64)
        body = b'{"type":"example.event","data":{"id":"evt_1"}}'
        resp = client.raw().post(
            "/api/webhooks/example",
            content=body,
            headers={
                "svix-id": SVIX_ID,
                "svix-timestamp": SVIX_TS,
                "svix-signature": _svix_sig(body),
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "received": True}

    def test_tampered_body_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "example_webhook_secret", SECRET_B64)
        signed_body = b'{"type":"example.event","data":{"id":"evt_1"}}'
        sig = _svix_sig(signed_body)

        # Send a DIFFERENT body with the same signature → 401
        resp = client.raw().post(
            "/api/webhooks/example",
            content=b'{"type":"example.other","data":{"id":"evt_2"}}',
            headers={
                "svix-id": SVIX_ID,
                "svix-timestamp": SVIX_TS,
                "svix-signature": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_missing_signature_headers_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "example_webhook_secret", SECRET_B64)
        resp = client.raw().post(
            "/api/webhooks/example",
            content=b'{"type":"example.event"}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401


class TestWebhookBypassWhenUnset:
    """Empty secret + bypass_when_unset=True → accept with WARNING."""

    def test_unset_secret_bypasses_with_warning(self, client, monkeypatch, caplog):
        monkeypatch.setattr(settings, "example_webhook_secret", "")

        with caplog.at_level(logging.WARNING, logger="noctusai_lib.security.webhook_signatures"):
            resp = client.raw().post(
                "/api/webhooks/example",
                content=b'{"type":"example.event"}',
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200
        assert any("bypass" in r.message.lower() or "unset" in r.message.lower()
                   for r in caplog.records), "expected bypass WARNING in log"


class TestWebhookBodyValidation:
    """Invalid-JSON body surfaces as 400, not 500."""

    def test_invalid_json_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(settings, "example_webhook_secret", "")  # bypass
        resp = client.raw().post(
            "/api/webhooks/example",
            content=b"not-json{",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
