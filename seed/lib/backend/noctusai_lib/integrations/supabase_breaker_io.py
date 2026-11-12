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

    #: True when this store runs on the APP Redis because `NOCTUS_BREAKER_REDIS_URL` is unset (the app marks it degraded)
    on_app_redis_fallback = False

    def __init__(self, client: Any) -> None:
        self._r = client

    def get(self, key: str) -> Optional[str]:
        return self._r.get(key)

    def mget(self, keys: list[str]) -> list[Optional[str]]:
        return list(self._r.mget(keys))

    @staticmethod
    def index_key(key: str) -> Optional[str]:
        """``noctus:breaker:<slug>:<source>`` -> its per-slug index set ``noctus:breaker:<slug>:index`` (None for the
        fleet key and anything else outside a product namespace). A product has RW only on its own namespace and the
        ops identity has no SCAN, so enumeration goes through this index (SADD here, SMEMBERS/SREM by ops)."""
        parts = key.split(":", 3)
        if len(parts) < 4 or parts[0] != "noctus" or parts[1] != "breaker" or parts[3] in ("index", "audit") or parts[3].startswith("rearm:"):
            return None
        return f"noctus:breaker:{parts[2]}:index"

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        # no TTL for a trip by design (it persists across restarts until a human re-arms); a re-arm MARKER gets one
        self._r.set(key, value, ex=ttl) if ttl else self._r.set(key, value)
        idx = self.index_key(key)
        if idx:
            self._r.sadd(idx, key)

    def lrange(self, key: str, count: int) -> list[str]:
        return list(self._r.lrange(key, -count, -1))

    def index(self, key: str) -> None:
        idx = self.index_key(key)
        if idx:
            self._r.sadd(idx, key)

    def delete(self, key: str) -> None:
        self._r.delete(key)
        idx = self.index_key(key)
        if idx:
            self._r.srem(idx, key)

    def append_audit(self, key: str, value: str, cap: int) -> None:
        pipe = self._r.pipeline(transaction=False)  # batching only: MULTI/EXEC are not in a product's ACL grant
        pipe.rpush(key, value)
        pipe.ltrim(key, -cap, -1)  # capped: the audit list never grows without bound
        pipe.execute()


BREAKER_REDIS_URL_ENV = "NOCTUS_BREAKER_REDIS_URL"
BREAKER_REDIS_USER_ENV = "NOCTUS_BREAKER_REDIS_USERNAME"
BREAKER_REDIS_PASS_ENV = "NOCTUS_BREAKER_REDIS_PASSWORD"


def make_breaker_store(
    redis_url: Optional[str] = None, *, use_fake: bool = False, environ: Optional[dict[str, str]] = None,
    deploy: Optional[bool] = None,
) -> Any:
    """The breaker's store: the DEDICATED breaker Redis (feat/redis-acl-lockdown) when ``NOCTUS_BREAKER_REDIS_URL`` is set —
    credentials passed explicitly (``NOCTUS_BREAKER_REDIS_USERNAME`` / ``..._PASSWORD``; ``REDIS_*`` stays the app
    connection). Unset: in a DEPLOY context fall back to the app Redis (``redis_url`` / ``REDIS_URL``) with a loud warning
    (the cutover is per service and gradual); outside a deploy keep the in-memory Fake. ``use_fake`` always wins."""
    if use_fake:
        return InMemoryBreakerStore()
    env = environ if environ is not None else os.environ
    from noctusai_lib.integrations.redis import make_redis_client

    breaker_url = (env.get(BREAKER_REDIS_URL_ENV) or "").strip()
    if breaker_url:
        from noctusai_lib.integrations.redis import RedisAuthRequired

        try:
            # ONLY the breaker credentials: "" (not None) stops the seam falling back to REDIS_USERNAME/REDIS_PASSWORD,
            # and require_auth=True refuses to connect unauthenticated.
            client = make_redis_client(
                breaker_url,
                username=(env.get(BREAKER_REDIS_USER_ENV) or ""),
                password=(env.get(BREAKER_REDIS_PASS_ENV) or ""),
                require_auth=True,
                socket_connect_timeout=2, socket_timeout=2,
            )
        except RedisAuthRequired as exc:
            logger.critical("breaker: %s is set but no breaker credentials resolved (%s / %s): refusing to connect "
                            "unauthenticated — the breaker runs on the in-memory Fake (degraded)",
                            BREAKER_REDIS_URL_ENV, BREAKER_REDIS_USER_ENV, BREAKER_REDIS_PASS_ENV)
            return InMemoryBreakerStore()
        return RedisBreakerStore(client)
    if deploy is None:
        from noctusai_lib.config.deploy_config import is_deploy_context

        deploy = is_deploy_context()
    app_url = redis_url or env.get("REDIS_URL") or ""
    if deploy and app_url:
        # NOC-REMEDIATE[breaker-redis-cutover]: set NOCTUS_BREAKER_REDIS_URL/USERNAME/PASSWORD for this service (the per-service env file of feat/redis-acl-lockdown) so the breaker leaves the app Redis — destination: the redis-acl-lockdown rollout, service by service — 2026-11-10
        logger.warning("breaker: %s is unset — falling back to the APP Redis for breaker keys. After the ACL cutover the app "
                       "user has no breaker keys and every breaker write fails NOPERM: set the dedicated breaker Redis "
                       "credentials (NOC-REMEDIATE[breaker-redis-cutover]).", BREAKER_REDIS_URL_ENV)
        fallback = RedisBreakerStore(make_redis_client(app_url, socket_connect_timeout=2, socket_timeout=2))
        fallback.on_app_redis_fallback = True
        return fallback
    logger.error("breaker: no %s%s — trips are held in memory only (lost on restart, invisible to the fleet key and the "
                 "MCP tool)", BREAKER_REDIS_URL_ENV, " and no app Redis" if deploy else " (not a deploy context)")
    return InMemoryBreakerStore()


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
