"""Correlation-ID ContextVar — dependency-free home for the per-request ID.

Lives in its own module (separate from `api/middleware.py`) so that
`logging_config.py` and other utility modules can import it WITHOUT
pulling in `fastapi` / `starlette`. The middleware module re-exports
the same names for backward compatibility with consumers that already
do `from noctusai_lib.api.middleware import get_correlation_id`.

Why this matters: `noctusai_lib.logging_config` is imported by CLI
tools (the MCP toolkit, ad-hoc scripts) that have no FastAPI runtime.
Pulling in FastAPI as a side-effect of `import logging_config` made
the MCP venv mandatorily install ~50 SDKs and silently masked import
errors in the `try/except ImportError` fallbacks at MCP startup.
"""
from __future__ import annotations

from contextvars import ContextVar

# Thread-safe per-request slot. Default is the empty string so callers can
# branch on truthiness without `is None` checks.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the current request's correlation ID (or `""` if unset)."""
    return correlation_id_var.get()
