"""Commerce periodic jobs (CONTRACT §2.4 / D30 / D34 / D35) -- plain functions + one registration helper.

Every job is an idempotent SWEEP over all orgs (it runs with the host's service client and filters by
status/time, not by org), safe to run twice and safe to skip a tick:

    commerce_expire_orders      hourly   past-`expires_at` `pending_payment` -> `expired` + `on_expired`
    commerce_expiry_reminders   hourly   `before_expiry` 24 h ahead, `after_expiry` 24 h after; signed, expiring
                                         `my_orders` link (never the bare order token); <= 1 mail / recipient / hour
    commerce_dispute_poll       6-hourly re-read every `disputed` order's charge (Asaas has NO "dispute lost"
                                         webhook -- a loss is only visible on the payment; W3)
    commerce_fiscal_purge       daily    `purge_expired_fiscal_retention` (D30; closes
                                         `NOC-REMEDIATE[commerce-fiscal-purge-schedule]`)

A host calls `register_commerce_jobs(register, ...)` with the seed scheduler's `register`
(`noctusai_lib.api.scheduler.register`) from its `app/scheduler.py`; the jobs themselves import no scheduler.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from noctusai_lib.integrations.email.types import EmailSender, OutgoingEmail
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from . import access_links as links
from ._common import first, now, now_iso, tbl
from .config import CommerceConfig
from .fiscal_retention import purge_expired_fiscal_retention
from .fulfillment import FulfillmentRegistry
from .money import MoneyDeps, parse_ts
from .order_charges import ensure_attempt_row, set_attempt_status
from .order_state import OrderEvent
from .orders import StaleOrder, apply_transition, list_items
from .profile import get_profile
from .reconcile import sync_order_with_gateway
from .types import ChargeAttemptStatus, OrderEventSource, OrderStatus, ReminderKind

logger = logging.getLogger(__name__)

_ORDERS = "commerce_orders"
_REMINDERS = "commerce_order_reminders"
_CUSTOMERS = "commerce_customers"
_HOSTS = "commerce_storefront_hosts"

#: The recovery link lives a week: it must outlive the reminder gap.
RECOVERY_LINK_TTL_MINUTES = 7 * 24 * 60
BEFORE_EXPIRY_WINDOW = timedelta(hours=24)
AFTER_EXPIRY_DELAY = timedelta(hours=24)
#: An `after_expiry` mail older than this is not worth sending any more.
AFTER_EXPIRY_GIVE_UP = timedelta(hours=72)
MAIL_SPACING = timedelta(hours=1)


def _scan(label: str, build: Callable[[Any], Any], db: Any) -> list[dict]:
    """Every row of a cross-org query, paged past the PostgREST cap and materialised BEFORE any write
    (writing while offset-paging shifts the window)."""
    def fetch(start: int, end: int):
        return build(db).order("id").range(start, end).execute().data

    return list(iter_paged_rows(fetch, id_key="id", label=label))


# ─── expiry ────────────────────────────────────────────────────────────────


def commerce_expire_orders(db: Any, *, fulfillment: FulfillmentRegistry, at: Optional[datetime] = None) -> int:
    """Expire every `pending_payment` order past `expires_at`. Returns how many moved."""
    moment = at or now()
    due = _scan(
        "commerce_expire_orders",
        lambda c: tbl(c, _ORDERS).select("*").eq("status", OrderStatus.PENDING_PAYMENT.value).lte("expires_at", moment.isoformat()),
        db,
    )
    count = 0
    for order in due:
        org_id = order["org_id"]
        try:
            expired = apply_transition(db, org_id, order, OrderEvent.EXPIRED, source=OrderEventSource.SYSTEM, reason="prazo de pagamento esgotado")
        except StaleOrder:
            logger.info("commerce expire sweep lost a race on order=%s (first wins)", order["id"])
            continue
        for row in ensure_attempt_row(db, org_id, order):
            if row["gateway_charge_id"] == order.get("gateway_charge_id") and row["status"] == ChargeAttemptStatus.PENDING.value:
                set_attempt_status(db, org_id, row["id"], ChargeAttemptStatus.EXPIRED)
        try:
            fulfillment.dispatch_expired(expired, list_items(db, org_id, order["id"]))
        except Exception:  # noqa: BLE001 - the order IS expired; a hook failure is reported, not fatal
            logger.error("commerce expire sweep: on_expired failed for order=%s", order["id"], exc_info=True)
        count += 1
    if count:
        logger.info("commerce_expire_orders: expired %d order(s)", count)
    return count


# ─── reminders ─────────────────────────────────────────────────────────────


def _store_base_url(db: Any, org_id: Any, cache: dict[str, Optional[str]]) -> Optional[str]:
    key = str(org_id)
    if key not in cache:
        rows = tbl(db, _HOSTS).select("*").eq("org_id", key).order("is_primary", desc=True).limit(1).execute().data or []
        cache[key] = f"https://{rows[0]['hostname']}" if rows else None
    return cache[key]


def _recently_mailed(db: Any, since: datetime) -> set[str]:
    # Bounded by design: at most one reminder per recipient per hour is ever sent, so this window is tiny
    # (the table has no `id` column to page on -- its key is (order_id, kind)).
    reminders = tbl(db, _REMINDERS).select("*").gte("sent_at", since.isoformat()).limit(1000).execute().data or []
    emails: set[str] = set()
    for rem in reminders:
        order = first(tbl(db, _ORDERS).select("customer_id").eq("org_id", str(rem["org_id"])).eq("id", str(rem["order_id"])).limit(1).execute())
        if not order:
            continue
        cust = first(tbl(db, _CUSTOMERS).select("email").eq("org_id", str(rem["org_id"])).eq("id", str(order["customer_id"])).limit(1).execute())
        if cust and cust.get("email"):
            emails.add(cust["email"])
    return emails


def _reminder_mail(kind: ReminderKind, store: str, url: str) -> tuple[str, str, str]:
    if kind is ReminderKind.BEFORE_EXPIRY:
        subject = f"Seu pedido em {store} expira em breve"
        intro = "O prazo de pagamento do seu pedido termina nas próximas 24 horas. Finalize o pagamento pelo link abaixo."
    else:
        subject = f"Seu pedido em {store} expirou — gere um novo pagamento"
        intro = "O prazo de pagamento do seu pedido terminou. Se ainda quiser a compra, gere um novo pagamento pelo link abaixo."
    text = f"{intro}\n\n{url}\n\nO link vale por 7 dias. Se você não fez essa compra, ignore esta mensagem.\n\n— {store}"
    html = f'<p>{intro}</p><p><a href="{url}">{url}</a></p><p>O link vale por 7 dias. Se você não fez essa compra, ignore esta mensagem.</p><p>— {store}</p>'
    return subject, text, html


async def commerce_expiry_reminders(
    db: Any, *, cfg: CommerceConfig, email: EmailSender, link_secret: str, at: Optional[datetime] = None
) -> int:
    """Send the due payment-recovery e-mails. Returns how many left. Idempotent on `(order, kind)`."""
    moment = at or now()
    plans: list[tuple[ReminderKind, dict]] = []
    before = _scan(
        "commerce_reminders_before",
        lambda c: tbl(c, _ORDERS).select("*").eq("status", OrderStatus.PENDING_PAYMENT.value)
        .gt("expires_at", moment.isoformat()).lte("expires_at", (moment + BEFORE_EXPIRY_WINDOW).isoformat()),
        db,
    )
    plans += [(ReminderKind.BEFORE_EXPIRY, o) for o in before]
    after = _scan(
        "commerce_reminders_after",
        lambda c: tbl(c, _ORDERS).select("*").eq("status", OrderStatus.EXPIRED.value)
        .lte("expires_at", (moment - AFTER_EXPIRY_DELAY).isoformat()).gt("expires_at", (moment - AFTER_EXPIRY_GIVE_UP).isoformat()),
        db,
    )
    plans += [(ReminderKind.AFTER_EXPIRY, o) for o in after]
    if not plans:
        return 0

    mailed = _recently_mailed(db, moment - MAIL_SPACING)
    bases: dict[str, Optional[str]] = {}
    sent = 0
    for kind, order in plans:
        org_id = order["org_id"]
        done = first(
            tbl(db, _REMINDERS).select("order_id").eq("order_id", str(order["id"])).eq("kind", kind.value).limit(1).execute()
        )
        if done:
            continue
        customer = first(tbl(db, _CUSTOMERS).select("*").eq("org_id", str(org_id)).eq("id", str(order["customer_id"])).limit(1).execute())
        if not customer or customer.get("anonymized_at") or not customer.get("email"):
            continue
        if customer["email"] in mailed:
            continue  # at most one e-mail per recipient per hour; the next tick picks this one up
        base = _store_base_url(db, org_id, bases)
        if base is None:
            logger.warning("commerce reminders: org=%s has no storefront host; no link can be built", org_id)
            continue
        # Claim first (PK = idempotency), send second; a failed send releases the claim.
        try:
            tbl(db, _REMINDERS).insert(
                {"order_id": str(order["id"]), "kind": kind.value, "org_id": str(org_id), "sent_at": now_iso()}
            ).execute()
        except Exception as exc:  # noqa: BLE001 - narrowed below
            if is_unique_violation(exc):
                continue
            raise
        token = links.sign_token(
            link_secret, purpose=links.PURPOSE_MY_ORDERS, org_id=org_id, subject=customer["id"], ttl_minutes=RECOVERY_LINK_TTL_MINUTES, at=moment
        )
        url = base + cfg.my_orders_path_template.format(token=token)
        store = (get_profile(db, org_id) or {}).get("trade_name") or "Loja"
        subject, text, html = _reminder_mail(kind, store, url)
        try:
            await email.send(OutgoingEmail(to=[customer["email"]], subject=subject, text=text, html=html))
        except Exception:  # noqa: BLE001 - release the claim so the next tick retries
            logger.error("commerce reminders: send failed for order=%s kind=%s", order["id"], kind.value, exc_info=True)
            tbl(db, _REMINDERS).delete().eq("order_id", str(order["id"])).eq("kind", kind.value).execute()
            continue
        mailed.add(customer["email"])
        sent += 1
    return sent


# ─── disputes / fiscal ─────────────────────────────────────────────────────


async def commerce_dispute_poll(db: Any, *, deps: MoneyDeps) -> int:
    """Re-read every `disputed` order against its gateway (the only way to see a lost Asaas dispute). Returns the count checked."""
    disputed = _scan(
        "commerce_dispute_poll",
        lambda c: tbl(c, _ORDERS).select("*").eq("status", OrderStatus.DISPUTED.value),
        db,
    )
    checked = 0
    for order in disputed:
        try:
            await sync_order_with_gateway(db, order["org_id"], deps, order, source=OrderEventSource.SYSTEM)
            checked += 1
        except Exception:  # noqa: BLE001 - one order's gateway failure must not stop the sweep
            logger.error("commerce_dispute_poll: order=%s could not be synced", order["id"], exc_info=True)
    return checked


def commerce_fiscal_purge(db: Any) -> int:
    """Daily D30 purge of buyer tax identity past its retention window."""
    return purge_expired_fiscal_retention(db)


# ─── registration ──────────────────────────────────────────────────────────


def register_commerce_jobs(
    register: Callable[..., None],
    *,
    cfg: CommerceConfig,
    get_db: Callable[[], Any],
    get_deps: Callable[[], MoneyDeps],
    get_link_secret: Callable[[], str],
) -> tuple[str, ...]:
    """Register the four commerce jobs on the host's scheduler. `register` is
    `noctusai_lib.api.scheduler.register` (`register(name, fn, hours=|cron=)`); the getters are called per tick,
    never captured, so a test's overridden client / a rotated secret is seen. Returns the job names."""

    async def expire() -> None:
        commerce_expire_orders(get_db(), fulfillment=get_deps().fulfillment)

    async def reminders() -> None:
        deps = get_deps()
        if deps.email is None:
            logger.warning("commerce_expiry_reminders skipped: no e-mail sender configured")
            return
        await commerce_expiry_reminders(get_db(), cfg=cfg, email=deps.email, link_secret=get_link_secret())

    async def dispute_poll() -> None:
        await commerce_dispute_poll(get_db(), deps=get_deps())

    async def fiscal_purge() -> None:
        commerce_fiscal_purge(get_db())

    register("commerce_expire_orders", expire, hours=1)
    register("commerce_expiry_reminders", reminders, hours=1)
    register("commerce_dispute_poll", dispute_poll, hours=6)
    register("commerce_fiscal_purge", fiscal_purge, cron="30 3 * * *")
    return ("commerce_expire_orders", "commerce_expiry_reminders", "commerce_dispute_poll", "commerce_fiscal_purge")


__all__ = [
    "AFTER_EXPIRY_DELAY",
    "BEFORE_EXPIRY_WINDOW",
    "MAIL_SPACING",
    "RECOVERY_LINK_TTL_MINUTES",
    "commerce_dispute_poll",
    "commerce_expire_orders",
    "commerce_expiry_reminders",
    "commerce_fiscal_purge",
    "register_commerce_jobs",
]
