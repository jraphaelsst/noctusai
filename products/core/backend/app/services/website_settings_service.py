"""Website settings — versioned config the public site + the website HTML
serving middleware both read.

Contract: `products/core/frontend/src/website/docs/15-api-contract.md` §2.

- **Version 0 = the FE build's defaults.** `website_settings` starts empty;
  the FE's `src/website/content/defaults.ts` is emitted at build time to
  `SERVE_SPA_DIR/_site/settings.defaults.json`. When no row exists yet,
  this module reads that file and reports it as version 0. It never
  invents a default in Python — a missing file at that point is a real
  build/deploy problem and raises `WebsiteDefaultsMissing` loudly instead
  of silently serving `{}`.
- **30s in-process cache**, invalidated on every write (`update`,
  `rollback`) in the SAME process. A multi-worker deploy has one cache per
  worker — a write on worker A can serve worker B a stale read for up to
  30s, which is the same tradeoff `SERVE_SPA_DIR` manifest caching already
  accepts platform-wide (see `website_html.py`).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from app.database import get_admin_client
from app.schemas.website import WebsiteSettings
from app.services.website_paths import get_spa_dir

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30.0

# {"expires_at": float, "version": int, "data": dict} | None
_cache: Optional[dict] = None


class WebsiteDefaultsMissing(RuntimeError):
    """`website_settings` has no rows AND the FE-built defaults file is
    absent. Never invented in Python — see module docstring."""


class WebsiteVersionConflict(RuntimeError):
    """`expected_version` didn't match the current version at write time."""


class WebsiteSocialProofEmpty(RuntimeError):
    """`sections.social_proof` is True but `social_proof_items` is empty."""


def _defaults_path() -> Path:
    return get_spa_dir() / "_site" / "settings.defaults.json"


def _load_defaults() -> dict:
    path = _defaults_path()
    if not path.is_file():
        raise WebsiteDefaultsMissing(
            f"website_settings has no rows and the FE-built defaults file "
            f"is missing at {path}. Build the website slice first "
            f"(`npm run build` under products/core/frontend) — the BE "
            f"never invents defaults."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WebsiteDefaultsMissing(f"failed reading/parsing {path}: {exc}") from exc


def invalidate_cache() -> None:
    global _cache
    _cache = None


def _fetch_current_from_db() -> Optional[tuple[int, dict]]:
    db = get_admin_client()
    result = (
        db.table("website_settings")
        .select("version, data")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    return int(row["version"]), row["data"]


def get_current(*, use_cache: bool = True) -> tuple[int, dict]:
    """Return `(version, settings_dict)` — the current row, or `(0, defaults)`
    when `website_settings` is empty."""
    global _cache
    now = time.monotonic()
    if use_cache and _cache is not None and _cache["expires_at"] > now:
        return _cache["version"], _cache["data"]

    found = _fetch_current_from_db()
    version, data = found if found is not None else (0, _load_defaults())

    _cache = {"expires_at": now + _CACHE_TTL_SECONDS, "version": version, "data": data}
    return version, data


def get_history(limit: int = 50) -> list[dict]:
    db = get_admin_client()
    result = (
        db.table("website_settings")
        .select("version, created_at, created_by")
        .order("version", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _validate_shape(data: dict) -> WebsiteSettings:
    """Re-validate the full shape (the router already validated the inbound
    body once; this guards `rollback`, which copies a stored row verbatim
    without going back through the Pydantic body parser)."""
    parsed = WebsiteSettings.model_validate(data)
    if parsed.sections.social_proof and not parsed.social_proof_items:
        raise WebsiteSocialProofEmpty(
            "sections.social_proof is true but social_proof_items is empty"
        )
    return parsed


def update(new_settings: dict, expected_version: int, created_by: Optional[str]) -> dict:
    """Insert a new version row. Raises `WebsiteVersionConflict` when
    `expected_version` doesn't match the CURRENT version (read fresh, not
    from cache — a write must never race against a 30s-stale read)."""
    _validate_shape(new_settings)

    current_version, _ = get_current(use_cache=False)
    if expected_version != current_version:
        raise WebsiteVersionConflict(
            f"expected_version={expected_version} != current={current_version}"
        )

    db = get_admin_client()
    row = {
        "version": current_version + 1,
        "data": new_settings,
        "created_by": created_by,
    }
    result = db.table("website_settings").insert(row).execute()
    if not result.data:
        raise RuntimeError("website_settings insert returned no row")

    invalidate_cache()
    return result.data[0]


def rollback(version: int, created_by: Optional[str]) -> dict:
    """Copy `version`'s data as a brand-new version (never deletes history).
    Raises `LookupError` (404 at the router) when `version` doesn't exist."""
    db = get_admin_client()
    target = (
        db.table("website_settings")
        .select("version, data")
        .eq("version", version)
        .single()
        .execute()
    )
    if not target.data:
        raise LookupError(f"website_settings version {version} not found")

    old_data = target.data["data"]
    _validate_shape(old_data)
    current_version, _ = get_current(use_cache=False)

    row = {
        "version": current_version + 1,
        "data": old_data,
        "created_by": created_by,
    }
    result = db.table("website_settings").insert(row).execute()
    if not result.data:
        raise RuntimeError("website_settings insert returned no row")

    invalidate_cache()
    return result.data[0]


def public_subset(data: dict) -> dict:
    """Contract §2 · Public subset — what anonymous clients see.

    - `trust_items` without `verified_at` are filtered out; the surviving
      items drop `verified_by`.
    - `social_proof_items[].consent_ref` is dropped.
    - `social_proof_items` is emptied when `sections.social_proof` is False.
    - `products` is filtered to `visible`.
    """
    out: dict[str, Any] = dict(data)

    trust_items = []
    for item in data.get("trust_items", []) or []:
        if not item.get("verified_at"):
            continue
        item = dict(item)
        item.pop("verified_by", None)
        trust_items.append(item)
    out["trust_items"] = trust_items

    sections = data.get("sections", {}) or {}
    if sections.get("social_proof"):
        social_proof_items = []
        for item in data.get("social_proof_items", []) or []:
            item = dict(item)
            item.pop("consent_ref", None)
            social_proof_items.append(item)
        out["social_proof_items"] = social_proof_items
    else:
        out["social_proof_items"] = []

    out["products"] = [p for p in (data.get("products", []) or []) if p.get("visible")]

    return out


__all__ = [
    "WebsiteDefaultsMissing",
    "WebsiteSocialProofEmpty",
    "WebsiteVersionConflict",
    "get_current",
    "get_history",
    "invalidate_cache",
    "public_subset",
    "rollback",
    "update",
]
