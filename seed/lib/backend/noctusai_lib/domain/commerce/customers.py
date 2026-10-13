"""Customers -- per-org buyers (NOT `noctus_users`), consents, privacy requests.

Buyers are guest checkouts: one `commerce_customers` row per `(org_id, email)`.
Per-field PROVENANCE lives in `field_sources` (`{field: {source, at, verified}}`)
and drives the enrichment rule (CONTRACT §2, D26):

    payment (3) > staff (2) > form (1)

A value is written only when its source's priority is >= the stored source's, so
a confirmed payment's name/doc/email/phone/address overwrite what the buyer typed
(`verified=true`), a staff edit beats a later form value, and **a later `form`
value never downgrades a `payment` field**. `merge_customer_fields` is the one
pure function that decides it -- checkout and the webhook both call it.

LGPD: `export_customer` (portability/access) and `anonymize_customer` (deletion)
are staff acts triggered by a VERIFIED request; anonymization scrubs PII from the
customer row and the consents' ip/user-agent but keeps order rows and amounts
(commercial/fiscal records).
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import in_batched_rows, paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import digits, first, get_row, like_term, new_id, now_iso, page_rows, tbl
from .errors import not_found
from .types import ConsentKind, FieldSource, PrivacyRequestKind, PrivacyRequestStatus

logger = logging.getLogger(__name__)

_CUSTOMERS = "commerce_customers"
_CONSENTS = "commerce_consents"
_PRIVACY = "commerce_privacy_requests"
_ORDERS = "commerce_orders"
_ITEMS = "commerce_order_items"
_EVENTS = "commerce_order_events"

#: Customer columns subject to provenance (email is also the identity key).
FIELDS: tuple[str, ...] = ("name", "doc", "email", "phone", "address")

#: Higher wins. Equal priority overwrites (latest form / latest payment wins).
PRIORITY: dict[str, int] = {
    FieldSource.FORM.value: 1,
    FieldSource.STAFF.value: 2,
    FieldSource.PAYMENT.value: 3,
}


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == {}


def _normalize_incoming(incoming: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in FIELDS:
        value = incoming.get(field)
        if field == "email" and isinstance(value, str):
            value = normalize_email(value)
        elif field in ("doc", "phone") and isinstance(value, str):
            value = digits(value)
        elif field == "name" and isinstance(value, str):
            value = value.strip()
        if not _empty(value):
            out[field] = value
    return out


def merge_customer_fields(
    existing: Optional[Mapping[str, Any]],
    incoming: Mapping[str, Any],
    source: FieldSource | str,
    *,
    at: str,
    skip_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Column updates to apply for `incoming` data of `source` -- `{}` when nothing changes.

    Pure: the caller persists. The returned dict holds the changed field values
    plus the complete merged `field_sources`.
    """
    src = FieldSource(source).value
    pri = PRIORITY[src]
    current_sources = dict((existing or {}).get("field_sources") or {})
    new_sources = dict(current_sources)
    changes: dict[str, Any] = {}
    for field, value in _normalize_incoming(incoming).items():
        if field in skip_fields:
            continue
        cur_value = (existing or {}).get(field)
        meta = current_sources.get(field) or {}
        cur_pri = PRIORITY.get(meta.get("source", FieldSource.FORM.value), 1) if not _empty(cur_value) else 0
        if _empty(cur_value) or pri >= cur_pri:
            if cur_value != value:
                changes[field] = value
            if cur_value != value or meta.get("source") != src or bool(meta.get("verified")) != (src == FieldSource.PAYMENT.value):
                new_sources[field] = {"source": src, "at": at, "verified": src == FieldSource.PAYMENT.value}
    if new_sources != current_sources:
        changes["field_sources"] = new_sources
    return changes


def find_by_email(db: Any, org_id: Any, email: str) -> Optional[dict]:
    resp = (
        tbl(db, _CUSTOMERS).select("*").eq("org_id", str(org_id)).eq("email", normalize_email(email)).limit(1).execute()
    )
    return first(resp)


def upsert_buyer(db: Any, org_id: Any, buyer: Mapping[str, Any], *, source: FieldSource = FieldSource.FORM) -> dict:
    """Create the customer for `buyer['email']` or enrich the existing one."""
    at = now_iso()
    email = normalize_email(buyer["email"])
    existing = find_by_email(db, org_id, email)
    if existing is None:
        data = _normalize_incoming({**buyer, "email": email})
        sources = {
            field: {"source": source.value, "at": at, "verified": source is FieldSource.PAYMENT} for field in data
        }
        row = {
            "id": new_id(),
            "org_id": str(org_id),
            "email": email,
            "name": data.get("name", ""),
            "doc": data.get("doc"),
            "phone": data.get("phone"),
            "address": data.get("address") or {},
            "field_sources": sources,
            "created_at": at,
            "updated_at": at,
        }
        try:
            return first(tbl(db, _CUSTOMERS).insert(row).execute()) or row
        except Exception as exc:  # noqa: BLE001 - a concurrent first checkout for the same buyer
            if not is_unique_violation(exc):
                raise
            existing = find_by_email(db, org_id, email)
            if existing is None:
                raise
    changes = merge_customer_fields(existing, {**buyer, "email": email}, source, at=at, skip_fields=("email",))
    if not changes:
        return existing
    changes["updated_at"] = at
    updated = tbl(db, _CUSTOMERS).update(changes).eq("org_id", str(org_id)).eq("id", str(existing["id"])).execute()
    return first(updated) or {**existing, **changes}


def enrich_from_payment(db: Any, org_id: Any, customer_id: Any, gateway_data: Mapping[str, Any]) -> dict:
    """Apply a confirmed payment's customer data (`source=payment, verified=true`).

    The e-mail is the customer's identity key: it is only replaced when no OTHER
    customer of the org already owns the gateway's e-mail (otherwise two buyers
    would merge); a skipped e-mail is logged, never silent.
    """
    customer = get_row(db, _CUSTOMERS, org_id, customer_id)
    if customer is None:
        raise not_found("Cliente")
    skip: tuple[str, ...] = ()
    gateway_email = normalize_email(str(gateway_data.get("email") or ""))
    if gateway_email and gateway_email != customer["email"]:
        other = find_by_email(db, org_id, gateway_email)
        if other is not None and str(other["id"]) != str(customer["id"]):
            logger.warning("commerce enrichment: gateway e-mail already belongs to another customer; keeping the form e-mail")
            skip = ("email",)
    at = now_iso()
    changes = merge_customer_fields(customer, gateway_data, FieldSource.PAYMENT, at=at, skip_fields=skip)
    if not changes:
        return customer
    changes["updated_at"] = at
    updated = tbl(db, _CUSTOMERS).update(changes).eq("org_id", str(org_id)).eq("id", str(customer_id)).execute()
    return first(updated) or {**customer, **changes}


def get_customer(db: Any, org_id: Any, customer_id: Any) -> dict:
    row = get_row(db, _CUSTOMERS, org_id, customer_id)
    if row is None:
        raise not_found("Cliente")
    return row


def list_customers(
    db: Any, org_id: Any, *, q: Optional[str] = None, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int, int, int]:
    if not (q and q.strip()):
        return page_rows(db, _CUSTOMERS, org_id, page=page, page_size=page_size)
    # Search = e-mail OR name. Two bounded ilike reads merged by id (an OR filter
    # string would interpolate user text into the PostgREST filter grammar).
    pat = like_term(q)
    merged: dict[str, dict] = {}
    for column in ("email", "name"):
        resp = (
            tbl(db, _CUSTOMERS)
            .select("*")
            .eq("org_id", str(org_id))
            .ilike(column, pat)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        for row in resp.data or []:
            merged[str(row["id"])] = dict(row)
    rows = sorted(merged.values(), key=lambda r: str(r.get("created_at", "")), reverse=True)
    page_n = max(1, page)
    size = max(1, min(page_size, 200))
    return rows[(page_n - 1) * size : page_n * size], len(rows), page_n, size


# ─── consents ────────────────────────────────────────────────────────────


def record_consents(
    db: Any,
    org_id: Any,
    customer_id: Any,
    *,
    order_id: Optional[Any],
    entries: list[tuple[ConsentKind, str, bool]],
    ip: Optional[str],
    user_agent: Optional[str],
) -> list[dict]:
    """Append one consent row per `(kind, version, granted)` (never updates)."""
    at = now_iso()
    rows = [
        {
            "id": new_id(),
            "org_id": str(org_id),
            "customer_id": str(customer_id),
            "order_id": str(order_id) if order_id else None,
            "kind": kind.value,
            "version": version,
            "granted": bool(granted),
            "ip": ip,
            "user_agent": (user_agent or "")[:300] or None,
            "at": at,
        }
        for kind, version, granted in entries
    ]
    if rows:
        tbl(db, _CONSENTS).insert(rows).execute()
    return rows


def list_consents(db: Any, org_id: Any, customer_id: Any) -> list[dict]:
    rows = paged_rows(db, _CONSENTS, org_id, eq_filters={"customer_id": str(customer_id)})
    return sorted(rows, key=lambda r: str(r.get("at", "")), reverse=True)


# ─── privacy requests ────────────────────────────────────────────────────


def create_privacy_request(
    db: Any, org_id: Any, customer_id: Any, kind: PrivacyRequestKind, details: Optional[str]
) -> dict:
    row = {
        "id": new_id(),
        "org_id": str(org_id),
        "customer_id": str(customer_id),
        "kind": kind.value,
        "status": PrivacyRequestStatus.OPEN.value,
        "details": details,
        "verified_at": None,
        "created_at": now_iso(),
        "resolved_at": None,
    }
    return first(tbl(db, _PRIVACY).insert(row).execute()) or row


def verify_privacy_request(db: Any, org_id: Any, request_id: Any) -> dict:
    """The e-mailed link was followed: `open -> verified`. A `revoke_consent`
    request is fully actionable by itself, so it also withdraws marketing consent
    and closes as `done`."""
    row = get_row(db, _PRIVACY, org_id, request_id)
    if row is None:
        raise not_found("Solicitação")
    if row["status"] != PrivacyRequestStatus.OPEN.value:
        return row
    at = now_iso()
    patch: dict[str, Any] = {"status": PrivacyRequestStatus.VERIFIED.value, "verified_at": at}
    if row["kind"] == PrivacyRequestKind.REVOKE_CONSENT.value:
        record_consents(
            db, org_id, row["customer_id"], order_id=None,
            entries=[(ConsentKind.MARKETING, "revoked", False)], ip=None, user_agent=None,
        )
        patch.update({"status": PrivacyRequestStatus.DONE.value, "resolved_at": at})
    updated = tbl(db, _PRIVACY).update(patch).eq("org_id", str(org_id)).eq("id", str(request_id)).execute()
    return first(updated) or {**row, **patch}


def list_privacy_requests(db: Any, org_id: Any, customer_id: Any) -> list[dict]:
    rows = paged_rows(db, _PRIVACY, org_id, eq_filters={"customer_id": str(customer_id)})
    return sorted(rows, key=lambda r: str(r.get("created_at", "")), reverse=True)


# ─── staff views: detail, export, anonymize ──────────────────────────────


def customer_detail(db: Any, org_id: Any, customer_id: Any) -> dict:
    customer = get_customer(db, org_id, customer_id)
    orders = paged_rows(db, _ORDERS, org_id, eq_filters={"customer_id": str(customer_id)})
    orders.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return {
        **customer,
        "orders": orders,
        "consents": list_consents(db, org_id, customer_id),
        "privacy_requests": list_privacy_requests(db, org_id, customer_id),
    }


def export_customer(db: Any, org_id: Any, customer_id: Any) -> dict:
    """Everything held about the customer (LGPD art. 18 access/portability)."""
    detail = customer_detail(db, org_id, customer_id)
    orders = detail["orders"]
    order_ids = [str(o["id"]) for o in orders]
    items = in_batched_rows(db, _ITEMS, org_id, "order_id", order_ids)
    events = in_batched_rows(db, _EVENTS, org_id, "order_id", order_ids)
    for order in orders:
        oid = str(order["id"])
        order["items"] = [i for i in items if str(i["order_id"]) == oid]
        order["events"] = sorted((e for e in events if str(e["order_id"]) == oid), key=lambda e: str(e.get("at", "")))
    return {"exported_at": now_iso(), "customer": {k: v for k, v in detail.items() if k not in ("orders", "consents", "privacy_requests")},
            "orders": orders, "consents": detail["consents"], "privacy_requests": detail["privacy_requests"]}


def anonymize_customer(db: Any, org_id: Any, customer_id: Any) -> dict:
    """Scrub the customer's PII (idempotent). Orders/amounts are kept: they are
    commercial records; the link from them to a person is what is cut."""
    customer = get_customer(db, org_id, customer_id)
    if customer.get("anonymized_at"):
        return customer
    at = now_iso()
    cid = str(customer_id)
    patch = {
        "name": "Cliente anonimizado",
        "email": f"anon-{cid}@anonymized.invalid",
        "doc": None,
        "phone": None,
        "address": {},
        "field_sources": {},
        "anonymized_at": at,
        "updated_at": at,
    }
    updated = tbl(db, _CUSTOMERS).update(patch).eq("org_id", str(org_id)).eq("id", cid).execute()
    tbl(db, _CONSENTS).update({"ip": None, "user_agent": None}).eq("org_id", str(org_id)).eq("customer_id", cid).execute()
    for request in list_privacy_requests(db, org_id, customer_id):
        if request["kind"] == PrivacyRequestKind.DELETION.value and request["status"] in (
            PrivacyRequestStatus.OPEN.value, PrivacyRequestStatus.VERIFIED.value,
        ):
            tbl(db, _PRIVACY).update(
                {"status": PrivacyRequestStatus.DONE.value, "resolved_at": at}
            ).eq("org_id", str(org_id)).eq("id", str(request["id"])).execute()
    return first(updated) or {**customer, **patch}


__all__ = [
    "FIELDS",
    "PRIORITY",
    "anonymize_customer",
    "create_privacy_request",
    "customer_detail",
    "enrich_from_payment",
    "export_customer",
    "find_by_email",
    "get_customer",
    "list_consents",
    "list_customers",
    "list_privacy_requests",
    "merge_customer_fields",
    "normalize_email",
    "record_consents",
    "upsert_buyer",
    "verify_privacy_request",
]
