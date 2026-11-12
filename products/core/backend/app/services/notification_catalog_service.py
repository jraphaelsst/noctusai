"""Notificações — the owner's view of every owner-facing notification the products send, and its on/off switch.

Reads/writes core `public.notification_kinds` (each product's declared kinds, upserted by the product at runtime)
and reads `public.notification_sends` (one row per dispatch decision). Migration core 117;
seed side `noctusai_lib.domain.notification_catalog`.

The products cache the switch for up to 60 s (`SWITCH_TTL_SECONDS`), so a toggle takes effect within a minute —
the page says so instead of pretending it is instant.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from noctusai_lib.domain.notification_catalog import KINDS_TABLE, SEND_STATUSES, SENDS_TABLE

STATS_WINDOW = timedelta(days=30)
#: The platform shell is not a `products` row but sends owner notices of its own (skill-scout); always on the roster.
PLATFORM_PRODUCT = "core"
_SENDS_PAGE = 1000
_SENDS_MAX = 20000


class KindNotFound(LookupError):
    """No catalog row for (product, kind)."""


def _blank_counts() -> dict[str, int]:
    return {s: 0 for s in SEND_STATUSES}


def live_roster(db: Any) -> list[str]:
    """Slugs of every product that runs in prod (`ativo` + `deploy_scope='live'`) plus the platform shell.

    The page lists these even while they declare no kinds, so "this product has no owner notification" is something
    the owner SEES, not a product that silently vanished from the page."""
    rows = db.table("products").select("slug, ativo, deploy_scope").execute().data or []
    slugs = {r["slug"] for r in rows if r.get("slug") and r.get("ativo") and r.get("deploy_scope") == "live"}
    return sorted(slugs | {PLATFORM_PRODUCT})


def list_catalog(db: Any, now: datetime) -> dict:
    """Every declared kind grouped by product (plus every live product, empty when it declares none), with
    30-day counts per status and the last dispatch."""
    kinds = db.table(KINDS_TABLE).select("*").order("product").order("kind").execute().data or []
    since = (now - STATS_WINDOW).isoformat()
    sends: list[dict] = []
    offset = 0
    while offset < _SENDS_MAX:
        page = (
            db.table(SENDS_TABLE).select("product, kind, status, created_at").gte("created_at", since)
            .order("created_at", desc=True).range(offset, offset + _SENDS_PAGE - 1).execute().data or []
        )
        sends.extend(page)
        if len(page) < _SENDS_PAGE:
            break
        offset += _SENDS_PAGE
    stats: dict[tuple[str, str], dict] = {}
    for row in sends:  # newest first
        key = (row["product"], row["kind"])
        entry = stats.setdefault(key, {"counts": _blank_counts(), "last": None, "last_sent_at": None})
        if row.get("status") in entry["counts"]:
            entry["counts"][row["status"]] += 1
        if entry["last"] is None:
            entry["last"] = {"status": row.get("status"), "at": row.get("created_at")}
        if entry["last_sent_at"] is None and row.get("status") in ("sent", "partial"):
            entry["last_sent_at"] = row.get("created_at")

    products: dict[str, list[dict]] = {slug: [] for slug in live_roster(db)}
    for k in kinds:
        s = stats.get((k["product"], k["kind"]), {"counts": _blank_counts(), "last": None, "last_sent_at": None})
        products.setdefault(k["product"], []).append({
            "product": k["product"],
            "kind": k["kind"],
            "titulo": k.get("titulo"),
            "descricao": k.get("descricao"),
            "gatilho": k.get("gatilho"),
            "canais": k.get("canais") or [],
            "enabled": bool(k.get("enabled", True)),
            "toggled_at": k.get("toggled_at"),
            "registered_at": k.get("registered_at"),
            "last_seen_at": k.get("last_seen_at"),
            "counts_30d": s["counts"],
            "last_dispatch": s["last"],
            "last_sent_at": s["last_sent_at"],
        })
    return {
        "window_days": STATS_WINDOW.days,
        "sends_truncated": len(sends) >= _SENDS_MAX,
        "products": [
            {
                "product": p,
                "kinds": rows,
                "enabled_count": sum(1 for r in rows if r["enabled"]),
                "total": len(rows),
                "declared": bool(rows),
            }
            for p, rows in sorted(products.items())
        ],
    }


def set_enabled(db: Any, *, product: str, kind: Optional[str], enabled: bool, user_id: Optional[str], now: datetime) -> int:
    """Flip one kind (``kind`` given) or every kind of a product. Returns how many rows changed state or matched."""
    patch = {"enabled": bool(enabled), "toggled_at": now.isoformat(), "toggled_by": user_id}
    query = db.table(KINDS_TABLE).update(patch).eq("product", product)
    if kind is not None:
        query = query.eq("kind", kind)
    rows = query.execute().data or []
    if not rows:
        raise KindNotFound(f"{product}/{kind}" if kind else product)
    return len(rows)


def list_sends(db: Any, *, product: Optional[str], kind: Optional[str], limit: int) -> list[dict]:
    query = db.table(SENDS_TABLE).select("*")
    if product:
        query = query.eq("product", product)
    if kind:
        query = query.eq("kind", kind)
    return query.order("created_at", desc=True).limit(limit).execute().data or []


__all__ = ["KindNotFound", "PLATFORM_PRODUCT", "STATS_WINDOW", "live_roster", "list_catalog", "list_sends", "set_enabled"]
