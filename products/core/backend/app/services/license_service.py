"""License grant/revoke — one place for the writes and their side effects.

Extracted from `app/routers/licenses.py` so the admin router and the
billing flow grant and revoke the same way.

`licenses.source` (migration 050) says who owns a license:

* `legacy`       — every license that existed before 050. Nothing automatic
                   ever touches these.
* `manual`       — granted by a platform admin in the UI.
* `subscription` — granted by the billing flow, linked by `subscription_id`.

The billing flow only ever revokes `source='subscription'` rows linked to
the subscription being ended (`revoke_subscription_licenses`). When an org
already holds an active legacy/manual license for the product, a
subscription grant does NOT create a second one (the partial unique index
forbids it anyway) and does NOT adopt the existing one — it reports
`covered_by_existing` and leaves that license exactly as it is.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

SOURCES = ("legacy", "manual", "subscription")


class LicenseConflict(RuntimeError):
    """An active license already exists for this org + product."""


@dataclass(frozen=True)
class GrantResult:
    license: dict[str, Any]
    created: bool
    reason: str  # "created" | "already_granted" | "covered_by_existing"


def _now(clock: Optional[Callable[[], datetime]]) -> datetime:
    return clock() if clock is not None else datetime.now(timezone.utc)


def grant_license(
    db: Any,
    *,
    org_id: str,
    product_id: str,
    source: str = "manual",
    subscription_id: Optional[str] = None,
    fim: Optional[str] = None,
) -> GrantResult:
    """Insert an active license, or explain why none was needed.

    Raises `LicenseConflict` for a MANUAL grant over an existing active
    license (the admin asked for something that already exists).
    """
    if source not in SOURCES or source == "legacy":
        raise ValueError(f"grant_license: source must be 'manual' or 'subscription', got {source!r}")
    if source == "subscription" and not subscription_id:
        raise ValueError("grant_license: a subscription grant needs subscription_id")

    # postgrest-unbounded-ok: the partial unique index allows ONE active license per org+product.
    existing = (
        db.table("licenses")
        .select("id, org_id, product_id, status, source, subscription_id, fim")
        .eq("org_id", org_id)
        .eq("product_id", product_id)
        .eq("status", "active")
        .execute()
        .data
        or []
    )
    if existing:
        current = existing[0]
        if source == "manual":
            raise LicenseConflict("Esta organização já possui uma licença ativa para este produto")
        if current.get("source") == "subscription" and current.get("subscription_id") == subscription_id:
            return GrantResult(current, created=False, reason="already_granted")
        logger.info(
            "license_service: org=%s product=%s already covered by %s license %s; "
            "subscription %s grants nothing",
            org_id, product_id, current.get("source"), current.get("id"), subscription_id,
        )
        return GrantResult(current, created=False, reason="covered_by_existing")

    payload: dict[str, Any] = {
        "org_id": org_id,
        "product_id": product_id,
        "status": "active",
        "source": source,
    }
    if subscription_id:
        payload["subscription_id"] = subscription_id
    if fim:
        payload["fim"] = fim
    result = db.table("licenses").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Erro ao criar licença")
    logger.info("license_service: granted org=%s product=%s source=%s", org_id, product_id, source)
    return GrantResult(result.data[0], created=True, reason="created")


def revoke_license(
    db: Any, license_id: str, *, clock: Optional[Callable[[], datetime]] = None
) -> Optional[dict[str, Any]]:
    """Admin revoke of one license (any source). None when it doesn't exist."""
    result = (
        db.table("licenses")
        .update({"status": "revoked", "fim": _now(clock).isoformat()})
        .eq("id", license_id)
        .execute()
    )
    if not result.data:
        return None
    revoked = result.data[0]
    logger.info("license_service: revoked license %s", license_id)
    invalidate_sso_sessions(db, revoked.get("org_id"))
    return revoked


def revoke_subscription_licenses(
    db: Any,
    subscription_id: str,
    *,
    clock: Optional[Callable[[], datetime]] = None,
) -> list[dict[str, Any]]:
    """Revoke the licenses THIS subscription granted — and nothing else.

    The three filters are the whole safety story: `subscription_id` (only
    this subscription's grant), `source='subscription'` (a legacy or manual
    license can never match, even if mislinked), `status='active'`
    (idempotent — a second call revokes nothing).
    """
    result = (
        db.table("licenses")
        .update({"status": "revoked", "fim": _now(clock).isoformat()})
        .eq("subscription_id", subscription_id)
        .eq("source", "subscription")
        .eq("status", "active")
        .execute()
    )
    revoked = result.data or []
    for row in revoked:
        logger.info(
            "license_service: subscription %s ended → license %s revoked", subscription_id, row.get("id")
        )
    org_ids = {row.get("org_id") for row in revoked if row.get("org_id")}
    for org_id in org_ids:
        invalidate_sso_sessions(db, org_id)
    return revoked


def invalidate_sso_sessions(db: Any, org_id: Optional[str]) -> None:
    """Flush cached SSO sessions so a revocation bites on the next refresh."""
    if not org_id:
        return
    try:
        from app.routers.sso import invalidate_sso_cache_for_org

        invalidate_sso_cache_for_org(db, org_id)
    except Exception as exc:  # noqa: BLE001 — the revoke itself already succeeded
        logger.warning("license_service: SSO cache invalidation failed for org=%s: %s", org_id, exc)


async def announce_grant(*, actor_user_id: Optional[str], license_row: dict[str, Any]) -> None:
    """Audit + team notification + outbound webhook (best-effort, logged)."""
    org_id = license_row.get("org_id")
    license_id = license_row.get("id")
    try:
        from app.services import audit_service

        await audit_service.log(
            user_id=actor_user_id, org_id=org_id,
            action="grant", resource_type="license", resource_id=license_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("license_service: grant audit log failed for license_id=%s (%s); grant succeeded", license_id, exc)
    try:
        from app.services import notification_service

        await notification_service.notify_team(
            org_id=org_id,
            type="system",
            title="Licença concedida",
            message="Uma nova licença de produto foi ativada para sua organização.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("license_service: team notification on grant failed for org=%s (%s); grant succeeded", org_id, exc)
    try:
        from app.services import webhook_delivery

        await webhook_delivery.dispatch(
            org_id=org_id,
            event_type="license.granted",
            payload={"license_id": license_id, "product_id": license_row.get("product_id")},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("license_service: webhook dispatch on grant failed for org=%s (%s); grant succeeded", org_id, exc)


async def announce_revoke(*, actor_user_id: Optional[str], license_row: dict[str, Any]) -> None:
    """Audit + outbound webhook for a revocation (best-effort, logged)."""
    org_id = license_row.get("org_id")
    license_id = license_row.get("id")
    try:
        from app.services import audit_service

        await audit_service.log(
            user_id=actor_user_id, org_id=org_id,
            action="revoke", resource_type="license", resource_id=license_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("license_service: revoke audit log failed for license_id=%s (%s); revocation succeeded", license_id, exc)
    try:
        from app.services import webhook_delivery

        if org_id:
            await webhook_delivery.dispatch(
                org_id=org_id,
                event_type="license.revoked",
                payload={"license_id": license_id},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("license_service: webhook dispatch on revoke failed for license_id=%s (%s); revocation succeeded", license_id, exc)


__all__ = [
    "GrantResult",
    "LicenseConflict",
    "SOURCES",
    "announce_grant",
    "announce_revoke",
    "grant_license",
    "invalidate_sso_sessions",
    "revoke_license",
    "revoke_subscription_licenses",
]
