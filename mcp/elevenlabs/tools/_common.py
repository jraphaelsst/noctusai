"""Shared leaf helpers (settings → api context)."""
from __future__ import annotations

from ..settings import get_settings


def ctx(timeout: float | None = None) -> dict:
    s = get_settings()
    return {"base_url": s.base_url, "api_key": s.api_key or "",
            "timeout": timeout if timeout is not None else s.timeout_seconds}
