"""`receiver_token_service` — mint, resolve, rotate, revoke.

The security-relevant assertions here are the two that keep this table
from becoming an accidental bearer-credential store:

* a `pk_*` api_token must never resolve as a receiver token;
* the plaintext must never be readable back out of the row.

Both are cheap to keep and expensive to notice the absence of — a
receiver token lives in a vendor-visible URL, so the day the two token
kinds become interchangeable is the day pasting a URL into Canal Pro
grants Grupo OLX full API access to that org.
"""
from __future__ import annotations

import pytest

from noctusai_lib.api.auth.session import hash_token

from app.modules.portal_leads.services.receiver_token_service import (
    RECEIVER_TOKEN_PREFIX,
    UnknownReceiverProvider,
    generate_receiver_token,
    list_receiver_tokens,
    mint_receiver_token,
    resolve_receiver_token,
    revoke_receiver_token,
)

from tests.modules.portal_leads.conftest import ORG_A, ORG_B

# The conftest org ids are strings; the resolver returns a UUID by design
# (callers pass it straight to `OlxWebhookService`, which types it as one).
ORG_A_UUID = __import__("uuid").UUID(ORG_A)
ORG_B_UUID = __import__("uuid").UUID(ORG_B)


@pytest.fixture
def client(mock_db):
    """The schema-scoped shape `get_leads_client()` hands the router."""
    return mock_db.schema("social_wiring")


def _mint(client, org_id=ORG_A, provider="olx", label="Canal Pro"):
    return mint_receiver_token(
        client, org_id=org_id, provider=provider, label=label
    )


class TestGeneration:
    def test_token_carries_the_receiver_prefix(self):
        assert generate_receiver_token().startswith(RECEIVER_TOKEN_PREFIX)

    def test_tokens_are_unique(self):
        assert generate_receiver_token() != generate_receiver_token()

    def test_token_is_url_path_safe(self):
        # It is pasted into a vendor form as a path segment; a `/` or a
        # `+` there would silently truncate or re-route the URL.
        token = generate_receiver_token()
        assert "/" not in token
        assert "+" not in token
        assert "=" not in token


class TestMint:
    def test_returns_a_usable_plaintext(self, client):
        minted = _mint(client)

        assert minted.plaintext.startswith(RECEIVER_TOKEN_PREFIX)
        assert minted.org_id == ORG_A
        assert minted.provider == "olx"

    def test_stores_the_digest_never_the_plaintext(self, client):
        minted = _mint(client)

        # postgrest-unbounded-ok: one row, minted by this test.
        rows = client.table("portal_receiver_tokens").select("*").execute().data
        stored = rows[0]

        assert stored["token_hash"] == hash_token(minted.plaintext)
        # The plaintext must not be recoverable from any column.
        assert minted.plaintext not in str(stored)

    def test_prefix_column_is_short_enough_to_be_useless(self, client):
        minted = _mint(client)

        assert len(minted.token_prefix) == 8
        assert minted.plaintext.startswith(minted.token_prefix)

    def test_unknown_provider_is_refused_before_the_database(self, client):
        with pytest.raises(UnknownReceiverProvider):
            _mint(client, provider="zap")


class TestResolve:
    def test_resolves_to_the_minting_org(self, client):
        minted = _mint(client, org_id=ORG_B)

        assert (
            resolve_receiver_token(client, provider="olx", token=minted.plaintext)
            == ORG_B_UUID
        )

    def test_a_bearer_api_token_never_resolves(self, client):
        """The property that keeps the two token kinds separate.

        `pk_*` is the `api_tokens` prefix. If one ever resolved here, a
        URL pasted into Canal Pro would be a live API credential.
        """
        _mint(client)

        assert (
            resolve_receiver_token(
                client, provider="olx", token="pk_" + "a" * 43
            )
            is None
        )

    def test_unknown_token_resolves_to_none(self, client):
        _mint(client)

        assert (
            resolve_receiver_token(
                client, provider="olx", token=generate_receiver_token()
            )
            is None
        )

    def test_token_does_not_cross_providers(self, client):
        """An OLX token must not route an ImovelWeb delivery.

        Same table, two portals — without the provider filter, one
        advertiser's OLX token would silently accept their ImovelWeb
        traffic too, and the split would be invisible in the data.
        """
        minted = _mint(client, provider="olx")

        assert (
            resolve_receiver_token(
                client, provider="imovelweb", token=minted.plaintext
            )
            is None
        )

    def test_empty_token_resolves_to_none(self, client):
        assert resolve_receiver_token(client, provider="olx", token="") is None


class TestRotationAndRevocation:
    def test_two_active_tokens_both_resolve(self, client):
        """Rotation overlap is the point, not an accident.

        Switching the URL in Canal Pro is a human action, so old and new
        must both work during the window. Revoking first would drop every
        lead delivered in the gap, and Grupo OLX never replays those.
        """
        first = _mint(client, label="old")
        second = _mint(client, label="new")

        assert (
            resolve_receiver_token(client, provider="olx", token=first.plaintext)
            == ORG_A_UUID
        )
        assert (
            resolve_receiver_token(client, provider="olx", token=second.plaintext)
            == ORG_A_UUID
        )

    def test_revoked_token_stops_resolving(self, client):
        minted = _mint(client)

        assert revoke_receiver_token(client, org_id=ORG_A, token_id=minted.id) is True
        assert (
            resolve_receiver_token(client, provider="olx", token=minted.plaintext)
            is None
        )

    def test_cannot_revoke_another_orgs_token(self, client):
        """The `org_id` filter is the only guard on the admin client.

        `revoke_receiver_token` runs service-role, so RLS is not standing
        between ORG_B and ORG_A's token — this filter is.
        """
        minted = _mint(client, org_id=ORG_A)

        assert revoke_receiver_token(client, org_id=ORG_B, token_id=minted.id) is False
        assert (
            resolve_receiver_token(client, provider="olx", token=minted.plaintext)
            == ORG_A_UUID
        )


class TestListing:
    def test_listing_never_exposes_a_token(self, client):
        minted = _mint(client)

        rows = list_receiver_tokens(client, org_id=ORG_A)

        assert len(rows) == 1
        # The property that matters: the plaintext is unreachable. It was
        # never stored, so no projection choice can leak it.
        assert minted.plaintext not in str(rows)
        # NOT asserted: that `token_hash` is absent from the row.
        # `list_receiver_tokens` does not select it, but `MockSupabaseClient`
        # does not model PostgREST column projection — it returns the whole
        # row regardless — so an assertion here would be testing the double,
        # not the query. The digest is not a secret in any case: it is a
        # SHA-256 of a ≥256-bit token and buys an attacker nothing.

    def test_listing_is_scoped_to_the_org(self, client):
        _mint(client, org_id=ORG_A)
        _mint(client, org_id=ORG_B)

        assert len(list_receiver_tokens(client, org_id=ORG_A)) == 1

    def test_listing_can_filter_by_provider(self, client):
        _mint(client, provider="olx")
        _mint(client, provider="imovelweb")

        rows = list_receiver_tokens(client, org_id=ORG_A, provider="olx")

        assert [r["provider"] for r in rows] == ["olx"]
