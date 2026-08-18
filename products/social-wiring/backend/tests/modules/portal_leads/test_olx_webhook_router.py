"""`POST /api/portals/olx/leads` — the status-code contract.

These are the highest-stakes assertions in the module. OLX reads **only**
our status code, retries a non-2xx three times, and then discards the
lead after 14 days with no replay API. So each status this route can
return is a deliberate decision about whether a real customer's enquiry
survives, and every one of them is pinned here.
"""
from __future__ import annotations

import base64
import copy
import pytest

from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD

from app.modules.portal_leads.deps import configure_portal_leads, reset_portal_leads
from app.services.app_config_store import OlxConfig

from tests.modules.portal_leads.conftest import ORG_A, WEBHOOK_SECRET

URL = "/api/portals/olx/leads"


def _basic(secret: str, username: str = "vivareal") -> dict:
    token = base64.b64encode(f"{username}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _body(**overrides):
    body = copy.deepcopy(OLX_SAMPLE_LEAD)
    body.update(overrides)
    return body


@pytest.fixture
def configured():
    """The receiver's secret + a single-tenant default org.

    Injected through the module's config seam — NOT
    `patch("...resolve_olx_config")`. Patching our own module is
    forbidden here (`KB § PATTERNS/backend/di-test-seam.md`) and
    `check_all_products` flags it high-severity, for a concrete reason: a
    patched attribute proves the stub works, not the wiring, and it keeps
    passing after the call site stops using that function.
    """
    config = OlxConfig(webhook_secret=WEBHOOK_SECRET, leads_org_id=ORG_A)
    configure_portal_leads(config_provider=lambda: config)
    try:
        yield config
    finally:
        reset_portal_leads()


class TestAuthentication:
    def test_valid_secret_is_accepted(self, http_client, configured):
        resp = http_client.post(URL, json=_body(), headers=_basic(WEBHOOK_SECRET))

        assert resp.status_code == 200

    def test_wrong_secret_is_401(self, http_client, configured):
        resp = http_client.post(URL, json=_body(), headers=_basic("wrong"))

        assert resp.status_code == 401

    def test_missing_authorization_header_is_401(self, http_client, configured):
        resp = http_client.post(URL, json=_body())

        assert resp.status_code == 401

    def test_wrong_basic_username_is_401(self, http_client, configured):
        resp = http_client.post(
            URL, json=_body(), headers=_basic(WEBHOOK_SECRET, username="attacker")
        )

        assert resp.status_code == 401

    def test_unconfigured_secret_is_401_not_open(self, http_client):
        """`bypass_when_unset=False`. An unconfigured receiver that
        accepted anything would write attacker-supplied leads into a real
        CRM — strictly worse than being temporarily down."""
        configure_portal_leads(config_provider=OlxConfig)
        try:
            resp = http_client.post(URL, json=_body(), headers=_basic("anything"))
        finally:
            reset_portal_leads()

        assert resp.status_code == 401


class TestStatusCodeContract:
    def test_accepted_lead_returns_200(self, http_client, configured):
        resp = http_client.post(URL, json=_body(), headers=_basic(WEBHOOK_SECRET))

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_listing_lead_without_client_listing_id_is_422(self, http_client, configured):
        """The ONE documented refusal: the vendor asks for a 4xx here so it
        requeues the lead with the field populated."""
        body = _body()
        del body["clientListingId"]

        resp = http_client.post(URL, json=body, headers=_basic(WEBHOOK_SECRET))

        assert resp.status_code == 422
        assert resp.json()["reason"] == "missing-client-listing-id"

    def test_mcmv_lead_without_listing_ids_is_200(self, http_client, configured):
        """MCMV leads never carry listing ids. 4xx-ing one would requeue a
        lead the vendor will never enrich, three times, and then drop it."""
        body = _body(leadOrigin="MCMV_OLX")
        del body["clientListingId"]
        del body["originListingId"]

        resp = http_client.post(URL, json=body, headers=_basic(WEBHOOK_SECRET))

        assert resp.status_code == 200

    def test_unknown_enum_value_still_returns_200(self, http_client, configured):
        """A channel the vendor adds next week is a stale doc on our side,
        not a bad lead. Refusing it would cost a real customer."""
        body = _body(temperature="Escaldante")
        body["extraData"]["leadType"] = "CLICK_TELEPATHY"

        resp = http_client.post(URL, json=body, headers=_basic(WEBHOOK_SECRET))

        assert resp.status_code == 200

    def test_malformed_json_returns_200_not_a_retry_request(self, http_client, configured):
        """A retry would deliver the same malformed body two more times.
        The 200 stops the loop; the log is what makes it findable."""
        resp = http_client.post(
            URL, content=b"{not json", headers={
                **_basic(WEBHOOK_SECRET), "Content-Type": "application/json",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["reason"] == "malformed-json"

    def test_body_without_origin_lead_id_returns_200(self, http_client, configured):
        body = _body()
        del body["originLeadId"]

        resp = http_client.post(URL, json=body, headers=_basic(WEBHOOK_SECRET))

        assert resp.status_code == 200
        assert resp.json()["reason"] == "no-origin-lead-id"

    def test_json_array_body_returns_200(self, http_client, configured):
        resp = http_client.post(URL, json=[1, 2], headers=_basic(WEBHOOK_SECRET))

        assert resp.status_code == 200
        assert resp.json()["reason"] == "not-an-object"


class TestIdempotency:
    def test_redelivery_is_reported_as_duplicate_and_still_200(
        self, http_client, configured
    ):
        """Retries and the 14-day store make duplicate delivery ordinary
        traffic. It must be cheap and it must be a 2xx."""
        first = http_client.post(URL, json=_body(), headers=_basic(WEBHOOK_SECRET))
        second = http_client.post(URL, json=_body(), headers=_basic(WEBHOOK_SECRET))

        assert first.status_code == 200
        assert first.json()["status"] == "accepted"
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"

    def test_the_delivery_is_recorded_before_processing(
        self, http_client, configured, mock_db
    ):
        """Persist-then-200: the inbox row, not the status code, is what
        makes a processing failure recoverable.

        Read back through `get_leads_client()`, NOT a fresh
        `mock_db.schema(...)`: that call returns a brand-new wrapper with
        an empty per-table cache every time, so a fresh one sees none of
        the route's writes (documented at `app/modules/leads/deps.py`).
        """
        from app.modules.leads.deps import get_leads_client

        http_client.post(URL, json=_body(), headers=_basic(WEBHOOK_SECRET))

        events = get_leads_client().table("olx_lead_events").select("*").execute().data
        assert len(events) == 1
        assert events[0]["id"] == "59ee0fc6e4b043e1b2a6d863"
        assert events[0]["payload"]["name"] == "Nome Consumidor"
