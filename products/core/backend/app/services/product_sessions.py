"""Product-session registry writer (SSO lifecycle S2, observe mode).

``_generate_session`` mints a FRESH Supabase session per product entry; this records
``session_id -> product_slug`` in ``public.sso_product_sessions`` so the seed auth dependency can
tell a product-born session from a core-born one (``noctusai_lib.api.auth.session_audience``).

Observe mode: a registry write failure MUST NOT fail the mint -- the user still gets a session, and
the failure is logged loudly as ``sso_registry_write_failed`` (alert on it: every miss is a product
session core will later mistake for a core session). The enforce mode (S8) is not implemented; it
will make this write fail closed.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.api.auth.session_audience import REGISTRY_TABLE, parse_mode, session_id_of

from app.config import settings

logger = logging.getLogger(__name__)


def register_product_session(
    db: Any, *, access_token: str, user_id: str, product_slug: Optional[str], jti: Optional[str] = None,
) -> bool:
    """Write the registry row for a just-minted session. True iff written; never raises."""
    try:
        mode = parse_mode(getattr(settings, "sso_product_session_mode", "observe"))
    except (ValueError, RuntimeError):
        # A bad/unsupported mode is refused at app build; if it still got here, behave as observe.
        logger.error("sso_registry_write_failed reason=bad_mode", exc_info=True)
        mode = "observe"
    if mode == "off":
        return False
    session_id = None
    try:
        # Decoded WITHOUT verification: core minted this token a moment ago.
        session_id = session_id_of(access_token)
        if session_id is None:
            raise ValueError("minted access token has no session_id claim")
        if not product_slug:
            raise ValueError("mint carries no product slug")
        db.table(REGISTRY_TABLE).upsert(
            {"session_id": session_id, "user_id": user_id, "product_slug": product_slug, "jti": jti},
            on_conflict="session_id",
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001 - observe mode: logged loudly below, the mint continues
        logger.error(
            "sso_registry_write_failed session_id=%s user_id=%s product=%s reason=%s",
            session_id or "-", user_id, product_slug or "-", type(exc).__name__, exc_info=True,
        )
        return False
