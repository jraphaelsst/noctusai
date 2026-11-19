"""The MCP's three seams into the seed TTS adapter (`noctusai_lib.integrations.tts`).

The adapter owns every ElevenLabs rule (guards, body, alignment, billing). This
file only supplies what the connector itself owns:

- `KitTransport`: routes the adapter's HTTP through `elevenlabs.api.request_*`
  (the connector's `_kit.transport` seam, the one its tests fake), turning its
  `ElevenLabsApiError` into the adapter's `TtsUpstreamError` (status kept).
- `OperatorConsent`: the connector's consent authority is the operator -- the
  confirm gate on every spend plus `consent_reference` on clone -- so the port
  says yes for the single reference `OPERATOR_CONSENT_REF`. Product code never
  uses this; it implements `ConsentChecker` against its own consent ledger.
"""
from __future__ import annotations

from typing import Callable, Optional

from _kit.transport import encode_multipart
from noctusai_lib.integrations.tts import TtsUpstreamError

from . import api

OPERATOR_CONSENT_REF = "mcp-operator-confirm"


class OperatorConsent:
    def vigente(self, org: Optional[str], voice_id: str) -> bool:
        return True


class KitTransport:
    def __init__(self, ctx: Callable[..., dict]) -> None:
        self._ctx = ctx

    def json(self, method, path, *, params=None, body=None, timeout=20.0):
        try:
            return api.request_json(method, path, params=params, body=body, **self._ctx(timeout))
        except api.ElevenLabsApiError as e:
            raise TtsUpstreamError(str(e), status=e.status) from e

    def bytes(self, method, path, *, params=None, body=None, files=None, data=None, timeout=120.0):
        raw = None
        if files is not None:
            raw = encode_multipart(data, [(name, f[0], f[1], f[2]) for name, f in files])
        try:
            return api.request_bytes(method, path, params=params, body=body, raw_body=raw, **self._ctx(timeout))
        except api.ElevenLabsApiError as e:
            raise TtsUpstreamError(str(e), status=e.status) from e
