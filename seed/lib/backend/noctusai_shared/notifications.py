"""Shared notification utilities for Portuguese field mapping."""
from __future__ import annotations

NOTIFICATION_FIELD_MAP_TO_PT = {
    "type": "tipo",
    "title": "titulo",
    "message": "mensagem",
    "read": "is_read",
}

NOTIFICATION_FIELD_MAP_FROM_PT = {v: k for k, v in NOTIFICATION_FIELD_MAP_TO_PT.items()}


def map_notification_to_pt(record: dict) -> dict:
    """Map a core notification record (English fields) to Portuguese API fields."""
    mapped = {}
    for key, value in record.items():
        pt_key = NOTIFICATION_FIELD_MAP_TO_PT.get(key, key)
        mapped[pt_key] = value
    # Extract link from metadata (always include the key for consistency)
    meta = record.get("metadata")
    mapped["link"] = meta.get("link") if isinstance(meta, dict) else None
    return mapped


def map_notification_from_pt(data: dict) -> dict:
    """Map Portuguese API fields back to core notification record (English)."""
    mapped = {}
    for key, value in data.items():
        en_key = NOTIFICATION_FIELD_MAP_FROM_PT.get(key, key)
        mapped[en_key] = value
    return mapped
