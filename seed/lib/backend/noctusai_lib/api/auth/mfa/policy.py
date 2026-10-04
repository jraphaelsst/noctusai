"""``MfaPolicy`` — per-product admin-MFA mode (``off`` | ``warn`` | ``enforce``).

Protocol + Fake + Real + factory (``KB § PATTERNS/backend/seed-fake-real-adapter.md``).
Resolution: the product's own row wins; else the fleet-default row; else
``off``. ``off`` is also the answer on a read error — but that error is
LOGGED at ERROR, never silent (a broken policy store must be visible; it
must not lock admins out, and M2's gate cannot read "enforce" from nothing).

Expected table (migration lands in M3, NOT here)::

    public.mfa_policy (
        scope      text primary key,   -- 'fleet' or a product slug
        mode       text not null check (mode in ('off','warn','enforce')),
        updated_at timestamptz not null default now(),
        updated_by uuid
    )
    -- service-role write only; RLS on, no policies for anon/authenticated.
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional, Protocol, runtime_checkable


logger = logging.getLogger(__name__)

MfaMode = Literal["off", "warn", "enforce"]
MFA_POLICY_TABLE = "mfa_policy"
FLEET_SCOPE = "fleet"
_MODES = ("off", "warn", "enforce")


@runtime_checkable
class MfaPolicy(Protocol):
    async def resolve(self, product: str) -> MfaMode:
        """Effective mode for ``product`` (override > fleet default > ``off``)."""
        ...


class FakeMfaPolicy:
    """In-memory policy for tests/dev. ``rows`` maps scope -> mode."""

    def __init__(self, rows: Optional[dict[str, str]] = None, *, fail: bool = False) -> None:
        self.rows = dict(rows or {})
        self.fail = fail
        self.calls: list[str] = []

    async def resolve(self, product: str) -> MfaMode:
        self.calls.append(product)
        if self.fail:
            logger.error("mfa.policy: fake read failure — defaulting to off")
            return "off"
        return pick_mode(self.rows, product)


def pick_mode(rows: dict[str, Any], product: str) -> MfaMode:
    """Product override, then fleet default, then ``off``. Unknown values are ignored."""
    for scope in (product, FLEET_SCOPE):
        mode = rows.get(scope)
        if mode in _MODES:
            return mode  # type: ignore[return-value]
        if mode is not None:
            logger.error("mfa.policy: invalid mode %r for scope %r — ignored", mode, scope)
    return "off"


class SupabaseMfaPolicy:
    """Reads ``public.mfa_policy`` through a public-schema client (same
    ``core_client`` convention as ``make_resolve_platform_role``)."""

    def __init__(self, core_client: Any) -> None:
        self._db = core_client

    async def resolve(self, product: str) -> MfaMode:
        try:
            resp = (
                self._db.from_(MFA_POLICY_TABLE)
                .select("scope,mode")
                .in_("scope", [product, FLEET_SCOPE])
                .execute()
            )
            rows = {r["scope"]: r["mode"] for r in (resp.data or [])}
        except Exception as exc:  # noqa: BLE001 — logged, default off
            logger.error(
                "mfa.policy: could not read %s (%s: %s) — defaulting to off",
                MFA_POLICY_TABLE, type(exc).__name__, exc,
            )
            return "off"
        return pick_mode(rows, product)


def make_mfa_policy(*, use_fake: bool = False, core_client: Any = None,
                    rows: Optional[dict[str, str]] = None) -> MfaPolicy:
    """Fake when ``use_fake``; else the Supabase-backed policy (needs ``core_client``)."""
    if use_fake:
        return FakeMfaPolicy(rows)
    if core_client is None:
        raise ValueError("make_mfa_policy: core_client is required unless use_fake=True")
    return SupabaseMfaPolicy(core_client)


__all__ = [
    "FLEET_SCOPE", "MFA_POLICY_TABLE", "FakeMfaPolicy", "MfaMode", "MfaPolicy",
    "SupabaseMfaPolicy", "make_mfa_policy", "pick_mode",
]
