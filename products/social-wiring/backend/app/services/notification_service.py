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


class _GmailEmailSender:
    """Adapts a seed `GmailClient` to `EmailService`'s send signature.

    Exists so `_send_email_logged` stays transport-agnostic: it already knows
    how to call `send_email(to=, subject=, html_body=, text_body=)` and how to
    turn an `EmailServiceError` into a `failed` log row. Wrapping here means
    swapping SMTP → Gmail changed the TRANSPORT and nothing about the
    per-recipient error containment that surrounds it.

    Gmail failures are re-raised as `EmailServiceError` for exactly that
    reason — a 403 (missing scope) or 429 (quota) must land in
    `notification_log` with its message, not escape as an unhandled type the
    caller has no branch for.
    """

    def __init__(self, gmail: Any, *, sender_label: str | None = None) -> None:
        self._gmail = gmail
        #: The mailbox mail is sent FROM. Gmail derives the actual `From:`
        #: header from the authenticated account, so this is for logging and
        #: diagnostics only — it is never used to forge a sender.
        self.sender_label = sender_label

    async def send_email(
        self, *, to: str, subject: str, html_body: str, text_body: str
    ) -> None:
        try:
            await self._gmail.send_message(
                to=to, subject=subject, body_text=text_body, body_html=html_body
            )
        except Exception as exc:  # noqa: BLE001
            raise EmailServiceError(
                f"gmail send failed (from={self.sender_label or '?'}): {exc}"
            ) from exc


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
        gmail_sender_factory: "Callable[..., Any] | None" = None,
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
        # DI seam for the Gmail transport. Signature is
        # ``(org_id=, marca_id=) -> sender | None`` so a test can assert
        # WHICH marca's mailbox was asked for — the per-marca routing is
        # the point of this feature, and a factory that ignored marca_id
        # would pass a naive test while sending every marca's mail from one
        # mailbox.
        self._gmail_sender_factory: "Callable[..., Any] | None" = (
            gmail_sender_factory
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
        self, *, org_id: UUID, lead: dict[str, Any], marca_id: Any = None
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
        recipients, tier = self.resolve_lead_recipients(
            org_id=org_id, marca_id=marca_id
        )
        if not recipients:
            # 🔴 NOT a quiet no-op. A lead just arrived and there is nobody
            # to tell — which is a CONFIGURATION gap, not a non-event, and it
            # is invisible from every other angle: the lead lands correctly in
            # the CRM, no error is raised, and the absence of a WhatsApp
            # message looks identical to "no leads today".
            #
            # Observed in production 2026-08-04: two real leads arrived and
            # neither alerted anyone, because `notification_recipients` was
            # empty. Nothing in the logs said so. WARNING, not INFO, because
            # the operator is silently losing the alerting they asked for.
            logger.warning(
                "notify_new_lead: lead %s arrived for org %s (client=%s, tier=%s) "
                "but NO active notification recipient is configured — nobody was "
                "alerted. Add one under Configuração → Configurações "
                "(notifications); a client-scoped recipient covers just that "
                "client, an org-wide one covers everything unattributed.",
                lead.get("id"), org_id, marca_id or "—", tier,
            )
            return DispatchOutcome()

        message = self._build_lead_message(lead)
        return await self._dispatch(
            kind="lead",
            org_id=org_id,
            recipients=recipients,
            message=message,
            # Selects the SENDING mailbox, mirroring the tier that selected
            # the recipients — so One's leads are sent from One's Gmail to
            # One's people, and João's from João's.
            marca_id=marca_id,
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
        marca_id: Any = None,
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
        # Email transport, in preference order:
        #   1. the CLIENT's connected Gmail mailbox — mail arrives from a real
        #      address the recipient recognises, and each client sends from its
        #      own account, so One's leads never appear to come from João's.
        #   2. SMTP, if it is configured.
        # SMTP has never actually been configured on this deployment (verified
        # 2026-08-05: unset in prod env, container env and the Fernet vault),
        # which is why email notifications had never worked. Gmail is now the
        # real transport; SMTP stays as the fallback rather than being ripped
        # out, because removing a configured-elsewhere path is a separate
        # decision from adding this one.
        email_service = self._try_build_gmail_sender(
            org_id=org_id, marca_id=marca_id
        ) or self._try_build_email_service()
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
                error_message=(
                    "no email transport: no connected Gmail mailbox for this "
                    "client (Configuração → Integrações) and SMTP unset"
                ),
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

    def resolve_lead_recipients(
        self, *, org_id: UUID, marca_id: Any = None
    ) -> tuple[list[dict[str, Any]], str]:
        """Who to alert about a lead, resolved by client with an org fallback.

        Two tiers, and the order between them is the whole design:

        1. **Client tier** — active recipients whose ``marca_id`` matches the
           client this lead belongs to. If the client has any, they are the
           ONLY recipients: a client with its own roster must not also reach
           the org-wide fallback, or "One's leads go to One" quietly becomes
           "One's leads go to One *and* everyone else".
        2. **Org tier** (``marca_id IS NULL``) — used when the lead resolves
           to no client, or to a client that has no active recipient of its
           own. This tier is what stops an unattributed lead from alerting
           nobody, which is the exact silent failure this area shipped with.

        Returns ``(recipients, tier)`` — the tier is returned rather than
        inferred by the caller because "0 recipients" needs different wording
        depending on whether a client was resolved at all, and a caller
        guessing that would get it wrong.
        """
        if marca_id:
            client_rows = self._fetch_recipients_scoped(
                org_id=org_id, marca_id=str(marca_id)
            )
            if client_rows:
                return client_rows, "client"
        return self._fetch_recipients_scoped(org_id=org_id, marca_id=None), "org"

    def _fetch_recipients_scoped(
        self, *, org_id: UUID, marca_id: str | None
    ) -> list[dict[str, Any]]:
        """Active recipients for one tier. ``marca_id=None`` selects the
        org-wide rows (``marca_id IS NULL``), NOT "any client" — the two
        readings differ and conflating them would make every client-scoped
        recipient also an org-wide one."""
        query = (
            self._admin
            .schema(_SCHEMA)
            .table(_RECIPIENTS)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("is_active", True)
        )
        query = (
            query.is_("marca_id", "null") if marca_id is None
            else query.eq("marca_id", marca_id)
        )
        try:
            return list(query.execute().data or [])
        except Exception:  # noqa: BLE001
            # Pre-migration-045 databases have no such column at all; 045
            # shipped it as `client_id` and 046 renamed it `marca_id`. Degrade
            # to the org-wide roster rather than alerting nobody: a deploy that
            # lands before its migration must not silence alerts.
            logger.warning(
                "notification recipients: client scoping unavailable (is "
                "migration 045 applied?) — falling back to the whole roster"
            )
            return self._fetch_recipients(org_id=org_id)

    def _try_build_gmail_sender(self, *, org_id: UUID, marca_id: Any = None):
        """The client's connected Gmail mailbox as an email transport.

        Returns an object exposing the same ``send_email(...)`` signature as
        ``EmailService`` so the per-recipient send path is untouched — the
        transport swap is invisible below this line.

        ``None`` when no usable mailbox exists (not connected, no refresh
        token, missing send scope, GCP app unconfigured). Each of those is
        logged with its specific cause by ``build_gmail_client_for``; the
        caller then falls back to SMTP and, failing that, writes a `failed`
        notification_log row. At no point does a send silently succeed.
        """
        if self._gmail_sender_factory is not None:
            return self._gmail_sender_factory(org_id=org_id, marca_id=marca_id)
        try:
            from app.config import settings
            from app.services.account_credentials import build_gmail_client_for

            gmail, sender = build_gmail_client_for(
                self._admin, settings, org_id=org_id, marca_id=marca_id
            )
            if gmail is None:
                return None
            return _GmailEmailSender(gmail, sender_label=sender)
        except Exception:  # noqa: BLE001 — never let transport selection raise
            logger.exception(
                "notification: could not build a Gmail sender for org=%s "
                "client=%s; falling back to SMTP",
                org_id, marca_id,
            )
            return None

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


# ─── construction ───────────────────────────────────────────────────────────
#: The seven channel-credential attributes every caller has to forward.
_CHANNEL_ATTRS = (
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "waha_base_url",
    "waha_api_key",
    "waha_session",
)


def build_notification_service(
    admin_supabase: Any, source: Any = None, **overrides: Any
) -> NotificationService:
    """Construct a :class:`NotificationService` from a credential source.

    Formalized at N=3 per the recurrence rule: the YouTube upload router
    passed an org-scoped ``cfg``, ``whatsapp_intake_service`` passed the
    global ``settings``, and the Meta leadgen receiver was about to become
    the third hand-rolled copy of the same seven-keyword call. All three
    sources expose the same attribute names, which is precisely why the
    duplication was invisible — and why a new channel credential would have
    had to be threaded through every call site by hand.

    ``source`` defaults to the global ``settings``; pass an org-scoped config
    object to keep per-org credentials. ``overrides`` forwards the DI seams
    (``email_service_factory`` / ``whatsapp_client_factory``) untouched.
    """
    if source is None:
        from app.config import settings as source  # noqa: PLC0415

    creds = {name: getattr(source, name) for name in _CHANNEL_ATTRS}
    return NotificationService(admin_supabase=admin_supabase, **creds, **overrides)
