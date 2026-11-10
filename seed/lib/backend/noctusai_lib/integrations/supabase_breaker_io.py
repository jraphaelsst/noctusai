"""IO for the Supabase breaker: Redis state store + owner email alerter (Fake + Real + factory).

Neither depends on Supabase (the thing that may be down) nor on the WhatsApp owner line (latent, not configured in
prod). Redis goes through the seam (`integrations.redis.make_redis_client`); the email goes through the seed's own
Resend sender (`integrations.email`), the same provider the platform watchdog uses. Missing config is NEVER silent:
the Real alerter raises `BreakerAlertNotConfigured` naming exactly what is missing, which the breaker logs at CRITICAL
and keeps for retry.

KB § PATTERNS/backend/supabase-request-breaker.md
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from noctusai_lib.primitives.supabase_breaker import (
    BreakerAlertNotConfigured,
    InMemoryBreakerStore,
    RecordingAlerter,
)

logger = logging.getLogger(__name__)

__all__ = [
    "RedisBreakerStore",
    "ResendBreakerAlerter",
    "make_breaker_alerter",
    "make_breaker_store",
]

ALERT_EMAIL_ENVS = ("NOCTUS_BREAKER_ALERT_EMAIL", "WATCHDOG_ALERT_EMAIL")
ALERT_FROM_ENV = "NOCTUS_BREAKER_ALERT_FROM"
DEFAULT_FROM = "NoctusAI <noreply@noctusai.com>"  # same sender the prod watchdog uses


class RedisBreakerStore:
    """`BreakerStore` over a sync Redis client from the seam. Short socket timeouts: a dead Redis must fail fast
    (the breaker fails open), never hang a request or a worker."""

    def __init__(self, client: Any) -> None:
        self._r = client

    def get(self, key: str) -> Optional[str]:
        return self._r.get(key)

    def mget(self, keys: list[str]) -> list[Optional[str]]:
        return list(self._r.mget(keys))

    def set(self, key: str, value: str) -> None:
        self._r.set(key, value)  # no TTL by design: a trip persists across restarts until a human re-arms

    def delete(self, key: str) -> None:
        self._r.delete(key)


def make_breaker_store(redis_url: Optional[str] = None, *, use_fake: bool = False) -> Any:
    """Real Redis store when a URL resolves, else (or ``use_fake``) the in-memory Fake.

    A missing URL returns the Fake AND logs loudly: a breaker whose trips do not persist is a degraded breaker."""
    if use_fake:
        return InMemoryBreakerStore()
    url = redis_url or os.environ.get("REDIS_URL") or ""
    if not url:
        logger.error("breaker: no REDIS_URL — trips will be held in memory only (lost on restart, invisible to the "
                     "fleet key and the MCP tool)")
        return InMemoryBreakerStore()
    from noctusai_lib.integrations.redis import make_redis_client

    return RedisBreakerStore(make_redis_client(url, socket_connect_timeout=2, socket_timeout=2))


class ResendBreakerAlerter:
    """Owner email via the seed Resend sender. Raises `BreakerAlertNotConfigured` naming what is missing."""

    def __init__(self, environ: Optional[dict[str, str]] = None, *, sender_factory: Any = None) -> None:
        self._env = environ if environ is not None else os.environ
        self._sender_factory = sender_factory

    def _config(self) -> tuple[str, str, str]:
        api_key = (self._env.get("RESEND_API_KEY") or "").strip()
        to = next((v.strip() for k in ALERT_EMAIL_ENVS if (v := self._env.get(k))), "")
        missing = [n for n, v in (("RESEND_API_KEY", api_key), (" or ".join(ALERT_EMAIL_ENVS), to)) if not v]
        if missing:
            raise BreakerAlertNotConfigured(f"breaker alert email is not configured — missing {', '.join(missing)}")
        return api_key, to, (self._env.get(ALERT_FROM_ENV) or DEFAULT_FROM).strip()

    def send(self, subject: str, body: str) -> None:
        from noctusai_lib.integrations.email import OutgoingEmail, make_email_sender
        from noctusai_lib.integrations.email.resend_adapter import ResendConfig

        api_key, to, sender = self._config()
        name, _, addr = sender.partition("<")
        cfg = ResendConfig(api_key=api_key, from_email=(addr.rstrip(">") or name).strip(),
                           from_name=name.strip() if addr else "")
        email_sender = (self._sender_factory or make_email_sender)(cfg)
        # Runs on a daemon thread (never inside a request / event loop): a private loop is safe here.
        asyncio.run(email_sender.send(OutgoingEmail(to=[to], subject=subject, text=body)))


def make_breaker_alerter(*, use_fake: bool = False) -> Any:
    return RecordingAlerter() if use_fake else ResendBreakerAlerter()
