"""
Centralized exception handling for the NoctusAI Core API.
"""
from typing import Any, Optional
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


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
