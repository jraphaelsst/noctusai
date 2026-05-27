"""openai.diagnostics.connection_status — never-faked READY/UNCONFIGURED signal."""
from __future__ import annotations

import logging
from typing import Any

from mcp.types import Tool

from .. import openai_client
from ..settings import get_settings
from ..types import DiagnosticsInput, DiagnosticsOutput

logger = logging.getLogger(__name__)


async def handle_connection_status(_args: dict) -> dict:
    settings = get_settings()
    sdk_version: str | None = None
    reachable: bool | None = None
    error: dict | None = None

    try:
        import openai  # type: ignore[import-not-found]
        sdk_version = getattr(openai, "__version__", None)
    except ImportError:
        sdk_version = None

    if settings.configured:
        try:
            client = openai_client.get_client()
            # Cheap ping: list models. Doesn't burn tokens.
            _ = client.models.list()
            reachable = True
        except Exception as exc:  # noqa: BLE001
            reachable = False
            error = {
                "kind": type(exc).__name__,
                "message": str(exc)[:200],
            }

    return DiagnosticsOutput(
        ok=bool(settings.configured and reachable),
        configured=settings.configured,
        reachable=reachable,
        default_chat_model=settings.default_chat_model,
        default_embedding_model=settings.default_embedding_model,
        default_vision_model=settings.default_vision_model,
        default_audio_model=settings.default_audio_model,
        sdk_version=sdk_version,
        error=error,
    ).model_dump()


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="openai.diagnostics.connection_status",
            description=(
                "Read-only never-faked health check: reports whether "
                "OPENAI_API_KEY is configured + whether a cheap models.list() "
                "call succeeds + the default model surface + installed SDK "
                "version. Use this BEFORE assuming any other openai.* tool "
                "will work — gated-capability honesty (KB § PATTERNS/common/"
                "gated-capability-honesty.md)."
            ),
            inputSchema=DiagnosticsInput.model_json_schema(),
        ),
    ]


HANDLERS: dict[str, Any] = {"openai.diagnostics.connection_status": handle_connection_status}


def register(server) -> None:
    pass
