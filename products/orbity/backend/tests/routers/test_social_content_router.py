"""
Auth-boundary + validation tests for the /api/content/* router and the
public /api/content/approve/{token} endpoints.

Auth rules (strict):
  - All /api/content/* authed endpoints → assert == 401 (never 404 or 422).
  - Public /api/content/approve/{token} endpoints → must NOT return 401.

Validation:
  - StrictHttpModel extra='forbid' → unknown fields → 422.
  - Literal field violations → 422.
"""
import pytest

TEST_ORG = "00000000-0000-0000-0000-000000000001"
TEST_TOKEN = "00000000-0000-0000-0000-000000000099"


# ---------------------------------------------------------------------------
# Auth boundary — all authed endpoints must return 401 without credentials
# ---------------------------------------------------------------------------

class TestCampaignsRouterAuth:
    """Every /api/content/campaigns/* endpoint requires authentication."""

    def test_list_campaigns_without_auth_returns_401(self, client):
        assert client.raw().get("/api/content/campaigns").status_code == 401

    def test_create_campaign_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/content/campaigns",
            json={"name": "Q3 Social", "month": "2026-07"},
        ).status_code == 401

    def test_get_campaign_without_auth_returns_401(self, client):
        assert client.raw().get("/api/content/campaigns/some-id").status_code == 401

    def test_update_campaign_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/content/campaigns/some-id",
            json={"name": "Updated"},
        ).status_code == 401

    def test_delete_campaign_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/content/campaigns/some-id").status_code == 401


class TestPostsRouterAuth:
    """Every /api/content/posts/* endpoint requires authentication."""

    def test_list_posts_without_auth_returns_401(self, client):
        assert client.raw().get("/api/content/posts").status_code == 401

    def test_create_post_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/content/posts",
            json={"platform": "instagram"},
        ).status_code == 401

    def test_get_post_without_auth_returns_401(self, client):
        assert client.raw().get("/api/content/posts/some-id").status_code == 401

    def test_update_post_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/content/posts/some-id",
            json={"caption": "hi"},
        ).status_code == 401

    def test_delete_post_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/content/posts/some-id").status_code == 401


class TestApprovalsRouterAuth:
    """Every /api/content/approvals + /posts/{id}/approvals endpoint requires auth."""

    def test_create_approval_link_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/content/posts/some-id/approvals",
            json={"expires_in_days": 7},
        ).status_code == 401

    def test_list_post_approvals_without_auth_returns_401(self, client):
        assert client.raw().get(
            "/api/content/posts/some-id/approvals"
        ).status_code == 401

    def test_list_approvals_without_auth_returns_401(self, client):
        assert client.raw().get("/api/content/approvals").status_code == 401

    def test_get_approval_without_auth_returns_401(self, client):
        assert client.raw().get("/api/content/approvals/some-id").status_code == 401


# ---------------------------------------------------------------------------
# Validation — inbound schema enforcement
# ---------------------------------------------------------------------------

class TestCampaignValidation:
    """Pydantic validation on campaign inbound schemas."""

    def test_create_campaign_missing_name_returns_422(self, client):
        resp = client.post("/api/content/campaigns", json={"month": "2026-07"})
        assert resp.status_code == 422

    def test_create_campaign_missing_month_returns_422(self, client):
        resp = client.post("/api/content/campaigns", json={"name": "Q3"})
        assert resp.status_code == 422

    def test_create_campaign_invalid_month_format_returns_422(self, client):
        resp = client.post(
            "/api/content/campaigns",
            json={"name": "Q3", "month": "2026/07"},
        )
        assert resp.status_code == 422

    def test_create_campaign_invalid_status_returns_422(self, client):
        resp = client.post(
            "/api/content/campaigns",
            json={"name": "Q3", "month": "2026-07", "status": "unknown"},
        )
        assert resp.status_code == 422

    def test_create_campaign_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/content/campaigns",
            json={"name": "Q3", "month": "2026-07", "rogue": True},
        )
        assert resp.status_code == 422

    def test_update_campaign_empty_body_returns_400(self, client):
        resp = client.patch("/api/content/campaigns/some-id", json={})
        assert resp.status_code == 400


class TestPostValidation:
    """Pydantic validation on post inbound schemas."""

    def test_create_post_missing_platform_returns_422(self, client):
        resp = client.post("/api/content/posts", json={"caption": "hi"})
        assert resp.status_code == 422

    def test_create_post_invalid_platform_returns_422(self, client):
        resp = client.post(
            "/api/content/posts",
            json={"platform": "snapchat"},
        )
        assert resp.status_code == 422

    def test_create_post_invalid_status_returns_422(self, client):
        resp = client.post(
            "/api/content/posts",
            json={"platform": "instagram", "status": "queued"},
        )
        assert resp.status_code == 422

    def test_create_post_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/content/posts",
            json={"platform": "instagram", "rogue": True},
        )
        assert resp.status_code == 422

    def test_update_post_empty_body_returns_400(self, client):
        resp = client.patch("/api/content/posts/some-id", json={})
        assert resp.status_code == 400


class TestApprovalValidation:
    """Pydantic validation on approval inbound schemas."""

    def test_create_approval_expires_too_low_returns_422(self, client):
        resp = client.post(
            "/api/content/posts/some-id/approvals",
            json={"expires_in_days": 0},
        )
        assert resp.status_code == 422

    def test_create_approval_expires_too_high_returns_422(self, client):
        resp = client.post(
            "/api/content/posts/some-id/approvals",
            json={"expires_in_days": 91},
        )
        assert resp.status_code == 422

    def test_create_approval_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/content/posts/some-id/approvals",
            json={"expires_in_days": 7, "rogue": True},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Public approve endpoints — must NOT return 401 (unauthenticated by design)
# ---------------------------------------------------------------------------

class TestPublicApproveEndpoints:
    """The /api/content/approve/{token} endpoints are public — no auth required."""

    def test_get_approval_public_no_auth_does_not_return_401(self, client):
        """GET approve — must be accessible without auth (may 404/410/502 but not 401)."""
        resp = client.raw().get(f"/api/content/approve/{TEST_TOKEN}")
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_post_approval_public_no_auth_does_not_return_401(self, client):
        """POST approve — must be accessible without auth."""
        resp = client.raw().post(
            f"/api/content/approve/{TEST_TOKEN}",
            json={"decision": "approved"},
        )
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_post_approval_invalid_decision_returns_422(self, client):
        """Invalid decision value → Pydantic 422 before service layer."""
        resp = client.raw().post(
            f"/api/content/approve/{TEST_TOKEN}",
            json={"decision": "reject"},
        )
        assert resp.status_code == 422

    def test_post_approval_extra_field_returns_422(self, client):
        """StrictHttpModel extra='forbid' enforced even on public endpoint."""
        resp = client.raw().post(
            f"/api/content/approve/{TEST_TOKEN}",
            json={"decision": "approved", "rogue": True},
        )
        assert resp.status_code == 422

    def test_get_approval_with_auth_does_not_return_401(self, client):
        """Public endpoint works for authenticated callers too (404/410/502 expected)."""
        resp = client.get(f"/api/content/approve/{TEST_TOKEN}")
        assert resp.status_code != 401

    def test_post_approval_with_auth_does_not_return_401(self, client):
        resp = client.post(
            f"/api/content/approve/{TEST_TOKEN}",
            json={"decision": "revision", "feedback": "Please darken the colours."},
        )
        assert resp.status_code != 401
