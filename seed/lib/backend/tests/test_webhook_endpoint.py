"""End-to-end tests for `webhook_endpoint(...)` FastAPI dependency factory.

Uses a fresh FastAPI app + TestClient to assert the dep factory:
  - reads the body once
  - resolves the secret via the supplied resolver (sync OR async)
  - verifies per the configured scheme (`sha256_prefixed`, `sha256_hex`, `svix`,
    `basic_shared_secret`)
  - bypasses with WARNING when `bypass_when_unset=True` and resolver returns None
  - returns 401 on signature mismatch / missing-required-headers / expired timestamp
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    static_secret_resolver,
    webhook_endpoint,
)


def _hub_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _hex_sig(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _svix_secret_and_sig(body: bytes, svix_id: str, svix_ts: str) -> tuple[str, str]:
    raw = b"the-key-bytes"
    secret_b64 = base64.b64encode(raw).decode("ascii")
    payload = f"{svix_id}.{svix_ts}.{body.decode()}".encode("utf-8")
    sig = base64.b64encode(hmac.new(raw, payload, hashlib.sha256).digest()).decode("ascii")
    return secret_b64, f"v1,{sig}"


def _make_app(dep) -> TestClient:
    app = FastAPI()

    @app.post("/wh")
    async def handler(verified: VerifiedWebhook = dep):
        return {"ok": True, "body": verified.body.decode(), "extras": verified.extras}

    return TestClient(app)


# -- sha256_prefixed (Hub-Signature) -----------------------------------------


def test_endpoint_accepts_valid_sha256_prefixed_signature():
    secret = "shh"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="sha256_prefixed",
    )
    client = _make_app(dep)
    body = b'{"event":"x"}'
    resp = client.post(
        "/wh",
        content=body,
        headers={"X-Hub-Signature-256": _hub_sig(body, secret)},
    )
    assert resp.status_code == 200
    assert resp.json()["body"] == body.decode()


def test_endpoint_rejects_bad_signature():
    secret = "shh"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="sha256_prefixed",
    )
    client = _make_app(dep)
    resp = client.post(
        "/wh",
        content=b'{"event":"tampered"}',
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 401


def test_endpoint_rejects_missing_signature_header():
    secret = "shh"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="sha256_prefixed",
    )
    client = _make_app(dep)
    resp = client.post("/wh", content=b'{"event":"x"}')
    assert resp.status_code == 401


# -- sha256_hex --------------------------------------------------------------


def test_endpoint_accepts_valid_hex_signature():
    secret = "shh"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="sha256_hex",
        signature_header="X-WAHA-Sig",
    )
    client = _make_app(dep)
    body = b'{"event":"x"}'
    resp = client.post(
        "/wh", content=body, headers={"X-WAHA-Sig": _hex_sig(body, secret)},
    )
    assert resp.status_code == 200


# -- Svix --------------------------------------------------------------------


def test_endpoint_accepts_valid_svix_signature():
    body = b'{"type":"email.delivered"}'
    secret_b64, sig = _svix_secret_and_sig(body, "msg_1", "1700000000")
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret_b64),
        scheme="svix",
    )
    client = _make_app(dep)
    resp = client.post(
        "/wh",
        content=body,
        headers={
            "svix-id": "msg_1",
            "svix-timestamp": "1700000000",
            "svix-signature": sig,
        },
    )
    assert resp.status_code == 200


def test_endpoint_rejects_svix_when_replay_window_enforced_and_stale():
    import time

    body = b'{"x":1}'
    stale_ts = str(int(time.time()) - 3600)
    secret_b64, sig = _svix_secret_and_sig(body, "msg_1", stale_ts)
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret_b64),
        scheme="svix",
        enforce_replay_window=True,
    )
    client = _make_app(dep)
    resp = client.post(
        "/wh",
        content=body,
        headers={
            "svix-id": "msg_1",
            "svix-timestamp": stale_ts,
            "svix-signature": sig,
        },
    )
    assert resp.status_code == 401


# -- Replay-window enforcement (HMAC) ----------------------------------------


def test_endpoint_rejects_expired_timestamp_header():
    import time

    secret = "shh"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="sha256_prefixed",
        timestamp_header="X-Webhook-Timestamp",
    )
    client = _make_app(dep)
    body = b'{"x":1}'
    resp = client.post(
        "/wh",
        content=body,
        headers={
            "X-Hub-Signature-256": _hub_sig(body, secret),
            "X-Webhook-Timestamp": str(int(time.time()) - 3600),
        },
    )
    assert resp.status_code == 401


def test_endpoint_rejects_non_numeric_timestamp_header():
    secret = "shh"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="sha256_prefixed",
        timestamp_header="X-Webhook-Timestamp",
    )
    client = _make_app(dep)
    body = b'{"x":1}'
    resp = client.post(
        "/wh",
        content=body,
        headers={
            "X-Hub-Signature-256": _hub_sig(body, secret),
            "X-Webhook-Timestamp": "not-a-number",
        },
    )
    assert resp.status_code == 401


# -- bypass_when_unset --------------------------------------------------------


def test_endpoint_bypasses_with_warning_when_secret_unset(caplog):
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(None),
        scheme="sha256_prefixed",
        bypass_when_unset=True,
        log_prefix="testwh",
    )
    client = _make_app(dep)
    with caplog.at_level(logging.WARNING, logger="noctusai_lib.security.webhook_signatures"):
        resp = client.post("/wh", content=b'{"x":1}')
    assert resp.status_code == 200
    assert any("testwh: secret unset" in rec.getMessage() for rec in caplog.records)


def test_endpoint_returns_401_when_secret_unset_and_bypass_off():
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(None),
        scheme="sha256_prefixed",
        bypass_when_unset=False,
    )
    client = _make_app(dep)
    resp = client.post("/wh", content=b'{"x":1}')
    assert resp.status_code == 401


# -- Async resolver + ResolvedSecret extras ----------------------------------


def test_endpoint_accepts_async_resolver_and_passes_extras_through():
    secret = "shh"

    async def resolver(request, body):
        return ResolvedSecret(secret=secret, extras={"org_id": "o1", "page_id": "p1"})

    dep = webhook_endpoint(secret_resolver=resolver, scheme="sha256_prefixed")
    client = _make_app(dep)
    body = b'{"x":1}'
    resp = client.post(
        "/wh", content=body, headers={"X-Hub-Signature-256": _hub_sig(body, secret)},
    )
    assert resp.status_code == 200
    assert resp.json()["extras"] == {"org_id": "o1", "page_id": "p1"}


def test_endpoint_resolver_can_return_plain_string():
    """Resolver returning bare `str` (not wrapped in ResolvedSecret) still works."""
    def resolver(request, body):
        return "shh"

    dep = webhook_endpoint(secret_resolver=resolver, scheme="sha256_prefixed")
    client = _make_app(dep)
    body = b'{"x":1}'
    resp = client.post(
        "/wh", content=body, headers={"X-Hub-Signature-256": _hub_sig(body, "shh")},
    )
    assert resp.status_code == 200


# -- basic_shared_secret (Grupo OLX leads) -----------------------------------


def _basic_header(username: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{username}:{secret}".encode()).decode("ascii")


def test_endpoint_accepts_valid_basic_shared_secret():
    secret = "594F803B380A41396ED63DCA39503542"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="basic_shared_secret",
    )
    client = _make_app(dep)

    resp = client.post(
        "/wh",
        content=b'{"originLeadId":"abc"}',
        headers={"Authorization": _basic_header("vivareal", secret)},
    )

    assert resp.status_code == 200
    assert resp.json()["body"] == '{"originLeadId":"abc"}'


def test_endpoint_rejects_wrong_basic_secret_with_401():
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver("right"),
        scheme="basic_shared_secret",
    )
    client = _make_app(dep)

    resp = client.post(
        "/wh",
        content=b"{}",
        headers={"Authorization": _basic_header("vivareal", "wrong")},
    )

    assert resp.status_code == 401


def test_endpoint_rejects_missing_authorization_header_with_401():
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver("k"),
        scheme="basic_shared_secret",
    )
    client = _make_app(dep)

    assert client.post("/wh", content=b"{}").status_code == 401


def test_endpoint_basic_scheme_defaults_to_the_authorization_header():
    """The scheme's default `signature_header` must be `Authorization` —
    a wrong default would silently read an absent header and 401 every
    genuine delivery."""
    secret = "k"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="basic_shared_secret",
    )
    client = _make_app(dep)

    resp = client.post(
        "/wh", content=b"{}", headers={"Authorization": _basic_header("vivareal", secret)}
    )

    assert resp.status_code == 200


def test_endpoint_basic_username_override_is_honoured():
    secret = "k"
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(secret),
        scheme="basic_shared_secret",
        basic_username="grupoolx",
    )
    client = _make_app(dep)

    assert client.post(
        "/wh", content=b"{}", headers={"Authorization": _basic_header("grupoolx", secret)}
    ).status_code == 200
    assert client.post(
        "/wh", content=b"{}", headers={"Authorization": _basic_header("vivareal", secret)}
    ).status_code == 401


def test_endpoint_basic_scheme_unset_secret_401s_when_bypass_disabled():
    """The OLX receiver runs `bypass_when_unset=False`: an unconfigured
    secret must 401, never wave the delivery through."""
    dep = webhook_endpoint(
        secret_resolver=static_secret_resolver(None),
        scheme="basic_shared_secret",
        bypass_when_unset=False,
    )
    client = _make_app(dep)

    resp = client.post(
        "/wh", content=b"{}", headers={"Authorization": _basic_header("vivareal", "k")}
    )

    assert resp.status_code == 401
