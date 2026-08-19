"""`POST /api/portals/olx/leads/{receiver_token}` — the multi-tenant form.

The tokenless route's status-code contract is pinned in
`test_olx_webhook_router.py` and is not re-tested here. What is unique to
this route is **who the lead is attributed to**, and the two ways that can
go wrong are opposite failures:

* refusing an unresolvable token → Grupo OLX retries three times, then
  discards a real customer after 14 days, with no replay API;
* falling back to a configured default org → that customer is delivered
  into a *different advertiser's* CRM, silently and irreversibly.

The second is the one a reasonable implementation drifts into, because
`get_olx_service` already exists and already does the fallback. It is
regression-tested below.
"""
from __future__ import annotations

import base64
import copy
import pytest

from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD

from app.modules.portal_leads.deps import configure_portal_leads, reset_portal_leads
from app.modules.portal_leads.services.receiver_token_service import (
    generate_receiver_token,
    mint_receiver_token,
)
from app.services.app_config_store import OlxConfig

from tests.modules.portal_leads.conftest import ORG_A, ORG_B, WEBHOOK_SECRET

BASE = "/api/portals/olx/leads"


def _basic(secret: str, username: str = "vivareal") -> dict:
    token = base64.b64encode(f"{username}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _body(**overrides):
    body = copy.deepcopy(OLX_SAMPLE_LEAD)
    body.update(overrides)
    return body


@pytest.fixture
def configured():
    """Secret set, and `OLX_LEADS_ORG_ID` pointing at **ORG_A**.

    ORG_A is deliberately not the org any token below is minted for. It
    is the wrong answer, sitting in reach of the code under test, so a
    fallback regression shows up as a failed assertion rather than as a
    lead quietly landing in the wrong CRM.
    """
    config = OlxConfig(webhook_secret=WEBHOOK_SECRET, leads_org_id=ORG_A)
    configure_portal_leads(config_provider=lambda: config)
    try:
        yield config
    finally:
        reset_portal_leads()


@pytest.fixture
def leads_client(http_client):
    """The very client the receiver writes through.

    `MockSupabaseClient.schema()` returns a NEW object per call, and rows
    written through one are invisible to another. Reaching for
    `mock_db.schema("social_wiring")` here would therefore read an empty
    store no matter what the route did — every negative assertion below
    would pass for the wrong reason, which is worse than failing.
    `get_leads_client()` is memoised per admin client, so asking it is
    asking the app.
    """
    from app.modules.leads.deps import get_leads_client

    return get_leads_client()


@pytest.fixture
def token_for_org_b(leads_client):
    return mint_receiver_token(
        leads_client,
        org_id=ORG_B,
        provider="olx",
        label="One Consultoria",
    )


def _lead_org_ids(client) -> list[str]:
    rows = client.table("leads").select("*").execute().data
    return [str(r.get("org_id")) for r in (rows or [])]


class TestAuthentication:
    def test_wrong_secret_is_401(self, http_client, configured, token_for_org_b):
        resp = http_client.post(
            f"{BASE}/{token_for_org_b.plaintext}",
            json=_body(),
            headers=_basic("wrong"),
        )

        assert resp.status_code == 401

    def test_missing_authorization_header_is_401(
        self, http_client, configured, token_for_org_b
    ):
        resp = http_client.post(
            f"{BASE}/{token_for_org_b.plaintext}", json=_body()
        )

        assert resp.status_code == 401

    def test_auth_is_checked_before_the_token(self, http_client, configured):
        """A bad secret on a nonsense token is still exactly 401.

        Not `in (401, 404)`: a 404 here would mean the router matched no
        route, which proves nothing about the auth boundary
        (`KB § PATTERNS/compliance/auth-boundary-false-green.md`).
        """
        resp = http_client.post(
            f"{BASE}/rcv_nonexistent", json=_body(), headers=_basic("wrong")
        )

        assert resp.status_code == 401


class TestTenantAttribution:
    def test_lead_lands_in_the_token_org(
        self, http_client, configured, token_for_org_b, leads_client
    ):
        resp = http_client.post(
            f"{BASE}/{token_for_org_b.plaintext}",
            json=_body(),
            headers=_basic(WEBHOOK_SECRET),
        )

        assert resp.status_code == 200
        assert ORG_B in _lead_org_ids(leads_client)

    def test_token_org_wins_over_the_configured_default(
        self, http_client, configured, token_for_org_b, leads_client
    ):
        """ORG_A is configured as the default; the token says ORG_B."""
        http_client.post(
            f"{BASE}/{token_for_org_b.plaintext}",
            json=_body(),
            headers=_basic(WEBHOOK_SECRET),
        )

        assert ORG_A not in _lead_org_ids(leads_client)

    def test_unknown_token_is_still_200(
        self, http_client, configured, leads_client
    ):
        """The lead must survive a rotated or mistyped token.

        Authentication already passed, so this delivery came from Grupo
        OLX. A 4xx would spend the three retries and then bin a real
        enquiry.
        """
        resp = http_client.post(
            f"{BASE}/{generate_receiver_token()}",
            json=_body(),
            headers=_basic(WEBHOOK_SECRET),
        )

        assert resp.status_code == 200

    def test_unknown_token_does_not_fall_back_to_the_default_org(
        self, http_client, configured, leads_client
    ):
        """🔴 The tenant-leak regression.

        `get_olx_service` resolves to `OLX_LEADS_ORG_ID`, and reaching for
        it here — the obvious reuse — would deliver this advertiser's
        customer into ORG_A's CRM. An unresolved token must park, not
        guess.
        """
        http_client.post(
            f"{BASE}/{generate_receiver_token()}",
            json=_body(),
            headers=_basic(WEBHOOK_SECRET),
        )

        assert ORG_A not in _lead_org_ids(leads_client)

    def test_a_bearer_token_in_the_path_does_not_route(
        self, http_client, configured, leads_client
    ):
        """A `pk_*` api_token is not a receiver token, in either direction."""
        resp = http_client.post(
            f"{BASE}/pk_{'a' * 43}", json=_body(), headers=_basic(WEBHOOK_SECRET)
        )

        assert resp.status_code == 200
        assert ORG_A not in _lead_org_ids(leads_client)


class TestDownstreamForwarding:
    """The wiring, not the service. `test_forward_service.py` proves the
    outbox behaves; this proves a real delivery actually reaches it."""

    def test_a_delivery_enqueues_a_forward_for_the_token_org(
        self, http_client, configured, token_for_org_b, leads_client
    ):
        leads_client.table("portal_lead_forward_targets").insert(
            {
                "id": "tgt-1",
                "org_id": ORG_B,
                "provider": "olx",
                "label": "Lais",
                "url": "https://crm.test/hook",
                "auth_mode": "passthrough",
                "is_active": True,
            }
        ).execute()

        resp = http_client.post(
            f"{BASE}/{token_for_org_b.plaintext}",
            json=_body(),
            headers=_basic(WEBHOOK_SECRET),
        )

        assert resp.status_code == 200
        queued = (
            leads_client.table("portal_lead_forwards").select("*").execute().data or []
        )
        assert len(queued) == 1
        assert queued[0]["org_id"] == ORG_B

    def test_the_queued_body_is_the_bytes_the_vendor_sent(
        self, http_client, configured, token_for_org_b, leads_client
    ):
        """Not our re-serialisation of a parse.

        The downstream CRM is entitled to any field we do not model yet,
        so the router carries the raw body down rather than letting the
        forward rebuild it from `OlxLead`.
        """
        leads_client.table("portal_lead_forward_targets").insert(
            {
                "id": "tgt-1", "org_id": ORG_B, "provider": "olx", "label": "Lais",
                "url": "https://crm.test/hook", "auth_mode": "passthrough",
                "is_active": True,
            }
        ).execute()

        body = _body()
        body["campoQueNaoModelamos"] = "preserve me"
        http_client.post(
            f"{BASE}/{token_for_org_b.plaintext}",
            json=body,
            headers=_basic(WEBHOOK_SECRET),
        )

        queued = leads_client.table("portal_lead_forwards").select("*").execute().data
        assert "campoQueNaoModelamos" in (queued[0]["body"] or "")

    def test_an_org_with_no_target_queues_nothing(
        self, http_client, configured, token_for_org_b, leads_client
    ):
        """Most advertisers forward nowhere; that must cost nothing."""
        http_client.post(
            f"{BASE}/{token_for_org_b.plaintext}",
            json=_body(),
            headers=_basic(WEBHOOK_SECRET),
        )

        queued = (
            leads_client.table("portal_lead_forwards").select("*").execute().data or []
        )
        assert queued == []


class TestCoexistenceWithTheTokenlessRoute:
    def test_tokenless_route_still_uses_the_configured_org(
        self, http_client, configured, leads_client
    ):
        """Rung 3 survives. Any homologation already registered against
        the bare URL keeps working after this route ships."""
        resp = http_client.post(
            BASE, json=_body(), headers=_basic(WEBHOOK_SECRET)
        )

        assert resp.status_code == 200
        assert ORG_A in _lead_org_ids(leads_client)
