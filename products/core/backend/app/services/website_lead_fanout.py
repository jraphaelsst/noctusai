"""Lead fan-out — contract §3 "Side effects of POST /leads" + 10-conversion-
and-leads.md § Fan-out.

Runs AFTER the lead row is committed, via FastAPI `BackgroundTasks` (so the
`201` never waits on a third party). Each channel is independently
optional — an unset config value SKIPS it with a debug log (not an error);
a CONFIGURED channel that fails is caught and recorded as a `fanout_failed`
activity. Never silent, never blocks the response either way.

Every collaborator AND every config value `run_fanout` reads is an
explicit keyword parameter defaulting to `app.config.settings` /
`app.services.website_leads_service.record_fanout_failure` — the DI seam
(`KB § PATTERNS/backend/di-test-seam.md`) that lets tests supply fakes and
fixed values instead of monkeypatching the settings singleton or our own
functions (both forbidden — `KB § PATTERNS/compliance/testing.md`).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, Protocol

from app.config import settings as _settings
from noctusai_lib.integrations.outbound_webhook import make_outbound_webhook_sender
from noctusai_lib.integrations.whatsapp import chat_id_for_phone, get_whatsapp_client
from noctusai_lib.primitives.phone import normalize_phone
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

logger = logging.getLogger(__name__)


class _EmailSenderFn(Protocol):
    def __call__(self, to: str, lead: dict) -> bool: ...


async def _fanout_email(lead: dict, *, to: str, sender: Optional[_EmailSenderFn]) -> None:
    if not to:
        logger.debug("website lead fan-out: email skipped (website_leads_notify_email unset)")
        return
    if sender is None:
        from app.services.email_service import send_website_lead_notification
        sender = send_website_lead_notification

    ok = sender(to, lead)
    if not ok:
        raise RuntimeError(f"email notify to {to!r} returned False (not configured or send failed)")


async def _fanout_whatsapp(
    lead: dict, *, target: str, client: Any, waha_base_url: str, waha_api_key: str, waha_session: str,
) -> None:
    if not target:
        logger.debug("website lead fan-out: whatsapp skipped (website_sales_whatsapp unset)")
        return

    phone = normalize_phone(target)
    if not phone:
        raise RuntimeError(f"website_sales_whatsapp does not normalize to E.164: {target!r}")

    if client is None:
        client = get_whatsapp_client(
            base_url=waha_base_url or None, api_key=waha_api_key or None, session=waha_session,
        )

    contact = lead.get("email") or lead.get("phone_e164") or "sem contato"
    text = (
        f"Novo lead ({lead.get('source')}) — {lead.get('name')}\n"
        f"Contato: {contact}\n"
        f"Origem: {lead.get('landing_path') or '—'}"
    )
    await client.send_text(chat_id_for_phone(phone), text)


async def _fanout_webhook(lead: dict, *, url: str, secret: str, sender: Any) -> None:
    if not url:
        logger.debug("website lead fan-out: webhook skipped (website_leads_webhook_url unset)")
        return

    if sender is None:
        sender = make_outbound_webhook_sender()

    body = json.dumps(lead, default=str, ensure_ascii=False)
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Signature"] = compute_hmac_sha256_hex(body.encode("utf-8"), secret)

    attempt = await sender.send(url=url, body=body, headers=headers)
    if not attempt.succeeded:
        raise RuntimeError(
            f"webhook delivery to {url!r} failed: status={attempt.status_code} "
            f"kind={attempt.failure_kind} error={attempt.error}"
        )


async def run_fanout(
    lead: dict,
    *,
    email_sender: Optional[_EmailSenderFn] = None,
    whatsapp_client: Any = None,
    webhook_sender: Any = None,
    notify_email: Optional[str] = None,
    sales_whatsapp: Optional[str] = None,
    webhook_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
    waha_base_url: Optional[str] = None,
    waha_api_key: Optional[str] = None,
    waha_session: Optional[str] = None,
    record_failure: Optional[Callable[[str, str, str], None]] = None,
) -> None:
    """Run every fan-out channel best-effort. Each failure is caught here
    (never propagated — this runs in a `BackgroundTasks` context with no
    caller left to see an exception) and recorded via `record_failure`
    (default `website_leads_service.record_fanout_failure`).

    Every `Optional[str]` parameter defaults to the matching
    `app.config.settings` field when omitted — production call sites pass
    nothing and get today's config; tests pass fixed values instead of
    monkeypatching `settings`."""
    notify_email = _settings.website_leads_notify_email if notify_email is None else notify_email
    sales_whatsapp = _settings.website_sales_whatsapp if sales_whatsapp is None else sales_whatsapp
    webhook_url = _settings.website_leads_webhook_url if webhook_url is None else webhook_url
    webhook_secret = _settings.website_leads_webhook_secret if webhook_secret is None else webhook_secret
    waha_base_url = _settings.waha_base_url if waha_base_url is None else waha_base_url
    waha_api_key = _settings.waha_api_key if waha_api_key is None else waha_api_key
    waha_session = _settings.waha_session if waha_session is None else waha_session

    if record_failure is None:
        from app.services.website_leads_service import record_fanout_failure
        record_failure = record_fanout_failure

    channels: list[tuple[str, Callable[[], Any]]] = [
        ("email", lambda: _fanout_email(lead, to=notify_email, sender=email_sender)),
        ("whatsapp", lambda: _fanout_whatsapp(
            lead, target=sales_whatsapp, client=whatsapp_client,
            waha_base_url=waha_base_url, waha_api_key=waha_api_key, waha_session=waha_session,
        )),
        ("webhook", lambda: _fanout_webhook(lead, url=webhook_url, secret=webhook_secret, sender=webhook_sender)),
    ]
    for channel, call in channels:
        try:
            await call()
        except Exception as exc:  # noqa: BLE001 — best-effort by contract; every failure is recorded, never dropped
            logger.warning(
                "website lead fan-out: channel=%s failed lead_id=%s error=%s",
                channel, lead.get("id"), exc,
            )
            record_failure(lead["id"], channel, str(exc))


__all__ = ["run_fanout"]
