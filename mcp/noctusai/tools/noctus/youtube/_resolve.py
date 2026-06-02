"""Account resolution helpers for ``noctus.youtube.*`` tools.

All read tools accept an ``account`` parameter that can be:
  - a UUID string  → matched against ``integration_accounts.id``
  - a label string → matched against ``integration_accounts.account_label``
                     (case-insensitive prefix, returns the first match)
  - empty string / ``None`` → resolves the org's single YouTube account
    (fails with a structured error if there are zero or multiple)

The resolver is intentionally narrow: it only queries accounts with
``provider = 'youtube'`` and ``status = 'active'``.  Inactive / errored
accounts are excluded so that tools never accidentally report stale data
from a disconnected channel.

If resolution fails the tool should return a dict with ``"error": "account_not_found"``
rather than raising, so the agent can surface the issue gracefully.
"""
from __future__ import annotations

import logging
import uuid as _uuid_mod
from typing import Any

logger = logging.getLogger(__name__)

_PROVIDER = "youtube"
_ACTIVE_STATUS = "active"


def _is_uuid(s: str) -> bool:
    try:
        _uuid_mod.UUID(s)
        return True
    except ValueError:
        return False


def resolve_account(client, account: str | None) -> dict | None:
    """Return the integration_accounts row for the given ``account`` specifier.

    Parameters
    ----------
    client:
        Supabase client (service-role, ``social_wiring`` schema).
    account:
        UUID, account_label substring, or empty/None for auto-select.

    Returns
    -------
    dict | None
        The matching row dict, or ``None`` when not found.
        On ambiguous-empty (multiple active accounts, no specifier) returns
        a special dict with ``"error": "ambiguous"`` to distinguish from
        "not found".
    """
    query = (
        client.table("integration_accounts")
        .select(
            "id, account_label, channel_info, status, org_id, created_at"
        )
        .eq("provider", _PROVIDER)
        .eq("status", _ACTIVE_STATUS)
    )

    if account and _is_uuid(account):
        query = query.eq("id", account)
    elif account:
        # case-insensitive label match via ilike
        query = query.ilike("account_label", f"%{account}%")
    # else: no filter — auto-select (works only if exactly one row)

    resp = query.execute()
    rows: list[dict[str, Any]] = resp.data or []

    if len(rows) == 0:
        logger.warning("resolve_account: no active YouTube account found for specifier=%r", account)
        return None
    if len(rows) > 1 and not account:
        # Multiple accounts, no specifier — ambiguous
        logger.warning(
            "resolve_account: multiple active YouTube accounts (%d) and no specifier; "
            "caller must pass account label or id",
            len(rows),
        )
        return {
            "error": "ambiguous",
            "count": len(rows),
            "accounts": [
                {"id": r["id"], "label": r.get("account_label", "")} for r in rows
            ],
        }
    if len(rows) > 1:
        # Multiple matches for a label — return the best match (exact first)
        account_lower = (account or "").lower()
        exact = next(
            (r for r in rows if (r.get("account_label") or "").lower() == account_lower),
            None,
        )
        return exact if exact else rows[0]

    return rows[0]
