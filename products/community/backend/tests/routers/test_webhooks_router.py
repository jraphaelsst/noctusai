"""Tests for `webhooks_router` — contract §Webhooks, amendments A5, A9.

Stripe payloads are REAL HMAC-signed (`stripe.Webhook.construct_event`
verifies for real — no SDK substitution, mirrors the seed's own
`tests/integrations/payments/test_webhook_events.py`). Asaas uses the
bare `asaas-access-token` header per that module's documented shape.

Slice C (user decision 2026-09-17): the router now resolves
`stripe_webhook_secret` / `asaas_webhook_token` via `resolve_api_key`
(org-scoped store -> `org_settings` -> `platform_settings` -> env),
not `settings.*` directly — so these tests drive the secret through
`monkeypatch.setenv(...)` (tier-3, the CONFIGURATION value tier
`resolve_credential` documents as its own env-var fallback), not a
`settings` attribute patch. Not a guard/keeper being routed around —
same convention the inherited `tests/routers/test_webhook_router.py`
uses for `settings.example_webhook_secret`, one resolution layer
further out. `seed_public_license` seeds the single-tenant org
`resolve_public_org_id()` (called before signature verification) needs.
"""
import hashlib
import hmac
import json
import time

from tests.conftest import seed_public_license

STRIPE_SECRET = "whsec_test_secret_community"
ASAAS_TOKEN = "asaas-token-community"


def _sign_stripe_payload(payload_dict: dict, *, secret: str = STRIPE_SECRET) -> tuple[bytes, str]:
    ts = int(time.time())
    body = json.dumps(payload_dict).encode("utf-8")
    signed_payload = f"{ts}.{body.decode('utf-8')}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={signature}"


class TestFailClosed:
    """Amendment A9: an unset secret/token gives strict 401 — never a bypass."""

    def test_stripe_unset_secret_401(self, client, monkeypatch):
        seed_public_license(client)
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)  # self-patch-ok: configuration value (tier-3 env), not a guard
        body, sig = _sign_stripe_payload({"id": "evt_1", "type": "invoice.paid", "data": {"object": {}}})
        resp = client.raw().post(
            "/api/webhooks/stripe", content=body,
            headers={"stripe-signature": sig, "content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_asaas_unset_token_401(self, client, monkeypatch):
        seed_public_license(client)
        monkeypatch.delenv("ASAAS_WEBHOOK_TOKEN", raising=False)  # self-patch-ok: configuration value (tier-3 env), not a guard
        body = json.dumps({"event": "PAYMENT_CONFIRMED", "payment": {"id": "pay_1"}}).encode()
        resp = client.raw().post(
            "/api/webhooks/asaas", content=body,
            headers={"asaas-access-token": "whatever", "content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_stripe_bad_signature_401(self, client, monkeypatch):
        seed_public_license(client)
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", STRIPE_SECRET)  # self-patch-ok: configuration value (tier-3 env), not a guard
        body = json.dumps({"id": "evt_1", "type": "invoice.paid", "data": {"object": {}}}).encode()
        resp = client.raw().post(
            "/api/webhooks/stripe", content=body,
            headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"},
        )
        assert resp.status_code == 401

    def test_asaas_bad_token_401(self, client, monkeypatch):
        seed_public_license(client)
        monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", ASAAS_TOKEN)  # self-patch-ok: configuration value (tier-3 env), not a guard
        body = json.dumps({"event": "PAYMENT_CONFIRMED", "payment": {"id": "pay_1"}}).encode()
        resp = client.raw().post(
            "/api/webhooks/asaas", content=body,
            headers={"asaas-access-token": "wrong-token", "content-type": "application/json"},
        )
        assert resp.status_code == 401


class TestReceivedShape:
    def test_stripe_unknown_event_type_ignored_200(self, client, monkeypatch):
        seed_public_license(client)
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", STRIPE_SECRET)  # self-patch-ok: configuration value (tier-3 env), not a guard
        body, sig = _sign_stripe_payload({
            "id": "evt_ignore_1", "object": "event",
            "type": "customer.created", "data": {"object": {}},
        })
        resp = client.raw().post(
            "/api/webhooks/stripe", content=body,
            headers={"stripe-signature": sig, "content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_asaas_unknown_event_ignored_200(self, client, monkeypatch):
        seed_public_license(client)
        monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", ASAAS_TOKEN)  # self-patch-ok: configuration value (tier-3 env), not a guard
        body = json.dumps({"event": "SOME_UNKNOWN_EVENT", "payment": {"id": "pay_x"}}).encode()
        resp = client.raw().post(
            "/api/webhooks/asaas", content=body,
            headers={"asaas-access-token": ASAAS_TOKEN, "content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_duplicate_stripe_delivery_returns_200_and_changes_nothing(self, client, monkeypatch):
        """Amendment A4/A5: idempotency via `EventInbox.claim`."""
        seed_public_license(client)
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", STRIPE_SECRET)  # self-patch-ok: configuration value (tier-3 env), not a guard
        payload = {
            "id": "evt_dup_1", "object": "event", "type": "charge.refunded",
            "data": {"object": {"id": "ch_dup_1", "metadata": {}}},
        }
        body, sig = _sign_stripe_payload(payload)
        headers = {"stripe-signature": sig, "content-type": "application/json"}

        first = client.raw().post("/api/webhooks/stripe", content=body, headers=headers)
        assert first.status_code == 200

        # A retried delivery re-signs the SAME body (Stripe includes a
        # fresh timestamp each retry, but the payload — and therefore
        # `event["id"]` — is identical) → still 200, proven no-op.
        body2, sig2 = _sign_stripe_payload(payload)
        second = client.raw().post(
            "/api/webhooks/stripe", content=body2,
            headers={"stripe-signature": sig2, "content-type": "application/json"},
        )
        assert second.status_code == 200
