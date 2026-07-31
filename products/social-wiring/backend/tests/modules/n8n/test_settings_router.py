"""Tests for GET/PUT /api/n8n/settings.

Covers: the GET status-DERIVATION rule (base_url absence overrides the
stored status column), auth boundary, 403/404 account resolution, and
the PUT credential-merge + tag-resolution + reachability-ping flow.
"""
from __future__ import annotations

from tests.modules.n8n.conftest import make_n8n_account


class TestAuthBoundary:
    def test_get_settings_requires_auth(self, n8n_env):
        resp = n8n_env.client.raw().get(
            "/api/n8n/settings", params={"account_id": "00000000-0000-0000-0000-000000000001"}
        )
        assert resp.status_code == 401, resp.text

    def test_put_settings_requires_auth(self, n8n_env):
        resp = n8n_env.client.raw().put(
            "/api/n8n/settings",
            json={"account_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 401, resp.text


class TestAccountResolution:
    def test_get_settings_unknown_account_is_404(self, n8n_env):
        resp = n8n_env.client.get(
            "/api/n8n/settings", params={"account_id": "00000000-0000-0000-0000-000000009999"}
        )
        assert resp.status_code == 404, resp.text

    def test_get_settings_other_org_account_is_403(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, org_id=n8n_env.OTHER_ORG)
        resp = n8n_env.client.get(
            "/api/n8n/settings", params={"account_id": str(account.id)}
        )
        assert resp.status_code == 403, resp.text


class TestGetSettingsDerivation:
    def test_complete_credential_reports_stored_status(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)  # base_url + api_key both present
        resp = n8n_env.client.get(
            "/api/n8n/settings", params={"account_id": str(account.id)}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["base_url"] == "https://n8n.example.com"
        assert body["has_api_key"] is True
        assert body["status"] == "validated"
        assert body["reachable"] is None  # GET never pings

    def test_missing_base_url_forces_error_status_even_if_stored_status_says_validated(
        self, n8n_env
    ):
        """The load-bearing derivation rule: a pre-reshape row with a
        stored status='validated' but no base_url in the decrypted
        credential must still report status='error'."""
        account = make_n8n_account(n8n_env.svc, base_url=None, api_key="some-key")
        # Confirm the STORED column really does say 'validated' (the
        # lying state this rule exists to override).
        assert account.status == "validated"
        resp = n8n_env.client.get(
            "/api/n8n/settings", params={"account_id": str(account.id)}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "error"
        assert body["base_url"] is None

    def test_configured_tag_is_surfaced(self, n8n_env):
        account = make_n8n_account(
            n8n_env.svc, tag={"id": "fake-tag-1", "name": "prod"}
        )
        resp = n8n_env.client.get(
            "/api/n8n/settings", params={"account_id": str(account.id)}
        )
        body = resp.json()
        assert body["tag"] == {"id": "fake-tag-1", "name": "prod"}


class TestPutSettings:
    def test_saves_base_url_and_api_key_and_reports_reachable(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, base_url=None, api_key=None)
        resp = n8n_env.client.put(
            "/api/n8n/settings",
            json={
                "account_id": str(account.id),
                "base_url": "https://n8n.new.com",
                "api_key": "fresh-key",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["base_url"] == "https://n8n.new.com"
        assert body["has_api_key"] is True
        assert body["status"] == "validated"
        assert body["reachable"] is True

        # Persisted — a subsequent GET reflects the saved credential.
        get_resp = n8n_env.client.get(
            "/api/n8n/settings", params={"account_id": str(account.id)}
        )
        assert get_resp.json()["base_url"] == "https://n8n.new.com"

    def test_partial_update_leaves_other_field_untouched(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, base_url="https://n8n.old.com", api_key="k1")
        resp = n8n_env.client.put(
            "/api/n8n/settings",
            json={"account_id": str(account.id), "api_key": "k2"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["base_url"] == "https://n8n.old.com"

    def test_tag_id_resolves_name_via_live_lookup(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.put(
            "/api/n8n/settings",
            json={"account_id": str(account.id), "tag_id": "fake-tag-1"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tag"] == {"id": "fake-tag-1", "name": "prod"}

    def test_unknown_tag_id_is_404(self, n8n_env):
        account = make_n8n_account(n8n_env.svc)
        resp = n8n_env.client.put(
            "/api/n8n/settings",
            json={"account_id": str(account.id), "tag_id": "ghost-tag"},
        )
        assert resp.status_code == 404, resp.text

    def test_tag_id_without_complete_credential_is_424(self, n8n_env):
        account = make_n8n_account(n8n_env.svc, base_url=None, api_key=None)
        resp = n8n_env.client.put(
            "/api/n8n/settings",
            json={"account_id": str(account.id), "tag_id": "fake-tag-1"},
        )
        assert resp.status_code == 424, resp.text
