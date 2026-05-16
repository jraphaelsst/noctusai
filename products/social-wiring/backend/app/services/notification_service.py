"""Notification fan-out — dispatch upload-completion alerts.

Triggered at the tail of ``upload_service.run_upload_job`` once a job
reaches ``status='published'``. Resolves recipients filtered by
(a) presence in the job's ``notify_recipients[]`` array AND
(b) ``is_active=true`` on the recipient row, then dispatches per active
channel (email + WhatsApp) and logs every attempt to ``notification_log``.

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
from typing import Any
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
    ):
        self._admin = admin_supabase
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._waha_base_url = waha_base_url
        self._waha_api_key = waha_api_key
        self._waha_session = waha_session

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

        recipients = self._fetch_recipients(
            org_id=UUID(job["org_id"]),
            recipient_ids=recipient_ids,
        )

        outcome = DispatchOutcome(recipients=len(recipients))
        if not recipients:
            return outcome

        # Build clients lazily — empty WAHA url → FakeWahaClient (logs
        # instead of sends, safe for dev). Email service raises
        # EmailNotConfigured when SMTP creds are missing; in that case
        # email channel becomes a per-log "skipped" row, not a fatal.
        email_service = self._try_build_email_service()
        whatsapp_client = self._build_whatsapp_client()

        message = self._build_message(job)

        # Dispatch per recipient × per channel. Tasks gathered in
        # parallel so a slow SMTP server doesn't serialize all sends.
        tasks: list = []
        for recipient in recipients:
            if recipient.get("email"):
                tasks.append(self._send_email_logged(
                    email_service=email_service,
                    job_id=job_id,
                    org_id=UUID(job["org_id"]),
                    recipient=recipient,
                    message=message,
                ))
            if recipient.get("whatsapp_number"):
                tasks.append(self._send_whatsapp_logged(
                    whatsapp_client=whatsapp_client,
                    job_id=job_id,
                    org_id=UUID(job["org_id"]),
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
        job_id: UUID,
        org_id: UUID,
        recipient: dict[str, Any],
        message: dict[str, str],
    ) -> bool:
        """Returns True when the send succeeded; False otherwise. Always
        writes a notification_log row (status=sent | failed)."""
        if email_service is None:
            self._log(
                job_id=job_id, org_id=org_id, recipient_id=recipient["id"],
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
                job_id=job_id, org_id=org_id, recipient_id=recipient["id"],
                channel="email", status="failed",
                error_message=str(exc),
            )
            return False
        except Exception as exc:                         # pragma: no cover
            logger.exception("unexpected email send failure")
            self._log(
                job_id=job_id, org_id=org_id, recipient_id=recipient["id"],
                channel="email", status="failed",
                error_message=f"unexpected: {exc}",
            )
            return False
        self._log(
            job_id=job_id, org_id=org_id, recipient_id=recipient["id"],
            channel="email", status="sent", error_message=None,
        )
        return True

    async def _send_whatsapp_logged(
        self,
        *,
        whatsapp_client,
        job_id: UUID,
        org_id: UUID,
        recipient: dict[str, Any],
        message: dict[str, str],
    ) -> bool:
        try:
            chat_id = chat_id_for_phone(recipient["whatsapp_number"])
            await whatsapp_client.send_text(chat_id, message["text"])
        except Exception as exc:
            self._log(
                job_id=job_id, org_id=org_id, recipient_id=recipient["id"],
                channel="whatsapp", status="failed",
                error_message=str(exc),
            )
            return False
        self._log(
            job_id=job_id, org_id=org_id, recipient_id=recipient["id"],
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
        self, *, org_id: UUID, recipient_ids: list[str]
    ) -> list[dict[str, Any]]:
        response = (
            self._admin
            .schema(_SCHEMA)
            .table(_RECIPIENTS)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("is_active", True)
            .in_("id", recipient_ids)
            .execute()
        )
        return list(response.data or [])

    def _try_build_email_service(self) -> EmailService | None:
        """Returns None when SMTP isn't configured — callers log the
        skip per-recipient rather than raising globally."""
        try:
            return EmailService(
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
        """Always returns SOMETHING — `get_whatsapp_client` falls back
        to ``FakeWahaClient`` when ``waha_base_url`` is empty (logs
        instead of sends, safe for dev)."""
        return get_whatsapp_client(
            base_url=self._waha_base_url,
            api_key=self._waha_api_key,
            session=self._waha_session,
        )

    def _build_message(self, job: dict[str, Any]) -> dict[str, str]:
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

    def _log(
        self,
        *,
        job_id: UUID,
        org_id: UUID,
        recipient_id: str,
        channel: str,
        status: str,
        error_message: str | None,
    ) -> None:
        """Insert a notification_log row. Best-effort — a logging
        failure must never tank the dispatch."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            (
                self._admin
                .schema(_SCHEMA)
                .table(_NOTIFICATION_LOG)
                .insert({
                    "org_id": str(org_id),
                    "upload_job_id": str(job_id),
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
                "(job_id=%s, recipient_id=%s, channel=%s)",
                job_id, recipient_id, channel,
            )
