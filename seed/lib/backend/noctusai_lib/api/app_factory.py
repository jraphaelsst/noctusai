"""
Shared FastAPI application bootstrap for all NoctusAI backends.

Consolidates the duplicated Sentry init, CORS setup, exception handler
registration, middleware registration, and rate-limit handler into a
single configure_app() call.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    postgrest_exception_handler,
    generic_exception_handler,
)
from .middleware import (
    CorrelationIdMiddleware,
    DEFAULT_MAX_BODY_BYTES,
    MaxBodySizeMiddleware,
    RequestLoggingMiddleware,
)

logger = logging.getLogger(__name__)


def configure_app(
    app: FastAPI,
    settings,
    *,
    limiter=None,
    cors_allow_headers: list[str] | None = None,
    cors_expose_headers: list[str] | None = None,
    max_body_bytes: int | None = None,
    max_body_path_overrides: Mapping[str, int] | None = None,
    allow_credentials: bool = True,
    product_name: str | None = None,
) -> None:
    """
    Apply shared configuration to a FastAPI app instance.

    This sets up:
    - Sentry error tracking (if settings.sentry_dsn is configured)
    - CORS middleware
    - Rate-limit exceeded handler (if limiter is provided)
    - Exception handlers (AppException, HTTPException, ValidationError,
      PostgREST APIError, and generic Exception)
    - CorrelationIdMiddleware, RequestLoggingMiddleware, MaxBodySizeMiddleware

    Args:
        app: The FastAPI application instance
        settings: Application settings (must have cors_origins_list,
                  sentry_dsn, is_production, debug attributes; optionally
                  max_body_bytes)
        limiter: Optional slowapi Limiter instance
        cors_allow_headers: Custom list of allowed CORS headers.
                            Defaults to standard set with correlation ID headers.
        cors_expose_headers: Custom list of exposed CORS headers.
                             Defaults to correlation ID and response time headers.
        max_body_bytes: Override the app-wide body-size cap (default 1 MB
                        or `settings.max_body_bytes` when present). Set to
                        a higher value for products that legitimately
                        receive large payloads (file-upload-via-webhook,
                        etc.). Keep the default low for webhook routes —
                        this is the DoS guard those routes rely on; use
                        `max_body_path_overrides` instead of raising this
                        for the routes that actually need more room.
        max_body_path_overrides: Per-route cap override (default `None` or
                        `settings.max_body_path_overrides` when present).
                        `{"<path-prefix>": <max-bytes>, ...}` — the longest
                        matching prefix of the request path wins; a path
                        matching no prefix uses `max_body_bytes`. Use this
                        for upload routes (documents/photos/video) that need
                        a bigger cap WITHOUT raising the app-wide default
                        that keeps webhook routes DoS-guarded. See
                        `noctusai_lib.api.middleware.MaxBodySizeMiddleware`.
        allow_credentials: Whether to send credentials in CORS responses.
                           Defaults to True. Mutually exclusive with a
                           wildcard `cors_origins='*'` — boot refuses the
                           combination (see CORS guard below).
        product_name: Optional product slug surfaced in the CORS guard
                      error message. When None, falls back to
                      `settings.product_name` or '<unknown>'.

    Raises:
        RuntimeError: If `settings.cors_origins_list` contains '*' AND
                      `allow_credentials=True` AND the override env var
                      `NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS` is unset.
                      Browsers reflect any Origin with credentials in
                      that combination — an auth-replay vulnerability.
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
    # CORS wildcard+credentials guard — auth-replay defense.
    #
    # Browsers reflect ANY Origin and forward credentials when both
    # `allow_origins=["*"]` and `allow_credentials=True` are mounted. That
    # permits cross-site auth-token replay by construction. Refuse to boot.
    #
    # Escape hatch for genuine dev scenarios (never in production):
    #   NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS=1
    # Emits a LOUD warning when used.
    # -----------------------------------------------------------------------
    _cors_origins = settings.cors_origins_list
    if "*" in _cors_origins and allow_credentials:
        _override = os.environ.get(
            "NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS", ""
        ).strip().lower() in ("1", "true", "yes")
        _product_label = product_name or getattr(
            settings, "product_name", "<unknown>"
        )
        if not _override:
            raise RuntimeError(
                "CORS misconfiguration: cors_origins='*' is incompatible with "
                "allow_credentials=True (auth-replay vulnerability). "
                "Enumerate cors_origins explicitly. "
                f"Product: {_product_label}. "
                "Override for local dev only via "
                "NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS=1."
            )
        logger.warning(
            "CORS wildcard+credentials override ACTIVE for product=%s — "
            "NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS=1 set. NEVER in production. "
            "Auth-replay risk: any origin can attach credentialed requests.",
            _product_label,
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
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=_allow_headers,
        expose_headers=_expose_headers,
    )

    # -----------------------------------------------------------------------
    # Middleware (order matters: registered last runs first)
    #
    # Stack order on incoming requests:
    #   MaxBodySizeMiddleware → CorrelationIdMiddleware → RequestLoggingMiddleware → handler
    #
    # Rationale: oversized bodies short-circuit before correlation/logging
    # do any work; correlation IDs must be set before request-logging emits
    # records.
    # -----------------------------------------------------------------------
    if max_body_bytes is None:
        max_body_bytes = getattr(settings, "max_body_bytes", DEFAULT_MAX_BODY_BYTES)
    if max_body_path_overrides is None:
        max_body_path_overrides = getattr(settings, "max_body_path_overrides", None)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=max_body_bytes,
        path_overrides=max_body_path_overrides,
    )

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
        logger.warning("app_factory: postgrest not installed; PostgREST exception handler not registered")

    app.add_exception_handler(Exception, generic_exception_handler)
