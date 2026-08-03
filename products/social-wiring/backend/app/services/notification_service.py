"""Notification fan-out — dispatch alerts across email + WhatsApp.

Two entry points share one channel fan-out core (:meth:`_dispatch`):

- ``notify_upload`` — triggered at the tail of
  ``upload_service.run_upload_job`` once a job reaches
  ``status='published'``. Recipients are the subset of the org's roster
  named in the job's ``notify_recipients[]`` array.
- ``notify_new_lead`` — triggered by the Meta leadgen webhook receiver
  right after it upserts a lead row. Recipients are EVERY active row on
  the org's roster (there's no per-lead opt-in subset like uploads have).

Both paths filter recipients on ``is_active=true`` on the recipient row,
then dispatch per active channel (email + WhatsApp) and log every
attempt to ``notification_log``.

Channel selection is per-recipient: a recipient with both ``email`` +
``whatsapp_number`` gets BOTH channels fired; one with just email gets
just email. The ``CHECK (email IS NOT NULL OR whatsapp_number IS NOT NULL)``
constraint on the recipients table guarantees at least one channel is
viable, but per-message channel-availability (e.g. WAHA disconnected)
is captured per-log-row.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from noctusai_lib.integrations.whatsapp import (
    chat_id_for_phone,
    get_whatsapp_client,
)

from app.services.email_service import (
    EmailNotConfigured,
    EmailService,
    EmailServiceError,
)

logger = logging.getLogger(__name__)

_NOTIFICATION_LOG = "notification_log"
_RECIPIENTS = "notification_recipients"
_SCHEMA = "social_wiring"


class NotificationServiceError(Exception):
    """Raised when fan-out cannot proceed (bad job_id, missing tables).
    Per-recipient/channel failures are NOT raised — they're logged to
    ``notification_log`` so the dashboard can surface the partial failure
    pattern without one bad address tanking the whole dispatch."""


@dataclass
class DispatchOutcome:
    """What :meth:`NotificationService.notify_upload` returns to the
    upload pipeline. Counts let the caller decide whether to flip the
    job row to ``status='notified'`` (any success) or leave at
    ``status='published'`` (all failures or no recipients selected)."""

    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    recipients: int = 0  # how many recipient ROWS were addressed


class NotificationService:
    """Per-request collaborator. Constructed from the service-role
    Supabase admin client (writes go through service-role because the
    background worker has no JWT context — same rationale as
    ``UploadService._update_status``).

    Email + WhatsApp clients are constructed lazily per dispatch call
    so a missing-config in one channel doesn't disable the other.
    """

    def __init__(
        self,
        *,
        admin_supabase,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        waha_base_url: str,
        waha_api_key: str,
        waha_session: str,
        email_service_factory: "Callable[..., EmailService] | None" = None,
        whatsapp_client_factory: "Callable[..., Any] | None" = None,
    ):
        self._admin = admin_supabase
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._waha_base_url = waha_base_url
        self._waha_api_key = waha_api_key
        self._waha_session = waha_session
        # DI seam for the SMTP wrapper. Defaults to the real ``EmailService``
        # class; tests inject a fake factory through the kwarg instead of
        # ``patch("...notification_service.EmailService")``. Per
        # ``KB § PATTERNS/di-test-seam.md`` (Class-C — service-factory DI).
        self._email_service_factory: "Callable[..., EmailService]" = (
            email_service_factory or EmailService
        )
        # DI seam for the WAHA client. Deliberately left NOT captured with
        # an eager ``or get_whatsapp_client`` default here — the existing
        # ``notify_upload`` test suite patches the module-level
        # ``get_whatsapp_client`` symbol (``patch("...notification_service
        # .get_whatsapp_client")``), which only takes effect on a NAME
        # LOOKED UP AT CALL TIME, not a reference captured at construction.
        # ``_build_whatsapp_client`` resolves the default lazily so both
        # seams stay live: pass a factory explicitly (new ``notify_new_lead``
        # tests) or rely on the patchable module global (existing tests).
        self._whatsapp_client_factory: "Callable[..., Any] | None" = (
            whatsapp_client_factory
        )

    async def notify_upload(self, *, job_id: UUID) -> DispatchOutcome:
        """Fan-out alerts for a published upload job.

        Returns a :class:`DispatchOutcome` with per-channel counts. Never
        raises for per-recipient failures — those become log rows. Raises
        :class:`NotificationServiceError` only when the job can't be
        loaded or recipients can't be resolved (catastrophic, not
        per-message).
        """
        job = self._fetch_job(job_id)
        if job is None:
            raise NotificationServiceError(
                f"upload_jobs row not found for job_id={job_id}"
            )

        recipient_ids = [str(r) for r in (job.get("notify_recipients") or [])]
        if not recipient_ids:
            # Honest no-op: the job opted out of notifications. Don't
            # log empty rows; just return.
            return DispatchOutcome()

        org_id = UUID(job["org_id"])
        recipients = self._fetch_recipients(
            org_id=org_id,
            recipient_ids=recipient_ids,
        )
        message = self._build_upload_message(job)
        return await self._dispatch(
            kind="upload",
            org_id=org_id,
            recipients=recipients,
            message=message,
            upload_job_id=job_id,
        )

    async def notify_new_lead(
        self, *, org_id: UUID, lead: dict[str, Any]
    ) -> DispatchOutcome:
        """Fan-out an alert for a freshly-upserted Meta lead.

        Called by the Meta leadgen webhook receiver right after it
        upserts the lead row — ``lead`` is the row dict the caller
        already holds (this method never re-queries Meta or Postgres for
        it). Expected keys mirror the ``meta_ads_leads`` row shape (see
        ``app/modules/meta_ads/services/leads_sync_service.py``):
        ``full_name``, ``phone``, ``email``, ``form_name``,
        ``campaign_name``, ``created_time`` (ISO-8601 string) — all
        individually optional, matching the nullable columns upstream.

        Recipients: EVERY active row in ``notification_recipients`` for
        the org. Unlike ``notify_upload``, there is no per-lead subset
        selection to resolve (``upload_jobs.notify_recipients[]`` has no
        lead-side equivalent) — the org's always-on recipient roster is
        the sensible org-level stand-in. If a per-recipient "notify me on
        leads but not uploads" toggle is ever needed, that's a new
        ``notify_on`` column on ``notification_recipients``, not
        something this method should invent silently.

        Never raises for per-recipient failures (same contract as
        ``notify_upload``) — a slow SMTP server or a down WAHA session
        must not surface as an exception here, since the webhook receiver
        calling this must not turn that into a non-2xx to Meta.
        """
        recipients = self._fetch_recipients(org_id=org_id)
        if not recipients:
            # Honest no-op: no active recipient on this org's roster.
            # Don't log empty rows; just return.
            return DispatchOutcome()

        message = self._build_lead_message(lead)
        return await self._dispatch(
            kind="lead",
            org_id=org_id,
            recipients=recipients,
            message=message,
        )

    # ─── Reusable fan-out core ──────────────────────────────────────────
    async def _dispatch(
        self,
        *,
        kind: str,
        org_id: UUID,
        recipients: list[dict[str, Any]],
        message: dict[str, str],
        upload_job_id: UUID | None = None,
    ) -> DispatchOutcome:
        """Channel fan-out shared by every notification entry point.

        Owns lazy per-channel client construction, per-recipient error
        containment (a failure becomes a ``notification_log`` row, never
        an exception), and dispatch counting. ``kind`` (e.g. "upload" |
        "lead") is a label for diagnostic log messages only — the
        ``notification_log`` schema has no per-kind column yet;
        ``upload_job_id`` stays the only structured link back to a
        triggering row and is ``None`` for non-upload callers.
        """
        outcome = DispatchOutcome(recipients=len(recipients))
        if not recipients:
            return outcome

        # Build clients lazily — empty WAHA url → FakeWahaClient (logs
        # instead of sends, safe for dev). Email service raises
        # EmailNotConfigured when SMTP creds are missing; in that case
        # email channel becomes a per-log "skipped" row, not a fatal.
        email_service = self._try_build_email_service()
        whatsapp_client = self._build_whatsapp_client()

        # Dispatch per recipient × per channel. Tasks gathered in
        # parallel so a slow SMTP server doesn't serialize all sends.
        tasks: list = []
        for recipient in recipients:
            if recipient.get("email"):
                tasks.append(self._send_email_logged(
                    email_service=email_service,
                    upload_job_id=upload_job_id,
                    org_id=org_id,
                    recipient=recipient,
                    message=message,
                    kind=kind,
                ))
            if recipient.get("whatsapp_number"):
                tasks.append(self._send_whatsapp_logged(
                    whatsapp_client=whatsapp_client,
                    upload_job_id=upload_job_id,
                    org_id=org_id,
                    recipient=recipient,
                    message=message,
                ))

        outcome.attempted = len(tasks)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) or result is False:
                outcome.failed += 1
            else:
                outcome.succeeded += 1
        return outcome

    # ─── Per-channel dispatch (always log; never raise) ────────────────
    async def _send_email_logged(
        self,
        *,
        email_service: EmailService | None,
        upload_job_id: UUID | None,
        org_id: UUID,
        recipient: dict[str, Any],
        message: dict[str, str],
        kind: str = "upload",
    ) -> bool:
        """Returns True when the send succeeded; False otherwise. Always
        writes a notification_log row (status=sent | failed)."""
        if email_service is None:
            self._log(
                upload_job_id=upload_job_id, org_id=org_id,
                recipient_id=recipient["id"],
                channel="email", status="failed",
                error_message="SMTP not configured (.env: SMTP_USER / SMTP_PASSWORD)",
            )
            return False
        try:
            await email_service.send_email(
                to=recipient["email"],
                subject=message["subject"],
                html_body=message["html"],
                text_body=message["text"],
            )
        except EmailServiceError as exc:
            self._log(
                upload_job_id=upload_job_id, org_id=org_id,
                recipient_id=recipient["id"],
                channel="email", status="failed",
                error_message=str(exc),
            )
            return False
        except Exception as exc:                         # pragma: no cover
            logger.exception("unexpected email send failure (kind=%s)", kind)
            self._log(
                upload_job_id=upload_job_id, org_id=org_id,
                recipient_id=recipient["id"],
                channel="email", status="failed",
                error_message=f"unexpected: {exc}",
            )
            return False
        self._log(
            upload_job_id=upload_job_id, org_id=org_id,
            recipient_id=recipient["id"],
            channel="email", status="sent", error_message=None,
        )
        return True

    async def _send_whatsapp_logged(
        self,
        *,
        whatsapp_client,
        upload_job_id: UUID | None,
        org_id: UUID,
        recipient: dict[str, Any],
        message: dict[str, str],
    ) -> bool:
        try:
            chat_id = chat_id_for_phone(recipient["whatsapp_number"])
            await whatsapp_client.send_text(chat_id, message["text"])
        except Exception as exc:
            self._log(
                upload_job_id=upload_job_id, org_id=org_id,
                recipient_id=recipient["id"],
                channel="whatsapp", status="failed",
                error_message=str(exc),
            )
            return False
        self._log(
            upload_job_id=upload_job_id, org_id=org_id,
            recipient_id=recipient["id"],
            channel="whatsapp", status="sent", error_message=None,
        )
        return True

    # ─── Internals ─────────────────────────────────────────────────────
    def _fetch_job(self, job_id: UUID) -> dict[str, Any] | None:
        response = (
            self._admin
            .schema(_SCHEMA)
            .table("upload_jobs")
            .select("*")
            .eq("id", str(job_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    def _fetch_recipients(
        self, *, org_id: UUID, recipient_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Active recipients for the org. ``recipient_ids=None`` (the
        ``notify_new_lead`` path) returns EVERY active row on the org's
        roster; a list (the ``notify_upload`` path) narrows to that
        per-job subset — same query, same filters, the ``.in_()`` leg is
        just conditional."""
        query = (
            self._admin
            .schema(_SCHEMA)
            .table(_RECIPIENTS)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("is_active", True)
        )
        if recipient_ids is not None:
            query = query.in_("id", recipient_ids)
        response = query.execute()
        return list(response.data or [])

    def _try_build_email_service(self) -> EmailService | None:
        """Returns None when SMTP isn't configured — callers log the
        skip per-recipient rather than raising globally."""
        try:
            return self._email_service_factory(
                smtp_host=self._smtp_host,
                smtp_port=self._smtp_port,
                smtp_user=self._smtp_user,
                smtp_password=self._smtp_password,
            )
        except EmailNotConfigured:
            logger.info(
                "email channel disabled: SMTP creds missing — recipients with "
                "an email address will get a per-log failure row"
            )
            return None

    def _build_whatsapp_client(self):
        """Always returns SOMETHING — the resolved factory (explicit DI
        seam, else the module-level ``get_whatsapp_client``) falls back
        to ``FakeWahaClient`` when ``waha_base_url`` is empty (logs
        instead of sends, safe for dev). The default lookup happens HERE
        (not captured in ``__init__``) so ``patch("...notification_
        service.get_whatsapp_client")`` in the existing test suite keeps
        working — see the constructor comment."""
        factory = self._whatsapp_client_factory or get_whatsapp_client
        return factory(
            base_url=self._waha_base_url,
            api_key=self._waha_api_key,
            session=self._waha_session,
        )

    def _build_upload_message(self, job: dict[str, Any]) -> dict[str, str]:
        """Compose the notification body — a small dict with subject /
        html / text. Templating stays inline for Phase 4; promote to
        a Jinja2 template module if a 2nd notification type ships.

        Enriched with property code + listing URL (from
        ``settings.listing_url_template``) so the recipient gets a
        one-click path to the listing alongside the YT URL."""
        from app.config import settings

        title = job.get("title") or "Untitled video"
        video_id = job.get("youtube_video_id")
        product_code = job.get("product_code") or ""
        url = (
            f"https://www.youtube.com/watch?v={video_id}"
            if video_id else "https://www.youtube.com"
        )
        listing_url = ""
        if product_code and settings.listing_url_template:
            try:
                listing_url = settings.listing_url_template.format(code=product_code)
            except (KeyError, IndexError):
                listing_url = ""

        subject = (
            f"[Social Wiring] Novo video publicado: {title}"
            + (f" ({product_code})" if product_code else "")
        )
        text_lines = [f"🎬 Novo video publicado: {title}", f"📺 {url}"]
        if listing_url:
            text_lines.append(f"📋 Anúncio: {listing_url}")
        text_lines.extend(["", "Enviado pelo Social Wiring."])
        text = "\n".join(text_lines)

        listing_html = (
            f"<p style='margin:0 0 12px'><a href='{listing_url}' "
            f"style='color:#2563eb;text-decoration:none'>📋 Anúncio do imóvel</a></p>"
            if listing_url else ""
        )
        html = (
            "<div style='font-family:sans-serif;max-width:560px'>"
            f"<h2 style='margin:0 0 8px'>🎬 Novo video publicado</h2>"
            f"<h3 style='margin:0 0 12px;font-weight:500'>{title}</h3>"
            f"<p style='margin:0 0 16px'>"
            f"<a href='{url}' style='display:inline-block;padding:10px 16px;"
            f"background:#cc0000;color:#fff;text-decoration:none;border-radius:6px'>"
            f"Assistir no YouTube</a></p>"
            f"{listing_html}"
            "<p style='color:#888;font-size:12px;margin:24px 0 0'>"
            "Enviado pelo Social Wiring.</p>"
            "</div>"
        )
        return {"subject": subject, "html": html, "text": text}

    def _build_lead_message(self, lead: dict[str, Any]) -> dict[str, str]:
        """Compose the new-lead notification body — pt-BR copy, same
        subject/html/text shape as :meth:`_build_upload_message`.

        ``lead`` is the ``meta_ads_leads`` row shape (see
        ``app/modules/meta_ads/services/leads_sync_service.py``):
        ``full_name``, ``phone``, ``email``, ``form_name``,
        ``campaign_name``, ``created_time`` — every field individually
        optional, so every line degrades to a generic label rather than
        raising on a missing key."""
        name = lead.get("full_name") or "Lead sem nome"
        phone = lead.get("phone") or "sem telefone"
        email = lead.get("email")
        form_name = lead.get("form_name") or "formulário não identificado"
        campaign_name = lead.get("campaign_name")
        when = self._format_lead_time(lead.get("created_time"))

        subject = f"[Social Wiring] Novo lead: {name}"

        text_lines = [f"🎯 Novo lead recebido: {name}", f"📞 {phone}"]
        if email:
            text_lines.append(f"✉️ {email}")
        text_lines.append(f"📝 Formulário: {form_name}")
        if campaign_name:
            text_lines.append(f"📢 Campanha: {campaign_name}")
        text_lines.append(f"🕐 Recebido em: {when}")
        text_lines.extend(["", "Enviado pelo Social Wiring."])
        text = "\n".join(text_lines)

        email_html = (
            f"<p style='margin:0 0 4px'>✉️ {email}</p>" if email else ""
        )
        campaign_html = (
            f"<p style='margin:0 0 4px'>📢 Campanha: {campaign_name}</p>"
            if campaign_name else ""
        )
        html = (
            "<div style='font-family:sans-serif;max-width:560px'>"
            "<h2 style='margin:0 0 8px'>🎯 Novo lead recebido</h2>"
            f"<h3 style='margin:0 0 12px;font-weight:500'>{name}</h3>"
            f"<p style='margin:0 0 4px'>📞 {phone}</p>"
            f"{email_html}"
            f"<p style='margin:0 0 4px'>📝 Formulário: {form_name}</p>"
            f"{campaign_html}"
            f"<p style='margin:0 0 16px'>🕐 Recebido em: {when}</p>"
            "<p style='color:#888;font-size:12px;margin:24px 0 0'>"
            "Enviado pelo Social Wiring.</p>"
            "</div>"
        )
        return {"subject": subject, "html": html, "text": text}

    def _format_lead_time(self, created_time: str | None) -> str:
        """Best-effort human-readable timestamp for ``created_time`` (an
        ISO-8601 string per ``leads_sync_service._iso``). Falls back to
        the raw value on an unexpected format — this is alert copy, not
        a structured field, so it must never raise."""
        if not created_time:
            return "agora"
        try:
            dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, AttributeError):
            return created_time

    def _log(
        self,
        *,
        upload_job_id: UUID | None,
        org_id: UUID,
        recipient_id: str,
        channel: str,
        status: str,
        error_message: str | None,
    ) -> None:
        """Insert a notification_log row. Best-effort — a logging
        failure must never tank the dispatch. ``upload_job_id`` is None
        for non-upload callers (e.g. ``notify_new_lead``) — the column is
        nullable; NEVER stringify a None into the literal ``"None"``."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            (
                self._admin
                .schema(_SCHEMA)
                .table(_NOTIFICATION_LOG)
                .insert({
                    "org_id": str(org_id),
                    "upload_job_id": (
                        str(upload_job_id) if upload_job_id is not None else None
                    ),
                    "recipient_id": recipient_id,
                    "channel": channel,
                    "status": status,
                    "error_message": error_message,
                    "sent_at": now if status == "sent" else None,
                })
                .execute()
            )
        except Exception:
            logger.exception(
                "notification_log insert failed for "
                "(upload_job_id=%s, recipient_id=%s, channel=%s)",
                upload_job_id, recipient_id, channel,
            )
