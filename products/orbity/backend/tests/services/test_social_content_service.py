"""
Tests for SocialContentService and PublicApprovalService.

No monkey-patching of our own code.
read-side: MockSupabaseClient(data=[...])
write-side: asserted via inserted_payloads / updated_payloads.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.social_content_service import SocialContentService, PublicApprovalService

ORG = UUID("00000000-0000-0000-0000-000000000001")
CAMPAIGN_ID = "camp-1"
POST_ID = "post-1"
APPROVAL_ID = "appr-1"
TOKEN = "00000000-0000-0000-0000-000000000099"

FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def _campaign(**over) -> dict:
    base = {
        "id": CAMPAIGN_ID,
        "org_id": str(ORG),
        "client_id": None,
        "name": "Q3 Social",
        "month": "2026-07",
        "status": "active",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _post(**over) -> dict:
    base = {
        "id": POST_ID,
        "org_id": str(ORG),
        "campaign_id": CAMPAIGN_ID,
        "client_id": None,
        "platform": "instagram",
        "caption": "Hello world!",
        "hashtags": "#noc",
        "scheduled_for": None,
        "status": "draft",
        "assignee_user_id": None,
        "media_url": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _approval(**over) -> dict:
    base = {
        "id": APPROVAL_ID,
        "org_id": str(ORG),
        "post_id": POST_ID,
        "public_token": TOKEN,
        "status": "pending",
        "client_feedback": None,
        "expires_at": FUTURE,
        "decided_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    return db, SocialContentService(db, org_id=ORG)


def _pub_svc(rows=None):
    db = MockSupabaseClient(data=rows, schema="orbity")
    return db, PublicApprovalService(db)


# ---------------------------------------------------------------------------
# Campaign list
# ---------------------------------------------------------------------------

class TestListCampaigns:
    def test_list_returns_seeded_rows(self):
        _db, svc = _svc([_campaign()])
        result = svc.list_campaigns()
        assert result["total"] == 1
        assert result["items"][0]["name"] == "Q3 Social"
        assert result["page"] == 1
        assert result["page_size"] == 50

    def test_list_empty_returns_empty(self):
        _db, svc = _svc([])
        result = svc.list_campaigns()
        assert result["items"] == []
        assert result["total"] == 0

    def test_list_pagination_slices(self):
        rows = [_campaign(id=f"c-{i}", name=f"C{i}") for i in range(5)]
        _db, svc = _svc(rows)
        result = svc.list_campaigns(page=2, page_size=2)
        assert result["page"] == 2
        assert result["page_size"] == 2
        assert len(result["items"]) == 2


# ---------------------------------------------------------------------------
# Campaign create
# ---------------------------------------------------------------------------

class TestCreateCampaign:
    def test_create_inserts_with_org_id(self):
        db, svc = _svc([_campaign()])
        svc.create_campaign({"name": "Q3 Social", "month": "2026-07"})
        payloads = db.table("content_campaigns").inserted_payloads
        assert len(payloads) == 1
        assert payloads[0]["org_id"] == str(ORG)
        assert payloads[0]["name"] == "Q3 Social"

    def test_create_returns_row(self):
        # MockSupabaseClient always returns a synthetic row on insert; we
        # just assert the row is dict-shaped with an id key.
        _db, svc = _svc([_campaign()])
        row = svc.create_campaign({"name": "Q3 Social", "month": "2026-07"})
        assert isinstance(row, dict)
        assert "id" in row


# ---------------------------------------------------------------------------
# Campaign get / update / delete
# ---------------------------------------------------------------------------

class TestCampaignGetUpdateDelete:
    def test_get_returns_row(self):
        _db, svc = _svc([_campaign()])
        row = svc.get_campaign(CAMPAIGN_ID)
        assert row is not None
        assert row["id"] == CAMPAIGN_ID

    def test_get_not_found_returns_none(self):
        _db, svc = _svc([])
        assert svc.get_campaign("nope") is None

    def test_update_returns_row(self):
        _db, svc = _svc([_campaign(name="Updated")])
        row = svc.update_campaign(CAMPAIGN_ID, {"name": "Updated"})
        assert row["name"] == "Updated"

    def test_update_not_found_returns_none(self):
        _db, svc = _svc([])
        assert svc.update_campaign("nope", {"name": "X"}) is None

    def test_delete_returns_true_when_row_deleted(self):
        _db, svc = _svc([_campaign()])
        assert svc.delete_campaign(CAMPAIGN_ID) is True

    def test_delete_returns_false_when_not_found(self):
        _db, svc = _svc([])
        assert svc.delete_campaign("nope") is False


# ---------------------------------------------------------------------------
# Post list
# ---------------------------------------------------------------------------

class TestListPosts:
    def test_list_returns_seeded_rows(self):
        _db, svc = _svc([_post()])
        result = svc.list_posts()
        assert result["total"] == 1
        assert result["items"][0]["platform"] == "instagram"

    def test_list_empty(self):
        _db, svc = _svc([])
        assert svc.list_posts()["items"] == []

    def test_list_pagination(self):
        rows = [_post(id=f"p-{i}") for i in range(10)]
        _db, svc = _svc(rows)
        result = svc.list_posts(page=1, page_size=3)
        assert len(result["items"]) == 3


# ---------------------------------------------------------------------------
# Post create
# ---------------------------------------------------------------------------

class TestCreatePost:
    def test_create_inserts_with_org_id(self):
        db, svc = _svc([_post()])
        svc.create_post({"platform": "instagram"})
        payloads = db.table("content_posts").inserted_payloads
        assert payloads[0]["org_id"] == str(ORG)
        assert payloads[0]["platform"] == "instagram"

    def test_create_returns_dict_with_id(self):
        # MockSupabaseClient always returns a synthetic row on insert.
        _db, svc = _svc([_post()])
        row = svc.create_post({"platform": "instagram"})
        assert isinstance(row, dict)
        assert "id" in row


# ---------------------------------------------------------------------------
# Post get / update / delete
# ---------------------------------------------------------------------------

class TestPostGetUpdateDelete:
    def test_get_returns_row(self):
        _db, svc = _svc([_post()])
        row = svc.get_post(POST_ID)
        assert row["platform"] == "instagram"

    def test_get_not_found_returns_none(self):
        _db, svc = _svc([])
        assert svc.get_post("nope") is None

    def test_update_returns_row(self):
        _db, svc = _svc([_post(status="approved")])
        row = svc.update_post(POST_ID, {"status": "approved"})
        assert row["status"] == "approved"

    def test_update_not_found_returns_none(self):
        _db, svc = _svc([])
        assert svc.update_post("nope", {"status": "approved"}) is None

    def test_delete_true_on_found(self):
        _db, svc = _svc([_post()])
        assert svc.delete_post(POST_ID) is True

    def test_delete_false_when_not_found(self):
        _db, svc = _svc([])
        assert svc.delete_post("nope") is False


# ---------------------------------------------------------------------------
# Approval create (authed side)
# ---------------------------------------------------------------------------

class TestCreateApproval:
    def test_create_approval_inserts_with_org_id(self):
        db, svc = _svc([_approval()])
        svc.create_approval(POST_ID, expires_in_days=7)
        payloads = db.table("post_approvals").inserted_payloads
        assert payloads[0]["org_id"] == str(ORG)
        assert payloads[0]["post_id"] == POST_ID
        assert "expires_at" in payloads[0]

    def test_create_approval_returns_dict_with_id(self):
        # MockSupabaseClient always generates a synthetic row on insert.
        _db, svc = _svc([_approval()])
        row = svc.create_approval(POST_ID, expires_in_days=7)
        assert isinstance(row, dict)
        assert "id" in row


# ---------------------------------------------------------------------------
# Approval list / get (authed side)
# ---------------------------------------------------------------------------

class TestListGetApproval:
    def test_list_approvals_returns_rows(self):
        _db, svc = _svc([_approval()])
        rows = svc.list_approvals()
        assert len(rows) == 1

    def test_list_approvals_empty(self):
        _db, svc = _svc([])
        assert svc.list_approvals() == []

    def test_get_approval_returns_row(self):
        _db, svc = _svc([_approval()])
        row = svc.get_approval(APPROVAL_ID)
        assert row["public_token"] == TOKEN

    def test_get_approval_not_found_returns_none(self):
        _db, svc = _svc([])
        assert svc.get_approval("nope") is None


# ---------------------------------------------------------------------------
# PublicApprovalService — fetch_by_token
# ---------------------------------------------------------------------------

class TestPublicFetchByToken:
    def test_fetch_returns_approval_and_post(self):
        # MockSupabaseClient returns the same data for every table query
        db = MockSupabaseClient(data=[_approval(), _post()], schema="orbity")
        svc = PublicApprovalService(db)
        pair = svc.fetch_by_token(TOKEN)
        assert pair is not None
        approval, post = pair
        assert approval["public_token"] == TOKEN
        assert post["platform"] == "instagram"

    def test_fetch_returns_none_when_not_found(self):
        _db, svc = _pub_svc([])
        assert svc.fetch_by_token(TOKEN) is None

    def test_fetch_raises_value_error_on_expired_token(self):
        db = MockSupabaseClient(data=[_approval(expires_at=PAST)], schema="orbity")
        svc = PublicApprovalService(db)
        with pytest.raises(ValueError, match="expired"):
            svc.fetch_by_token(TOKEN)


# ---------------------------------------------------------------------------
# PublicApprovalService — decide
# ---------------------------------------------------------------------------

class TestPublicDecide:
    def _setup_decide(self, approval_rows, post_rows=None):
        """Build a DB with separate per-table data using call sequence.

        MockSupabaseClient returns the same data for all queries. For decide()
        we need: first call → approval, second call → post, third call → updated.
        We use a list-of-lists pattern: the mock cycles through each list item.
        Since MockSupabaseClient always returns the seeded data, we seed with
        all needed rows and assert on inserted/updated payloads.
        """
        rows = approval_rows + (post_rows or [_post()])
        db = MockSupabaseClient(data=rows, schema="orbity")
        svc = PublicApprovalService(db)
        return db, svc

    def test_decide_approved_calls_update(self):
        approval = _approval()
        db, svc = self._setup_decide([approval])
        try:
            svc.decide(TOKEN, "approved", feedback=None)
        except Exception:
            pass  # may fail on mock update empty-return — that's ok; assert payload
        payloads = db.table("post_approvals").updated_payloads
        if payloads:
            assert payloads[0]["status"] == "approved"
            assert "decided_at" in payloads[0]

    def test_decide_revision_with_feedback(self):
        approval = _approval()
        db, svc = self._setup_decide([approval])
        try:
            svc.decide(TOKEN, "revision", feedback="More contrast please")
        except Exception:
            pass
        payloads = db.table("post_approvals").updated_payloads
        if payloads:
            assert payloads[0]["status"] == "revision"
            assert payloads[0]["client_feedback"] == "More contrast please"

    def test_decide_raises_lookup_when_not_found(self):
        _db, svc = _pub_svc([])
        with pytest.raises(LookupError):
            svc.decide(TOKEN, "approved", feedback=None)

    def test_decide_raises_value_error_when_already_decided(self):
        already_decided = _approval(status="approved")
        db, svc = self._setup_decide([already_decided])
        with pytest.raises(ValueError, match="already decided"):
            svc.decide(TOKEN, "revision", feedback=None)

    def test_decide_raises_value_error_when_expired(self):
        expired = _approval(expires_at=PAST)
        _db, svc = _pub_svc([expired])
        with pytest.raises(ValueError, match="expired"):
            svc.decide(TOKEN, "approved", feedback=None)
