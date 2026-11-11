"""Integration / config failures reach the browser as a CODE, never as exception text.

Owner rule "no-leaking" (2026-11-11): ``detail=str(exc)`` / ``f"... {exc}"`` echoes internal hostnames
(``http://waha-assistant:3000/...``), env-var names and driver messages to the caller. Every seed route that
turns a caught exception into an HTTP error calls :func:`integration_error` instead: the body is a FIXED pt-BR
message plus a stable machine ``code`` (the seed error shape ``{"detail", "code"}`` the app's
``http_exception_handler`` passes through flat), and the exception is logged server-side.

Telemetry is one structured line per dispatch (same ``key=value`` shape as ``req_timing``), so the codes are
countable from the logs without a new system::

    integration_error code=waha_unavailable status=502 op=qr exc=ConnectError

Gate: keeper ``check_http_detail_echoes_exception`` (build triad: this construction + the keeper + this line).
KB § PATTERNS/security/appsec-craft-canon.md
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger("noctusai.integration_error")

LOG_PREFIX = "integration_error"

# code -> (HTTP status, fixed pt-BR message). The message is safe by construction: no host, no env name, no driver text.
CATALOG: dict[str, tuple[int, str]] = {
    "waha_unavailable": (502, "Falha ao falar com o WhatsApp"),
    "waha_webhook_failed": (502, "Falha ao configurar o webhook do WhatsApp"),
    "upstream_error": (502, "Falha ao falar com um serviço externo"),
    "service_unavailable": (503, "Serviço temporariamente indisponível"),
    "not_configured": (503, "Recurso não configurado"),
    "invalid_request": (422, "Requisição inválida"),
    "invalid_payload": (400, "Payload inválido"),
}


def integration_error(
    code: str, *, exc: Optional[BaseException] = None, op: Optional[str] = None
) -> HTTPException:
    """Build (never raise) the HTTPException for ``code``; log ``code`` + the exception CLASS server-side.

    ``raise integration_error("waha_unavailable", exc=exc, op="qr") from exc``
    """
    status_code, message = CATALOG[code]
    logger.warning(
        "%s code=%s status=%d op=%s exc=%s",
        LOG_PREFIX, code, status_code, op or "-", type(exc).__name__ if exc is not None else "-",
        exc_info=exc if exc is not None else None,
    )
    return HTTPException(status_code=status_code, detail={"detail": message, "code": code})
