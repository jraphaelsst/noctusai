"""Shared product-level helpers for social-wiring."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def has_oauth_credential(
    store: Any,
    org_id: Any,
    provider: str,
    *,
    require_token: bool = False,
) -> bool:
    """True when the credential vault holds a usable ``(org, provider)`` row.

    Unifies the three previously-duplicated ``_has_oauth_credential`` gates
    (``services/calendar`` · ``services/drive_api`` · ``services/meta`` —
    N=3 → formalized per the DRY recurrence rule). ``org_id`` is coerced to
    ``str`` for the lookup so callers may pass either a ``UUID`` (Google
    OAuth path) or a ``str`` (Meta path).

    ``provider`` selects the credential row — Google issues ONE credential
    covering the Calendar/Drive/YouTube scope bundle, so both the calendar
    and drive sites pass the same ``CALENDAR_PROVIDER`` key (the Drive scope
    is bundled into the Calendar consent); Meta passes ``META_PROVIDER``.

    ``require_token`` — when set, a row only counts as connected if it
    carries a non-empty ``access_token`` (the Meta gate; matches the retired
    product factory's stricter check). Lookup failures are logged and treated
    as not-connected — never a silent swallow.
    """
    try:
        stored = store.get(str(org_id), provider)
    except Exception:
        logger.exception(
            "OAuth credential lookup failed (provider=%s); treating as not-connected",
            provider,
        )
        return False
    if require_token:
        return bool(
            stored is not None and getattr(stored, "tokens", {}).get("access_token")
        )
    return stored is not None
