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


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(self, resource: str, resource_id: Optional[str] = None):
        details = {"resource": resource}
        if resource_id:
            details["id"] = resource_id
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} não encontrado",
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
    """Handle FastAPI HTTPException and return standardized error response."""
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
