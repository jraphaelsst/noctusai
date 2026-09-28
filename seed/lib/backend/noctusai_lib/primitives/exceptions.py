"""
Centralized exception handling for all NoctusAI APIs.

Provides a hierarchy of typed exceptions and matching FastAPI exception
handlers that return standardized JSON error responses with proper
Portuguese messages.
"""
from __future__ import annotations

from typing import Any, Optional
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class AppException(Exception):
    """Base application exception with standardized error response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[dict] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


#: pt-BR nouns ending in "-ma"/"-pa" that are grammatically MASCULINE despite
#: the heuristic below reading a trailing "a" as feminine ("o problema", never
#: "a problema"). Kept intentionally small — resource labels this exception
#: actually receives ("Tarefa", "Pauta", "Marca", "Etapa", "Permuta"…), not an
#: exhaustive Portuguese dictionary.
_MASCULINOS_TERMINADOS_EM_A = {
    "problema", "sistema", "tema", "programa", "clima", "idioma", "mapa",
    "planeta", "cinema", "drama", "enigma", "dogma", "emblema", "esquema",
    "fantasma", "holograma", "poema", "panorama", "telefonema", "dia",
}


def _feminino_por_heuristica(resource: str) -> bool:
    """Best-effort pt-BR gender guess for a resource label.

    Not a grammar engine — a targeted heuristic for the labels this
    exception actually receives (a single noun, or a noun the caller already
    capitalized). Endings that are reliably feminine in this vocabulary:
    `-ção`/`-são` ("negociação", "permissão"), `-dade`, `-gem`, or a bare
    trailing "a" MINUS the small masculine-despite-"-a" exception list above.
    A caller that already composed a full sentence (e.g. ending in ".") falls
    through to the masculine default unchanged — this heuristic only ever
    ADDS correct agreement, never removes an existing one.
    """
    ultima_palavra = resource.strip().split()[-1].lower() if resource.strip() else ""
    if ultima_palavra in _MASCULINOS_TERMINADOS_EM_A:
        return False
    if ultima_palavra.endswith(("ção", "são", "dade", "gem")):
        return True
    return ultima_palavra.endswith("a")


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(
        self,
        resource: str,
        resource_id: Optional[str] = None,
        *,
        feminino: Optional[bool] = None,
    ):
        """
        Args:
            resource: The pt-BR noun shown to the user ("Tarefa", "cliente_documentos"…).
            resource_id: Optional id, carried in `details` only (never in the message).
            feminino: Force gender agreement ("...não encontrada" vs
                "...não encontrado") when the heuristic would guess wrong for
                an unusual label. Defaults to `None` — auto-detected from
                `resource` via :func:`_feminino_por_heuristica`. Keyword-only
                and defaulted so every existing two-positional-arg call site
                (`NotFoundError("Tarefa", tarefa_id)`) keeps working unchanged.
        """
        details = {"resource": resource}
        if resource_id:
            details["id"] = resource_id
        if feminino is None:
            feminino = _feminino_por_heuristica(resource)
        adjetivo = "não encontrada" if feminino else "não encontrado"
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} {adjetivo}",
            status_code=404,
            details=details,
        )


class ValidationError_(AppException):
    """Validation error for business logic."""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {}
        if field:
            details["field"] = field
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=400,
            details=details,
        )


class UnauthorizedError(AppException):
    """Authentication required."""

    def __init__(self, message: str = "Autenticação necessária"):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=401,
        )


class ForbiddenError(AppException):
    """Access denied."""

    def __init__(self, message: str = "Acesso negado"):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403,
        )


class ConflictError(AppException):
    """Resource conflict (e.g., duplicate)."""

    def __init__(self, message: str, resource: Optional[str] = None):
        details = {}
        if resource:
            details["resource"] = resource
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=409,
            details=details,
        )


class InternalError(AppException):
    """Internal server error."""

    def __init__(self, message: str = "Erro interno do servidor"):
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_error_response(
    code: str,
    message: str,
    details: Optional[dict] = None,
) -> dict:
    """Format a standardized error response."""
    response = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details:
        response["error"]["details"] = details
    return response


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle AppException and return standardized error response."""
    logger.warning(f"AppException: {exc.code} - {exc.message}", extra={"details": exc.details})
    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(exc.code, exc.message, exc.details),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTPException and return standardized error response.

    Two shapes, disambiguated by `exc.detail`'s type:

    - `exc.detail` is a `dict` with BOTH `"detail"` and `"code"` keys —
      the "seed error shape" a growing set of callers (`noctusai_lib.
      api.auth.session.scopes.require_scopes`, and any product route
      that raises `HTTPException(detail={"detail": "<msg>", "code":
      "<machine_code>"})` for a machine-readable error, e.g. contract
      §0 of `julia-agents-academia-2026-09`) already construct on
      purpose. Passed through VERBATIM (flat) — the machine `code` this
      shape exists for would otherwise be silently discarded by the
      legacy envelope below, which only derives a generic per-status
      code (`FORBIDDEN`, `NOT_FOUND`, …) and stringifies the whole dict
      into `message` (found 2026-09-14 wiring `require_scopes` into
      academia's first live route — the seed's OWN existing unit tests
      never caught this because they assert on the raised exception
      object directly, never through a live TestClient round-trip).
    - Anything else (the historical case — a plain string `detail`, or
      no detail at all): UNCHANGED legacy `{"error": {"code",
      "message"}}` envelope, so every existing product's tests (which
      assert THIS shape) keep passing.

    Both shapes forward `exc.headers` onto the `JSONResponse` — a route
    that raises `HTTPException(..., headers={"Retry-After": "10"})` (e.g.
    contract §E.11's 429 `julia_capacidade`) had that header silently
    dropped before this fix, since `JSONResponse(...)` was built with no
    `headers=` kwarg at all. `exc.headers` defaults to `None`, and
    `JSONResponse(headers=None)` is the same as omitting it, so this is
    purely additive — no existing caller's response changes.
    """
    if isinstance(exc.detail, dict) and "detail" in exc.detail and "code" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code, content=exc.detail, headers=exc.headers
        )

    code = "HTTP_ERROR"
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code == 400:
        code = "BAD_REQUEST"
    elif exc.status_code >= 500:
        code = "INTERNAL_ERROR"

    return JSONResponse(
        status_code=exc.status_code,
        content=format_error_response(code, str(exc.detail)),
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle Pydantic ValidationError and return standardized error response."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })

    return JSONResponse(
        status_code=422,
        content=format_error_response(
            code="VALIDATION_ERROR",
            message="Erro de validação nos dados enviados",
            details={"errors": errors},
        ),
    )


async def postgrest_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle PostgREST APIError with proper status codes for common PG errors."""
    pg_code = getattr(exc, "code", None) or ""
    message = getattr(exc, "message", str(exc))

    # PGRST116: .single() returned 0 rows -> 404
    if pg_code == "PGRST116":
        return JSONResponse(
            status_code=404,
            content=format_error_response("NOT_FOUND", "Recurso não encontrado"),
        )

    # 23505: unique constraint violation -> 409
    if pg_code == "23505":
        logger.warning(f"PostgREST unique violation: {message}")
        return JSONResponse(
            status_code=409,
            content=format_error_response("CONFLICT", "Registro duplicado — este recurso já existe"),
        )

    # 23503: foreign key violation -> 400
    if pg_code == "23503":
        logger.warning(f"PostgREST FK violation: {message}")
        return JSONResponse(
            status_code=400,
            content=format_error_response("BAD_REQUEST", "Referência inválida — recurso relacionado não encontrado"),
        )

    # 23502: not-null violation -> 400
    if pg_code == "23502":
        logger.warning(f"PostgREST not-null violation: {message}")
        return JSONResponse(
            status_code=400,
            content=format_error_response("BAD_REQUEST", "Campo obrigatório não preenchido"),
        )

    # All other PostgREST errors — log and surface the message
    logger.exception(f"PostgREST error [{pg_code}]: {message}")
    return JSONResponse(
        status_code=500,
        content=format_error_response("INTERNAL_ERROR", message or "Erro interno do servidor"),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=format_error_response(
            code="INTERNAL_ERROR",
            message="Erro interno do servidor",
        ),
    )
