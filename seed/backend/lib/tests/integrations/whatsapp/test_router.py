"""Webhook router tests — signature verification + idempotency + handler dispatch.

Tests the FastAPI factory `create_whatsapp_webhook_router` against a
TestClient. Sibling's `tests/test_webhook_hmac.py` only covered the HMAC
helper directly; these tests verify the router's end-to-end behavior.
"""

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.integrations.whatsapp import (
    WhatsAppInboundMessage,
    WhatsAppSettings,
    create_whatsapp_webhook_router,
)


def _hex_sig(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _build_app(settings: WhatsAppSettings, captured: list[WhatsAppInboundMessage]):
    async def on_message(inbound: WhatsAppInboundMessage) -> None:
        captured.append(inbound)

    app = FastAPI()
    app.include_router(
        create_whatsapp_webhook_router(settings, on_message),
        prefix="/webhooks/whatsapp",
    )
    return app


def _valid_payload(provider_id: str = "msg-1") -> dict:
    return {
        "event": "message",
        "session": "default",
        "payload": {
            "id": provider_id,
            "from": "5511999999999@c.us",
            "body": "Olá",
        },
    }


def test_router_dispatches_inbound_to_handler() -> None:
    captured: list[WhatsAppInboundMessage] = []
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret=None),
        captured,
    )
    client = TestClient(app)

    response = client.post("/webhooks/whatsapp", json=_valid_payload("m-1"))

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert len(captured) == 1
    assert captured[0].provider_message_id == "m-1"
    assert captured[0].text == "Olá"


def test_router_dedupes_repeated_provider_message_id() -> None:
    captured: list[WhatsAppInboundMessage] = []
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret=None),
        captured,
    )
    client = TestClient(app)

    payload = _valid_payload("m-dedup")
    first = client.post("/webhooks/whatsapp", json=payload)
    second = client.post("/webhooks/whatsapp", json=payload)

    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert len(captured) == 1


def test_router_returns_ignored_for_non_message_event() -> None:
    captured: list[WhatsAppInboundMessage] = []
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret=None),
        captured,
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/whatsapp",
        json={"event": "session.status", "session": "default", "payload": {"status": "WORKING"}},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert captured == []


def test_router_400_on_payload_with_no_text_and_no_media() -> None:
    captured: list[WhatsAppInboundMessage] = []
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret=None),
        captured,
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/whatsapp",
        json={
            "event": "message",
            "session": "default",
            "payload": {"id": "x", "from": "5511999999999@c.us", "body": ""},
        },
    )

    assert response.status_code == 400


def test_router_401_when_signature_required_but_missing() -> None:
    captured: list[WhatsAppInboundMessage] = []
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret="topsecret"),
        captured,
    )
    client = TestClient(app)

    response = client.post("/webhooks/whatsapp", json=_valid_payload("m-1"))

    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()
    assert captured == []


def test_router_401_on_invalid_signature() -> None:
    captured: list[WhatsAppInboundMessage] = []
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret="topsecret"),
        captured,
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/whatsapp",
        json=_valid_payload("m-1"),
        headers={"X-Webhook-Hmac-SHA256": "abc123notvalid"},
    )

    assert response.status_code == 401
    assert captured == []


def test_router_accepts_valid_signature() -> None:
    captured: list[WhatsAppInboundMessage] = []
    secret = "topsecret"
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret=secret),
        captured,
    )
    client = TestClient(app)

    payload = _valid_payload("m-1")
    body_bytes = json.dumps(payload, separators=(",", ":")).encode()
    sig = _hex_sig(body_bytes, secret)

    response = client.post(
        "/webhooks/whatsapp",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Hmac-SHA256": sig,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert len(captured) == 1


def test_router_400_on_invalid_json() -> None:
    captured: list[WhatsAppInboundMessage] = []
    app = _build_app(
        WhatsAppSettings(base_url="http://waha", webhook_hmac_secret=None),
        captured,
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/whatsapp",
        content=b"this is not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
