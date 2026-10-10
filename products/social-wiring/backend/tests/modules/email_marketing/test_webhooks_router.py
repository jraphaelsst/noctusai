"""Resend webhook router — Svix signature verification.

Pins the contract surfaced by `noctusai_lib.security.webhook_signatures`:
valid signature → 200, tampered body / wrong secret → 401. The legacy
"unset secret ⇒ WARNING + 200 bypass" is gone: the SW module is fail-closed
(unset ⇒ 401), pinned in ``test_routers.py::TestWebhooksRouter``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

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
        monkeypatch.setattr(settings, "resend_webhook_secret", SECRET_B64)  # self-patch-ok: config value under test, not a guard
        body = b'{"type":"email.delivered","data":{"email_id":"em_xyz","to":["a@b.com"]}}'
        client.mock_supabase.set_table_data("send_logs", [])

        resp = client.raw().post(
            "/api/email-marketing/webhooks/resend",
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
        monkeypatch.setattr(settings, "resend_webhook_secret", SECRET_B64)  # self-patch-ok: config value under test, not a guard
        signed_body = b'{"type":"email.delivered","data":{"email_id":"em_xyz"}}'
        sig = _svix_sig(signed_body)

        # Send a DIFFERENT body with the same signature → 401
        resp = client.raw().post(
            "/api/email-marketing/webhooks/resend",
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
        monkeypatch.setattr(settings, "resend_webhook_secret", SECRET_B64)  # self-patch-ok: config value under test, not a guard
        body = b'{"type":"email.delivered","data":{"email_id":"em_xyz"}}'

        resp = client.raw().post(
            "/api/email-marketing/webhooks/resend",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 401
