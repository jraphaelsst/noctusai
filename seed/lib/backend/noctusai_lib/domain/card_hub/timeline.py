"""The unified timeline — every kind of event on one card, newest first.

Lifted from social-wiring's `app/modules/card_hub/timeline_service.py`
(cursor codec + `get_timeline`). The gatherer DISPATCH is now a registry
(`CardHubConfig.timeline_gatherers`) rather than a module-level dict, so a
product adds its own kinds without forking the pager.

Response: `{"items": [...], "total": n, "next_cursor": str | None}` where each
item is `{id, kind, ocorrido_em, ator, **payload}` (the payload is FLATTENED —
the frontend reads `item.corpo`, never `item.payload.corpo`).

Cursor: urlsafe-base64 of `"{ocorrido_em}|{id}"`. Opaque to clients, stable
across releases — changing the encoding would invalidate every "load more"
link a client is holding. A cursor that does not decode is a typed 400
(`ValidationError_`), never a 500.

`total` counts every entry of the requested kinds, BEFORE the cursor filter —
it is the size of the whole thread, not of what is left.
"""
from __future__ import annotations

import base64
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import ValidationError_

from .config import CardHubConfig
from .services import ensure_entity

DEFAULT_LIMIT = 50


# ─── cursor codec ────────────────────────────────────────────────────────


def encode_cursor(ocorrido_em: str, entry_id: str) -> str:
    raw = f"{ocorrido_em}|{entry_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ocorrido_em, entry_id = raw.split("|", 1)
        return ocorrido_em, entry_id
    except Exception as exc:  # noqa: BLE001 — any decode failure is "bad cursor", re-raised typed
        raise ValidationError_(f"cursor inválido: {cursor!r}") from exc


def _sort_key(entry: dict) -> tuple[str, str]:
    return (entry["ocorrido_em"], entry["id"])


def all_kinds(cfg: CardHubConfig) -> set[str]:
    """The kinds this card can serve — exactly the registered gatherers."""
    return set(cfg.timeline_gatherers)


def get_timeline(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    *,
    kinds: Optional[set] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """One page of the card's thread.

    `kinds`: restricts to those kinds (unknown names are ignored — a filter
    naming only unknown kinds yields an empty page, not an error). `None` or
    empty ⇒ every registered kind.
    """
    entity = ensure_entity(cfg, db, org_id, entity_id)
    registered = all_kinds(cfg)
    requested = kinds & registered if kinds else set(registered)

    entries: list[dict] = []
    for kind, gather in cfg.timeline_gatherers.items():
        if kind in requested:
            entries.extend(gather(cfg, db, org_id, entity_id, entity))

    entries.sort(key=_sort_key, reverse=True)
    total = len(entries)

    if cursor:
        cursor_ocorrido_em, cursor_id = decode_cursor(cursor)
        entries = [
            e
            for e in entries
            if (e["ocorrido_em"], e["id"]) < (cursor_ocorrido_em, cursor_id)
        ]

    page = entries[:limit]
    next_cursor = None
    if len(entries) > limit:
        last = page[-1]
        next_cursor = encode_cursor(last["ocorrido_em"], last["id"])

    items = [
        {
            "id": e["id"],
            "kind": e["kind"],
            "ocorrido_em": e["ocorrido_em"],
            "ator": e["ator"],
            **e["payload"],
        }
        for e in page
    ]
    return {"items": items, "total": total, "next_cursor": next_cursor}


__all__ = [
    "DEFAULT_LIMIT",
    "all_kinds",
    "decode_cursor",
    "encode_cursor",
    "get_timeline",
]
