"""Tests for notification_service — fan-out + per-channel logging.

External seams (SMTP via smtplib, WAHA via the seed's get_whatsapp_client)
are mocked at the boundary; the service-internal logic (recipient
filtering, log-row composition, dispatch counting) is exercised against
real code paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.notification_service import (
    DispatchOutcome,
    NotificationService,
    NotificationServiceError,
)


# ─── Lean Supabase stub (mirrors test_video_cache_service.py shape) ────
class _MockSupabase:
    def __init__(self):
        self.inserted_payloads: list = []
        self._select_queue: list = []
        self._mode: str = "select"
        self._captured_filters: list = []

    def set_select(self, data):
        self._select_queue.append(data)

    def schema(self, _name): return self
    def table(self, _name): return self

    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def eq(self, key, value):
        self._captured_filters.append(("eq", key, value))
        return self

    def in_(self, key, values):
        self._captured_filters.append(("in", key, list(values)))
        return self

    def limit(self, *_a, **_k):
        return self

    def insert(self, payload, *_a, **_k):
        self._mode = "insert"
        self.inserted_payloads.append(payload)
        return self

    def execute(self):
        if self._mode == "insert":
            return MagicMock(data=[self.inserted_payloads[-1]])
        if self._select_queue:
            return MagicMock(data=self._select_queue.pop(0))
        return MagicMock(data=[])


def _service(admin, **overrides) -> NotificationService:
    base = dict(
        admin_supabase=admin,
        smtp_host="smtp.test", smtp_port=465,
        smtp_user="bot@test", smtp_password="sekret",
        waha_base_url="", waha_api_key="", waha_session="default",
    )
    base.update(overrides)
    return NotificationService(**base)


# ─── No recipients → no-op ─────────────────────────────────────────────
class TestNoRecipients:
    @pytest.mark.asyncio
    async def test_empty_notify_recipients_is_noop(self):
        admin = _MockSupabase()
        admin.set_select(data=[{
            "id": str(uuid4()), "org_id": str(uuid4()),
            "title": "T", "youtube_video_id": "v1",
            "notify_recipients": [],
        }])
        svc = _service(admin)
        outcome = await svc.notify_upload(job_id=uuid4())
        assert outcome.attempted == 0
        assert outcome.recipients == 0
        assert admin.inserted_payloads == []   # no log rows


class TestJobNotFound:
    @pytest.mark.asyncio
    async def test_missing_job_raises(self):
        admin = _MockSupabase()
        admin.set_select(data=[])             # job lookup returns nothing
        svc = _service(admin)
        with pytest.raises(NotificationServiceError):
            await svc.notify_upload(job_id=uuid4())


# ─── Email path ────────────────────────────────────────────────────────
class TestEmailDispatch:
    @pytest.mark.asyncio
    async def test_email_only_recipient_dispatches_once(self):
        admin = _MockSupabase()
        recipient_id = str(uuid4())
        admin.set_select(data=[{
            "id": str(uuid4()), "org_id": str(uuid4()),
            "title": "Big news", "youtube_video_id": "abc",
            "notify_recipients": [recipient_id],
        }])
        admin.set_select(data=[{
            "id": recipient_id, "name": "Sponsor",
            "email": "sponsor@example.com", "whatsapp_number": None,
            "is_active": True,
        }])

        svc = _service(admin)
        with patch("app.services.notification_service.EmailService") as email_cls:
            email_inst = MagicMock()
            email_inst.send_email = AsyncMock()
            email_cls.return_value = email_inst

            outcome = await svc.notify_upload(job_id=uuid4())

        assert outcome.recipients == 1
        assert outcome.attempted == 1
        assert outcome.succeeded == 1
        assert outcome.failed == 0
        # Exactly one notification_log row, status='sent'.
        log_rows = [p for p in admin.inserted_payloads if isinstance(p, dict) and p.get("channel") == "email"]
        assert len(log_rows) == 1
        assert log_rows[0]["status"] == "sent"

    @pytest.mark.asyncio
    async def test_smtp_unconfigured_logs_per_recipient_failure(self):
        """When SMTP creds are missing, EmailService construction raises;
        the dispatcher catches it and logs a per-recipient skip — does
        NOT raise globally."""
        admin = _MockSupabase()
        rid = str(uuid4())
        admin.set_select(data=[{
            "id": str(uuid4()), "org_id": str(uuid4()),
            "title": "T", "youtube_video_id": "v",
            "notify_recipients": [rid],
        }])
        admin.set_select(data=[{
            "id": rid, "name": "X",
            "email": "x@example.com", "whatsapp_number": None,
            "is_active": True,
        }])

        # SMTP creds missing → EmailService raises EmailNotConfigured.
        svc = _service(admin, smtp_user="", smtp_password="")
        outcome = await svc.notify_upload(job_id=uuid4())

        assert outcome.recipients == 1
        assert outcome.failed == 1
        log_rows = [p for p in admin.inserted_payloads if isinstance(p, dict) and p.get("channel") == "email"]
        assert len(log_rows) == 1
        assert log_rows[0]["status"] == "failed"
        assert "smtp" in log_rows[0]["error_message"].lower()


# ─── WhatsApp path ─────────────────────────────────────────────────────
class TestWhatsAppDispatch:
    @pytest.mark.asyncio
    async def test_whatsapp_only_recipient_dispatches_via_fake(self):
        """Empty waha_base_url → FakeWahaClient.send_text logs but
        doesn't raise. Should count as success."""
        admin = _MockSupabase()
        rid = str(uuid4())
        admin.set_select(data=[{
            "id": str(uuid4()), "org_id": str(uuid4()),
            "title": "T", "youtube_video_id": "v1",
            "notify_recipients": [rid],
        }])
        admin.set_select(data=[{
            "id": rid, "name": "Friend",
            "email": None, "whatsapp_number": "+5511999999999",
            "is_active": True,
        }])

        svc = _service(admin)             # waha_base_url="" → FakeWahaClient
        outcome = await svc.notify_upload(job_id=uuid4())
        assert outcome.attempted == 1
        assert outcome.succeeded == 1
        assert outcome.failed == 0

    @pytest.mark.asyncio
    async def test_whatsapp_send_failure_logs_failed(self):
        admin = _MockSupabase()
        rid = str(uuid4())
        admin.set_select(data=[{
            "id": str(uuid4()), "org_id": str(uuid4()),
            "title": "T", "youtube_video_id": "v1",
            "notify_recipients": [rid],
        }])
        admin.set_select(data=[{
            "id": rid, "name": "Friend",
            "email": None, "whatsapp_number": "+5511999999999",
            "is_active": True,
        }])

        svc = _service(admin)
        with patch("app.services.notification_service.get_whatsapp_client") as factory:
            client = MagicMock()
            client.send_text = AsyncMock(side_effect=RuntimeError("WAHA down"))
            factory.return_value = client

            outcome = await svc.notify_upload(job_id=uuid4())

        assert outcome.attempted == 1
        assert outcome.succeeded == 0
        assert outcome.failed == 1
        log_rows = [p for p in admin.inserted_payloads if isinstance(p, dict) and p.get("channel") == "whatsapp"]
        assert len(log_rows) == 1
        assert log_rows[0]["status"] == "failed"
        assert "waha" in log_rows[0]["error_message"].lower()


# ─── Multi-channel + multi-recipient ───────────────────────────────────
class TestFanout:
    @pytest.mark.asyncio
    async def test_dual_channel_recipient_fires_both(self):
        admin = _MockSupabase()
        rid = str(uuid4())
        admin.set_select(data=[{
            "id": str(uuid4()), "org_id": str(uuid4()),
            "title": "T", "youtube_video_id": "v1",
            "notify_recipients": [rid],
        }])
        admin.set_select(data=[{
            "id": rid, "name": "Both",
            "email": "x@example.com", "whatsapp_number": "+5511999999999",
            "is_active": True,
        }])

        svc = _service(admin)
        with patch("app.services.notification_service.EmailService") as email_cls:
            email_inst = MagicMock()
            email_inst.send_email = AsyncMock()
            email_cls.return_value = email_inst

            outcome = await svc.notify_upload(job_id=uuid4())

        assert outcome.recipients == 1
        assert outcome.attempted == 2     # email + whatsapp for one recipient
        assert outcome.succeeded == 2
        channels_logged = sorted(
            p["channel"] for p in admin.inserted_payloads
            if isinstance(p, dict) and "channel" in p
        )
        assert channels_logged == ["email", "whatsapp"]

    @pytest.mark.asyncio
    async def test_inactive_recipient_filtered_out(self):
        """The recipients fetcher applies eq("is_active", True) as a
        filter — inactive recipients should never reach dispatch.
        Verified by checking the captured filter chain."""
        admin = _MockSupabase()
        rid = str(uuid4())
        admin.set_select(data=[{
            "id": str(uuid4()), "org_id": str(uuid4()),
            "title": "T", "youtube_video_id": "v1",
            "notify_recipients": [rid],
        }])
        admin.set_select(data=[])         # no active recipients
        svc = _service(admin)
        outcome = await svc.notify_upload(job_id=uuid4())
        assert outcome.recipients == 0
        assert outcome.attempted == 0

        # Filter chain captured: must include eq is_active True.
        assert any(
            f == ("eq", "is_active", True)
            for f in admin._captured_filters
        )
