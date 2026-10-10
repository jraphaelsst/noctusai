"""Unit tests for SendService."""
import logging
from unittest.mock import MagicMock

import pytest

from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.modules.email_marketing.services.send_service import SendService

ORG = "org-test-001"


def _make_settings(**overrides):
    settings = MagicMock()
    settings.resend_api_key = overrides.get("resend_api_key", "")
    settings.default_from_name = overrides.get("default_from_name", "Noctus")
    settings.default_from_email = overrides.get("default_from_email", "noreply@noctus.ai")
    return settings


# ---------------------------------------------------------------------------
# queue_campaign_sends()
# ---------------------------------------------------------------------------

class TestQueueCampaignSends:
    def test_creates_send_log_rows_with_status_queued(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1", "list_id": "list1"}])
        db.set_table_data("contact_list_members", [
            {"list_id": "list1", "contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "active", "email_optin": "not_required"}},
            {"list_id": "list1", "contact_id": "ct2", "contacts": {"id": "ct2", "email": "b@test.com", "nome": "B", "empresa": "Y", "status": "active", "email_optin": "not_required"}},
        ])
        db.set_table_data("send_logs", [])

        svc = SendService(db, _make_settings())
        count = svc.queue_campaign_sends("c1", ORG)

        assert count == 2
        logs = db.table("send_logs").select("*").execute().data
        assert {l["email"] for l in logs} == {"a@test.com", "b@test.com"}
        assert all(l["status"] == "queued" and l["org_id"] == ORG and l["campaign_id"] == "c1" for l in logs)

    def test_skips_inactive_contacts(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1", "list_id": "list1"}])
        db.set_table_data("contact_list_members", [
            {"list_id": "list1", "contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "active", "email_optin": "not_required"}},
            {"list_id": "list1", "contact_id": "ct2", "contacts": {"id": "ct2", "email": "b@test.com", "nome": "B", "empresa": "Y", "status": "unsubscribed", "email_optin": "not_required"}},
            {"list_id": "list1", "contact_id": "ct3", "contacts": {"id": "ct3", "email": "c@test.com", "nome": "C", "empresa": "Z", "status": "bounced", "email_optin": "not_required"}},
        ])
        db.set_table_data("send_logs", [])

        svc = SendService(db, _make_settings())
        count = svc.queue_campaign_sends("c1", ORG)

        assert count == 1
        logs = db.table("send_logs").select("*").execute().data
        assert [l["email"] for l in logs] == ["a@test.com"]

    def test_updates_campaign_total_recipients(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1", "list_id": "list1"}])
        db.set_table_data("contact_list_members", [
            {"list_id": "list1", "contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "active", "email_optin": "not_required"}},
        ])
        db.set_table_data("send_logs", [])

        svc = SendService(db, _make_settings())
        count = svc.queue_campaign_sends("c1", ORG)

        assert count == 1
        campaign = db.table("campaigns").select("*").eq("id", "c1").execute().data[0]
        assert campaign["total_recipients"] == 1

    def test_returns_zero_when_campaign_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [])

        svc = SendService(db, _make_settings())
        assert svc.queue_campaign_sends("missing", ORG) == 0

    def test_returns_zero_when_no_list_id(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1"}])  # no list_id

        svc = SendService(db, _make_settings())
        assert svc.queue_campaign_sends("c1", ORG) == 0

    def test_returns_zero_when_no_active_contacts(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1", "list_id": "list1"}])
        db.set_table_data("contact_list_members", [
            {"list_id": "list1", "contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "bounced", "email_optin": "not_required"}},
        ])

        svc = SendService(db, _make_settings())
        assert svc.queue_campaign_sends("c1", ORG) == 0


# ---------------------------------------------------------------------------
# _render()
# ---------------------------------------------------------------------------

class TestRender:
    def test_replaces_known_variables(self):
        svc = SendService(MockSupabaseClient(), _make_settings())
        result = svc._render("Ola {{nome}} de {{empresa}}", {"nome": "Ana", "empresa": "Acme"})
        assert result == "Ola Ana de Acme"

    def test_leaves_unknown_variables(self):
        svc = SendService(MockSupabaseClient(), _make_settings())
        result = svc._render("{{nome}} {{cargo}}", {"nome": "Bob"})
        assert result == "Bob {{cargo}}"

    def test_empty_text(self):
        svc = SendService(MockSupabaseClient(), _make_settings())
        assert svc._render("", {"nome": "X"}) == ""

    def test_no_variables_in_text(self):
        svc = SendService(MockSupabaseClient(), _make_settings())
        assert svc._render("Texto puro", {"nome": "X"}) == "Texto puro"


# ---------------------------------------------------------------------------
# _mark_sent()
# ---------------------------------------------------------------------------

class TestMarkSent:
    @pytest.mark.asyncio
    async def test_updates_status_to_sent(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_sent": 0}])

        svc = SendService(db, _make_settings())
        logs = [{"id": "sl1", "campaign_id": "c1"}]

        await svc._mark_sent(logs)

        log = db.table("send_logs").select("*").eq("id", "sl1").execute().data[0]
        assert log["status"] == "sent" and log["sent_at"]
        assert db.table("campaigns").select("*").eq("id", "c1").execute().data[0]["total_sent"] == 1

    @pytest.mark.asyncio
    async def test_mark_sent_with_batch_data(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_sent": 5}])

        svc = SendService(db, _make_settings())
        logs = [{"id": "sl1", "campaign_id": "c1"}]
        batch_data = [{"id": "resend-msg-123"}]

        await svc._mark_sent(logs, batch_data=batch_data)

        assert db.table("send_logs").select("*").eq("id", "sl1").execute().data[0]["resend_message_id"] == "resend-msg-123"
        assert db.table("campaigns").select("*").eq("id", "c1").execute().data[0]["total_sent"] == 6

    @pytest.mark.asyncio
    async def test_mark_sent_empty_logs(self):
        db = MockSupabaseClient()
        svc = SendService(db, _make_settings())
        # Should not raise on empty list
        await svc._mark_sent([])


# ---------------------------------------------------------------------------
# _mark_failed()
# ---------------------------------------------------------------------------

class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_updates_status_to_failed_with_error(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_failed": 0}])

        svc = SendService(db, _make_settings())
        logs = [{"id": "sl1", "campaign_id": "c1"}]

        await svc._mark_failed(logs, "Connection timeout")

        log = db.table("send_logs").select("*").eq("id", "sl1").execute().data[0]
        assert log["status"] == "failed" and log["error_message"] == "Connection timeout"
        assert db.table("campaigns").select("*").eq("id", "c1").execute().data[0]["total_failed"] == 1

    @pytest.mark.asyncio
    async def test_mark_failed_empty_logs(self):
        db = MockSupabaseClient()
        svc = SendService(db, _make_settings())
        await svc._mark_failed([], "some error")

    @pytest.mark.asyncio
    async def test_mark_failed_multiple_logs(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}, {"id": "sl2"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_failed": 3}])

        svc = SendService(db, _make_settings())
        logs = [
            {"id": "sl1", "campaign_id": "c1"},
            {"id": "sl2", "campaign_id": "c1"},
        ]
        await svc._mark_failed(logs, "API rate limit")

        assert db.table("campaigns").select("*").eq("id", "c1").execute().data[0]["total_failed"] == 5
        assert all(
            db.table("send_logs").select("*").eq("id", i).execute().data[0]["status"] == "failed"
            for i in ("sl1", "sl2")
        )


# ---------------------------------------------------------------------------
# _finalize_campaign_if_done() — auto-trigger campaign debrief
#
# The debrief runs for real (no patching of our own service): the LLM boundary
# (`chat_completion`) is canned and the e-mail backend resolves to "none
# configured", so `send_digest` takes its own DRY-RUN branch and logs the
# recipient. That log line + the campaign row's status are the observable
# effects.
# ---------------------------------------------------------------------------

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

_DIGEST_CREDS = "noctusai_lib.integrations.email.digest.resolve_credential"
_NARRATIVE_LLM = "noctusai_lib.domain.digest.narrative.chat_completion"


def _campaign_row(**overrides):
    base = {
        "id": "c1",
        "org_id": "org-test-001",
        "status": "enviando",
        "created_by": "user-uuid-1",
        "nome": "Black Friday",
        "total_recipients": 0,
    }
    base.update(overrides)
    return base


def _user_lookup(email: str):
    """Shape `auth.admin.get_user_by_id` returns: object with .user.email."""
    return SimpleNamespace(user=SimpleNamespace(email=email))


def _status(db, campaign_id="c1"):
    rows = db.table("campaigns").select("*").eq("id", campaign_id).execute().data
    return rows[0]["status"] if rows else None


class TestFinalizeCampaign:
    @pytest.mark.asyncio
    async def test_fires_debrief_when_queue_drains(self, caplog):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])  # zero queued -> finalize triggers
        db.set_table_data("campaigns", [_campaign_row()])
        db.auth.admin.get_user_by_id.return_value = _user_lookup("creator@test.com")

        svc = SendService(db, _make_settings())
        with patch(_DIGEST_CREDS, return_value=None), patch(
            _NARRATIVE_LLM, new_callable=AsyncMock, return_value="Panorama.\n\nObs.\n\nRec."
        ), caplog.at_level(logging.INFO):
            await svc._finalize_campaign_if_done("c1")

        assert _status(db) == "enviada"
        assert any(
            "CAMPAIGN DEBRIEF" in r.getMessage() and "creator@test.com" in r.getMessage()
            for r in caplog.records
        ), "debrief was not dispatched to the campaign creator"

    @pytest.mark.asyncio
    async def test_skips_when_queued_remains(self, caplog):
        db = MockSupabaseClient()
        # one queued row for THIS campaign -> early return before any update
        db.set_table_data("send_logs", [{"id": "sl1", "campaign_id": "c1", "status": "queued"}])
        db.set_table_data("campaigns", [_campaign_row()])

        svc = SendService(db, _make_settings())
        with patch(_DIGEST_CREDS, return_value=None), caplog.at_level(logging.INFO):
            await svc._finalize_campaign_if_done("c1")

        assert _status(db) == "enviando"
        assert not any("CAMPAIGN DEBRIEF" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_other_campaigns_queue_does_not_block_finalize(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl9", "campaign_id": "other", "status": "queued"}])
        db.set_table_data("campaigns", [_campaign_row(created_by=None)])

        svc = SendService(db, _make_settings())
        await svc._finalize_campaign_if_done("c1")

        assert _status(db) == "enviada"

    @pytest.mark.asyncio
    async def test_idempotent_when_already_finalized(self, caplog):
        """Already 'enviada': the .neq filter flips nothing, so no second debrief."""
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])
        db.set_table_data("campaigns", [_campaign_row(status="enviada")])
        db.auth.admin.get_user_by_id.return_value = _user_lookup("creator@test.com")

        svc = SendService(db, _make_settings())
        with patch(_DIGEST_CREDS, return_value=None), caplog.at_level(logging.INFO):
            await svc._finalize_campaign_if_done("c1")

        assert not any("CAMPAIGN DEBRIEF" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_swallows_debrief_failure(self):
        """A failure inside the debrief must not propagate - the campaign is
        still finalized; the failure is logged at WARN."""
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])
        db.set_table_data("campaigns", [_campaign_row()])
        db.auth.admin.get_user_by_id.return_value = _user_lookup("creator@test.com")

        svc = SendService(db, _make_settings())
        with patch(_DIGEST_CREDS, side_effect=RuntimeError("credential store down")):
            await svc._finalize_campaign_if_done("c1")  # no exception escapes

        assert _status(db) == "enviada"

    @pytest.mark.asyncio
    async def test_skips_when_no_recipient_resolvable(self, caplog):
        """No `created_by` and no `debrief_recipient` override -> skip the
        debrief; the campaign is still flipped to 'enviada'."""
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])
        db.set_table_data("campaigns", [_campaign_row(created_by=None)])

        svc = SendService(db, _make_settings())
        with patch(_DIGEST_CREDS, return_value=None), caplog.at_level(logging.INFO):
            await svc._finalize_campaign_if_done("c1")

        assert _status(db) == "enviada"
        assert not any("CAMPAIGN DEBRIEF" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_operator_override_recipient_wins(self, caplog):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])
        db.set_table_data("campaigns", [_campaign_row(debrief_recipient="ops@test.com")])

        svc = SendService(db, _make_settings())
        with patch(_DIGEST_CREDS, return_value=None), patch(
            _NARRATIVE_LLM, new_callable=AsyncMock, return_value="x"
        ), caplog.at_level(logging.INFO):
            await svc._finalize_campaign_if_done("c1")

        assert any("ops@test.com" in r.getMessage() for r in caplog.records)
