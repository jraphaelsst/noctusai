"""Structured, secret-free reason for every 401 the auth layer answers.

Born 2026-10-13: a prod logout whose FIRST 401 could not be explained — the
401 was the trigger and nothing recorded WHY it was issued. Every 401 raised
from bearer / session auth calls :func:`log_auth_401` with a machine-readable
``reason`` so the next incident's first 401 is explainable from the logs alone.

Never pass a token, cookie value, or Authorization header here: only the
reason code, small non-secret facts (provider status/code, exception class
name, token *shape*), and the request's correlation id (added automatically).
"""
from __future__ import annotations

import logging

from noctusai_lib.primitives._correlation import get_correlation_id

logger = logging.getLogger("noctusai_lib.api.auth")


def token_shape(token: str | None) -> str:
    """Non-secret classification of a bearer value: ``empty`` / ``pk_*`` / ``jwt`` / ``opaque``."""
    if not token:
        return "empty"
    if token.startswith("pk_"):
        return "pk_token"
    return "jwt" if token.count(".") == 2 else "opaque"


def log_auth_401(reason: str, **fields: object) -> None:
    """Log one structured line: ``auth_401 reason=<code> cid=<id> k=v ...``."""
    extra = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.warning(
        "auth_401 reason=%s cid=%s%s",
        reason,
        get_correlation_id() or "-",
        f" {extra}" if extra else "",
    )
