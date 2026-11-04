"""Shared notification utilities: Portuguese field mapping, and the ONE
writer every product uses for an in-app (bell) notification.

THE RULE `write_in_app` owns (2026-10-10). Core's `public.notifications`
carries `CHECK (type IN ('team_invite', 'subscription_change',
'usage_alert', 'system'))` — core's own platform events. A PRODUCT event is
`type='system'` with the product's own kind in `metadata.tipo`. igig wrote
its kinds (`automacao`, `lembrete_cliente`, …) straight into `type`; the
CHECK refused every row, so no igig notification was ever stored in
production (found by the mock's migration-derived CHECK enforcement).
social-wiring and agents had each hand-copied `type='system'`. A product
never writes `type` itself; the next one can't rediscover the CHECK.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_NOTIFICATION_FIELD_MAP_TO_PT = {
    "type": "tipo",
    "title": "titulo",
    "message": "mensagem",
    "read": "is_read",
}

_NOTIFICATION_FIELD_MAP_FROM_PT = {v: k for k, v in _NOTIFICATION_FIELD_MAP_TO_PT.items()}


def map_notification_to_pt(record: dict) -> dict:
    """Map a core notification record (English fields) to Portuguese API fields."""
    mapped = {}
    for key, value in record.items():
        pt_key = _NOTIFICATION_FIELD_MAP_TO_PT.get(key, key)
        mapped[pt_key] = value
    # Extract link from metadata (always include the key for consistency)
    meta = record.get("metadata")
    mapped["link"] = meta.get("link") if isinstance(meta, dict) else None
    return mapped


def map_notification_from_pt(data: dict) -> dict:
    """Map Portuguese API fields back to core notification record (English)."""
    mapped = {}
    for key, value in data.items():
        en_key = _NOTIFICATION_FIELD_MAP_FROM_PT.get(key, key)
        mapped[en_key] = value
    return mapped


#: `public.notifications.type` for every PRODUCT event — the one value of
#: core's CHECK that isn't one of core's own platform events.
PRODUCT_NOTIFICATION_TYPE = "system"


def in_app_rows(
    *,
    user_ids: Iterable[Any],
    kind: str,
    title: str,
    message: str,
    metadata: dict | None = None,
    org_id: Any = None,
) -> list[dict]:
    """One `public.notifications` row per DISTINCT recipient (sorted):
    `type='system'`, the product's `kind` in `metadata.tipo`. `org_id` is
    omitted when None (a platform-admin alert belongs to no org)."""
    if not kind:
        raise ValueError("a product notification needs a kind (it lands in metadata.tipo)")
    meta = {**(metadata or {}), "tipo": kind}
    rows = []
    for uid in sorted({str(u) for u in user_ids if u}):
        row = {
            "user_id": uid,
            "type": PRODUCT_NOTIFICATION_TYPE,
            "title": title,
            "message": message,
            "metadata": meta,
        }
        if org_id is not None:
            row["org_id"] = str(org_id)
        rows.append(row)
    return rows


def write_in_app(
    core_client: Any,
    *,
    user_ids: Iterable[Any],
    kind: str,
    title: str,
    message: str,
    metadata: dict | None = None,
    org_id: Any = None,
) -> int:
    """Insert one in-app notification per distinct recipient into core's
    `public.notifications`; returns how many. Zero recipients writes nothing
    (and returns 0 — the caller decides whether that's worth a warning).
    Raises on a failed insert: the CALLER decides whether a notification
    failure may fail its operation."""
    rows = in_app_rows(
        user_ids=user_ids, kind=kind, title=title, message=message,
        metadata=metadata, org_id=org_id,
    )
    if rows:
        core_client.table("notifications").insert(rows).execute()
    return len(rows)


#: Org roles that receive OPERATIONAL notices by default (owner decision
#: 2026-11-04: "lets keep admins for now"). Same set as the platform's
#: org-admin gate (`api.auth.session.scopes.ADMIN_ORG_ROLES`).
OPERATIONAL_RECIPIENT_ROLES = frozenset({"owner", "admin"})

_PAGE = 1000


def _paged(query_fn: Any) -> list[dict]:
    out: list[dict] = []
    start = 0
    while True:
        rows = query_fn(start, start + _PAGE - 1) or []
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        start += _PAGE


def resolve_org_admin_user_ids(core_client: Any, org_id: Any) -> list[str]:
    """User ids of the org's owners + admins, from the TRUSTED rows only
    (`public.noctus_users` home org + active `public.org_memberships`; never
    `user_metadata`). Sorted, distinct. Raises on a DB error — the caller
    (`notify_org_admins`) decides isolation."""
    roles = sorted(OPERATIONAL_RECIPIENT_ROLES)
    oid = str(org_id)
    home = _paged(lambda a, b: core_client.table("noctus_users").select("id")
                  .eq("org_id", oid).in_("org_role", roles).order("id").range(a, b).execute().data)
    members = _paged(lambda a, b: core_client.table("org_memberships").select("user_id")
                     .eq("org_id", oid).eq("status", "active").in_("org_role", roles)
                     .order("id").range(a, b).execute().data)
    ids = {str(r["id"]) for r in home if r.get("id")} | {
        str(r["user_id"]) for r in members if r.get("user_id")}
    return sorted(ids)


def operational_metadata(
    *, produto: str, link: str | None = None, entidade: dict | None = None, **extra: Any
) -> dict:
    """The `metadata` of an OPERATIONAL notice (KB § PATTERNS/backend/notifications.md)."""
    return {**extra, "categoria": "operacional", "link": link, "produto": produto, "entidade": entidade}


def notify_org_admins(
    core_client: Any,
    *,
    org_id: Any,
    kind: str,
    title: str,
    message: str,
    produto: str,
    link: str | None = None,
    entidade: dict | None = None,
) -> int:
    """Emit one OPERATIONAL in-app notice to the org's owners + admins.

    NEVER raises: a failed notice must not fail the lead / the sync that
    triggered it (logged at ERROR). An empty recipient set logs WARNING and
    returns 0. Returns how many rows were written."""
    try:
        recipients = resolve_org_admin_user_ids(core_client, org_id)
        if not recipients:
            logger.warning("notify_org_admins: org %s has no owner/admin recipient; %r not delivered", org_id, kind)
            return 0
        return write_in_app(
            core_client, user_ids=recipients, kind=kind, title=title[:60], message=message[:160],
            metadata=operational_metadata(produto=produto, link=link, entidade=entidade), org_id=org_id,
        )
    except Exception:  # noqa: BLE001 — emission never fails the caller
        logger.exception("notify_org_admins: %r for org %s failed; the triggering operation is unaffected", kind, org_id)
        return 0
