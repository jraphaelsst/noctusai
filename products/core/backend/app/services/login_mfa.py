"""Login-time MFA discovery for core's server-side password login.

Platform-admin-mfa M5. After `sign_in_with_password` succeeds, core asks the
seed `MfaClient` (the one `create_product_app` parks on `app.state.mfa_gate`,
DI seam for tests) which VERIFIED factors the user has. No factors, no client
configured, or a lookup failure => `([])` and login proceeds exactly as before:
the admin gate (policy warn/enforce) is the enforcement point and re-challenges
through the 403 `mfa_required` interceptor, so failing open here never weakens it.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def verified_factors(request: Any, access_token: str) -> list[dict]:
    """`[{"id", "friendly_name"}]` of the user's verified TOTP factors (may be empty)."""
    cfg = getattr(request.app.state, "mfa_gate", None)
    client = getattr(cfg, "client", None)
    if client is None:
        return []
    try:
        factors = await client.list_factors(access_token)
    except Exception as exc:  # noqa: BLE001 — logged; the admin gate still enforces
        logger.warning("auth: login MFA factor lookup failed (%s); login proceeds without challenge", type(exc).__name__)
        return []
    return [
        {"id": f.id, "friendly_name": f.friendly_name}
        for f in factors
        if f.status == "verified"
    ]
