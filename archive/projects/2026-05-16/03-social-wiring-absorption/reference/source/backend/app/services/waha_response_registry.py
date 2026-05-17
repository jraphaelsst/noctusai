"""Local WAHA response-shape registry.

Stores one representative JSON payload per observed WAHA response shape in
the SQLite dev database. Runtime code should treat these samples as
diagnostics and compatibility context, not as strict contracts.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings

logger = logging.getLogger(__name__)


def record_waha_sample(
    *,
    source: str,
    direction: str,
    payload: Any,
    event_type: str | None = None,
    http_status: int | None = None,
    handling_notes: str | None = None,
) -> None:
    """Persist the first sample for each WAHA JSON structure.

    The app must never fail because sample capture failed, so this function
    is intentionally best-effort and only active for local SQLite dev mode.
    """
    if settings.database_backend.lower() != "sqlite":
        return
    if payload is None:
        return

    try:
        shape = _json_shape(payload)
        shape_json = json.dumps(shape, ensure_ascii=False, sort_keys=True)
        fingerprint = hashlib.sha256(shape_json.encode("utf-8")).hexdigest()[:16]
        sample_key = "|".join([
            source,
            direction,
            event_type or "",
            str(http_status or ""),
            fingerprint,
        ])
        sample_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        db_path = _sqlite_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO waha_response_samples (
                    id, sample_key, source, direction, event_type, http_status,
                    schema_fingerprint, schema_shape, sample_json, handling_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sample_key) DO UPDATE SET
                    observed_count = observed_count + 1,
                    last_seen_at = datetime('now')
                """,
                (
                    str(uuid4()),
                    sample_key,
                    source,
                    direction,
                    event_type,
                    http_status,
                    fingerprint,
                    shape_json,
                    sample_json,
                    handling_notes,
                ),
            )
    except Exception:
        logger.debug("failed to record WAHA response sample", exc_info=True)


def _sqlite_path() -> Path:
    path = Path(settings.sqlite_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _json_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_shape(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        if not value:
            return []
        seen: list[Any] = []
        for item in value[:5]:
            item_shape = _json_shape(item)
            if item_shape not in seen:
                seen.append(item_shape)
        return seen
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"

