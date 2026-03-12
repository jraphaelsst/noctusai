"""
Middleware for request tracking, logging, and monitoring.

Provides:
- CorrelationIdMiddleware: generates/extracts correlation IDs for request tracing
- RequestLoggingMiddleware: logs request/response details with timing
- get_correlation_id(): accessor for the current request's correlation ID
"""
from __future__ import annotations

import time
import uuid
import logging
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Context variable for correlation ID (thread-safe)
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current request's correlation ID."""
    return correlation_id_var.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates or extracts correlation IDs for request tracking.

    - Checks for X-Correlation-ID or X-Request-ID header
    - Generates a new UUID if not present
    - Adds correlation ID to response headers
    - Stores in context variable for use throughout request lifecycle
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate correlation ID
        correlation_id = (
            request.headers.get("X-Correlation-ID") or
            request.headers.get("X-Request-ID") or
            str(uuid.uuid4())
        )

        # Store in context variable
        token = correlation_id_var.set(correlation_id)

        try:
            response = await call_next(request)
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs request/response details with timing.

    Logs:
    - Request: method, path, client IP, query params
    - Response: status code, duration
    - Slow requests (> 1s) are logged at WARNING level
    """

    SLOW_REQUEST_THRESHOLD_MS = 1000  # 1 second

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        correlation_id = get_correlation_id()

        # Log request start
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            "Request started",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": client_ip,
                "query_params": str(request.query_params),
            }
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Determine log level based on response status and duration
            log_level = logging.INFO
            if response.status_code >= 500:
                log_level = logging.ERROR
            elif response.status_code >= 400:
                log_level = logging.WARNING
            elif duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
                log_level = logging.WARNING

            logger.log(
                log_level,
                "Request completed",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "slow_request": duration_ms > self.SLOW_REQUEST_THRESHOLD_MS,
                }
            )

            # Add timing header
            response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Request failed with exception",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                }
            )
            raise
