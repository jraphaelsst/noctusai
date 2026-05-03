"""Resend webhook router — Svix signature verification + bypass-on-unset.

Pins the contract surfaced by `noctusai_lib.security.webhook_signatures`:
valid signature → 200, tampered body / wrong secret → 401, unset secret
→ WARNING log + 200 (legacy bypass for early-dev environments).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from app.config import settings


SECRET_BYTES = b"the-actual-key-bytes"
SECRET_B64 = base64.b64encode(SECRET_BYTES).decode("ascii")
SVIX_ID = "msg_test_1"
SVIX_TS = "1700000000"


def _svix_sig(body: bytes) -> str:
    payload = f"{SVIX_ID}.{SVIX_TS}.{body.decode()}".encode("utf-8")
    sig = base64.b64encode(hmac.new(SECRET_BYTES, payload, hashlib.sha256).digest()).decode("ascii")
    return f"v1,{sig}"


class TestResendWebhookSignature:
    def test_valid_signature_returns_200(self, client, monkeypatch):
        monkeypatch.setattr(settings, "resend_webhook_secret", SECRET_B64)
        body = b'{"type":"email.delivered","data":{"email_id":"em_xyz","to":["a@b.com"]}}'
        client.mock_supabase.set_table_data("send_logs", [])

        resp = client.raw().post(
            "/api/webhooks/resend",
            content=body,
            headers={
                "svix-id": SVIX_ID,
                "svix-timestamp": SVIX_TS,
                "svix-signature": _svix_sig(body),
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200

    def test_tampered_body_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "resend_webhook_secret", SECRET_B64)
        signed_body = b'{"type":"email.delivered","data":{"email_id":"em_xyz"}}'
        sig = _svix_sig(signed_body)

        # Send a DIFFERENT body with the same signature → 401
        resp = client.raw().post(
            "/api/webhooks/resend",
            content=b'{"type":"email.bounced","data":{"email_id":"em_xyz"}}',
            headers={
                "svix-id": SVIX_ID,
                "svix-timestamp": SVIX_TS,
                "svix-signature": sig,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_missing_signature_headers_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(settings, "resend_webhook_secret", SECRET_B64)
        body = b'{"type":"email.delivered","data":{"email_id":"em_xyz"}}'

        resp = client.raw().post(
            "/api/webhooks/resend",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_unset_secret_bypasses_with_warning(self, client, monkeypatch, caplog):
        monkeypatch.setattr(settings, "resend_webhook_secret", "")
        client.mock_supabase.set_table_data("send_logs", [])

        with caplog.at_level(logging.WARNING, logger="noctusai_lib.security.webhook_signatures"):
            resp = client.raw().post(
                "/api/webhooks/resend",
                json={"type": "email.delivered", "data": {"email_id": "em_xyz"}},
            )

        assert resp.status_code == 200
        assert any(
            "resend-webhook: secret unset" in record.getMessage()
            for record in caplog.records
        ), "Expected seed-lib WARNING when secret is unset"
