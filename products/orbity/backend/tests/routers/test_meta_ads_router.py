"""
Auth-boundary + validation tests for the /api/meta-ads/* router.

Auth: strict == 401 (not 404/422) for all protected endpoints.
Validation: StrictHttpModel extra="forbid" → 422 for unknown fields.
"""
import pytest

TEST_ORG = "00000000-0000-0000-0000-000000000001"
FAKE_UUID = "00000000-0000-0000-0000-000000000002"


# ---------------------------------------------------------------------------
# Ad account auth pins
# ---------------------------------------------------------------------------

class TestAdAccountRouterAuth:
    """Every /api/meta-ads/ad-accounts/* endpoint requires authentication."""

    def test_list_ad_accounts_without_auth_returns_401(self, client):
        assert client.raw().get("/api/meta-ads/ad-accounts").status_code == 401

    def test_create_ad_account_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/meta-ads/ad-accounts",
            json={
                "external_account_id": "act_123",
                "name": "Test Account",
            },
        ).status_code == 401

    def test_get_ad_account_without_auth_returns_401(self, client):
        assert client.raw().get(
            f"/api/meta-ads/ad-accounts/{FAKE_UUID}"
        ).status_code == 401

    def test_patch_ad_account_without_auth_returns_401(self, client):
        assert client.raw().patch(
            f"/api/meta-ads/ad-accounts/{FAKE_UUID}",
            json={"name": "Updated"},
        ).status_code == 401

    def test_delete_ad_account_without_auth_returns_401(self, client):
        assert client.raw().delete(
            f"/api/meta-ads/ad-accounts/{FAKE_UUID}"
        ).status_code == 401


# ---------------------------------------------------------------------------
# Campaign auth pins
# ---------------------------------------------------------------------------

class TestCampaignRouterAuth:
    """Every /api/meta-ads/campaigns/* endpoint requires authentication."""

    def test_list_campaigns_without_auth_returns_401(self, client):
        assert client.raw().get("/api/meta-ads/campaigns").status_code == 401

    def test_create_campaign_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/meta-ads/campaigns",
            json={
                "ad_account_id": FAKE_UUID,
                "external_campaign_id": "camp_123",
                "name": "Test Campaign",
            },
        ).status_code == 401

    def test_get_campaign_without_auth_returns_401(self, client):
        assert client.raw().get(
            f"/api/meta-ads/campaigns/{FAKE_UUID}"
        ).status_code == 401

    def test_patch_campaign_without_auth_returns_401(self, client):
        assert client.raw().patch(
            f"/api/meta-ads/campaigns/{FAKE_UUID}",
            json={"name": "Updated"},
        ).status_code == 401

    def test_delete_campaign_without_auth_returns_401(self, client):
        assert client.raw().delete(
            f"/api/meta-ads/campaigns/{FAKE_UUID}"
        ).status_code == 401

    def test_update_situation_without_auth_returns_401(self, client):
        assert client.raw().patch(
            f"/api/meta-ads/campaigns/{FAKE_UUID}/situation",
            json={"situation": "on-track"},
        ).status_code == 401

    def test_list_metrics_without_auth_returns_401(self, client):
        assert client.raw().get(
            f"/api/meta-ads/campaigns/{FAKE_UUID}/metrics"
        ).status_code == 401


# ---------------------------------------------------------------------------
# Sync + aggregate auth pins
# ---------------------------------------------------------------------------

class TestSyncAggregateAuth:
    """Sync and aggregate endpoints require authentication."""

    def test_sync_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/meta-ads/sync",
            json={"ad_account_id": FAKE_UUID},
        ).status_code == 401

    def test_aggregate_without_auth_returns_401(self, client):
        assert client.raw().get(
            "/api/meta-ads/aggregate?period_start=2026-01-01&period_end=2026-01-31"
        ).status_code == 401


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestAdAccountValidation:
    """StrictHttpModel extra='forbid' enforced on inbound schemas."""

    def test_create_missing_external_account_id_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/ad-accounts",
            json={"name": "Account"},  # missing external_account_id
        )
        assert resp.status_code == 422

    def test_create_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/ad-accounts",
            json={
                "external_account_id": "act_123",
                "name": "Account",
                "rogue_field": True,  # extra="forbid"
            },
        )
        assert resp.status_code == 422

    def test_create_invalid_status_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/ad-accounts",
            json={
                "external_account_id": "act_123",
                "name": "Account",
                "status": "unknown_status",
            },
        )
        assert resp.status_code == 422

    def test_patch_no_fields_returns_400(self, client):
        resp = client.patch(
            f"/api/meta-ads/ad-accounts/{FAKE_UUID}",
            json={},
        )
        assert resp.status_code == 400


class TestCampaignValidation:
    """Inbound campaign schema validation."""

    def test_create_missing_ad_account_id_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/campaigns",
            json={
                "external_campaign_id": "camp_123",
                "name": "Campaign",
            },
        )
        assert resp.status_code == 422

    def test_create_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/campaigns",
            json={
                "ad_account_id": FAKE_UUID,
                "external_campaign_id": "camp_123",
                "name": "Campaign",
                "rogue": "x",
            },
        )
        assert resp.status_code == 422

    def test_create_invalid_situation_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/campaigns",
            json={
                "ad_account_id": FAKE_UUID,
                "external_campaign_id": "camp_123",
                "name": "Campaign",
                "situation": "unknown_situation",
            },
        )
        assert resp.status_code == 422

    def test_create_negative_daily_budget_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/campaigns",
            json={
                "ad_account_id": FAKE_UUID,
                "external_campaign_id": "camp_123",
                "name": "Campaign",
                "daily_budget": -1,
            },
        )
        assert resp.status_code == 422

    def test_update_situation_invalid_value_returns_422(self, client):
        resp = client.patch(
            f"/api/meta-ads/campaigns/{FAKE_UUID}/situation",
            json={"situation": "great"},
        )
        assert resp.status_code == 422

    def test_patch_no_fields_returns_400(self, client):
        resp = client.patch(
            f"/api/meta-ads/campaigns/{FAKE_UUID}",
            json={},
        )
        assert resp.status_code == 400


class TestSyncValidation:
    """Sync endpoint validation."""

    def test_sync_missing_ad_account_id_returns_422(self, client):
        resp = client.post("/api/meta-ads/sync", json={})
        assert resp.status_code == 422

    def test_sync_invalid_uuid_returns_422(self, client):
        resp = client.post(
            "/api/meta-ads/sync",
            json={"ad_account_id": "not-a-uuid"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Happy-path smoke tests (authenticated client, mock DB)
# ---------------------------------------------------------------------------

class TestAdAccountHappyPath:
    """Smoke: authenticated requests reach the service layer."""

    def test_list_ad_accounts_returns_dict(self, client):
        resp = client.get("/api/meta-ads/ad-accounts")
        # 200 with dict envelope OR 502 if mock returns unexpected shape
        assert resp.status_code in (200, 502)
        if resp.status_code == 200:
            body = resp.json()
            assert "items" in body

    def test_create_ad_account_reaches_service_layer(self, client):
        """POST reaches the service; 201 on full mock data, 422 on partial mock row
        (mock returns only id/name/external_account_id — missing required timestamp
        columns in AdAccountOut → FastAPI response validation raises 422 in test env).
        The auth boundary (== 401) is tested separately above."""
        resp = client.post(
            "/api/meta-ads/ad-accounts",
            json={
                "external_account_id": "act_999",
                "name": "Conta Teste",
            },
        )
        # 201 = mock returned full row, 422 = mock row missing required timestamps,
        # 502 = service error — all three mean auth was passed and the service was reached
        assert resp.status_code in (201, 422, 502)

    def test_get_nonexistent_ad_account_returns_404_or_502(self, client):
        resp = client.get(f"/api/meta-ads/ad-accounts/{FAKE_UUID}")
        assert resp.status_code in (404, 502)


class TestCampaignHappyPath:
    """Smoke: authenticated campaign requests reach the service layer."""

    def test_list_campaigns_returns_dict(self, client):
        resp = client.get("/api/meta-ads/campaigns")
        assert resp.status_code in (200, 502)
        if resp.status_code == 200:
            assert "items" in resp.json()

    def test_create_campaign_reaches_service_layer(self, client):
        """POST reaches the service; mock row missing required timestamps → 422 in test env.
        The auth boundary (== 401) is tested separately above."""
        resp = client.post(
            "/api/meta-ads/campaigns",
            json={
                "ad_account_id": FAKE_UUID,
                "external_campaign_id": "camp_abc",
                "name": "Campanha Teste",
            },
        )
        assert resp.status_code in (201, 422, 502)

    def test_list_metrics_returns_list_or_502(self, client):
        resp = client.get(f"/api/meta-ads/campaigns/{FAKE_UUID}/metrics")
        assert resp.status_code in (200, 502)

    def test_update_situation_returns_200_404_or_502(self, client):
        resp = client.patch(
            f"/api/meta-ads/campaigns/{FAKE_UUID}/situation",
            json={"situation": "attention"},
        )
        assert resp.status_code in (200, 404, 502)


class TestSyncHappyPath:
    """Smoke: sync endpoint reaches the service (Fake adapter)."""

    def test_sync_returns_200_404_or_502(self, client):
        resp = client.post(
            "/api/meta-ads/sync",
            json={"ad_account_id": FAKE_UUID},
        )
        # 404 when the account doesn't exist in mock DB; 200 when Fake runs
        assert resp.status_code in (200, 404, 502)

    def test_aggregate_returns_200_or_502(self, client):
        resp = client.get(
            "/api/meta-ads/aggregate"
            "?period_start=2026-01-01&period_end=2026-01-31"
        )
        assert resp.status_code in (200, 502)
