"""One error type for the whole `live_rooms` package.

Mirrors `noctusai_lib.integrations.payments.errors.PaymentGatewayError`'s
rationale: a call can happen inside a request handler, a background
job, or a webhook receiver, so raising an HTTP-flavored exception here
would be the wrong shape. A consumer's router/service translates
`LiveRoomError` to whatever surface it needs (HTTP 503, a persisted
failure flag, a retry) — see `KB § PATTERNS/backend/live-rooms-livekit.md`.

Deliberately NOT a silent fallback. The former
`products/therapy-platform/backend/app/services/livekit_service.py`
caught every real-provider exception, logged it, and returned
`{"mock": True, "error": ...}` — a live-prod LiveKit outage looked
identical to a successful mock-mode call. Both `RealLiveKitProvider` and
`FakeLiveRoomProvider` raise this SAME class (never swallow), so a
consumer catches one exception type regardless of which provider is
configured.
"""
from __future__ import annotations


class LiveRoomError(Exception):
    """A call to the configured live-room provider failed.

    Args:
        op: the Protocol method that failed (`"create_room"`,
            `"start_recording"`, ...) — lets a catcher log/branch
            without string-matching the message.
        detail: human-readable detail, usually `str(original_exception)`.
    """

    def __init__(self, op: str, detail: str) -> None:
        self.op = op
        self.detail = detail
        super().__init__(f"[{op}] {detail}")

    def __repr__(self) -> str:  # pragma: no cover - diagnostic
        return f"LiveRoomError(op={self.op!r}, detail={self.detail!r})"


class LiveRoomNotConfigured(LiveRoomError):
    """Raised by `make_live_room_provider` when `use_fake=False` and the
    real provider's required credentials (`url`/`api_key`/`api_secret`)
    are missing.

    Distinct from a runtime `LiveRoomError` so a caller can distinguish
    "misconfigured" (a startup/deploy problem) from "the provider call
    itself failed" (a runtime/outage problem).
    """

    def __init__(self, detail: str) -> None:
        super().__init__("configure", detail)


__all__ = ["LiveRoomError", "LiveRoomNotConfigured"]
