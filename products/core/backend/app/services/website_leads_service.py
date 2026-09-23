"""Website lead intake, dedupe, and follow-up (contract §1, §3, §10).

`create_or_merge_lead` is the ONLY write path for `POST /api/website/leads`
— dedupe by `lower(email)` or `phone_e164` (email wins when both are given;
documented below, not an arbitrary silent choice) so a repeat submission
merges into the existing lead as a new `form_submit` activity instead of a
second row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import settings
from app.database import get_admin_client
from app.schemas.website import WebsiteLeadCreate
from noctusai_lib.primitives.phone import normalize_phone
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

logger = logging.getLogger(__name__)

_MUTABLE_ON_RESUBMIT = (
    "company",
    "profile",
    "product_interest",
    "message",
    "locale",
    "utm",
    "landing_path",
    "referrer",
)


class WebsiteLeadContactMissing(ValueError):
    """Neither `email` nor a phone that normalizes was submitted."""


def hash_ip(ip: Optional[str]) -> str:
    """LGPD minimization for `consent.ip_hash` (contract §1) — never store
    the raw IP. Keyed HMAC (not a bare digest) so the hash isn't trivially
    reversible against the small IPv4 address space by rainbow table; reuses
    `settings.jwt_secret` as the key rather than introducing a dedicated
    secret for a single non-authentication use. Empty/unknown IP → a fixed
    marker, never a hash of `""` (which would collide across every request
    with no client IP available, e.g. in tests)."""
    if not ip:
        return "unknown"
    return compute_hmac_sha256_hex(ip.encode("utf-8"), settings.jwt_secret or "website-ip-hash")


def _dedupe_key(email: Optional[str], phone_e164: Optional[str]) -> str:
    """`lower(email)` wins when both are present — a documented, stable
    choice (not an arbitrary one): email survives a phone-number change,
    phone doesn't survive an email typo the same way, and the contract's
    DB comment (`052_website.sql`) lists email first."""
    if email:
        return f"email:{email.strip().lower()}"
    return f"phone:{phone_e164}"


def _insert_activity(db, lead_id: str, kind: str, actor: str, payload: dict) -> dict:
    result = (
        db.table("website_lead_activities")
        .insert({"lead_id": lead_id, "kind": kind, "actor": actor, "payload": payload})
        .execute()
    )
    return result.data[0] if result.data else {}


def create_or_merge_lead(
    body: WebsiteLeadCreate, *, ip_hash: str
) -> tuple[dict, bool]:
    """Returns `(lead_row, created)`. `created=False` means an existing
    lead with the same dedupe key got a `form_submit` activity + field
    refresh instead of a new row."""
    phone_e164 = normalize_phone(body.phone) if body.phone else None
    if not body.email and not phone_e164:
        raise WebsiteLeadContactMissing(
            "at least one of email/phone is required, and the phone "
            f"submitted ({body.phone!r}) did not normalize"
        )

    dedupe_key = _dedupe_key(body.email, phone_e164)
    now_iso = datetime.now(timezone.utc).isoformat()
    consent = {
        "marketing": body.consent_marketing,
        "text_version": body.consent_text_version,
        "at": now_iso,
        "ip_hash": ip_hash,
    }

    db = get_admin_client()
    existing = (
        db.table("website_leads")
        .select("*")
        .eq("dedupe_key", dedupe_key)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    submitted_fields = {
        "company": body.company,
        "profile": body.profile,
        "product_interest": body.product_interest or [],
        "message": body.message,
        "locale": body.locale,
        "utm": body.utm or {},
        "landing_path": body.landing_path,
        "referrer": body.referrer,
    }

    if existing.data:
        lead = existing.data[0]
        update_fields = {
            k: v for k, v in submitted_fields.items() if k in _MUTABLE_ON_RESUBMIT and v not in (None, "")
        }
        if update_fields:
            updated = (
                db.table("website_leads")
                .update(update_fields)
                .eq("id", lead["id"])
                .execute()
            )
            lead = updated.data[0] if updated.data else lead
        _insert_activity(
            db, lead["id"], "form_submit", "system",
            {"source": body.source, **submitted_fields},
        )
        return lead, False

    row = {
        "source": body.source,
        "name": body.name.strip(),
        "email": body.email,
        "phone_e164": phone_e164,
        "consent": consent,
        "dedupe_key": dedupe_key,
        **submitted_fields,
    }
    inserted = db.table("website_leads").insert(row).execute()
    if not inserted.data:
        raise RuntimeError("website_leads insert returned no row")
    lead = inserted.data[0]
    _insert_activity(db, lead["id"], "created", "system", {"source": body.source})
    return lead, True


def record_fanout_failure(lead_id: str, channel: str, error: str) -> None:
    """Every fan-out failure lands here — contract: "Never silent, never
    blocks the 201." Best-effort itself: a DB write failing here is logged,
    never re-raised (the lead + its 201 must not be jeopardized by the
    ERROR-RECORDING path failing too)."""
    db = get_admin_client()
    try:
        _insert_activity(
            db, lead_id, "fanout_failed", "system", {"channel": channel, "error": error}
        )
    except Exception:
        logger.exception(
            "website lead fan-out: failed to record fanout_failed activity "
            "lead_id=%s channel=%s", lead_id, channel,
        )


def list_leads(
    *, stage: Optional[str] = None, source: Optional[str] = None,
    q: Optional[str] = None, limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    db = get_admin_client()
    query = db.table("website_leads").select("*", count="exact")
    if stage:
        query = query.eq("stage", stage)
    if source:
        query = query.eq("source", source)
    if q:
        pattern = f"%{q}%"
        query = query.or_(
            f"name.ilike.{pattern},email.ilike.{pattern},"
            f"phone_e164.ilike.{pattern},company.ilike.{pattern}"
        )
    result = (
        query.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data or [], (result.count or 0)


def get_lead_with_activities(lead_id: str) -> Optional[dict]:
    db = get_admin_client()
    lead_result = db.table("website_leads").select("*").eq("id", lead_id).execute()
    if not lead_result.data:
        return None
    lead = lead_result.data[0]
    activities = (
        db.table("website_lead_activities")
        .select("*")
        .eq("lead_id", lead_id)
        .order("at", desc=True)
        .execute()
    )
    lead["activities"] = activities.data or []
    return lead


def patch_lead(lead_id: str, updates: dict, *, actor: str) -> Optional[dict]:
    db = get_admin_client()
    existing = db.table("website_leads").select("*").eq("id", lead_id).execute()
    if not existing.data:
        return None
    before = existing.data[0]

    result = db.table("website_leads").update(updates).eq("id", lead_id).execute()
    if not result.data:
        return None
    after = result.data[0]

    if "stage" in updates and updates["stage"] != before.get("stage"):
        _insert_activity(
            db, lead_id, "stage_change", actor,
            {"from": before.get("stage"), "to": updates["stage"]},
        )
    return after


def add_activity(lead_id: str, kind: str, body: str, *, actor: str) -> Optional[dict]:
    db = get_admin_client()
    existing = db.table("website_leads").select("id").eq("id", lead_id).execute()
    if not existing.data:
        return None
    return _insert_activity(db, lead_id, kind, actor, {"body": body})


def get_stats() -> dict[str, Any]:
    db = get_admin_client()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()

    new_today = (
        db.table("website_leads").select("id", count="exact")
        .gte("created_at", today_start).execute()
    ).count or 0
    new_7d = (
        db.table("website_leads").select("id", count="exact")
        .gte("created_at", week_start).execute()
    ).count or 0

    by_source: dict[str, int] = {}
    for row in (db.table("website_leads").select("source").execute()).data or []:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1

    by_stage: dict[str, int] = {}
    for row in (db.table("website_leads").select("stage").execute()).data or []:
        by_stage[row["stage"]] = by_stage.get(row["stage"], 0) + 1

    events_7d: dict[str, int] = {}
    for row in (
        db.table("website_events").select("event").gte("at", week_start).execute()
    ).data or []:
        events_7d[row["event"]] = events_7d.get(row["event"], 0) + 1

    return {
        "new_today": new_today,
        "new_7d": new_7d,
        "by_source": by_source,
        "by_stage": by_stage,
        "events_7d": events_7d,
    }


__all__ = [
    "WebsiteLeadContactMissing",
    "add_activity",
    "create_or_merge_lead",
    "get_lead_with_activities",
    "get_stats",
    "hash_ip",
    "list_leads",
    "patch_lead",
    "record_fanout_failure",
]
