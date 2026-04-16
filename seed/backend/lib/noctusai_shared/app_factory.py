"""
Shared FastAPI application bootstrap for all NoctusAI backends.

Consolidates the duplicated Sentry init, CORS setup, exception handler
registration, middleware registration, and rate-limit handler into a
single configure_app() call.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from noctusai_shared.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    postgrest_exception_handler,
    generic_exception_handler,
)
from noctusai_shared.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware


def configure_app(
    app: FastAPI,
    settings,
    *,
    limiter=None,
    cors_allow_headers: list[str] | None = None,
    cors_expose_headers: list[str] | None = None,
) -> None:
    """
    Apply shared configuration to a FastAPI app instance.

    This sets up:
    - Sentry error tracking (if settings.sentry_dsn is configured)
    - CORS middleware
    - Rate-limit exceeded handler (if limiter is provided)
    - Exception handlers (AppException, HTTPException, ValidationError,
      PostgREST APIError, and generic Exception)
    - CorrelationIdMiddleware and RequestLoggingMiddleware

    Args:
        app: The FastAPI application instance
        settings: Application settings (must have cors_origins_list,
                  sentry_dsn, is_production, debug attributes)
        limiter: Optional slowapi Limiter instance
        cors_allow_headers: Custom list of allowed CORS headers.
                            Defaults to standard set with correlation ID headers.
        cors_expose_headers: Custom list of exposed CORS headers.
                             Defaults to correlation ID and response time headers.
    """
    # -----------------------------------------------------------------------
    # Sentry (optional)
    # -----------------------------------------------------------------------
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                integrations=[
                    StarletteIntegration(transaction_style="endpoint"),
                    FastApiIntegration(transaction_style="endpoint"),
                ],
                traces_sample_rate=0.1 if settings.is_production else 1.0,
                profiles_sample_rate=0.1 if settings.is_production else 1.0,
                environment="production" if settings.is_production else "development",
                send_default_pii=False,
            )
            logging.info("Sentry SDK initialized successfully")
        except ImportError:
            logging.warning("Sentry SDK not installed. Error tracking disabled.")

    # -----------------------------------------------------------------------
    # Rate limiting
    # -----------------------------------------------------------------------
    if limiter is not None:
        from slowapi.errors import RateLimitExceeded

        app.state.limiter = limiter

        @app.exception_handler(RateLimitExceeded)
        async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Muitas requisições. Tente novamente em breve.",
                    }
                },
            )

    # -----------------------------------------------------------------------
    # CORS
    # -----------------------------------------------------------------------
    _allow_headers = cors_allow_headers or [
        "Authorization", "Content-Type", "Accept", "Origin",
        "X-Requested-With", "X-Correlation-ID", "X-Request-ID",
    ]
    _expose_headers = cors_expose_headers or [
        "X-Correlation-ID", "X-Response-Time-Ms", "Content-Disposition",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=_allow_headers,
        expose_headers=_expose_headers,
    )

    # -----------------------------------------------------------------------
    # Middleware (order matters: CorrelationId must run before Logging)
    # -----------------------------------------------------------------------
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # -----------------------------------------------------------------------
    # Exception handlers
    # -----------------------------------------------------------------------
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)

    # Handle PostgREST errors (e.g. .single() with 0 rows -> 404 instead of 500)
    try:
        from postgrest.exceptions import APIError as PostgRESTError
        app.add_exception_handler(PostgRESTError, postgrest_exception_handler)
    except ImportError:
        pass

    app.add_exception_handler(Exception, generic_exception_handler)
