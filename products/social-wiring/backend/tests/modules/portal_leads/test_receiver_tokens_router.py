"""`/api/portals/receiver-tokens/*` — minting the URL an operator pastes.

What this router exists to get right is narrow: produce a URL that will
actually receive, or refuse. Both failure modes it guards against are
silent ones — a URL that 404s, and a URL built against an unknown base —
and each presents downstream as "no leads are arriving", which is
indistinguishable from a quiet week.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.modules.portal_leads.services.receiver_token_service import (
    resolve_receiver_token,
)

from tests.modules.portal_leads.conftest import ORG_A

BASE = "/api/portals/receiver-tokens"
PUBLIC_HOST = "https://social-wiring.noctusai.com"


@pytest.fixture
def public_base(monkeypatch):
    """Set the deployment's public origin.

    Setting a settings VALUE, not patching our own behaviour: the code
    path under test still runs in full. `tunnel_hostname` is what the
    tunnel actually routes, which is why `_public_base_url` prefers it.
    """
    monkeypatch.setattr(settings, "tunnel_hostname", PUBLIC_HOST)


@pytest.fixture
def leads_client(http_client):
    from app.modules.leads.deps import get_leads_client

    return get_leads_client()


class TestAuthBoundary:
    """Strict `== 401`, never `in (401, 404)` — a non-401 here would pass
    just as happily if the route were absent."""

    def test_mint_rejects_anonymous(self, http_client):
        resp = http_client.post(BASE, json={"provider": "olx", "label": "x"})

        assert resp.status_code == 401

    def test_list_rejects_anonymous(self, http_client):
        assert http_client.get(BASE).status_code == 401

    def test_revoke_rejects_anonymous(self, http_client):
        resp = http_client.delete(f"{BASE}/00000000-0000-4000-8000-000000000001")

        assert resp.status_code == 401


class TestMint:
    def test_returns_a_url_that_matches_the_live_receiver_route(
        self, http_client, public_base, leads_client
    ):
        """The assertion that makes the URL trustworthy.

        A hand-built string could drift from the route the app actually
        serves and nobody would notice until a vendor pasted it. So the
        minted URL's path is checked against the router's own registered
        paths rather than against a copy of the expected string.
        """
        from app.main import app

        resp = http_client.post(
            BASE,
            json={"provider": "olx", "label": "One Consultoria"},
            headers={"Authorization": "Bearer any"},
        )

        assert resp.status_code == 201
        url = resp.json()["url"]
        assert url.startswith(f"{PUBLIC_HOST}/api/portals/olx/leads/")

        served = {getattr(r, "path", "") for r in app.routes}
        assert "/api/portals/olx/leads/{receiver_token}" in served

    def test_the_minted_url_actually_resolves(
        self, http_client, public_base, leads_client
    ):
        resp = http_client.post(
            BASE,
            json={"provider": "olx", "label": "One Consultoria"},
            headers={"Authorization": "Bearer any"},
        )

        token = resp.json()["url"].rsplit("/", 1)[-1]

        assert (
            resolve_receiver_token(leads_client, provider="olx", token=token)
            is not None
        )

    def test_unknown_provider_is_422(self, http_client, public_base):
        resp = http_client.post(
            BASE,
            json={"provider": "zap", "label": "x"},
            headers={"Authorization": "Bearer any"},
        )

        assert resp.status_code == 422

    def test_provider_without_a_receiver_route_is_refused(
        self, http_client, public_base, leads_client
    ):
        """`imovelweb` passes the table's CHECK but has no route on this
        branch. Minting it would hand over a URL that 404s — and a 404 is
        a non-2xx, which costs the lead after three retries."""
        resp = http_client.post(
            BASE,
            json={"provider": "imovelweb", "label": "x"},
            headers={"Authorization": "Bearer any"},
        )

        assert resp.status_code == 422
        # And nothing was persisted — no orphan token nobody can use.
        # postgrest-unbounded-ok: asserting the table is EMPTY; a cap
        # cannot hide rows that were never inserted.
        rows = (
            leads_client.table("portal_receiver_tokens").select("*").execute().data
        )
        assert rows in ([], None)

    def test_missing_public_base_is_refused_not_guessed(
        self, http_client, monkeypatch, leads_client
    ):
        """With no configured origin we cannot build a reachable URL.

        Returning a relative path would look like success and never
        receive anything, so this is a 503 instead.
        """
        monkeypatch.setattr(settings, "tunnel_hostname", "")
        monkeypatch.setattr(settings, "oauth_redirect_base_url", "")

        resp = http_client.post(
            BASE,
            json={"provider": "olx", "label": "x"},
            headers={"Authorization": "Bearer any"},
        )

        assert resp.status_code == 503
        # postgrest-unbounded-ok: asserting the table is EMPTY; a cap
        # cannot hide rows that were never inserted.
        rows = (
            leads_client.table("portal_receiver_tokens").select("*").execute().data
        )
        assert rows in ([], None)


class TestListing:
    def test_lists_without_ever_returning_a_plaintext(
        self, http_client, public_base
    ):
        minted = http_client.post(
            BASE,
            json={"provider": "olx", "label": "One Consultoria"},
            headers={"Authorization": "Bearer any"},
        ).json()
        plaintext = minted["url"].rsplit("/", 1)[-1]

        resp = http_client.get(BASE, headers={"Authorization": "Bearer any"})

        assert resp.status_code == 200
        assert plaintext not in resp.text
        assert resp.json()[0]["token_prefix"] == minted["token_prefix"]


class TestRevoke:
    def test_revoked_token_stops_resolving(
        self, http_client, public_base, leads_client
    ):
        minted = http_client.post(
            BASE,
            json={"provider": "olx", "label": "old"},
            headers={"Authorization": "Bearer any"},
        ).json()
        token = minted["url"].rsplit("/", 1)[-1]

        resp = http_client.delete(
            f"{BASE}/{minted['id']}", headers={"Authorization": "Bearer any"}
        )

        assert resp.status_code == 200
        assert resolve_receiver_token(leads_client, provider="olx", token=token) is None

    def test_malformed_id_is_422(self, http_client, public_base):
        resp = http_client.delete(
            f"{BASE}/not-a-uuid", headers={"Authorization": "Bearer any"}
        )

        assert resp.status_code == 422

    def test_unknown_id_is_404(self, http_client, public_base):
        resp = http_client.delete(
            f"{BASE}/00000000-0000-4000-8000-0000000000ff",
            headers={"Authorization": "Bearer any"},
        )

        assert resp.status_code == 404
