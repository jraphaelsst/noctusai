"""Security response headers (pure ASGI, so it stays safe under disconnects).

Applied to every HTTP response — API and the SPA shell served by
``serve_spa``. HSTS is emitted only on https requests (or when CloudFlare says
``X-Forwarded-Proto: https``) so local http dev is never pinned.

CSP is REPORT-ONLY: nothing is blocked, violations are only reported by the
browser. Tighten after reviewing reports. Origins allowed in the baseline:
Google Fonts, Supabase (https + wss), Sentry ingest, Cloudflare Turnstile,
and ``*.noctusai.com`` (SSO bridge / sibling product APIs).
"""
from __future__ import annotations

import os

from starlette.datastructures import Headers, MutableHeaders

HSTS = "max-age=31536000; includeSubDomains"

# Camera / mic / geolocation: only the product's own origin may use them
# (erp-imobiliario Campo uses geolocation; VoiceAnswerInput uses the mic).
PERMISSIONS_POLICY = "camera=(self), microphone=(self), geolocation=(self), payment=(), usb=()"

CSP_REPORT_ONLY = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob: https:",
    "connect-src 'self' https://*.supabase.co wss://*.supabase.co "
    "https://*.noctusai.com https://*.ingest.sentry.io https://*.ingest.us.sentry.io",
    "frame-src 'self' blob: https://challenges.cloudflare.com https://www.youtube.com",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


class SecurityHeadersMiddleware:
    def __init__(self, app, *, frame_options: str | None = None) -> None:
        self.app = app
        self.frame_options = frame_options or os.environ.get("X_FRAME_OPTIONS", "DENY")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        req = Headers(scope=scope)
        https = scope.get("scheme") == "https" or req.get("x-forwarded-proto", "").split(",")[0].strip() == "https"

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h.setdefault("X-Content-Type-Options", "nosniff")
                h.setdefault("X-Frame-Options", self.frame_options)
                h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                h.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
                if https:
                    h.setdefault("Strict-Transport-Security", HSTS)
                ctype = h.get("content-type", "")
                if ctype.startswith("text/html"):
                    h.setdefault("Content-Security-Policy-Report-Only", CSP_REPORT_ONLY)
            await send(message)

        await self.app(scope, receive, send_wrapper)
