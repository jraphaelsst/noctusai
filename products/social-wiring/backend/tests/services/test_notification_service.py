"""Tests for notification_service — fan-out + per-channel logging.

External seams (SMTP via smtplib, WAHA via the seed's get_whatsapp_client)
are mocked at the boundary; the service-internal logic (recipient
filtering, log-row composition, dispatch counting) is exercised against
real code paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.email_service import EmailServiceError
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

    def is_(self, key, value):
        # Real supabase-py exposes `.is_()` for NULL comparisons; the org-wide
        # recipient tier is `client_id IS NULL`, so the mock needs it or the
        # tests exercise an error path instead of the code under test.
        self._captured_filters.append(("is", key, value))
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

        # EmailService is our thin SMTP wrapper; inject a fake factory via
        # the `email_service_factory` DI seam (Class-C) instead of patching
        # the module symbol. Per KB § PATTERNS/di-test-seam.md.
        email_inst = MagicMock()
        email_inst.send_email = AsyncMock()
        svc = _service(admin, email_service_factory=lambda **_kw: email_inst)

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

        # Same Class-C DI-seam rationale as the single-channel email test above.
        email_inst = MagicMock()
        email_inst.send_email = AsyncMock()
        svc = _service(admin, email_service_factory=lambda **_kw: email_inst)

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


# ─── New Meta lead fan-out (notify_new_lead) ───────────────────────────
def _lead(**overrides) -> dict:
    base = dict(
        full_name="Maria Souza",
        phone="+5511988887777",
        email="maria@example.com",
        form_name="Fale com um corretor",
        campaign_name="Lançamento Jardins",
        created_time="2026-08-03T14:30:00+00:00",
    )
    base.update(overrides)
    return base


def _whatsapp_factory(client):
    """DI-seam factory matching get_whatsapp_client's kwarg shape —
    exercises the real resolution path (self._whatsapp_client_factory),
    never patches the module global."""
    return lambda **_kw: client


class TestNewLeadFanout:
    @pytest.mark.asyncio
    async def test_all_three_channel_attempts_from_one_dual_channel_recipient(self):
        """One recipient with both email + whatsapp on an org with a
        single active roster row -> both channels attempted, both
        succeed. ('all three channels' across the fixture set is
        covered by this test + the email-only/whatsapp-only tests below
        exercising the third arrangement.)"""
        admin = _MockSupabase()
        admin.set_select(data=[{
            "id": str(uuid4()), "name": "Ops",
            "email": "ops@example.com", "whatsapp_number": "+5511999998888",
            "is_active": True,
        }])

        email_inst = MagicMock()
        email_inst.send_email = AsyncMock()
        wa_client = MagicMock()
        wa_client.send_text = AsyncMock()
        svc = _service(
            admin,
            email_service_factory=lambda **_kw: email_inst,
            whatsapp_client_factory=_whatsapp_factory(wa_client),
        )

        outcome = await svc.notify_new_lead(org_id=uuid4(), lead=_lead())

        assert outcome.recipients == 1
        assert outcome.attempted == 2
        assert outcome.succeeded == 2
        assert outcome.failed == 0
        email_inst.send_email.assert_awaited_once()
        wa_client.send_text.assert_awaited_once()
        channels_logged = sorted(
            p["channel"] for p in admin.inserted_payloads
            if isinstance(p, dict) and "channel" in p
        )
        assert channels_logged == ["email", "whatsapp"]
        # upload_job_id must be a real None, never the "None" string.
        assert all(p["upload_job_id"] is None for p in admin.inserted_payloads)

    @pytest.mark.asyncio
    async def test_one_channel_failing_does_not_suppress_the_other(self):
        """Two recipients on the org roster — one email-only, one
        whatsapp-only. The email send fails; the whatsapp send for the
        OTHER recipient must still be attempted and succeed."""
        admin = _MockSupabase()
        admin.set_select(data=[
            {
                "id": str(uuid4()), "name": "Broken email",
                "email": "broken@example.com", "whatsapp_number": None,
                "is_active": True,
            },
            {
                "id": str(uuid4()), "name": "WA ok",
                "email": None, "whatsapp_number": "+5511977776666",
                "is_active": True,
            },
        ])

        email_inst = MagicMock()
        email_inst.send_email = AsyncMock(
            side_effect=EmailServiceError("smtp blew up")
        )
        wa_client = MagicMock()
        wa_client.send_text = AsyncMock()
        svc = _service(
            admin,
            email_service_factory=lambda **_kw: email_inst,
            whatsapp_client_factory=_whatsapp_factory(wa_client),
        )

        outcome = await svc.notify_new_lead(org_id=uuid4(), lead=_lead())

        assert outcome.recipients == 2
        assert outcome.attempted == 2
        assert outcome.succeeded == 1
        assert outcome.failed == 1
        wa_client.send_text.assert_awaited_once()  # not suppressed

    @pytest.mark.asyncio
    async def test_per_recipient_failure_is_logged_not_raised(self):
        admin = _MockSupabase()
        admin.set_select(data=[{
            "id": str(uuid4()), "name": "Broken",
            "email": "broken@example.com", "whatsapp_number": None,
            "is_active": True,
        }])
        svc = _service(admin, smtp_user="", smtp_password="")  # SMTP unconfigured

        outcome = await svc.notify_new_lead(org_id=uuid4(), lead=_lead())

        assert outcome.failed == 1
        log_rows = [p for p in admin.inserted_payloads if isinstance(p, dict) and p.get("channel") == "email"]
        assert len(log_rows) == 1
        assert log_rows[0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_lead_message_content_is_ptbr_and_carries_lead_fields(self):
        admin = _MockSupabase()
        admin.set_select(data=[{
            "id": str(uuid4()), "name": "Ops",
            "email": "ops@example.com", "whatsapp_number": None,
            "is_active": True,
        }])
        email_inst = MagicMock()
        email_inst.send_email = AsyncMock()
        svc = _service(admin, email_service_factory=lambda **_kw: email_inst)

        lead = _lead()
        await svc.notify_new_lead(org_id=uuid4(), lead=lead)

        _, kwargs = email_inst.send_email.await_args
        assert lead["full_name"] in kwargs["subject"]
        assert lead["full_name"] in kwargs["text_body"]
        assert lead["phone"] in kwargs["text_body"]
        assert lead["form_name"] in kwargs["text_body"]
        assert lead["campaign_name"] in kwargs["text_body"]
        # pt-BR copy, not English.
        assert "Novo lead" in kwargs["text_body"]
        assert "Formulário" in kwargs["text_body"]

    @pytest.mark.asyncio
    async def test_no_active_recipients_is_honest_noop(self):
        """No active roster row on the org -> no-op: not a crash, not a
        silent success pretending it sent anything."""
        admin = _MockSupabase()
        admin.set_select(data=[])  # no active recipients on this org

        svc = _service(admin)
        outcome = await svc.notify_new_lead(org_id=uuid4(), lead=_lead())

        assert outcome.recipients == 0
        assert outcome.attempted == 0
        assert outcome.succeeded == 0
        assert outcome.failed == 0
        assert admin.inserted_payloads == []   # no log rows at all

    @pytest.mark.asyncio
    async def test_recipient_resolution_is_org_wide_not_id_scoped(self):
        """notify_new_lead has no per-lead recipient subset (unlike
        notify_upload's notify_recipients[] array) — it must fetch every
        active recipient for the org, i.e. no `in_("id", ...)` filter."""
        admin = _MockSupabase()
        admin.set_select(data=[{
            "id": str(uuid4()), "name": "Ops",
            "email": "ops@example.com", "whatsapp_number": None,
            "is_active": True,
        }])
        svc = _service(admin, email_service_factory=lambda **_kw: MagicMock(send_email=AsyncMock()))

        await svc.notify_new_lead(org_id=uuid4(), lead=_lead())

        assert any(f == ("eq", "is_active", True) for f in admin._captured_filters)
        assert not any(f[0] == "in" for f in admin._captured_filters)


# ── per-client recipient routing (migration 045) ───────────────────────────

class _RecipientAdmin:
    """Chainable double that answers the two-tier recipient query.

    `rows_by_scope` maps the marca_id filter (or None for the org-wide tier)
    to the rows returned, so a test can say "One has recipients, the org tier
    does not" and have the resolver actually experience that.
    """

    def __init__(self, rows_by_scope: dict):
        self.rows_by_scope = rows_by_scope
        self._scope = "__unset__"
        self.queried_scopes: list = []

    def schema(self, _n): return self
    def table(self, _n): return self
    def select(self, *_a, **_k): return self
    def eq(self, col, val):
        if col == "marca_id":
            self._scope = val
        return self
    def is_(self, col, _val):
        if col == "marca_id":
            self._scope = None
        return self
    def in_(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def execute(self):
        from types import SimpleNamespace
        self.queried_scopes.append(self._scope)
        rows = self.rows_by_scope.get(self._scope, [])
        self._scope = "__unset__"
        return SimpleNamespace(data=rows)


ORG = UUID("11111111-1111-1111-1111-111111111111")
ONE = "c2b77620-c550-48e1-b789-b680c7e6bb0d"
JOAO = "9d4c1b63-9899-48c0-8b93-8fabb545817c"


def _svc(admin):
    from app.services.notification_service import NotificationService
    return NotificationService(
        admin_supabase=admin, smtp_host="", smtp_port=0, smtp_user="",
        smtp_password="", waha_base_url="", waha_api_key="", waha_session="",
    )


def test_a_client_with_its_own_recipients_gets_ONLY_those():
    """🔴 The requirement: One's leads reach One's people, not João's."""
    admin = _RecipientAdmin({
        ONE: [{"id": "r-one", "name": "One contact"}],
        None: [{"id": "r-org", "name": "Org fallback"}],
    })
    rows, tier = _svc(admin).resolve_lead_recipients(org_id=ORG, marca_id=ONE)
    assert tier == "client"
    assert [r["id"] for r in rows] == ["r-one"]


def test_a_client_with_NO_recipients_falls_back_to_the_org_tier():
    """Silence is the failure mode this whole area shipped with. A client
    nobody configured must still reach somebody."""
    admin = _RecipientAdmin({ONE: [], None: [{"id": "r-org"}]})
    rows, tier = _svc(admin).resolve_lead_recipients(org_id=ORG, marca_id=ONE)
    assert tier == "org"
    assert [r["id"] for r in rows] == ["r-org"]


def test_an_UNATTRIBUTED_lead_uses_the_org_tier():
    """A lead whose Page maps to no client — the state every existing form is
    in until someone assigns it."""
    admin = _RecipientAdmin({None: [{"id": "r-org"}]})
    rows, tier = _svc(admin).resolve_lead_recipients(org_id=ORG, marca_id=None)
    assert tier == "org"
    assert [r["id"] for r in rows] == ["r-org"]
    # The client tier must not even be queried when there is no client.
    assert admin.queried_scopes == [None]


def test_the_org_tier_means_client_id_IS_NULL_not_any_client():
    """🔴 Conflating 'org-wide' with 'all recipients' would make every
    client-scoped recipient also an org-wide one — One's contact would receive
    João's leads, which is the exact bug this feature exists to prevent."""
    admin = _RecipientAdmin({
        None: [{"id": "r-org"}],
        ONE: [{"id": "r-one"}],
        JOAO: [{"id": "r-joao"}],
    })
    rows, _ = _svc(admin).resolve_lead_recipients(org_id=ORG, marca_id=None)
    assert [r["id"] for r in rows] == ["r-org"]


def test_two_clients_are_routed_independently():
    admin = _RecipientAdmin({ONE: [{"id": "r-one"}], JOAO: [{"id": "r-joao"}]})
    svc = _svc(admin)
    assert [r["id"] for r in svc.resolve_lead_recipients(
        org_id=ORG, marca_id=ONE)[0]] == ["r-one"]
    assert [r["id"] for r in svc.resolve_lead_recipients(
        org_id=ORG, marca_id=JOAO)[0]] == ["r-joao"]


def test_a_pre_migration_database_degrades_to_the_whole_roster_not_to_silence():
    """If the code deploys before migration 045, selecting `marca_id` errors.
    Alerting everyone is wrong-but-loud; alerting nobody is wrong-and-silent,
    and this feature exists because silence went unnoticed for two real leads."""
    class _NoColumn(_RecipientAdmin):
        def execute(self):
            raise RuntimeError('column "marca_id" does not exist')

    svc = _svc(_NoColumn({}))
    svc._fetch_recipients = lambda **_kw: [{"id": "everyone"}]  # the legacy path
    rows, tier = svc.resolve_lead_recipients(org_id=ORG, marca_id=ONE)
    assert [r["id"] for r in rows] == ["everyone"]


# ── Gmail as the email transport, per client (2026-08-05) ──────────────────
# SMTP was never configured on this deployment — verified unset in prod env,
# container env AND the Fernet vault — so email notifications had never once
# worked. Email now sends from the CLIENT's connected Gmail mailbox.

def _raise_unconfigured(**_kw):
    from app.services.email_service import EmailNotConfigured
    raise EmailNotConfigured("no smtp configured")


class _RecordingGmail:
    """Stands in for the seed GmailClient. Records the sends."""

    def __init__(self, fail: bool = False):
        self.sent: list[dict] = []
        self.fail = fail

    async def send_message(self, *, to, subject, body_text, body_html=None):
        if self.fail:
            raise RuntimeError("403 insufficient scope")
        self.sent.append({"to": to, "subject": subject})
        from types import SimpleNamespace
        return SimpleNamespace(message_id="m1", thread_id="t1")


def _svc_with_gmail(admin, gmail, capture=None):
    from app.services.notification_service import (
        NotificationService, _GmailEmailSender,
    )

    def factory(*, org_id, marca_id=None):
        if capture is not None:
            capture.append({"org_id": org_id, "marca_id": marca_id})
        return _GmailEmailSender(gmail, sender_label="one@example.com")

    return NotificationService(
        admin_supabase=admin, smtp_host="", smtp_port=0, smtp_user="",
        smtp_password="", waha_base_url="", waha_api_key="", waha_session="",
        gmail_sender_factory=factory,
    )


@pytest.mark.asyncio
async def test_a_lead_email_is_sent_through_the_clients_gmail_mailbox():
    admin = _MockSupabase()
    admin.set_select(data=[{
        "id": str(uuid4()), "name": "One contact",
        "email": "contact@one.com", "whatsapp_number": None, "is_active": True,
    }])
    gmail = _RecordingGmail()
    svc = _svc_with_gmail(admin, gmail)

    await svc.notify_new_lead(org_id=uuid4(), lead=_lead(), marca_id=ONE)

    assert len(gmail.sent) == 1
    assert gmail.sent[0]["to"] == "contact@one.com"


@pytest.mark.asyncio
async def test_the_SENDING_mailbox_is_selected_by_the_SAME_client_as_the_recipients():
    """🔴 The requirement. A factory that ignored `marca_id` would pass a
    naive send-test while mailing every client's leads from one mailbox —
    which is the failure this feature exists to prevent."""
    admin = _MockSupabase()
    admin.set_select(data=[{
        "id": str(uuid4()), "name": "One", "email": "c@one.com",
        "whatsapp_number": None, "is_active": True,
    }])
    seen: list[dict] = []
    svc = _svc_with_gmail(admin, _RecordingGmail(), capture=seen)

    org = uuid4()
    await svc.notify_new_lead(org_id=org, lead=_lead(), marca_id=ONE)

    assert len(seen) == 1
    assert seen[0]["marca_id"] == ONE
    assert seen[0]["org_id"] == org


@pytest.mark.asyncio
async def test_two_clients_resolve_two_different_mailboxes():
    admin = _MockSupabase()
    row = [{"id": str(uuid4()), "name": "R", "email": "r@x.com",
            "whatsapp_number": None, "is_active": True}]
    # `set_select` QUEUES one response per call — two dispatches need two.
    admin.set_select(data=row)
    admin.set_select(data=row)
    seen: list[dict] = []
    svc = _svc_with_gmail(admin, _RecordingGmail(), capture=seen)

    org = uuid4()
    await svc.notify_new_lead(org_id=org, lead=_lead(), marca_id=ONE)
    await svc.notify_new_lead(org_id=org, lead=_lead(), marca_id=JOAO)

    assert [s["marca_id"] for s in seen] == [ONE, JOAO]


@pytest.mark.asyncio
async def test_a_gmail_send_failure_is_logged_as_failed_never_raised():
    """A 403 (missing scope) or 429 (quota) must land in notification_log with
    its message — the webhook that triggered this must not see an exception."""
    admin = _MockSupabase()
    admin.set_select(data=[{
        "id": str(uuid4()), "name": "R", "email": "r@x.com",
        "whatsapp_number": None, "is_active": True,
    }])
    svc = _svc_with_gmail(admin, _RecordingGmail(fail=True))

    outcome = await svc.notify_new_lead(org_id=uuid4(), lead=_lead(), marca_id=ONE)
    assert outcome.failed >= 1
    assert outcome.succeeded == 0


@pytest.mark.asyncio
async def test_no_mailbox_falls_back_rather_than_silently_succeeding():
    """`None` from the Gmail factory must degrade to SMTP (unset here) and
    therefore to an explicit `failed` row — never to a fake that accepts the
    send and delivers nothing."""
    admin = _MockSupabase()
    admin.set_select(data=[{
        "id": str(uuid4()), "name": "R", "email": "r@x.com",
        "whatsapp_number": None, "is_active": True,
    }])
    from app.services.notification_service import NotificationService

    svc = NotificationService(
        admin_supabase=admin, smtp_host="", smtp_port=0, smtp_user="",
        smtp_password="", waha_base_url="", waha_api_key="", waha_session="",
        gmail_sender_factory=lambda **_kw: None,
        # SMTP unconfigured — exactly prod's real state.
        email_service_factory=_raise_unconfigured,
    )
    outcome = await svc.notify_new_lead(org_id=uuid4(), lead=_lead(), marca_id=ONE)
    assert outcome.succeeded == 0
    assert outcome.failed >= 1
