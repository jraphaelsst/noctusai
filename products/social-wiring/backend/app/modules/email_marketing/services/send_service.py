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

logger = logging.getLogger(__name__)

VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


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
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    def queue_campaign_sends(self, campaign_id: str, org_id: str):
        """Resolve campaign recipients and create queued send_logs.

        Returns the number of sends queued.
        """
        campaign = self.db.table("campaigns").select("*").eq("id", campaign_id).execute()
        if not campaign.data:
            return 0
        campaign = campaign.data[0]

        # Get list contacts (only active, not unsubscribed/bounced)
        list_id = campaign.get("list_id")
        if not list_id:
            return 0

        # Resolve contacts from list members
        members = (self.db.table("contact_list_members")
                   .select("contact_id, contacts(id, email, nome, empresa, status)")
                   .eq("list_id", list_id).execute())

        contacts = []
        for m in (members.data or []):
            c = m.get("contacts")
            if c and c.get("status") == "active":
                contacts.append(c)

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

        # Group by campaign for template resolution
        by_campaign = {}
        for log in logs:
            cid = log.get("campaign_id") or "none"
            by_campaign.setdefault(cid, []).append(log)

        total_sent = 0
        for campaign_id, campaign_logs in by_campaign.items():
            sent = await self._send_batch(campaign_id, campaign_logs)
            total_sent += sent

        return total_sent

    async def _send_batch(self, campaign_id: str, logs: list) -> int:
        """Send a batch of emails via Resend Batch API.

        ``resend_api_key`` / ``default_from_name`` / ``default_from_email``
        are mailing-era settings not (yet) declared on
        ``SocialWiringSettings`` (seed ``ProductSettings`` is
        ``extra="ignore"``). ``getattr(..., default)`` keeps the existing
        dry-run-when-unconfigured behaviour instead of raising
        ``AttributeError`` from the scheduler thread. Add these fields to
        SocialWiringSettings to enable real sending (recommended config
        delta in the return)."""
        api_key = getattr(self.settings, "resend_api_key", "")
        if not api_key:
            logger.info("No RESEND_API_KEY — logging %d emails (dry run)", len(logs))
            await self._mark_sent(logs, dry_run=True)
            await self._finalize_campaign_if_done(campaign_id)
            return len(logs)

        # Resolve campaign template
        campaign = await _aexec(
            self.db.table("campaigns").select("*, templates(*)").eq("id", campaign_id)
        )
        if not campaign.data:
            return 0
        campaign = campaign.data[0]
        template = campaign.get("templates")
        if not template:
            return 0

        subject = campaign.get("assunto_override") or template.get("assunto", "")
        html_body = template.get("corpo_html", "")
        from_name = campaign.get("remetente_nome") or getattr(
            self.settings, "default_from_name", "NoctusAI"
        )
        from_email = campaign.get("remetente_email") or getattr(
            self.settings, "default_from_email", "noreply@noctusai.com"
        )

        # Build batch payload
        emails = []
        for log in logs:
            contact = log.get("contacts", {})
            variables = {
                "nome": contact.get("nome", ""),
                "email": log.get("email", ""),
                "empresa": contact.get("empresa", ""),
            }
            rendered_subject = self._render(subject, variables)
            rendered_body = self._render(html_body, variables)

            emails.append({
                "from": f"{from_name} <{from_email}>",
                "to": [log["email"]],
                "subject": rendered_subject,
                "html": rendered_body,
            })

        # Call Resend Batch API
        try:
            async with httpx.AsyncClient() as client:
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
