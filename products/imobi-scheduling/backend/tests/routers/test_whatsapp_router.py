"""
Tests for the WhatsApp inbound webhook wiring (Phase 5).

Pins the consumer-side ``on_message`` handler behavior + the seed router's
signature verification at our HTTP path (``/api/webhooks/whatsapp``). The
seed router itself is tested at ``seed/lib/backend/tests/integrations/whatsapp/``;
these tests cover the product-level hooks (authorization dispatch, pushName
refresh, pending-LID parking).

Webhook compliance 5-pin contract — status-code-assertion-rule applies
to every test in this file. Patches target the WAHA HTTP boundary (none
in inbound path — the seed router handles it) and the admin client
factory (``app.routers.whatsapp_router._resolve_admin_client``) per the
"no monkey-patching of our own guards" rule. The admin-client patch is
the canonical product-level seam, mirroring how the example_router tests
patch ``app.database._db.get_client`` at the fixture level.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from unittest.mock import patch

from noctusai_lib.testing import MockSupabaseClient

from app.config import settings


# ---------------------------------------------------------------------------
# Stable-scoped MockSupabaseClient — bridge for fresh-instance ``.schema()``
# ---------------------------------------------------------------------------
#
# ``MockSupabaseClient.schema(name)`` returns a fresh instance each call. The
# AuthorizationService caches its scoped client at __init__ so its writes
# observe consistently; tests at the *router* level can't reach in there,
# so we wrap a single stable scoped-client per (root_client) and replay it
# on every ``schema()`` call. Internal-uniform / edge-adapt: keep the seed
# Mock behavior intact, adapt at the test boundary.

class _StableScopedClient:
    """Wraps MockSupabaseClient with a single cached `.schema(name)` result.

    Every call to ``.schema(name)`` on the wrapper returns the SAME scoped
    client, so ``.table(...).inserted_payloads`` reads back what the
    service wrote. ``auth`` / ``storage`` proxy through to the underlying
    root for fixture compatibility.
    """

    def __init__(self, root: MockSupabaseClient):
        self._root = root
        self._scoped_cache: dict[str, MockSupabaseClient] = {}
        self.auth = root.auth
        self.storage = root.storage

    def schema(self, name: str) -> MockSupabaseClient:
        if name not in self._scoped_cache:
            self._scoped_cache[name] = self._root.schema(name)
        return self._scoped_cache[name]

    def table(self, name):
        return self._root.table(name)

    def from_(self, name):
        return self._root.from_(name)

    def scoped(self, name: str = "imobi_scheduling") -> MockSupabaseClient:
        """Test-time alias for the cached scoped client. Lets tests
        write ``db.scoped().table("users").inserted_payloads``."""
        return self.schema(name)


WHATSAPP_PATH = "/api/webhooks/whatsapp"

SECRET = "imobi-whatsapp-test-secret"


def _hex_sig(body: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 hex signature the seed router expects."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _inbound_payload(
    *,
    provider_id: str = "msg-1",
    from_phone: str = "5511999999999@c.us",
    text: str = "Bom dia",
    push_name: str | None = None,
) -> dict:
    payload = {
        "event": "message",
        "session": settings.waha_session_name,
        "payload": {
            "id": provider_id,
            "from": from_phone,
            "body": text,
        },
    }
    if push_name is not None:
        # WAHA carries pushName under `_data.notifyName` and at the top-level
        # `payload.notifyName` in newer versions. The seed mapper reads
        # `payload.notifyName` — match that shape.
        payload["payload"]["notifyName"] = push_name
    return payload


def _user_row(
    *,
    user_id: str = "11111111-1111-1111-1111-111111111111",
    org_id: str | None = None,
    phone: str = "+5511999999999",
    name: str = "Original Name",
    role: str = "real_estate_agent",
    linked_identity: str | None = None,
    active: bool = True,
) -> dict:
    # ``coerce_org_uuid("imobi-scheduling-default")`` lands on a deterministic
    # UUID derived from NAMESPACE_OID. Mirror the value the production code
    # computes so the AuthorizationService's `.eq("org_id", ...)` filter
    # matches the seeded row.
    if org_id is None:
        from app.dependencies import coerce_org_uuid
        org_id = str(coerce_org_uuid("imobi-scheduling-default"))
    return {
        "id": user_id,
        "org_id": org_id,
        "name": name,
        "phone_number": phone,
        "role": role,
        "linked_identity": linked_identity,
        "active": active,
    }


# ---------------------------------------------------------------------------
# Happy path — signature verification + authorized inbound
# ---------------------------------------------------------------------------


class TestWhatsAppRouterMounting:
    """The router is mounted at the canonical ``/api/webhooks/whatsapp`` path."""

    def test_router_is_reachable(self, client, monkeypatch):
        """Empty secret → bypass mode; a malformed event yields a documented
        4xx, never a 404 — proves the route is registered."""
        monkeypatch.setattr(settings, "imobi_whatsapp_webhook_secret", "")
        resp = client.raw().post(WHATSAPP_PATH, content=b"not json")
        assert resp.status_code == 400


class TestWhatsAppRouterSignatureVerification:
    """Pins 1-3 of the 5-pin contract — verified by the seed router.

    The seed factory captures ``settings.webhook_hmac_secret`` at router
    construction time (module-import time). Late ``monkeypatch.setattr``
    on the product settings therefore can't retroactively flip a router
    that was mounted with a None secret. We exercise three complementary
    angles instead:

      1. **Production shape (this fixture)** — empty secret default →
         bypass mode → 200 with WARNING. Pins the production-default
         contract.
      2. **Direct seed-router rebuild** — drive a fresh router with a
         live secret in-process via the seed factory; verify
         missing-signature → 401 + valid-signature → 200. This is the
         test that pins signature enforcement at the consumer wiring.
      3. **Seed tests** — the seed-side ``test_router.py`` covers the
         signature-verification matrix end-to-end (we don't re-test
         what the seed already pins).

    The "no-monkey-patching-of-our-own-code" rule applies — we don't
    patch settings; we construct a fresh seed router with the desired
    secret + mount on a throwaway FastAPI app.
    """

    def test_missing_signature_in_bypass_mode_returns_200(self, client, monkeypatch):
        """Empty secret default → bypass; webhook accepts unsigned
        payloads with a WARNING (production-default early-dev shape)."""
        with patch(
            "app.routers.whatsapp_router._resolve_admin_client",
            return_value=MockSupabaseClient(data=[_user_row()]),
        ):
            resp = client.raw().post(
                WHATSAPP_PATH,
                json=_inbound_payload(),
            )
        assert resp.status_code == 200
        assert resp.json()["status"] in {"accepted", "ignored"}

    def test_valid_signature_returns_200_against_rebuilt_router(self):
        """Pin signature enforcement at the consumer wiring shape.

        We construct a fresh seed router with a live secret + mount on a
        throwaway FastAPI app. Posting a body with a valid HMAC-SHA256
        hex signature lands on 200. This is the consumer-side
        equivalent of ``seed/tests/integrations/whatsapp/test_router.py
        ::test_router_accepts_valid_signature`` — it pins that the
        wiring path we use (``WhatsAppSettings`` + factory call shape)
        produces a router that actually verifies signatures.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from noctusai_lib.integrations.whatsapp import (
            WhatsAppSettings,
            create_whatsapp_webhook_router,
        )
        from app.routers.whatsapp_router import handle_inbound_whatsapp

        wa_settings = WhatsAppSettings(
            base_url="http://waha",
            webhook_hmac_secret=SECRET,
            session="imobi_scheduling",
        )
        seed_router = create_whatsapp_webhook_router(
            settings=wa_settings,
            on_message=handle_inbound_whatsapp,
        )
        app = FastAPI()
        app.include_router(seed_router, prefix="/api/webhooks/whatsapp")
        local = TestClient(app)

        payload = _inbound_payload(provider_id="sig-ok")
        body_bytes = json.dumps(payload, separators=(",", ":")).encode()
        sig = _hex_sig(body_bytes, SECRET)

        with patch(
            "app.routers.whatsapp_router._resolve_admin_client",
            return_value=MockSupabaseClient(data=[_user_row()]),
        ):
            resp = local.post(
                WHATSAPP_PATH,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Hmac-SHA256": sig,
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "accepted"}

    def test_missing_signature_returns_401_when_secret_configured(self):
        """When the secret IS configured, missing signature header → 401.

        Companion to the valid-signature test above — same fixture
        shape (rebuild router with a live secret on a throwaway app)
        so the seed factory's signature enforcement is exercised at
        the consumer-side wiring.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from noctusai_lib.integrations.whatsapp import (
            WhatsAppSettings,
            create_whatsapp_webhook_router,
        )
        from app.routers.whatsapp_router import handle_inbound_whatsapp

        wa_settings = WhatsAppSettings(
            base_url="http://waha",
            webhook_hmac_secret=SECRET,
        )
        seed_router = create_whatsapp_webhook_router(
            settings=wa_settings,
            on_message=handle_inbound_whatsapp,
        )
        app = FastAPI()
        app.include_router(seed_router, prefix="/api/webhooks/whatsapp")
        local = TestClient(app)

        resp = local.post(
            WHATSAPP_PATH,
            json=_inbound_payload(),
        )
        assert resp.status_code == 401


class TestWhatsAppInboundAuthorization:
    """The on_message handler dispatches authorization + persistence."""

    def test_authorized_phone_match_returns_200_accepted(self, client):
        mock_db = MockSupabaseClient(data=[_user_row()])
        with patch(
            "app.routers.whatsapp_router._resolve_admin_client",
            return_value=mock_db,
        ):
            resp = client.raw().post(
                WHATSAPP_PATH,
                json=_inbound_payload(provider_id="auth-1"),
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "accepted"}

    def test_unauthorized_lid_inbound_parks_pending(self, client):
        """LID inbound + no match → pending_chat_identities INSERT."""
        # Empty user table → no phone match + no LID match → pending park.
        mock_db = _StableScopedClient(MockSupabaseClient(data=[]))
        lid_chat_id = "5511888888888@lid_abcdef0123456789"
        with patch(
            "app.routers.whatsapp_router._resolve_admin_client",
            return_value=mock_db,
        ):
            resp = client.raw().post(
                WHATSAPP_PATH,
                json=_inbound_payload(
                    provider_id="park-1",
                    from_phone=lid_chat_id,
                    push_name="Pending User",
                ),
            )
        assert resp.status_code == 200
        # Verify pending row landed.
        inserts = (
            mock_db.scoped()
            .table("pending_chat_identities")
            .inserted_payloads
        )
        assert len(inserts) == 1
        assert inserts[0]["chat_id"] == lid_chat_id
        assert inserts[0]["push_name"] == "Pending User"
        assert inserts[0]["status"] == "pending"

    def test_unauthorized_non_lid_drops_silently_with_warning(self, client, caplog):
        """No LID + no phone match → log + drop (no DB write)."""
        mock_db = MockSupabaseClient(data=[])
        with patch(
            "app.routers.whatsapp_router._resolve_admin_client",
            return_value=mock_db,
        ):
            with caplog.at_level(logging.WARNING, logger="app.routers.whatsapp_router"):
                resp = client.raw().post(
                    WHATSAPP_PATH,
                    json=_inbound_payload(
                        provider_id="drop-1",
                        from_phone="5599000000000@c.us",  # unknown phone, not a LID
                    ),
                )
        assert resp.status_code == 200
        assert any(
            "rejected" in r.message.lower() for r in caplog.records
        ), "expected rejection WARNING in log"
        # No pending-LID row written (not a LID).
        inserts = (
            mock_db.schema("imobi_scheduling")
            .table("pending_chat_identities")
            .inserted_payloads
        )
        assert inserts == []


class TestWhatsAppInboundPushNameRefresh:
    """Authorized inbound + pushName → users.name UPDATE."""

    def test_push_name_writes_to_users_name(self, client):
        mock_db = _StableScopedClient(
            MockSupabaseClient(data=[_user_row(name="Stale Name")])
        )
        with patch(
            "app.routers.whatsapp_router._resolve_admin_client",
            return_value=mock_db,
        ):
            resp = client.raw().post(
                WHATSAPP_PATH,
                json=_inbound_payload(
                    provider_id="push-1",
                    push_name="Fresh Name",
                ),
            )
        assert resp.status_code == 200
        # Verify the UPDATE landed on users.
        updates = (
            mock_db.scoped()
            .table("users")
            .updated_payloads
        )
        # At least one update with `name=Fresh Name`. May also include
        # `linked_identity` capture from the service's path-3, but our
        # phone-match test uses `@c.us` (not a LID) so no LID write.
        push_name_updates = [u for u in updates if u.get("name") == "Fresh Name"]
        assert len(push_name_updates) >= 1


class TestWhatsAppInboundIdempotency:
    """The seed router dedups against provider_message_id — once per ID."""

    def test_duplicate_provider_id_returns_duplicate_status(self, client):
        mock_db = MockSupabaseClient(data=[_user_row()])
        with patch(
            "app.routers.whatsapp_router._resolve_admin_client",
            return_value=mock_db,
        ):
            first = client.raw().post(
                WHATSAPP_PATH,
                json=_inbound_payload(provider_id="dup-1"),
            )
            second = client.raw().post(
                WHATSAPP_PATH,
                json=_inbound_payload(provider_id="dup-1"),
            )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == {"status": "accepted"}
        assert second.json() == {"status": "duplicate"}


class TestWhatsAppInboundIgnoredEvents:
    """Non-message events (session.status etc.) return 200 + ``ignored``."""

    def test_session_status_event_ignored(self, client):
        # No admin call needed — ignored events short-circuit before the
        # on_message handler runs. Don't patch _resolve_admin_client; the
        # seed router never reaches the consumer hook.
        resp = client.raw().post(
            WHATSAPP_PATH,
            json={
                "event": "session.status",
                "session": settings.waha_session_name,
                "payload": {"status": "WORKING"},
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored"}
