"""Store-and-forward of inbound portal leads to a downstream CRM.

**The problem this solves.** Canal Pro holds ONE integration URL. When
NoctusAI takes it over from an advertiser's previous CRM, that CRM stops
being fed by Grupo OLX and starts being fed by us — and Grupo OLX treats
a lead as delivered the moment we answer 2xx, never resends it, and
offers no replay API. From the switch onward, a forward we drop is a lead
the downstream CRM never receives.

So the shape is an outbox, not a POST:

    receive → 200 to the vendor → enqueue (durable) → drain → deliver

The enqueue happens on the same durable write path as the lead itself.
The drain is the 15-minute scheduler job, so an attempt survives a
restart, a deploy, and a downstream outage longer than any in-process
retry loop could.

**Composition.** The HTTP attempt is
`noctusai_lib.integrations.outbound_webhook` (issue, classify, never
raise). The backoff schedule is `noctusai_lib.domain.jobs.retry_policy`
(`RetryPolicy` / `next_retry_at`), the same math social-wiring's
scheduling module already uses. Neither is re-implemented here; this
module is the persistence and the policy that joins them.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.jobs.retry_policy import RetryPolicy, next_retry_at
from noctusai_lib.integrations.outbound_webhook import (
    DeliveryAttempt,
    OutboundWebhookSender,
    make_outbound_webhook_sender,
)

logger = logging.getLogger(__name__)

_TARGETS = "portal_lead_forward_targets"
_FORWARDS = "portal_lead_forwards"

STATUS_PENDING = "pending"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"
STATUS_DEAD = "dead"

#: Slower and longer than an in-flight policy, because the drain is not
#: holding anyone's connection open and the thing being protected is a
#: real customer enquiry. Ten attempts over the growing backoff spans
#: roughly a day — long enough to ride out a downstream deploy or an
#: overnight outage, which is exactly the window an in-process loop
#: cannot cover.
FORWARD_RETRY_POLICY = RetryPolicy(
    max_retries=10,
    backoff_seconds=30.0,
    backoff_multiplier=2.0,
    max_backoff_seconds=3600.0,
)

#: The username half of the Grupo OLX Basic credential. The company
#: rebranded; the credential did not.
_OLX_BASIC_USERNAME = "vivareal"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ForwardTargetMisconfigured(RuntimeError):
    """A target exists but cannot produce a sendable request."""


# ─── enqueue ──────────────────────────────────────────────────────────


def active_targets(client: Any, *, org_id: UUID, provider: str) -> list[dict]:
    """Active forward destinations for one advertiser."""
    resp = (
        client.table(_TARGETS)
        .select("id, url, auth_mode, label")
        .eq("org_id", str(org_id))
        .eq("provider", provider)
        .eq("is_active", True)
        .execute()
    )
    return list(resp.data or [])


def enqueue_forwards(
    client: Any,
    *,
    org_id: UUID,
    provider: str,
    origin_lead_id: str,
    body: str,
) -> int:
    """Queue this lead for every active target. Returns rows enqueued.

    Idempotent by `(target_id, origin_lead_id)`, enforced by a UNIQUE
    constraint rather than a read-then-write: the receiver is called more
    than once for the same lead **by design** (the vendor retries and
    replays from a 14-day store), and two concurrent deliveries would
    race a check.

    Returns 0 when the advertiser has no targets — the overwhelmingly
    common case, and not an error: most orgs forward nowhere.
    """
    targets = active_targets(client, org_id=org_id, provider=provider)
    if not targets:
        return 0

    enqueued = 0
    for target in targets:
        row = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "target_id": str(target["id"]),
            "provider": provider,
            "origin_lead_id": origin_lead_id,
            "body": body,
            "status": STATUS_PENDING,
            "attempts": 0,
            "next_attempt_at": _now().isoformat(),
        }
        try:
            client.table(_FORWARDS).insert(row).execute()
            enqueued += 1
        except Exception as exc:  # noqa: BLE001
            # The expected case is the UNIQUE violation on a redelivery,
            # which means "already queued" — success, not failure. Any
            # other error is logged with the lead id so it is findable,
            # and does NOT propagate: this runs after the vendor already
            # has its 200, and raising here would only lose the lead we
            # have already stored in `olx_leads`.
            logger.warning(
                "portal-forward: enqueue skipped target=%s lead=%s (%s)",
                target.get("id"),
                origin_lead_id,
                exc,
            )
    return enqueued


# ─── one attempt ──────────────────────────────────────────────────────


def build_headers(auth_mode: str, *, webhook_secret: Optional[str]) -> dict[str, str]:
    """Headers for one forward.

    `passthrough` rebuilds the vendor's own `Authorization: Basic` from
    the secret the receiver already validates against. It is by
    construction the identical value Grupo OLX sent us, which is why the
    outbox stores no credential of its own — see migration 054.

    An unknown mode raises rather than sending an unauthenticated
    request: silently dropping the header would look like a downstream
    auth failure and send an operator hunting in the wrong system.
    """
    if auth_mode == "none":
        return {}
    if auth_mode == "passthrough":
        if not webhook_secret:
            raise ForwardTargetMisconfigured(
                "auth_mode='passthrough' needs the Grupo OLX webhook secret, "
                "which is not configured — refusing to forward unauthenticated"
            )
        token = base64.b64encode(
            f"{_OLX_BASIC_USERNAME}:{webhook_secret}".encode()
        ).decode()
        return {"Authorization": f"Basic {token}"}
    raise ForwardTargetMisconfigured(
        f"unsupported auth_mode {auth_mode!r} — supported: 'passthrough', 'none'"
    )


def _record_outcome(
    client: Any, row: dict, attempt: DeliveryAttempt, *, attempts: int
) -> str:
    """Persist one attempt's result and return the new status."""
    if attempt.succeeded:
        update = {
            "status": STATUS_DELIVERED,
            "attempts": attempts,
            "last_status_code": attempt.status_code,
            "last_error": None,
            "delivered_at": _now().isoformat(),
            # LGPD minimisation by construction: once delivered we have no
            # further use for the body. The ROW stays — it is the
            # idempotency key, and deleting it would let a vendor
            # redelivery forward the same lead a second time.
            "body": None,
        }
    elif not attempt.is_retryable:
        # The downstream understood and refused. Retrying spends a budget
        # a transient failure will need, and changes nothing.
        update = {
            "status": STATUS_FAILED,
            "attempts": attempts,
            "last_status_code": attempt.status_code,
            "last_error": (attempt.response_body or attempt.error or "")[:1000],
        }
    elif attempts > FORWARD_RETRY_POLICY.max_retries:
        update = {
            "status": STATUS_DEAD,
            "attempts": attempts,
            "last_status_code": attempt.status_code,
            "last_error": (attempt.response_body or attempt.error or "")[:1000],
        }
    else:
        update = {
            "status": STATUS_PENDING,
            "attempts": attempts,
            "last_status_code": attempt.status_code,
            "last_error": (attempt.response_body or attempt.error or "")[:1000],
            "next_attempt_at": next_retry_at(
                attempts - 1, FORWARD_RETRY_POLICY, _now()
            ).isoformat(),
        }

    client.table(_FORWARDS).update(update).eq("id", row["id"]).execute()
    return str(update["status"])


async def attempt_forward(
    client: Any,
    row: dict,
    *,
    sender: OutboundWebhookSender,
    webhook_secret: Optional[str],
    target: Optional[dict] = None,
) -> str:
    """Deliver one outbox row once. Returns its new status."""
    attempts = int(row.get("attempts") or 0) + 1

    if target is None:
        resp = (
            client.table(_TARGETS)
            .select("id, url, auth_mode, label")
            .eq("id", str(row["target_id"]))
            .limit(1)
            .execute()
        )
        rows = list(resp.data or [])
        target = rows[0] if rows else None

    if target is None:
        # The destination was deleted under us. Not retryable, and not an
        # error worth alarming on — but it must not sit `pending` forever
        # pretending it is still going somewhere.
        client.table(_FORWARDS).update(
            {"status": STATUS_FAILED, "attempts": attempts,
             "last_error": "forward target no longer exists"}
        ).eq("id", row["id"]).execute()
        return STATUS_FAILED

    body = row.get("body")
    if body is None:
        # Delivered rows have their body NULLed. Reaching here means the
        # row was resurrected to `pending` without a body, which cannot
        # be delivered and must not be retried forever.
        client.table(_FORWARDS).update(
            {"status": STATUS_FAILED, "attempts": attempts,
             "last_error": "body already cleared — nothing to forward"}
        ).eq("id", row["id"]).execute()
        return STATUS_FAILED

    try:
        headers = build_headers(
            str(target.get("auth_mode") or "passthrough"),
            webhook_secret=webhook_secret,
        )
    except ForwardTargetMisconfigured as exc:
        # Configuration, not transport. Retrying an unconfigured target
        # every 30 seconds forever would bury the real signal.
        logger.error("portal-forward: %s (target=%s)", exc, target.get("id"))
        client.table(_FORWARDS).update(
            {"status": STATUS_FAILED, "attempts": attempts, "last_error": str(exc)[:1000]}
        ).eq("id", row["id"]).execute()
        return STATUS_FAILED

    attempt = await sender.send(url=str(target["url"]), body=body, headers=headers)
    status = _record_outcome(client, row, attempt, attempts=attempts)

    if status == STATUS_DELIVERED:
        logger.info(
            "portal-forward: delivered lead=%s target=%s",
            row.get("origin_lead_id"), target.get("id"),
        )
    elif status == STATUS_DEAD:
        logger.error(
            "portal-forward: giving up on lead=%s target=%s after %d attempts — "
            "this lead will NOT reach the downstream CRM",
            row.get("origin_lead_id"), target.get("id"), attempts,
        )
    return status


# ─── the drain ────────────────────────────────────────────────────────


def due_forwards(client: Any, *, limit: int = 100) -> list[dict]:
    """Pending rows whose `next_attempt_at` has passed, oldest first."""
    resp = (
        client.table(_FORWARDS)
        .select("id, org_id, target_id, provider, origin_lead_id, body, attempts")
        .eq("status", STATUS_PENDING)
        .lte("next_attempt_at", _now().isoformat())
        .order("next_attempt_at")
        .limit(limit)
        .execute()
    )
    return list(resp.data or [])


async def drain_forwards(
    client: Any,
    *,
    webhook_secret: Optional[str],
    sender: Optional[OutboundWebhookSender] = None,
    limit: int = 100,
) -> dict[str, int]:
    """Attempt every due forward once. Returns a per-status tally.

    One pass, one attempt per row — the backoff schedule, not this loop,
    decides when a row is tried again. A loop that retried in place would
    re-introduce exactly the in-process retry this outbox replaced.
    """
    sender = sender or make_outbound_webhook_sender()
    rows = due_forwards(client, limit=limit)
    tally = {"examined": len(rows), STATUS_DELIVERED: 0, STATUS_PENDING: 0,
             STATUS_FAILED: 0, STATUS_DEAD: 0}

    for row in rows:
        try:
            status = await attempt_forward(
                client, row, sender=sender, webhook_secret=webhook_secret
            )
        except Exception as exc:  # noqa: BLE001 — one bad row must not stop the drain
            logger.warning(
                "portal-forward: row %s raised during attempt: %s",
                row.get("id"), exc, exc_info=True,
            )
            continue
        if status in tally:
            tally[status] += 1

    if tally["examined"]:
        logger.info(
            "portal-forward drain: examined=%d delivered=%d pending=%d failed=%d dead=%d",
            tally["examined"], tally[STATUS_DELIVERED], tally[STATUS_PENDING],
            tally[STATUS_FAILED], tally[STATUS_DEAD],
        )
    return tally


__all__ = [
    "FORWARD_RETRY_POLICY",
    "STATUS_DEAD",
    "STATUS_DELIVERED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "ForwardTargetMisconfigured",
    "active_targets",
    "attempt_forward",
    "build_headers",
    "drain_forwards",
    "due_forwards",
    "enqueue_forwards",
]
