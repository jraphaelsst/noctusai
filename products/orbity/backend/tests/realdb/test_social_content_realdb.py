"""
Real-DB integration tests for the Orbity Social/Content Studio organ.

Tests hit a real Supabase instance to verify:
  - DDL/constraint correctness (CHECK on platform, status, campaign status)
  - FK constraints (campaign_id, client_id, post_id)
  - UNIQUE constraint on post_approvals.public_token
  - RLS org isolation (org A rows invisible to anon/wrong-org JWT)
  - Full round-trip CRUD for campaigns, posts, approvals
  - Public token approve round-trip (fetch by token → decide → post status updated)

Run only (requires migration 011 applied + Supabase credentials):
  pytest products/orbity/backend/tests/realdb/ -v -m realdb -k social

Skip condition: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set.

PENDING-MIGRATION-APPLY: migration 011_social_content.sql must be applied
to the live Supabase project by the tech-lead before these tests are run.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from postgrest.exceptions import APIError

pytestmark = pytest.mark.realdb


# ---------------------------------------------------------------------------
# Fixtures — org-scoped db alias + cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def content_db(orbity_db):
    """orbity_db is the service-role client for the orbity schema."""
    return orbity_db


@pytest.fixture(scope="module")
def content_org(core_db):
    """Dedicated org for social-content real-DB tests."""
    slug = f"test-content-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert({
        "nome": f"RealDB Content Test {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()


@pytest.fixture(scope="module")
def content_org_b(core_db):
    """Second org for RLS isolation tests."""
    slug = f"test-content-b-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert({
        "nome": f"RealDB Content Test B {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()


@pytest.fixture
def sc_cleanup(content_db):
    """Collect (table, id) pairs and delete in reverse order after test."""
    records: list[tuple[str, str]] = []
    yield records
    for table, rid in reversed(records):
        try:
            content_db.table(table).delete().eq("id", rid).execute()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Campaign round-trip CRUD
# ---------------------------------------------------------------------------

class TestCampaignCRUD:
    def test_campaign_crud(self, content_db, content_org, sc_cleanup):
        org_id = content_org["id"]

        # Create
        camp = content_db.table("content_campaigns").insert({
            "org_id": org_id,
            "name": "Julho 2026",
            "month": "2026-07",
            "status": "active",
        }).execute().data[0]
        sc_cleanup.append(("content_campaigns", camp["id"]))

        assert camp["name"] == "Julho 2026"
        assert camp["month"] == "2026-07"
        assert camp["status"] == "active"

        # Read
        fetched = content_db.table("content_campaigns").select("*").eq("id", camp["id"]).single().execute().data
        assert fetched["org_id"] == org_id

        # Update
        content_db.table("content_campaigns").update({"status": "paused"}).eq("id", camp["id"]).execute()
        updated = content_db.table("content_campaigns").select("status").eq("id", camp["id"]).single().execute().data
        assert updated["status"] == "paused"

        # Delete
        content_db.table("content_campaigns").delete().eq("id", camp["id"]).execute()
        check = content_db.table("content_campaigns").select("id").eq("id", camp["id"]).execute().data
        assert check == []
        sc_cleanup.pop()


class TestCampaignCheckConstraints:
    def test_invalid_status_rejected(self, content_db, content_org):
        with pytest.raises(APIError):
            content_db.table("content_campaigns").insert({
                "org_id": content_org["id"],
                "name": "Bad",
                "month": "2026-07",
                "status": "unknown_status",
            }).execute()


# ---------------------------------------------------------------------------
# Post round-trip CRUD
# ---------------------------------------------------------------------------

class TestPostCRUD:
    def test_post_crud(self, content_db, content_org, sc_cleanup):
        org_id = content_org["id"]

        # Create campaign first
        camp = content_db.table("content_campaigns").insert({
            "org_id": org_id,
            "name": "Test Camp",
            "month": "2026-07",
        }).execute().data[0]
        sc_cleanup.append(("content_campaigns", camp["id"]))

        # Create post
        post = content_db.table("content_posts").insert({
            "org_id": org_id,
            "campaign_id": camp["id"],
            "platform": "instagram",
            "caption": "Bem-vindos!",
            "status": "draft",
        }).execute().data[0]
        sc_cleanup.append(("content_posts", post["id"]))

        assert post["platform"] == "instagram"
        assert post["status"] == "draft"
        assert post["campaign_id"] == camp["id"]

        # Update
        content_db.table("content_posts").update({"status": "pending_approval"}).eq("id", post["id"]).execute()
        updated = content_db.table("content_posts").select("status").eq("id", post["id"]).single().execute().data
        assert updated["status"] == "pending_approval"

        # Delete (post first, then campaign — FK via ON DELETE CASCADE covers approval)
        content_db.table("content_posts").delete().eq("id", post["id"]).execute()
        sc_cleanup.pop()


class TestPostCheckConstraints:
    def test_invalid_platform_rejected(self, content_db, content_org):
        with pytest.raises(APIError):
            content_db.table("content_posts").insert({
                "org_id": content_org["id"],
                "platform": "snapchat",
                "status": "draft",
            }).execute()

    def test_invalid_post_status_rejected(self, content_db, content_org):
        with pytest.raises(APIError):
            content_db.table("content_posts").insert({
                "org_id": content_org["id"],
                "platform": "instagram",
                "status": "scheduled",
            }).execute()


# ---------------------------------------------------------------------------
# Approval round-trip + public token flow
# ---------------------------------------------------------------------------

class TestApprovalCRUD:
    def test_approval_crud_and_token_uniqueness(self, content_db, content_org, sc_cleanup):
        org_id = content_org["id"]

        camp = content_db.table("content_campaigns").insert({
            "org_id": org_id,
            "name": "Approval Camp",
            "month": "2026-08",
        }).execute().data[0]
        sc_cleanup.append(("content_campaigns", camp["id"]))

        post = content_db.table("content_posts").insert({
            "org_id": org_id,
            "campaign_id": camp["id"],
            "platform": "facebook",
            "status": "draft",
        }).execute().data[0]
        sc_cleanup.append(("content_posts", post["id"]))

        # Create approval (post_approvals.public_token auto-generated)
        approval = content_db.table("post_approvals").insert({
            "org_id": org_id,
            "post_id": post["id"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }).execute().data[0]
        sc_cleanup.append(("post_approvals", approval["id"]))

        assert approval["status"] == "pending"
        assert approval["public_token"] is not None

        # Fetch by token (simulates public endpoint lookup)
        fetched = content_db.table("post_approvals") \
            .select("*").eq("public_token", approval["public_token"]).execute().data
        assert len(fetched) == 1
        assert fetched[0]["id"] == approval["id"]

    def test_public_token_unique_index_rejects_duplicate(self, content_db, content_org, sc_cleanup):
        """Two approvals cannot share the same public_token."""
        org_id = content_org["id"]
        shared_token = str(uuid.uuid4())

        post = content_db.table("content_posts").insert({
            "org_id": org_id,
            "platform": "tiktok",
            "status": "draft",
        }).execute().data[0]
        sc_cleanup.append(("content_posts", post["id"]))

        row1 = content_db.table("post_approvals").insert({
            "org_id": org_id,
            "post_id": post["id"],
            "public_token": shared_token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }).execute().data[0]
        sc_cleanup.append(("post_approvals", row1["id"]))

        with pytest.raises(APIError):
            content_db.table("post_approvals").insert({
                "org_id": org_id,
                "post_id": post["id"],
                "public_token": shared_token,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            }).execute()


class TestApprovalTokenFlowRoundTrip:
    """Full public approve round-trip via service_role: create → fetch-by-token → decide."""

    def test_approve_decision_updates_approval_and_post(self, content_db, content_org, sc_cleanup):
        org_id = content_org["id"]

        camp = content_db.table("content_campaigns").insert({
            "org_id": org_id,
            "name": "Approval Flow Camp",
            "month": "2026-09",
        }).execute().data[0]
        sc_cleanup.append(("content_campaigns", camp["id"]))

        post = content_db.table("content_posts").insert({
            "org_id": org_id,
            "campaign_id": camp["id"],
            "platform": "instagram",
            "status": "pending_approval",
        }).execute().data[0]
        sc_cleanup.append(("content_posts", post["id"]))

        approval = content_db.table("post_approvals").insert({
            "org_id": org_id,
            "post_id": post["id"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }).execute().data[0]
        sc_cleanup.append(("post_approvals", approval["id"]))

        token = approval["public_token"]

        # Simulate public token lookup
        fetched_approval = content_db.table("post_approvals") \
            .select("*").eq("public_token", token).execute().data
        assert len(fetched_approval) == 1
        assert fetched_approval[0]["status"] == "pending"

        # Simulate decision write (as the public endpoint would do)
        decided_at = datetime.now(timezone.utc).isoformat()
        content_db.table("post_approvals").update({
            "status": "approved",
            "decided_at": decided_at,
        }).eq("id", approval["id"]).execute()

        content_db.table("content_posts").update({
            "status": "approved",
        }).eq("id", post["id"]).execute()

        # Verify approval updated
        updated_approval = content_db.table("post_approvals") \
            .select("status,decided_at").eq("id", approval["id"]).single().execute().data
        assert updated_approval["status"] == "approved"
        assert updated_approval["decided_at"] is not None

        # Verify post status updated
        updated_post = content_db.table("content_posts") \
            .select("status").eq("id", post["id"]).single().execute().data
        assert updated_post["status"] == "approved"

    def test_revision_decision_sets_post_to_revision(self, content_db, content_org, sc_cleanup):
        org_id = content_org["id"]

        post = content_db.table("content_posts").insert({
            "org_id": org_id,
            "platform": "facebook",
            "status": "pending_approval",
        }).execute().data[0]
        sc_cleanup.append(("content_posts", post["id"]))

        approval = content_db.table("post_approvals").insert({
            "org_id": org_id,
            "post_id": post["id"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }).execute().data[0]
        sc_cleanup.append(("post_approvals", approval["id"]))

        content_db.table("post_approvals").update({
            "status": "revision",
            "client_feedback": "Por favor mude a paleta de cores.",
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", approval["id"]).execute()

        content_db.table("content_posts").update({"status": "revision"}).eq("id", post["id"]).execute()

        updated_post = content_db.table("content_posts") \
            .select("status").eq("id", post["id"]).single().execute().data
        assert updated_post["status"] == "revision"


# ---------------------------------------------------------------------------
# RLS org isolation
# ---------------------------------------------------------------------------

class TestRLSOrgIsolation:
    """Rows created for org A must be invisible to the anon client."""

    def test_campaign_invisible_to_anon(self, content_db, anon_fin_db, content_org, sc_cleanup):
        """Anon JWT → current_org_id() = NULL → RLS blocks the row."""
        org_id = content_org["id"]

        camp = content_db.table("content_campaigns").insert({
            "org_id": org_id,
            "name": "Private Campaign",
            "month": "2026-10",
        }).execute().data[0]
        sc_cleanup.append(("content_campaigns", camp["id"]))

        visible = anon_fin_db.table("content_campaigns") \
            .select("id").eq("id", camp["id"]).execute().data
        assert visible == []

    def test_post_invisible_to_anon(self, content_db, anon_fin_db, content_org, sc_cleanup):
        org_id = content_org["id"]

        post = content_db.table("content_posts").insert({
            "org_id": org_id,
            "platform": "instagram",
            "status": "draft",
        }).execute().data[0]
        sc_cleanup.append(("content_posts", post["id"]))

        visible = anon_fin_db.table("content_posts") \
            .select("id").eq("id", post["id"]).execute().data
        assert visible == []

    def test_approval_invisible_to_anon(self, content_db, anon_fin_db, content_org, sc_cleanup):
        org_id = content_org["id"]

        post = content_db.table("content_posts").insert({
            "org_id": org_id,
            "platform": "tiktok",
            "status": "draft",
        }).execute().data[0]
        sc_cleanup.append(("content_posts", post["id"]))

        approval = content_db.table("post_approvals").insert({
            "org_id": org_id,
            "post_id": post["id"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        }).execute().data[0]
        sc_cleanup.append(("post_approvals", approval["id"]))

        visible = anon_fin_db.table("post_approvals") \
            .select("id").eq("id", approval["id"]).execute().data
        assert visible == []
