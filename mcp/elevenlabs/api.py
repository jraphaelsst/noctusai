"""ElevenLabs HTTP runner — the external-service seam for this connector.

`request_json` / `request_bytes` are the HTTP boundary; urllib mechanics
are delegated to `_kit.transport`. This wrapper owns `ElevenLabsApiError`,
the 424 not-configured gate and the `xi-api-key` header.

**Test seam.** Tests `patch("elevenlabs.api.request_json" | "...request_bytes")`
(external-service patch, CLAUDE.md §1); our own guards are never patched.

Error contract (`status`): 412 confirm required · 422 refused by our own
guard (cap, consent, path) · 424 not configured · upstream status passed
through · 502 unreachable/unparseable. Error text never carries the key
or request text (the transport truncates upstream bodies only).
"""
from __future__ import annotations

from typing import Optional

from _kit.errors import confirmation_required_message
from _kit.transport import request_bytes as _http_request_bytes
from _kit.transport import request_json as _http_request_json


class ElevenLabsApiError(Exception):
    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(ElevenLabsApiError):
    def __init__(self, action: str, effect: str = ""):
        super().__init__(
            confirmation_required_message(action, effect, noun="credit-spending / consent-bearing action"),
            status=412,
        )


class RefusedError(ElevenLabsApiError):
    """Refused by one of OUR guards (cap, consent, path). No call was made."""

    def __init__(self, message: str):
        super().__init__(message, status=422)


def _check(api_key: str) -> None:
    if not api_key:
        raise ElevenLabsApiError(
            "ElevenLabs connector not configured — set ELEVENLABS_API_KEY in "
            "mcp/elevenlabs/.env (or the environment).",
            status=424,
        )


def _auth(api_key: str) -> tuple[str, str]:
    return ("xi-api-key", api_key)


def request_json(method: str, path: str, *, base_url: str, api_key: str,
                 params: Optional[dict] = None, body: Optional[object] = None,
                 timeout: float = 20.0) -> object:
    _check(api_key)
    return _http_request_json(
        method, f"{base_url.rstrip('/')}{path}", auth_header=_auth(api_key),
        params=params, body=body, timeout=timeout,
        error_cls=ElevenLabsApiError, empty_result={},
        label=f"ElevenLabs API {method.upper()} {path}",
    )


def request_bytes(method: str, path: str, *, base_url: str, api_key: str,
                  params: Optional[dict] = None, body: Optional[object] = None,
                  raw_body: Optional[tuple] = None, timeout: float = 120.0
                  ) -> tuple[bytes, dict]:
    _check(api_key)
    return _http_request_bytes(
        method, f"{base_url.rstrip('/')}{path}", auth_header=_auth(api_key),
        params=params, body=body, raw_body=raw_body, timeout=timeout,
        error_cls=ElevenLabsApiError,
        label=f"ElevenLabs API {method.upper()} {path}",
    )


__all__ = ["request_json", "request_bytes", "ElevenLabsApiError",
           "ConfirmationRequiredError", "RefusedError"]
