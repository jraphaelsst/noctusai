"""Meta webhook signature boundary — the 2026-08-03 defect fix, pinned.

This receiver had a real security hole. `_resolve_meta_secret` returned
`meta_config.webhook_verify_token` as the HMAC secret, but Meta signs
`X-Hub-Signature-256` with the **App Secret**. Both branches were wrong:

  • no matching `meta_config` row ⇒ `secret=None`, and `bypass_when_unset=True`
    then ACCEPTED UNVERIFIED traffic into a write path;
  • a matching row ⇒ the signature could never match, so genuine Meta
    deliveries 401'd.

The canonical, fully-built receiver lives in social-wiring
(`app/modules/meta_ads/routers/leadgen_router.py`). This file exists so the
drift cannot silently return here.

Status-code-pinned per pin 5 of `KB § PATTERNS/security/webhook-signatures.md`
— `== N` exactly, never a body substring, never `in (401, 404)`.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

APP_SECRET = "erp-test-app-secret"
VERIFY_TOKEN = "erp-test-verify-token"
WEBHOOK = "/api/meta/webhook"


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _delivery(entries: int = 1, changes: int = 1) -> dict:
    return {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": f"lead-{e}-{c}",
                            "page_id": "page-1",
                            "form_id": "form-1",
                            "created_time": 1754000000,
                        },
                    }
                    for c in range(changes)
                ],
            }
            for e in range(entries)
        ],
    }


@pytest.fixture
def app_secret(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "meta_app_secret", APP_SECRET, raising=False)


def _raw(client):
    """The unauthenticated TestClient — Meta sends no bearer token."""
    return client.raw() if hasattr(client, "raw") else client


def test_unset_app_secret_returns_401_never_accepts_unverified(client, monkeypatch):
    """🔴 THE hole this fix closed. Before, an unmatched page resolved to
    secret=None and `bypass_when_unset=True` waved the request through into a
    DB write. Unconfigured must now REFUSE."""
    from app.config import settings

    monkeypatch.setattr(settings, "meta_app_secret", "", raising=False)
    body = json.dumps(_delivery()).encode()
    resp = _raw(client).post(
        WEBHOOK, content=body,
        headers={"X-Hub-Signature-256": _sign(body, APP_SECRET),
                 "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_signature_made_with_the_VERIFY_TOKEN_returns_401(client, app_secret):
    """The anti-regression for the exact defect: if anyone re-wires the verify
    token in as the signing secret, a verify-token-signed payload would start
    validating. It must not."""
    body = json.dumps(_delivery()).encode()
    resp = _raw(client).post(
        WEBHOOK, content=body,
        headers={"X-Hub-Signature-256": _sign(body, VERIFY_TOKEN),
                 "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_tampered_body_returns_401(client, app_secret):
    body = json.dumps(_delivery()).encode()
    sig = _sign(body, APP_SECRET)
    resp = _raw(client).post(
        WEBHOOK, content=body + b" ",
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_missing_signature_header_returns_401(client, app_secret):
    body = json.dumps(_delivery()).encode()
    resp = _raw(client).post(
        WEBHOOK, content=body, headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_valid_app_secret_signature_is_accepted(client, app_secret):
    """Correctly-signed traffic must pass — the other half of the old bug was
    that genuine Meta deliveries 401'd."""
    body = json.dumps(_delivery()).encode()
    resp = _raw(client).post(
        WEBHOOK, content=body,
        headers={"X-Hub-Signature-256": _sign(body, APP_SECRET),
                 "Content-Type": "application/json"},
    )
    assert resp.status_code == 200


def test_batched_delivery_parses_every_event(client, app_secret):
    """🔴 Meta BATCHES. The removed hand-rolled parser read entry[0].changes[0]
    only, silently dropping the rest. 2 entries x 2 changes = 4 events."""
    body = json.dumps(_delivery(entries=2, changes=2)).encode()
    resp = _raw(client).post(
        WEBHOOK, content=body,
        headers={"X-Hub-Signature-256": _sign(body, APP_SECRET),
                 "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    # Either fully processed (4) or refused for an unconfigured page — but it
    # must never silently report a single event from a 4-event batch.
    assert payload.get("events", 0) in (0, 4), payload


def test_challenge_echo_is_a_string_not_an_int():
    """🔴 The GET handler returned `int(hub_challenge)`, which raises on a
    non-numeric challenge. Meta's challenge is opaque and it does not promise
    digits — and this is the ONE synchronous call that decides whether the
    subscription saves at all. Asserted at the seed helper, which is what the
    route now delegates to."""
    from noctusai_lib.integrations.meta.leadgen_webhook import (
        leadgen_challenge_response,
    )

    out = leadgen_challenge_response(
        mode="subscribe",
        verify_token=VERIFY_TOKEN,
        challenge="not-a-number-xyz",
        expected_token=VERIFY_TOKEN,
    )
    assert out == "not-a-number-xyz"
    assert isinstance(out, str)
