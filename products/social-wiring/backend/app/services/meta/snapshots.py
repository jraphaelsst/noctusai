"""Instagram metric-snapshot capture — ``ig_metric_snapshots`` writer.

Two entry points:

- :func:`capture_ig_snapshot` — capture ONE Instagram account's current
  numbers (followers / follows / media count from
  ``adapter.list_instagram_accounts()``, reach / profile_views summed
  from ``adapter.get_instagram_account_insights()``) and persist a row.
  Consumed directly by the ``POST /api/meta/instagram/{ig_user_id}/snapshot``
  endpoint (adapter already built by the router).

- :func:`capture_all_ig_snapshots` — capture EVERY Instagram account
  visible to an org's Meta adapter. Builds the adapter itself (org-scoped
  credential resolution) so it can be called standalone — the shape the
  daily scheduler job needs (one call per org, no adapter plumbing at the
  call site).

Both use ``get_admin_client()`` (service role — bypasses RLS, same as
``credential_vault``); RLS on ``ig_metric_snapshots`` gates the
authenticated-user READ path only (``GET /snapshots``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.services.credential_vault import EncryptionNotConfigured, build_credential_store
from app.services.meta import MetaGraphError, get_meta_adapter

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_TABLE = "ig_metric_snapshots"


class IGAccountNotFoundError(Exception):
    """Raised when ``ig_user_id`` isn't in the adapter's
    ``list_instagram_accounts()`` — mapped to a 404 by the router."""


def capture_ig_snapshot(
    admin: Any,
    org_id: UUID | str,
    ig_user_id: str,
    adapter: Any,
) -> dict[str, Any]:
    """Capture + persist one Instagram account's current numbers.

    Finds ``ig_user_id`` in ``adapter.list_instagram_accounts()`` for the
    followers/follows/media counts, then sums ``reach`` /
    ``profile_views`` off ``adapter.get_instagram_account_insights()``
    (best-effort — a ``MetaGraphError`` on the insights call degrades to
    ``0`` for those two fields rather than failing the whole capture; the
    account-level numbers still land).

    Raises :class:`IGAccountNotFoundError` when ``ig_user_id`` doesn't
    match any account the adapter can see.
    """
    accounts = adapter.list_instagram_accounts()
    account = next((a for a in accounts if a.id == ig_user_id), None)
    if account is None:
        raise IGAccountNotFoundError(
            f"Instagram account {ig_user_id!r} not found for this org's "
            "Meta connection."
        )

    reach = 0
    profile_views = 0
    raw: list[dict[str, Any]] = []
    try:
        insights = adapter.get_instagram_account_insights(ig_user_id)
        reach = int(insights.metrics.get("reach") or 0)
        profile_views = int(insights.metrics.get("profile_views") or 0)
        raw = list(insights.raw)
    except MetaGraphError as exc:
        logger.warning(
            "ig snapshot: account-insights fetch failed for %s: %s — "
            "persisting account counts only (reach/profile_views=0)",
            ig_user_id, exc,
        )

    row = {
        "org_id": str(org_id),
        "ig_user_id": ig_user_id,
        "username": account.username,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "followers_count": account.followers_count,
        "follows_count": account.follows_count,
        "media_count": account.media_count,
        "reach": reach,
        "profile_views": profile_views,
        "raw": raw,
    }
    (
        admin
        .schema(_SCHEMA)
        .table(_TABLE)
        .insert(row)
        .execute()
    )
    return row


def capture_all_ig_snapshots(admin: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    """Capture a snapshot for every Instagram account this org's Meta
    connection can see. Builds the adapter itself (org-scoped credential
    resolution via the product's ``get_meta_adapter`` seam) — the shape
    the daily scheduler job needs: one call per org.

    An org with no Meta connection (Fake adapter, zero seeded accounts)
    returns an empty list — not an error.
    """
    try:
        store = build_credential_store(admin)
    except EncryptionNotConfigured:
        store = None

    adapter = get_meta_adapter(
        org_id=org_id if store else None,
        credential_store=store,
    )

    results: list[dict[str, Any]] = []
    for account in adapter.list_instagram_accounts():
        try:
            results.append(
                capture_ig_snapshot(admin, org_id, account.id, adapter)
            )
        except IGAccountNotFoundError:  # pragma: no cover — can't happen;
            # account.id came from the same list_instagram_accounts() call.
            continue
    return results


__all__ = [
    "IGAccountNotFoundError",
    "capture_all_ig_snapshots",
    "capture_ig_snapshot",
]
