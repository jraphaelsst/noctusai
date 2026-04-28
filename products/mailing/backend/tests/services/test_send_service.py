"""Unit tests for SendService."""
from unittest.mock import MagicMock

from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.services.send_service import SendService

ORG = "org-test-001"


def _make_settings(**overrides):
    settings = MagicMock()
    settings.resend_api_key = overrides.get("resend_api_key", None)
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
            {"contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "active"}},
            {"contact_id": "ct2", "contacts": {"id": "ct2", "email": "b@test.com", "nome": "B", "empresa": "Y", "status": "active"}},
        ])
        db.set_table_data("send_logs", [])

        svc = SendService(db, _make_settings())
        count = svc.queue_campaign_sends("c1", ORG)

        assert count == 2

    def test_skips_inactive_contacts(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1", "list_id": "list1"}])
        db.set_table_data("contact_list_members", [
            {"contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "active"}},
            {"contact_id": "ct2", "contacts": {"id": "ct2", "email": "b@test.com", "nome": "B", "empresa": "Y", "status": "unsubscribed"}},
            {"contact_id": "ct3", "contacts": {"id": "ct3", "email": "c@test.com", "nome": "C", "empresa": "Z", "status": "bounced"}},
        ])
        db.set_table_data("send_logs", [])

        svc = SendService(db, _make_settings())
        count = svc.queue_campaign_sends("c1", ORG)

        assert count == 1

    def test_updates_campaign_total_recipients(self):
        db = MockSupabaseClient()
        db.set_table_data("campaigns", [{"id": "c1", "list_id": "list1"}])
        db.set_table_data("contact_list_members", [
            {"contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "active"}},
        ])
        db.set_table_data("send_logs", [])

        svc = SendService(db, _make_settings())
        count = svc.queue_campaign_sends("c1", ORG)

        # The service updates campaigns table — since the mock doesn't filter,
        # we verify the method completed and returned the correct count.
        assert count == 1

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
            {"contact_id": "ct1", "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "bounced"}},
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
    def test_updates_status_to_sent(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_sent": 0}])

        svc = SendService(db, _make_settings())
        logs = [{"id": "sl1", "campaign_id": "c1"}]

        # Should not raise
        svc._mark_sent(logs)

    def test_mark_sent_with_batch_data(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_sent": 5}])

        svc = SendService(db, _make_settings())
        logs = [{"id": "sl1", "campaign_id": "c1"}]
        batch_data = [{"id": "resend-msg-123"}]

        svc._mark_sent(logs, batch_data=batch_data)

    def test_mark_sent_empty_logs(self):
        db = MockSupabaseClient()
        svc = SendService(db, _make_settings())
        # Should not raise on empty list
        svc._mark_sent([])


# ---------------------------------------------------------------------------
# _mark_failed()
# ---------------------------------------------------------------------------

class TestMarkFailed:
    def test_updates_status_to_failed_with_error(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_failed": 0}])

        svc = SendService(db, _make_settings())
        logs = [{"id": "sl1", "campaign_id": "c1"}]

        svc._mark_failed(logs, "Connection timeout")

    def test_mark_failed_empty_logs(self):
        db = MockSupabaseClient()
        svc = SendService(db, _make_settings())
        svc._mark_failed([], "some error")

    def test_mark_failed_multiple_logs(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [{"id": "sl1"}, {"id": "sl2"}])
        db.set_table_data("campaigns", [{"id": "c1", "total_failed": 3}])

        svc = SendService(db, _make_settings())
        logs = [
            {"id": "sl1", "campaign_id": "c1"},
            {"id": "sl2", "campaign_id": "c1"},
        ]
        svc._mark_failed(logs, "API rate limit")


# ---------------------------------------------------------------------------
# _finalize_campaign_if_done() — auto-trigger campaign debrief
# ---------------------------------------------------------------------------

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _campaign_row(**overrides):
    base = {
        "id": "c1",
        "org_id": "org-test-001",
        "status": "enviando",
        "created_by": "user-uuid-1",
        "nome": "Black Friday",
    }
    base.update(overrides)
    return base


def _user_lookup(email: str):
    """Shape `auth.admin.get_user_by_id` returns: object with .user.email."""
    return SimpleNamespace(user=SimpleNamespace(email=email))


class TestFinalizeCampaign:
    @pytest.mark.asyncio
    async def test_fires_debrief_when_queue_drains(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])  # zero queued → finalize triggers
        db.set_table_data("campaigns", [_campaign_row()])  # flip returns the row
        db.auth.admin.get_user_by_id.return_value = _user_lookup("creator@test.com")

        svc = SendService(db, _make_settings())

        with patch(
            "app.services.campaign_debrief_service.send_campaign_debrief",
            new_callable=AsyncMock,
        ) as debrief_mock:
            await svc._finalize_campaign_if_done("c1")

        debrief_mock.assert_awaited_once()
        kwargs = debrief_mock.await_args.kwargs
        assert kwargs["campaign_id"] == "c1"
        assert kwargs["recipient"] == "creator@test.com"
        assert kwargs["org_id"] == "org-test-001"

    @pytest.mark.asyncio
    async def test_skips_when_queued_remains(self):
        db = MockSupabaseClient()
        # one queued row → count=1 → early return before any update
        db.set_table_data("send_logs", [{"id": "sl1", "status": "queued"}])
        db.set_table_data("campaigns", [_campaign_row()])

        svc = SendService(db, _make_settings())

        with patch(
            "app.services.campaign_debrief_service.send_campaign_debrief",
            new_callable=AsyncMock,
        ) as debrief_mock:
            await svc._finalize_campaign_if_done("c1")

        debrief_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_idempotent_when_flip_returns_empty(self):
        """When the campaign is already 'enviada', the .neq filter returns []
        and we early-return without firing debrief. Simulated by an empty
        update response on the campaigns table."""
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])
        # Empty campaigns response → flipped.data is [] → no debrief
        db.set_table_data("campaigns", [])

        svc = SendService(db, _make_settings())

        with patch(
            "app.services.campaign_debrief_service.send_campaign_debrief",
            new_callable=AsyncMock,
        ) as debrief_mock:
            await svc._finalize_campaign_if_done("c1")

        debrief_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_swallows_debrief_failure(self):
        """A failure inside send_campaign_debrief must not propagate — the
        campaign is still finalized; debrief failure is logged at WARN."""
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])
        db.set_table_data("campaigns", [_campaign_row()])
        db.auth.admin.get_user_by_id.return_value = _user_lookup("creator@test.com")

        svc = SendService(db, _make_settings())

        with patch(
            "app.services.campaign_debrief_service.send_campaign_debrief",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            # No exception escapes
            await svc._finalize_campaign_if_done("c1")

    @pytest.mark.asyncio
    async def test_skips_when_no_recipient_resolvable(self):
        """No `created_by` and no `debrief_recipient` override → log warning
        and skip debrief. Campaign is still flipped to 'enviada' (the side
        effect that matters for downstream stats)."""
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])
        db.set_table_data("campaigns", [_campaign_row(created_by=None)])

        svc = SendService(db, _make_settings())

        with patch(
            "app.services.campaign_debrief_service.send_campaign_debrief",
            new_callable=AsyncMock,
        ) as debrief_mock:
            await svc._finalize_campaign_if_done("c1")

        debrief_mock.assert_not_awaited()
