"""Auth boundary for `/api/meta/leadgen/*`.

This router is unusual and therefore worth an explicit test: it deliberately
mixes PUBLIC and AUTHENTICATED routes under one prefix. Meta calls the two
`/webhook` routes unauthenticated (there is no way for it not to), while the
operator-facing management routes must require auth like everything else.

So the assertion is two-directional, and both directions matter:
  • the management routes assert strict ``== 401`` (never ``in (401, 404)``,
    which would pass for a route that does not exist) —
    `KB § PATTERNS/compliance/auth-boundary-false-green.md`;
  • the webhook routes assert they are NOT 401, because if someone "helpfully"
    adds an auth dependency to them, Meta delivery breaks silently and the
    only symptom is leads quietly not arriving — the exact failure this whole
    initiative exists to fix.
"""
from __future__ import annotations

import pytest

_AUTHED_ROUTES = [
    ("get", "/api/meta/leadgen/subscriptions", {}),
    ("post", "/api/meta/leadgen/subscriptions", {"json": {"page_ids": None}}),
    ("delete", "/api/meta/leadgen/subscriptions/page-1", {}),
    ("get", "/api/meta/leadgen/events", {}),
    # 🔴 The SSE stream. It carries lead PII continuously rather than once,
    # so an unauthenticated subscriber is a worse leak than an unauthenticated
    # read — it keeps receiving. Its org is derived from the session, never
    # from a path or query param, precisely so a caller cannot name someone
    # else's scope; this asserts the front door is shut in the first place.
    ("get", "/api/meta/leadgen/stream", {}),
]

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


@pytest.mark.parametrize(
    "method, path, kwargs", _AUTHED_ROUTES,
    ids=[f"{m}:{p}" for m, p, _ in _AUTHED_ROUTES],
)
def test_management_routes_require_auth_strict_401(client, method, path, kwargs):
    resp = getattr(client.raw(), method)(path, **kwargs)
    assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"


@pytest.fixture
def secrets_configured(monkeypatch):
    """Both Meta secrets resolved, so the ONLY thing that could still make a
    webhook route reject is an auth dependency — which is what we are testing
    for the absence of."""
    import app.services.app_config_store as store

    monkeypatch.setattr(store, "resolve_meta_app_creds",
                        lambda **_kw: ("app-id", APP_SECRET), raising=False)
    monkeypatch.setattr(store, "resolve_meta_webhook_verify_token",
                        lambda **_kw: VERIFY_TOKEN, raising=False)


def test_webhook_get_is_reachable_without_a_bearer_token(client, secrets_configured):
    """Meta cannot authenticate. If someone adds an auth dependency here,
    the handshake fails and the subscription can never be saved — and the
    only symptom is leads quietly not arriving."""
    resp = client.raw().get("/api/meta/leadgen/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "ok",
    })
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_webhook_post_is_reachable_without_a_bearer_token(client, secrets_configured):
    """A correctly-signed delivery must succeed with NO Authorization header.
    Meta has no bearer token to offer; requiring one breaks delivery silently."""
    import hashlib
    import hmac
    import json

    body = json.dumps({"object": "page", "entry": []}).encode()
    sig = "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    resp = client.raw().post(
        "/api/meta/leadgen/webhook",
        content=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
