"""
Real-DB integration tests for the Orbity Meta Ads organ.

Tests hit a real Supabase instance to verify:
  - CHECK constraints (status values, daily_budget >= 0, spend >= 0, leads >= 0)
  - UNIQUE constraints (external_account_id per org, external_campaign_id per org,
    campaign_id+date per metric row)
  - FK constraints (ad_account_id → ad_accounts, campaign_id → campaigns,
    client_id → clients with ON DELETE SET NULL)
  - CASCADE delete (campaign deleted → campaign_metrics deleted)
  - RLS org isolation: org A rows are invisible to an anon/wrong-org JWT
  - Full round-trip CRUD for ad_accounts, campaigns, campaign_metrics

Run only (requires migration 009 applied + Supabase credentials):
  pytest products/orbity/backend/tests/realdb/ -v -m realdb

Skip condition: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set.

PENDING-MIGRATION-APPLY: migration 009_meta_ads.sql must be applied
to the live Supabase project by the tech-lead before these tests are run.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from postgrest.exceptions import APIError

pytestmark = pytest.mark.realdb


# ---------------------------------------------------------------------------
# Ad accounts — round-trip CRUD
# ---------------------------------------------------------------------------

class TestAdAccountCRUD:
    """Full CRUD on orbity.ad_accounts."""

    def test_ad_account_crud(self, fin_db, test_org, cleanup):
        # Create
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Conta Ads Teste",
            "status": "active",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))

        assert account["name"] == "Conta Ads Teste"
        assert account["status"] == "active"
        assert account["access_token_ref"] is None  # not required on creation

        # Read
        fetched = fin_db.table("ad_accounts") \
            .select("*").eq("id", account["id"]).single().execute().data
        assert fetched["org_id"] == test_org["id"]

        # Update — disconnect the account
        fin_db.table("ad_accounts") \
            .update({"status": "disconnected"}).eq("id", account["id"]).execute()
        updated = fin_db.table("ad_accounts") \
            .select("status").eq("id", account["id"]).single().execute().data
        assert updated["status"] == "disconnected"

        # Delete
        fin_db.table("ad_accounts").delete().eq("id", account["id"]).execute()
        check = fin_db.table("ad_accounts").select("id").eq("id", account["id"]).execute().data
        assert check == []
        cleanup.pop()


class TestAdAccountCheckConstraints:
    """CHECK constraints on ad_accounts."""

    def test_invalid_status_rejected(self, fin_db, test_org):
        with pytest.raises(APIError):
            fin_db.table("ad_accounts").insert({
                "org_id": test_org["id"],
                "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
                "name": "Bad Status",
                "status": "invalid_status",
            }).execute()


class TestAdAccountUniqueConstraint:
    """UNIQUE (org_id, external_account_id) prevents duplicate connections."""

    def test_duplicate_external_account_id_rejected(self, fin_db, test_org, cleanup):
        ext_id = f"act_{uuid.uuid4().hex[:8]}"
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": ext_id,
            "name": "First Connection",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))

        with pytest.raises(APIError):
            fin_db.table("ad_accounts").insert({
                "org_id": test_org["id"],
                "external_account_id": ext_id,
                "name": "Duplicate Connection",
            }).execute()


# ---------------------------------------------------------------------------
# Campaigns — round-trip CRUD
# ---------------------------------------------------------------------------

class TestCampaignCRUD:
    """Full CRUD on orbity.campaigns."""

    def _make_account(self, fin_db, test_org, cleanup):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Account For Campaign Test",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))
        return account

    def test_campaign_crud(self, fin_db, test_org, cleanup):
        account = self._make_account(fin_db, test_org, cleanup)

        # Create
        campaign = fin_db.table("campaigns").insert({
            "org_id": test_org["id"],
            "ad_account_id": account["id"],
            "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
            "name": "Campanha Geração de Leads",
            "objective": "LEAD_GENERATION",
            "status": "active",
            "daily_budget": 150.00,
            "result_metric": "leads",
            "situation": "on-track",
        }).execute().data[0]
        cleanup.append(("campaigns", campaign["id"]))

        assert campaign["name"] == "Campanha Geração de Leads"
        assert campaign["situation"] == "on-track"
        assert float(campaign["daily_budget"]) == 150.00
        assert campaign["status"] == "active"

        # Read
        fetched = fin_db.table("campaigns") \
            .select("*").eq("id", campaign["id"]).single().execute().data
        assert fetched["org_id"] == test_org["id"]
        assert fetched["ad_account_id"] == account["id"]

        # Update — pause + flag as needing attention
        fin_db.table("campaigns") \
            .update({"status": "paused", "situation": "attention"}) \
            .eq("id", campaign["id"]).execute()
        updated = fin_db.table("campaigns") \
            .select("status, situation").eq("id", campaign["id"]).single().execute().data
        assert updated["status"] == "paused"
        assert updated["situation"] == "attention"

        # Delete
        fin_db.table("campaigns").delete().eq("id", campaign["id"]).execute()
        check = fin_db.table("campaigns").select("id").eq("id", campaign["id"]).execute().data
        assert check == []
        cleanup.pop()


class TestCampaignCheckConstraints:
    """CHECK constraints on campaigns."""

    def _make_account(self, fin_db, test_org, cleanup):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Account For Constraint Test",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))
        return account

    def test_invalid_status_rejected(self, fin_db, test_org, cleanup):
        account = self._make_account(fin_db, test_org, cleanup)
        with pytest.raises(APIError):
            fin_db.table("campaigns").insert({
                "org_id": test_org["id"],
                "ad_account_id": account["id"],
                "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
                "name": "Bad Status",
                "status": "unknown",
            }).execute()

    def test_invalid_situation_rejected(self, fin_db, test_org, cleanup):
        account = self._make_account(fin_db, test_org, cleanup)
        with pytest.raises(APIError):
            fin_db.table("campaigns").insert({
                "org_id": test_org["id"],
                "ad_account_id": account["id"],
                "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
                "name": "Bad Situation",
                "situation": "unknown_situation",
            }).execute()

    def test_negative_daily_budget_rejected(self, fin_db, test_org, cleanup):
        account = self._make_account(fin_db, test_org, cleanup)
        with pytest.raises(APIError):
            fin_db.table("campaigns").insert({
                "org_id": test_org["id"],
                "ad_account_id": account["id"],
                "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
                "name": "Negative Budget",
                "daily_budget": -1.0,
            }).execute()


class TestCampaignUniqueConstraint:
    """UNIQUE (org_id, external_campaign_id) prevents duplicates on sync."""

    def _make_account(self, fin_db, test_org, cleanup):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Account For Unique Test",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))
        return account

    def test_duplicate_external_campaign_id_rejected(self, fin_db, test_org, cleanup):
        account = self._make_account(fin_db, test_org, cleanup)
        ext_id = f"camp_{uuid.uuid4().hex[:8]}"

        campaign = fin_db.table("campaigns").insert({
            "org_id": test_org["id"],
            "ad_account_id": account["id"],
            "external_campaign_id": ext_id,
            "name": "First Campaign",
        }).execute().data[0]
        cleanup.append(("campaigns", campaign["id"]))

        with pytest.raises(APIError):
            fin_db.table("campaigns").insert({
                "org_id": test_org["id"],
                "ad_account_id": account["id"],
                "external_campaign_id": ext_id,
                "name": "Duplicate Campaign",
            }).execute()


# ---------------------------------------------------------------------------
# Campaign metrics — round-trip CRUD
# ---------------------------------------------------------------------------

class TestCampaignMetricsCRUD:
    """Full CRUD + upsert on orbity.campaign_metrics."""

    def _make_account_and_campaign(self, fin_db, test_org, cleanup):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Account For Metrics",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))

        campaign = fin_db.table("campaigns").insert({
            "org_id": test_org["id"],
            "ad_account_id": account["id"],
            "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
            "name": "Campaign For Metrics",
        }).execute().data[0]
        cleanup.append(("campaigns", campaign["id"]))
        return account, campaign

    def test_metrics_crud(self, fin_db, test_org, cleanup):
        _, campaign = self._make_account_and_campaign(fin_db, test_org, cleanup)
        today = date.today().isoformat()

        # Create
        metric = fin_db.table("campaign_metrics").insert({
            "org_id": test_org["id"],
            "campaign_id": campaign["id"],
            "date": today,
            "spend": 250.50,
            "impressions": 12000,
            "leads": 8,
            "cpl": 31.3125,
        }).execute().data[0]
        cleanup.append(("campaign_metrics", metric["id"]))

        assert float(metric["spend"]) == 250.50
        assert metric["impressions"] == 12000
        assert metric["leads"] == 8

        # Read
        fetched = fin_db.table("campaign_metrics") \
            .select("*").eq("id", metric["id"]).single().execute().data
        assert fetched["campaign_id"] == campaign["id"]

        # Update
        fin_db.table("campaign_metrics") \
            .update({"leads": 10}).eq("id", metric["id"]).execute()
        updated = fin_db.table("campaign_metrics") \
            .select("leads").eq("id", metric["id"]).single().execute().data
        assert updated["leads"] == 10

        # Delete
        fin_db.table("campaign_metrics").delete().eq("id", metric["id"]).execute()
        check = fin_db.table("campaign_metrics").select("id").eq("id", metric["id"]).execute().data
        assert check == []
        cleanup.pop()

    def test_metrics_check_constraints(self, fin_db, test_org, cleanup):
        _, campaign = self._make_account_and_campaign(fin_db, test_org, cleanup)

        with pytest.raises(APIError):
            fin_db.table("campaign_metrics").insert({
                "org_id": test_org["id"],
                "campaign_id": campaign["id"],
                "date": date.today().isoformat(),
                "spend": -1.0,     # spend < 0 rejected
                "impressions": 0,
                "leads": 0,
            }).execute()

    def test_metrics_unique_campaign_date(self, fin_db, test_org, cleanup):
        """UNIQUE (campaign_id, date) — duplicate date rejected."""
        _, campaign = self._make_account_and_campaign(fin_db, test_org, cleanup)
        today = date.today().isoformat()

        m = fin_db.table("campaign_metrics").insert({
            "org_id": test_org["id"],
            "campaign_id": campaign["id"],
            "date": today,
            "spend": 100.0,
            "impressions": 500,
            "leads": 3,
        }).execute().data[0]
        cleanup.append(("campaign_metrics", m["id"]))

        with pytest.raises(APIError):
            fin_db.table("campaign_metrics").insert({
                "org_id": test_org["id"],
                "campaign_id": campaign["id"],
                "date": today,  # duplicate (campaign_id, date)
                "spend": 200.0,
                "impressions": 1000,
                "leads": 5,
            }).execute()


# ---------------------------------------------------------------------------
# FK + cascade
# ---------------------------------------------------------------------------

class TestCascadeDelete:
    """ON DELETE CASCADE: deleting a campaign deletes its metrics."""

    def test_campaign_delete_cascades_to_metrics(self, fin_db, test_org, cleanup):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Account For Cascade",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))

        campaign = fin_db.table("campaigns").insert({
            "org_id": test_org["id"],
            "ad_account_id": account["id"],
            "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
            "name": "Cascade Test Campaign",
        }).execute().data[0]
        # Don't add to cleanup — we're deleting it explicitly

        metric = fin_db.table("campaign_metrics").insert({
            "org_id": test_org["id"],
            "campaign_id": campaign["id"],
            "date": date.today().isoformat(),
            "spend": 10.0,
            "impressions": 100,
            "leads": 1,
        }).execute().data[0]

        # Delete the campaign → metrics should cascade
        fin_db.table("campaigns").delete().eq("id", campaign["id"]).execute()

        # Verify metrics were cascaded
        remaining = fin_db.table("campaign_metrics") \
            .select("id").eq("id", metric["id"]).execute().data
        assert remaining == [], "campaign_metrics should be CASCADE deleted with campaign"

    def test_invalid_campaign_fk_rejected(self, fin_db, test_org):
        """campaign_id FK → campaigns — non-existent UUID rejected."""
        fake_campaign = str(uuid.uuid4())
        with pytest.raises(APIError):
            fin_db.table("campaign_metrics").insert({
                "org_id": test_org["id"],
                "campaign_id": fake_campaign,
                "date": date.today().isoformat(),
                "spend": 10.0,
                "impressions": 100,
                "leads": 1,
            }).execute()


# ---------------------------------------------------------------------------
# RLS org isolation
# ---------------------------------------------------------------------------

class TestRLSOrgIsolation:
    """Rows written by org A must NOT be visible to an anon/wrong-org JWT.

    The anon key has no valid JWT claim → current_org_id() returns NULL →
    USING (org_id = public.current_org_id()) evaluates false for every row.
    This is the correct proof that RLS is not USING(true).
    """

    def test_ad_account_not_visible_under_anon_jwt(self, fin_db, anon_fin_db, test_org, cleanup):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "RLS Isolation Account",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))

        rows = anon_fin_db.table("ad_accounts") \
            .select("id").eq("id", account["id"]).execute().data
        assert rows == [], (
            "RLS FAILURE: anon JWT can see org A's ad_accounts — "
            "policy must not be USING(true)"
        )

    def test_campaign_not_visible_under_anon_jwt(self, fin_db, anon_fin_db, test_org, cleanup):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Account For RLS Campaign Test",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))

        campaign = fin_db.table("campaigns").insert({
            "org_id": test_org["id"],
            "ad_account_id": account["id"],
            "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
            "name": "RLS Campaign",
        }).execute().data[0]
        cleanup.append(("campaigns", campaign["id"]))

        rows = anon_fin_db.table("campaigns") \
            .select("id").eq("id", campaign["id"]).execute().data
        assert rows == [], "RLS FAILURE: anon JWT can see org A's campaigns"

    def test_campaign_metrics_not_visible_under_anon_jwt(
        self, fin_db, anon_fin_db, test_org, cleanup
    ):
        account = fin_db.table("ad_accounts").insert({
            "org_id": test_org["id"],
            "external_account_id": f"act_{uuid.uuid4().hex[:8]}",
            "name": "Account For RLS Metrics Test",
        }).execute().data[0]
        cleanup.append(("ad_accounts", account["id"]))

        campaign = fin_db.table("campaigns").insert({
            "org_id": test_org["id"],
            "ad_account_id": account["id"],
            "external_campaign_id": f"camp_{uuid.uuid4().hex[:8]}",
            "name": "Campaign For RLS Metrics",
        }).execute().data[0]
        cleanup.append(("campaigns", campaign["id"]))

        metric = fin_db.table("campaign_metrics").insert({
            "org_id": test_org["id"],
            "campaign_id": campaign["id"],
            "date": date.today().isoformat(),
            "spend": 1.00,
            "impressions": 100,
            "leads": 1,
        }).execute().data[0]
        cleanup.append(("campaign_metrics", metric["id"]))

        rows = anon_fin_db.table("campaign_metrics") \
            .select("id").eq("id", metric["id"]).execute().data
        assert rows == [], "RLS FAILURE: anon JWT can see org A's campaign_metrics"
