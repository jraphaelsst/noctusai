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

from noctusai_lib.api.token_link import TokenLinkGone, TokenLinkNotFound, resolve_token_link

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
    """The public read goes token -> approval row (resolve_token_link) -> the post INSIDE the approval's org."""

    def test_fetch_returns_approval_and_post(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("post_approvals", [_approval()])
        db.set_table_data("content_posts", [_post()])
        svc = PublicApprovalService(db)
        approval = resolve_token_link(TOKEN, svc.fetch_approval_row)
        assert approval["public_token"] == TOKEN
        assert svc.post_of(approval)["platform"] == "instagram"

    def test_unknown_token_is_not_found(self):
        _db, svc = _pub_svc([])
        with pytest.raises(TokenLinkNotFound):
            resolve_token_link(TOKEN, svc.fetch_approval_row)

    def test_expired_token_is_gone(self):
        db = MockSupabaseClient(data=[_approval(expires_at=PAST)], schema="orbity")
        with pytest.raises(TokenLinkGone):
            resolve_token_link(TOKEN, PublicApprovalService(db).fetch_approval_row)

    def test_a_missing_or_unparsable_expiry_fails_closed(self):
        for bad in (None, "not-a-date"):
            db = MockSupabaseClient(data=[_approval(expires_at=bad)], schema="orbity")
            with pytest.raises(TokenLinkGone):
                resolve_token_link(TOKEN, PublicApprovalService(db).fetch_approval_row)

    def test_an_approval_of_org_a_never_reads_the_post_of_org_b(self):
        """LEAK (security review round 3): the approval row's post_id pointing at ANOTHER org's post reads nothing."""
        org_b = "00000000-0000-0000-0000-0000000000bb"
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("post_approvals", [_approval()])  # org A
        db.set_table_data("content_posts", [_post(org_id=org_b)])  # the post it points at belongs to org B
        svc = PublicApprovalService(db)
        assert svc.post_of(resolve_token_link(TOKEN, svc.fetch_approval_row)) is None


# ---------------------------------------------------------------------------
# PublicApprovalService — decide
# ---------------------------------------------------------------------------

class TestPublicDecide:
    def _setup_decide(self, approval_rows, post_rows=None):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("post_approvals", approval_rows)
        db.set_table_data("content_posts", post_rows if post_rows is not None else [_post()])
        return db, PublicApprovalService(db)

    @staticmethod
    def _decide(svc, decision, feedback=None):
        return svc.decide(resolve_token_link(TOKEN, svc.fetch_approval_row), decision, feedback=feedback)

    def test_decide_approved_calls_update(self):
        db, svc = self._setup_decide([_approval()])
        result = self._decide(svc, "approved")
        payloads = db.table("post_approvals").updated_payloads
        assert payloads[0]["status"] == "approved"
        assert "decided_at" in payloads[0]
        assert db.table("content_posts").updated_payloads[-1] == {"status": "approved"}
        assert result["status"] == "approved"

    def test_decide_revision_with_feedback(self):
        db, svc = self._setup_decide([_approval()])
        self._decide(svc, "revision", "More contrast please")
        payloads = db.table("post_approvals").updated_payloads
        assert payloads[0]["status"] == "revision"
        assert payloads[0]["client_feedback"] == "More contrast please"

    def test_decide_of_org_a_approval_never_writes_the_post_of_org_b(self):
        """LEAK: an approval whose post_id points at another org's post neither reads nor WRITES that post."""
        org_b = "00000000-0000-0000-0000-0000000000bb"
        db, svc = self._setup_decide([_approval()], [_post(org_id=org_b)])
        with pytest.raises(LookupError):
            self._decide(svc, "approved")
        assert db.table("content_posts").updated_payloads == []
        assert db.table("post_approvals").updated_payloads == []

    def test_decide_is_one_time_and_atomic(self):
        """The UPDATE re-states status='pending': when it matches 0 rows (someone decided first) the call is Gone (410)."""
        db, svc = self._setup_decide([_approval(status="approved")])  # already decided -> the guarded UPDATE matches nothing
        approval = resolve_token_link(TOKEN, svc.fetch_approval_row)
        with pytest.raises(TokenLinkGone):
            svc.decide(approval, "revision", feedback=None)
        assert db.table("content_posts").updated_payloads == []

    # --- team notification (the client page promises "a equipe foi notificada") ---

    def _core(self, users):
        return MockSupabaseClient(data=users, schema="public")

    def _notify_db(self, post):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("post_approvals", [_approval()])
        db.set_table_data("content_posts", [post])
        return db

    def test_decide_notifies_org_admins_when_post_has_no_assignee(self):
        db = self._notify_db(_post())
        core = self._core([{"id": "u-admin", "org_id": str(ORG), "org_role": "admin"}])
        result = self._decide(PublicApprovalService(db, core_db=core), "approved")
        sent = core.table("notifications").inserted_payloads
        assert [n["user_id"] for n in sent] == ["u-admin"]
        assert sent[0]["metadata"]["tipo"] == "aprovacao_conteudo"
        assert sent[0]["metadata"]["decision"] == "approved"
        assert sent[0]["org_id"] == str(ORG)
        assert result["team_notified"] == 1

    def test_decide_notifies_assignee_with_feedback_on_revision(self):
        db = self._notify_db(_post(assignee_user_id="u-assignee"))
        core = self._core([{"id": "u-assignee", "org_id": str(ORG), "org_role": "member"}])
        self._decide(PublicApprovalService(db, core_db=core), "revision", "Trocar a foto")
        sent = core.table("notifications").inserted_payloads
        assert [n["user_id"] for n in sent] == ["u-assignee"]
        assert "Trocar a foto" in sent[0]["message"]

    def test_decide_never_notifies_an_assignee_who_is_not_in_the_org(self):
        """The assignee id on the post is not trusted at the sink: a user of ANOTHER org (stale or forged id) is dropped and the
        org's admins are told instead."""
        db = self._notify_db(_post(assignee_user_id="u-outsider"))
        other_org = "00000000-0000-4000-8000-0000000000ff"
        core = self._core([
            {"id": "u-outsider", "org_id": other_org, "org_role": "member"},
            {"id": "u-admin", "org_id": str(ORG), "org_role": "admin"},
        ])
        self._decide(PublicApprovalService(db, core_db=core), "approved")
        assert [n["user_id"] for n in core.table("notifications").inserted_payloads] == ["u-admin"]

    def test_decide_without_core_client_records_decision_and_reports_zero(self, caplog):
        db, svc = self._setup_decide([_approval()])  # no core_db
        result = self._decide(svc, "approved")
        assert result["status"] == "approved"
        assert result["team_notified"] == 0
        assert "notify skipped" in caplog.text

    def test_unknown_token_is_not_found_before_any_decision(self):
        _db, svc = _pub_svc([])
        with pytest.raises(TokenLinkNotFound):
            self._decide(svc, "approved")

    def test_expired_link_is_gone_before_any_decision(self):
        db, svc = self._setup_decide([_approval(expires_at=PAST)])
        with pytest.raises(TokenLinkGone):
            self._decide(svc, "approved")
        assert db.table("post_approvals").updated_payloads == []
