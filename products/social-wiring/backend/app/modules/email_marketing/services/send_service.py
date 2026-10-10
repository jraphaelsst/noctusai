"""
Core send engine — the heart of the Mailing product.

Handles: recipient resolution, send_log creation, template rendering,
Resend Batch API calls, and status tracking.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from .click_tracking import rewrite_links
from .email_optin import receives_marketing_email
from .unsubscribe_links import (
    UNSUBSCRIBE_VARIABLE,
    one_click_headers,
    unsubscribe_url,
    with_unsubscribe,
)

logger = logging.getLogger(__name__)

VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")

DRY_RUN_REASON = "dry-run: RESEND_API_KEY not configured — email NOT delivered"
UNSUBSCRIBE_REFUSAL = (
    "refused: no unsubscribe link in the rendered email — FRONTEND_BASE_URL (and "
    "JWT_SECRET) must be set so each contact's link can be built (LGPD opt-out precondition)"
)


def delivery_mode(settings) -> dict:
    """What a send will actually do right now — returned to the caller so a
    dry-run is never silent."""
    if getattr(settings, "resend_api_key", ""):
        return {"mode": "live", "reason": None}
    return {"mode": "dry_run", "reason": DRY_RUN_REASON}


async def _aexec(query):
    """Run a Supabase query's blocking `.execute()` on a worker thread.

    The supabase-py client is synchronous; calling `.execute()` from an
    async context can hang the event loop on a network or DNS failure
    (see scheduler missed-run warnings). Using `asyncio.to_thread` keeps
    the loop responsive — other scheduled jobs continue to fire even
    when one DB call is wedged.
    """
    return await asyncio.to_thread(query.execute)


class SendService:
    def __init__(self, db, settings, http_client_factory=httpx.AsyncClient):
        self.db = db
        self.settings = settings
        # Seam for tests (the Resend HTTP boundary), never for production code.
        self._http_client_factory = http_client_factory

    def queue_campaign_sends(self, campaign_id: str, org_id: str):
        """Resolve campaign recipients and create queued send_logs.

        Returns the number of sends queued.
        """
        campaign = self.db.table("campaigns").select("*").eq("id", campaign_id).execute()
        if not campaign.data:
            return 0
        campaign = campaign.data[0]

        list_id = campaign.get("list_id")
        if not list_id:
            return 0

        # Resolve contacts from list members. The send gate is
        # `receives_marketing_email`: active (not unsubscribed/bounced) AND not
        # awaiting double opt-in confirmation.
        members = (self.db.table("contact_list_members")
                   .select("contact_id, contacts(id, email, nome, empresa, status, email_optin)")
                   .eq("list_id", list_id).execute())

        contacts = []
        held = 0
        for m in (members.data or []):
            c = m.get("contacts")
            if receives_marketing_email(c):
                contacts.append(c)
            elif c and c.get("status") == "active":
                held += 1
        if held:
            logger.info("campaign %s: %d contact(s) awaiting double opt-in confirmation excluded",
                        campaign_id, held)

        if not contacts:
            return 0

        # Create send_log entries in batch
        rows = [{
            "org_id": org_id,
            "contact_id": c["id"],
            "email": c["email"],
            "campaign_id": campaign_id,
            "status": "queued",
        } for c in contacts]

        self.db.table("send_logs").insert(rows).execute()

        # Update campaign total
        self.db.table("campaigns").update({
            "total_recipients": len(rows),
        }).eq("id", campaign_id).execute()

        logger.info("Queued %d sends for campaign %s", len(rows), campaign_id)
        return len(rows)

    async def process_queued_sends(self, batch_size: int = 100):
        """Pick up queued send_logs and send via Resend Batch API.

        Called by the scheduler every 30 seconds.
        """
        result = await _aexec(
            self.db.table("send_logs").select("*, contacts(nome, empresa, email)")
            .eq("status", "queued")
            .order("created_at")
            .limit(batch_size)
        )

        logs = result.data or []
        if not logs:
            return 0

        # Group for template resolution: by campaign, or -- an automation send has no
        # campaign -- by the automation step whose config names the template.
        groups: dict = {}
        for log in logs:
            if log.get("campaign_id"):
                key = (log["campaign_id"], None)
            elif log.get("automation_step_id"):
                key = (None, log["automation_step_id"])
            else:
                key = ("none", None)
            groups.setdefault(key, []).append(log)

        total_sent = 0
        for (campaign_id, step_id), group_logs in groups.items():
            sent = await self._send_batch(campaign_id, group_logs, automation_step_id=step_id)
            total_sent += sent

        return total_sent

    async def _resolve_template_source(self, campaign_id, automation_step_id, logs):
        """``(subject, html, from_name, from_email)`` for a batch, or None when unresolvable.

        A campaign batch takes them from the campaign + its template. An automation batch
        (no campaign) takes the template from its ``send_email`` step's ``config.template_id``,
        scoped to the logs' org; the sender is the default one. Everything after this -- render,
        unsubscribe injection, guards, Resend call -- is the same path."""
        if campaign_id is None:
            step = await _aexec(self.db.table("automation_steps").select("*").eq("id", automation_step_id))
            template_id = (step.data[0].get("config") or {}).get("template_id") if step.data else None
            if not template_id:
                return None
            tpl = await _aexec(
                self.db.table("templates").select("*").eq("id", template_id).eq("org_id", logs[0].get("org_id"))
            )
            if not tpl.data:
                return None
            template = tpl.data[0]
            return (template.get("assunto", ""), template.get("corpo_html", ""),
                    self.settings.default_from_name, self.settings.default_from_email)
        campaign = await _aexec(
            self.db.table("campaigns").select("*, templates(*)").eq("id", campaign_id)
        )
        if not campaign.data:
            return None
        campaign = campaign.data[0]
        template = campaign.get("templates")
        if not template:
            return None
        return (
            campaign.get("assunto_override") or template.get("assunto", ""),
            template.get("corpo_html", ""),
            campaign.get("remetente_nome") or self.settings.default_from_name,
            campaign.get("remetente_email") or self.settings.default_from_email,
        )

    async def _send_batch(self, campaign_id: Optional[str], logs: list, automation_step_id: Optional[str] = None) -> int:
        """Send a batch of emails via Resend Batch API.

        No ``RESEND_API_KEY`` ⇒ a LOUD dry-run: WARNING + every row recorded
        ``failed`` with ``DRY_RUN_REASON`` (never "sent"). A live batch is
        refused unless each rendered email carries the contact's unsubscribe
        link — injected as a footer when the template has no
        ``{{unsubscribe_url}}`` (``unsubscribe_links``)."""
        api_key = self.settings.resend_api_key
        if not api_key:
            # LOUD, and recorded as NOT delivered — until 2026-10-10 this path
            # logged at INFO and marked every row "sent".
            logger.warning("%s — %d email(s) for campaign %s", DRY_RUN_REASON, len(logs), campaign_id)
            await self._mark_failed(logs, DRY_RUN_REASON)
            await self._finalize_campaign_if_done(campaign_id)
            return 0

        source = await self._resolve_template_source(campaign_id, automation_step_id, logs)
        if source is None:
            if campaign_id is None:  # no campaign row to retry against: record it, never loop on it
                logger.error("automation step %s: template unresolvable", automation_step_id)
                await self._mark_failed(logs, "automation template could not be resolved")
            return 0
        subject, html_body, from_name, from_email = source

        # Build batch payload
        # No real send without a per-contact opt-out link (LGPD), by construction:
        # a template without {{unsubscribe_url}} gets the footer appended, and every
        # rendered body must contain that contact's own URL — else the batch is refused.
        html_body = with_unsubscribe(html_body)
        emails = []
        for log in logs:
            contact = log.get("contacts", {})
            link = unsubscribe_url(self.settings, log.get("org_id", ""), log.get("contact_id", ""), log.get("email", ""))
            variables = {
                "nome": contact.get("nome", ""),
                "email": log.get("email", ""),
                "empresa": contact.get("empresa", ""),
                UNSUBSCRIBE_VARIABLE: link or "",
            }
            rendered_subject = self._render(subject, variables)
            rendered_body = self._render(html_body, variables)
            if not link or link not in rendered_body:
                logger.error("%s (campaign %s)", UNSUBSCRIBE_REFUSAL, campaign_id)
                await self._mark_failed(logs, UNSUBSCRIBE_REFUSAL)
                await self._finalize_campaign_if_done(campaign_id)
                return 0
            # P1b(c) click tracking: per-recipient (this send_log's id is in every
            # token); the unsubscribe link stays verbatim. The guard above already
            # proved FRONTEND_BASE_URL + JWT_SECRET are set (the link was built).
            rendered_body = rewrite_links(
                rendered_body,
                base=self.settings.frontend_base_url,
                secret=self.settings.jwt_secret,
                send_log_id=str(log["id"]),
                keep={link},
            )

            emails.append({
                "from": f"{from_name} <{from_email}>",
                "to": [log["email"]],
                "subject": rendered_subject,
                "html": rendered_body,
                "headers": one_click_headers(link),
            })

        # Call Resend Batch API
        try:
            async with self._http_client_factory() as client:
                resp = await client.post(
                    "https://api.resend.com/emails/batch",
                    json=emails,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )

            if resp.status_code == 200:
                batch_data = resp.json().get("data", [])
                await self._mark_sent(logs, batch_data=batch_data)
                logger.info("Sent batch of %d emails for campaign %s", len(logs), campaign_id)
                await self._finalize_campaign_if_done(campaign_id)
                return len(logs)
            else:
                logger.error("Resend batch API error: %s %s", resp.status_code, resp.text)
                await self._mark_failed(logs, f"Resend API {resp.status_code}")
                await self._finalize_campaign_if_done(campaign_id)
                return 0

        except Exception as e:
            logger.error("Resend batch send error: %s", e)
            await self._mark_failed(logs, str(e))
            await self._finalize_campaign_if_done(campaign_id)
            return 0

    def _render(self, text: str, variables: dict) -> str:
        def replacer(match):
            key = match.group(1)
            return str(variables.get(key, f"{{{{{key}}}}}"))
        return VARIABLE_PATTERN.sub(replacer, text)

    async def _mark_sent(self, logs: list, batch_data: list = None, dry_run: bool = False):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for i, log in enumerate(logs):
            update = {"status": "sent", "sent_at": now}
            if batch_data and i < len(batch_data):
                update["resend_message_id"] = batch_data[i].get("id")
            await _aexec(self.db.table("send_logs").update(update).eq("id", log["id"]))

        # Update campaign total_sent
        if logs:
            campaign_id = logs[0].get("campaign_id")
            if campaign_id:
                campaign = await _aexec(
                    self.db.table("campaigns").select("total_sent").eq("id", campaign_id)
                )
                if campaign.data:
                    current = campaign.data[0].get("total_sent", 0)
                    await _aexec(
                        self.db.table("campaigns").update({
                            "total_sent": current + len(logs)
                        }).eq("id", campaign_id)
                    )

    async def _mark_failed(self, logs: list, error: str):
        for log in logs:
            await _aexec(
                self.db.table("send_logs").update({
                    "status": "failed", "error_message": error
                }).eq("id", log["id"])
            )
        if logs:
            campaign_id = logs[0].get("campaign_id")
            if campaign_id:
                campaign = await _aexec(
                    self.db.table("campaigns").select("total_failed").eq("id", campaign_id)
                )
                if campaign.data:
                    current = campaign.data[0].get("total_failed", 0)
                    await _aexec(
                        self.db.table("campaigns").update({
                            "total_failed": current + len(logs)
                        }).eq("id", campaign_id)
                    )

    async def _finalize_campaign_if_done(self, campaign_id: str) -> None:
        """If no rows remain in 'queued' for this campaign, atomically flip status
        to 'enviada' and fire the campaign-debrief email. Safe to call repeatedly:
        the .neq('status', 'enviada') guard makes the flip the idempotency boundary
        — exactly one caller wins the transition; subsequent callers no-op.

        Errors during recipient resolution or debrief send are logged at WARN
        and swallowed; the campaign is finalized regardless.
        """
        if not campaign_id:
            return

        remaining = await _aexec(
            self.db.table("send_logs")
            .select("id", count="exact")
            .eq("campaign_id", campaign_id)
            .eq("status", "queued")
            .limit(1)
        )
        if (remaining.count or 0) > 0:
            return

        flipped = await _aexec(
            self.db.table("campaigns")
            .update({"status": "enviada",
                     "completed_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", campaign_id)
            .neq("status", "enviada")
        )
        if not flipped.data:
            return

        campaign_row = flipped.data[0]
        org_id = campaign_row.get("org_id")
        recipient = self._resolve_debrief_recipient(campaign_row)
        if not recipient:
            logger.warning(
                "auto_debrief_skipped_no_recipient",
                extra={"campaign_id": campaign_id, "created_by": campaign_row.get("created_by")},
            )
            return

        try:
            from app.modules.email_marketing.services.campaign_debrief_service import send_campaign_debrief
            await send_campaign_debrief(
                self.db,
                campaign_id=campaign_id,
                recipient=recipient,
                org_id=org_id,
            )
        except Exception as e:
            logger.warning(
                "auto_debrief_failed",
                extra={"campaign_id": campaign_id, "org_id": org_id, "error": str(e)},
            )

    def _resolve_debrief_recipient(self, campaign: dict) -> Optional[str]:
        """Resolve the email of the campaign creator. Returns None when missing.

        Order: explicit `debrief_recipient` field on campaign (operator override)
        → looked-up auth user email by `created_by` → None.
        """
        override = campaign.get("debrief_recipient")
        if override:
            return override

        created_by = campaign.get("created_by")
        if not created_by:
            return None

        try:
            user_lookup = self.db.auth.admin.get_user_by_id(created_by)
        except Exception as e:
            logger.warning(
                "debrief_recipient_lookup_failed",
                extra={"created_by": created_by, "error": str(e)},
            )
            return None

        user = getattr(user_lookup, "user", None)
        if user is None and isinstance(user_lookup, dict):
            user = user_lookup.get("user") or user_lookup
        return getattr(user, "email", None) if user is not None else None
