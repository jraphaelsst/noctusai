"""Cloudflare Turnstile `siteverify` — the Real `TurnstileVerifier`.

One HTTP call, no SDK: `POST https://challenges.cloudflare.com/turnstile/
v0/siteverify` with `{secret, response, remoteip?}` as form data, returns
`{"success": bool, "error-codes": [...], ...}`. httpx.AsyncClient mirrors
the convention `noctusai_lib.integrations.payments.real_asaas` already
uses (constructor-injectable `transport=` for `httpx.MockTransport` in
tests — no network in this package's own test suite).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from .types import TurnstileVerificationResult

logger = logging.getLogger(__name__)

DEFAULT_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
DEFAULT_TIMEOUT_SECONDS = 5.0


class RealTurnstileVerifier:
    """Calls Cloudflare's `siteverify` endpoint over HTTPS.

    Fails CLOSED, never open: any transport error, timeout, or malformed
    response is logged at WARNING and returned as
    `TurnstileVerificationResult(success=False)` — never raised. A
    network hiccup must deny the checkout, not silently let a bot
    through, and a consumer's router does not need a second exception
    type to handle alongside `403`.
    """

    def __init__(
        self,
        *,
        secret: str,
        verify_url: str = DEFAULT_VERIFY_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._secret = secret
        self._verify_url = verify_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport)

    async def verify(
        self, token: str, *, remote_ip: Optional[str] = None
    ) -> TurnstileVerificationResult:
        if not token:
            return TurnstileVerificationResult(
                success=False, error_codes=("missing-input-response",)
            )
        payload = {"secret": self._secret, "response": token}
        if remote_ip:
            payload["remoteip"] = remote_ip
        try:
            async with self._client() as client:
                response = await client.post(self._verify_url, data=payload)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("turnstile: siteverify call failed: %s", exc)
            return TurnstileVerificationResult(
                success=False, error_codes=("internal-error",)
            )
        success = bool(data.get("success"))
        error_codes = tuple(data.get("error-codes") or ())
        if not success:
            logger.warning("turnstile: verification failed: %s", error_codes)
        return TurnstileVerificationResult(success=success, error_codes=error_codes, raw=data)


__all__ = ["RealTurnstileVerifier", "DEFAULT_VERIFY_URL", "DEFAULT_TIMEOUT_SECONDS"]
