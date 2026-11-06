"""Lead fan-out — contract §3 "Side effects of POST /leads" + 10-conversion-
and-leads.md § Fan-out.

Runs AFTER the lead row is committed, via FastAPI `BackgroundTasks` (so the
`201` never waits on a third party). NO e-mail is ever sent for a lead (owner
2026-11-05: "no more notifications via email for new leads"); the owner is
informed by an in-app notice to the platform org's owners/admins instead.
(`website_leads_notify_email` survives only for the owner daily brief.)
Each other channel is independently optional — an unset config value SKIPS
it with a debug log (not an error); a CONFIGURED channel that fails is caught and recorded as a `fanout_failed`
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
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

logger = logging.getLogger(__name__)


class _InAppNotifierFn(Protocol):
    """Writes the in-app lead notice; returns how many rows were written."""
    def __call__(self, lead: dict) -> int: ...


#: Admin website-leads page (core FE route `/admin/website/leads/:id`).
LEAD_LINK_PREFIX = "/admin/website/leads"


def lead_notice_text(lead: dict) -> tuple[str, str]:
    """(title, message) of the in-app notice — no contact PII beyond the name."""
    name = (lead.get("name") or "").strip() or "sem nome"
    interest = lead.get("product_interest") or []
    interest_txt = ", ".join(str(i) for i in interest) if isinstance(interest, list) else str(interest)
    message = f"Origem: {lead.get('source') or '—'} · Interesse: {interest_txt or '—'}"
    return f"Novo lead do site: {name}", message


def _default_in_app_notifier(lead: dict) -> int:
    """Real notifier: the PLATFORM org (`organizations.is_platform`) owners/admins."""
    from app.database import get_admin_client
    from noctusai_lib.domain.notifications import notify_org_admins

    db = get_admin_client()
    rows = db.table("organizations").select("id").eq("is_platform", True).limit(1).execute().data or []
    if not rows:
        raise RuntimeError("no platform organization (organizations.is_platform) to notify")
    title, message = lead_notice_text(lead)
    return notify_org_admins(
        db, org_id=rows[0]["id"], kind="lead_novo", title=title, message=message,
        produto="core", link=f"{LEAD_LINK_PREFIX}/{lead['id']}",
        entidade={"tipo": "website_lead", "id": str(lead["id"])},
    )


def _fanout_in_app(lead: dict, *, notifier: Optional[_InAppNotifierFn]) -> None:
    """In-app leg — replaces the retired e-mail leg (owner 2026-11-05).
    `notify_org_admins` never raises and returns 0 on any problem, so 0 rows
    is a failure here (recorded), not a silent skip."""
    written = (notifier or _default_in_app_notifier)(lead)
    if not written:
        raise RuntimeError("in-app lead notice wrote 0 rows (no platform owner/admin recipient or write failed)")


def _fanout_whatsapp(lead: dict, *, target: str) -> None:
    """WhatsApp leg — REMOVED (julia-line contract §A4, owner 2026-11-04).

    Core owns no WhatsApp line: the platform org has none, and sending from a
    tenant's line (e.g. Julia's number in One Consultoria) would cross tenants.
    Website-lead alerts go in-app (and the webhook) only. A still-configured
    `website_sales_whatsapp` is a stale expectation, so it is recorded as a
    loud `sem_linha_da_plataforma` failure — never a silent skip, never a send.
    """
    if not target:
        return
    raise RuntimeError(
        "sem_linha_da_plataforma: website_sales_whatsapp is set but core has no WhatsApp line; "
        "website-lead alerts go in-app/webhook only (julia-line contract §A4)"
    )


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
    in_app_notifier: Optional[_InAppNotifierFn] = None,
    webhook_sender: Any = None,
    sales_whatsapp: Optional[str] = None,
    webhook_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
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
    sales_whatsapp = _settings.website_sales_whatsapp if sales_whatsapp is None else sales_whatsapp
    webhook_url = _settings.website_leads_webhook_url if webhook_url is None else webhook_url
    webhook_secret = _settings.website_leads_webhook_secret if webhook_secret is None else webhook_secret

    if record_failure is None:
        from app.services.website_leads_service import record_fanout_failure
        record_failure = record_fanout_failure

    channels: list[tuple[str, Callable[[], Any]]] = [
        ("in_app", lambda: _sync(_fanout_in_app, lead, notifier=in_app_notifier)),
        ("whatsapp", lambda: _sync(_fanout_whatsapp, lead, target=sales_whatsapp)),
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


async def _sync(fn: Callable[..., None], *args: Any, **kwargs: Any) -> None:
    fn(*args, **kwargs)


__all__ = ["run_fanout"]
