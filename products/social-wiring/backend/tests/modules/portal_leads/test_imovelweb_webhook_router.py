"""`POST /api/portals/imovelweb/leads` — the status-code contract.

The highest-stakes assertions in this slice. The vendor allows 1.5 seconds
to answer, retries a failure until 72 hours have passed, then marks the
callback ``VENCIDO``. So every status this route returns is a decision about
whether a real customer's enquiry survives, and every one is pinned.

Two of them differ from the OLX sibling and a reviewer will be tempted to
"fix" them back. Both are commented at the assertion, not just in the router.
"""
from __future__ import annotations

import base64
import copy

import pytest

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_SAMPLE_BODIES,
    basic_credential,
)

from app.modules.portal_leads.deps import configure_portal_leads, reset_portal_leads
from app.services.app_config_store import ImovelWebConfig

from tests.modules.portal_leads.conftest import IMOVELWEB_WEBHOOK_SECRET, ORG_A

URL = "/api/portals/imovelweb/leads"


def _auth(secret: str = IMOVELWEB_WEBHOOK_SECRET) -> dict:
    return {"Authorization": basic_credential(secret)}


def _basic(secret: str, username: str) -> dict:
    token = base64.b64encode(f"{username}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _body(**overrides):
    body = copy.deepcopy(IMOVELWEB_SAMPLE_BODIES["EN2"])
    body.update(overrides)
    return body


@pytest.fixture
def configured():
    """The receiver's secret + a single-tenant default org, through the
    module's config seam — NOT `patch(...)`. Patching our own module is
    forbidden here (`KB § PATTERNS/backend/di-test-seam.md`): a patched
    attribute proves the stub works, not the wiring, and it keeps passing
    after the call site stops using that function."""
    config = ImovelWebConfig(
        webhook_secret=IMOVELWEB_WEBHOOK_SECRET, leads_org_id=ORG_A
    )
    configure_portal_leads(imovelweb_config_provider=lambda: config)
    try:
        yield config
    finally:
        reset_portal_leads()


class TestAuthentication:
    def test_valid_credential_is_accepted(self, http_client, configured):
        resp = http_client.post(URL, json=_body(), headers=_auth())

        assert resp.status_code == 200

    def test_wrong_secret_is_401(self, http_client, configured):
        # Substituted for the KB template's "tampered body" case: this
        # scheme has NO body binding, so a tampered-body test would assert
        # nothing. See test_tampered_body_still_200 below, which documents
        # the weakness instead of pretending it is covered.
        resp = http_client.post(URL, json=_body(), headers=_auth("wrong"))

        assert resp.status_code == 401

    def test_missing_authorization_header_is_401(self, http_client, configured):
        resp = http_client.post(URL, json=_body())

        assert resp.status_code == 401

    def test_the_olx_username_is_rejected(self, http_client, configured):
        # The seed's default username is Grupo OLX's `vivareal`. Leaving it
        # would mean this receiver accepted the OTHER pipe's credential
        # shape — different vendor, different secret, no relationship.
        resp = http_client.post(
            URL, json=_body(), headers=_basic(IMOVELWEB_WEBHOOK_SECRET, "vivareal")
        )

        assert resp.status_code == 401

    def test_unconfigured_secret_is_401_not_open(self, http_client):
        """`bypass_when_unset=False`, the INVERSE of the KB template's
        fourth case (which asserts bypass-with-WARNING). Pinned here with
        the reason so nobody "fixes" it back to the template: an
        unconfigured receiver that accepted anything would write
        attacker-supplied leads into a real CRM, which is strictly worse
        than being temporarily down."""
        configure_portal_leads(imovelweb_config_provider=ImovelWebConfig)
        try:
            resp = http_client.post(URL, json=_body(), headers=_auth("anything"))
        finally:
            reset_portal_leads()

        assert resp.status_code == 401

    def test_tampered_body_still_200(self, http_client, configured):
        """Documents the scheme's weakness rather than hiding it.

        `basic_shared_secret` authenticates the CALLER, not the BODY: there
        is no signature over the payload, so anyone holding the secret can
        send anything. The compensations are TLS, idempotency on `eventId`,
        and the fact that the body is a hint — `imovelweb.leads.get_message`
        is authoritative for anything that matters.
        """
        resp = http_client.post(
            URL, json=_body(name="Tampered", email="attacker@example.com"),
            headers=_auth(),
        )

        assert resp.status_code == 200


class TestStatusProtocol:
    def test_malformed_json_is_200(self, http_client, configured):
        # The retry arrives equally malformed, so a non-2xx would only
        # burn the 72-hour window on a body that cannot improve.
        resp = http_client.post(
            URL, content=b"{not json", headers={**_auth(), "Content-Type": "application/json"}
        )

        assert resp.status_code == 200
        assert resp.json()["reason"] == "malformed-json"

    def test_a_json_array_is_200(self, http_client, configured):
        resp = http_client.post(URL, json=[1, 2, 3], headers=_auth())

        assert resp.status_code == 200
        assert resp.json()["reason"] == "not-an-object"

    def test_no_event_id_is_200(self, http_client, configured):
        body = _body()
        body.pop("eventId")
        resp = http_client.post(URL, json=body, headers=_auth())

        assert resp.status_code == 200
        assert resp.json()["reason"] == "no-event-id"

    def test_missing_client_listing_id_is_200_not_422(self, http_client, configured):
        """🔴 THE DIVERGENCE FROM OLX. Do not copy the 422 from
        `olx_webhook.py`.

        Grupo OLX documents a requeue path for a listing lead with no
        `clientListingId`, so a 4xx there is correct. ImovelWeb documents
        NO such path, and the field is legitimately absent when the listing
        was never associated — so a 4xx here starts a 72-hour retry loop
        over a field that will never arrive.
        """
        body = _body()
        body.pop("clientListingId")
        resp = http_client.post(URL, json=body, headers=_auth())

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_a_duplicate_delivery_is_200(self, http_client, configured):
        # Ordinary traffic, not an anomaly: the vendor retries for 72 hours
        # AND the reconcile job re-reads the same window.
        first = http_client.post(URL, json=_body(), headers=_auth())
        second = http_client.post(URL, json=_body(), headers=_auth())

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"

    def test_a_pt_body_is_accepted(self, http_client, configured):
        """The registered language decides the vendor's FIELD NAMES. A
        receiver that only understood EN2 would 200-and-ignore every body
        after someone changed the setting vendor-side."""
        resp = http_client.post(
            URL, json=copy.deepcopy(IMOVELWEB_SAMPLE_BODIES["PT"]), headers=_auth()
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_durable_write_failure_is_5xx(self, http_client, configured, monkeypatch):
        """🔴 THE OTHER DIVERGENCE, and the one place a non-2xx is right.

        Everywhere else a non-2xx to this vendor costs a lead. Here it
        SAVES one: we could not store the body, so a 200 would tell the
        vendor to forget an enquiry we do not have. It retries for 72 hours
        and the pull API backstops that; a 200 over a failed write has no
        backstop at all. Documented so nobody "fixes" it.
        """
        from app.modules.portal_leads.routers import imovelweb_webhook
        from app.main import app

        class _FailingService:
            def is_duplicate(self, event_id):
                return False

            def record_event(self, lead, **kwargs):
                raise RuntimeError("database unavailable")

            def record_unparseable(self, *a, **k):
                return None

        app.dependency_overrides[imovelweb_webhook.get_imovelweb_service] = (
            lambda: _FailingService()
        )
        try:
            resp = http_client.post(URL, json=_body(), headers=_auth())
        finally:
            app.dependency_overrides.pop(
                imovelweb_webhook.get_imovelweb_service, None
            )

        assert resp.status_code == 503
        assert resp.json()["reason"] == "durable-write-failed"


class TestResponseBudget:
    def test_the_request_path_makes_at_most_two_round_trips(
        self, http_client, configured
    ):
        """The deterministic form of the 1.5-second budget.

        A wall-clock assertion would be flaky; the count of database
        round-trips before answering is not, and it is the thing that
        actually varies when someone adds "just one more lookup" to the
        request path. Two today: the dedup SELECT and the INSERT — see the
        NOC-REMEDIATE marker on `record_event`.
        """
        from app.modules.portal_leads.routers import imovelweb_webhook
        from app.modules.portal_leads.services.imovelweb_webhook_service import (
            ImovelWebWebhookService,
        )
        from app.main import app

        captured = {}

        class _CountingService(ImovelWebWebhookService):
            def process_lead(self, lead):
                # The background half must not be counted — it runs after
                # the response is on the wire.
                captured["before_response"] = self.calls_before_response
                return None

        from noctusai_lib.testing import MockSupabaseClient

        svc = _CountingService(client=MockSupabaseClient().schema("social_wiring"))
        app.dependency_overrides[imovelweb_webhook.get_imovelweb_service] = lambda: svc
        try:
            resp = http_client.post(URL, json=_body(), headers=_auth())
        finally:
            app.dependency_overrides.pop(
                imovelweb_webhook.get_imovelweb_service, None
            )

        assert resp.status_code == 200
        assert svc.calls_before_response <= 2, (
            "the vendor allows 1500ms for the whole response; every extra "
            "round-trip on this path spends part of that budget"
        )

    def test_the_response_reports_its_own_latency(self, http_client, configured):
        # The vendor ignores our body, so this is for us — and it is what
        # `imovelweb.webhook.simulate` reads back to check the budget
        # locally, before Gate 1 can measure it for real.
        resp = http_client.post(URL, json=_body(), headers=_auth())

        payload = resp.json()
        assert "elapsedMs" in payload
        assert payload["withinBudget"] is True
