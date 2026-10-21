"""Short-TTL POSITIVE cache of validated Supabase access tokens.

Every authenticated request used to call Supabase Auth ``get_user`` (a network
round-trip, ~25-50 ms) to turn the bearer token into a user — and the SPA fires
several requests at once, so the same token was validated N times a second.
This caches the *verified user* for ``ttl`` seconds (default
:data:`DEFAULT_TTL_S` = 30; ``Settings.auth_token_cache_ttl_seconds``; ``0``
disables).

Security contract (owner-approved 2026-10-21):

* **Revocation latency.** A session revoked in Supabase (logout, password
  change, admin sign-out) can keep working for up to ``ttl`` seconds on a
  process that already cached it. This is the accepted trade-off; the logout
  path evicts explicitly (:meth:`TokenCache.discard`) so the user's *own*
  logout is immediate on that process.
* **Never the raw token.** Entries are keyed by ``sha256(token)``; the token
  itself is never stored, logged or returned.
* **Positive results only.** A rejection / outage / "no user" is never cached,
  so a token that becomes valid (or a provider that recovers) works at once.
* **Never past the token's own ``exp``.** The entry expires at
  ``min(now + ttl, exp)`` where ``exp`` is read from the JWT *after* Supabase
  accepted it (the claim is not trusted for anything else); a token with no
  readable ``exp`` is not cached at all.
* **Bounded.** LRU with ``max_entries``.
* **Only the verified user payload** is stored (a deep copy on the way in and
  out, so a handler mutating ``user`` cannot poison the next request).
* **Per-validator.** Each ``make_get_current_user*`` factory call / each
  ``ProductDependencies`` owns its own cache instance, so nothing is shared
  across apps or tests.

Thread-safe: one lock around the ``OrderedDict``; ``get``/``put`` are O(1).
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import weakref
from collections import OrderedDict
from typing import Any, Optional

import jwt

logger = logging.getLogger(__name__)

#: Owner-chosen value (2026-10-21). A revoked session may keep working this long.
DEFAULT_TTL_S: float = 30.0
DEFAULT_MAX_ENTRIES: int = 2048

#: Process-level TTL, set once at app build from settings; read on every ``put``.
_configured_ttl_s: float = DEFAULT_TTL_S


def configure_token_cache(ttl_s: Optional[float]) -> None:
    """Set the process TTL (seconds). ``None`` restores the default, ``0`` disables."""
    global _configured_ttl_s
    if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)):
        _configured_ttl_s = DEFAULT_TTL_S  # unset / not a number (e.g. a test double): the default
    else:
        _configured_ttl_s = max(0.0, float(ttl_s))


def configured_ttl_s() -> float:
    return _configured_ttl_s


def token_digest(token: str) -> str:
    """The cache key: ``sha256(token)`` hex — the raw token is never a key."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_exp(token: str) -> Optional[float]:
    """The JWT's ``exp`` (epoch seconds) or ``None``. Unverified read — only ever
    called for a token the auth provider has ALREADY accepted."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
    except Exception:  # noqa: BLE001 - an unreadable token is simply not cached
        return None
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    return float(exp)


def _copy(user: Any) -> Any:
    model_copy = getattr(user, "model_copy", None)
    if callable(model_copy):
        return model_copy(deep=True)
    import copy

    return copy.deepcopy(user)


#: Every live cache, so a logout can evict its token from all of them.
_instances: "weakref.WeakSet[TokenCache]" = weakref.WeakSet()


def discard_token_everywhere(token: str) -> int:
    """Evict ``token`` from every live cache in this process (logout / explicit
    revoke). Returns how many caches held it."""
    return sum(1 for cache in list(_instances) if cache.discard(token))


class TokenCache:
    """LRU + TTL map ``sha256(token) -> verified user``."""

    def __init__(self, *, max_entries: int = DEFAULT_MAX_ENTRIES, ttl_s: Optional[float] = None):
        self._max = max_entries
        self._ttl_override = ttl_s  # None => follow the process setting
        self._lock = threading.Lock()
        self._store: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        _instances.add(self)

    @property
    def ttl_s(self) -> float:
        return _configured_ttl_s if self._ttl_override is None else self._ttl_override

    def get(self, token: str) -> Optional[Any]:
        """A copy of the cached verified user, or ``None`` (absent / expired / disabled)."""
        if self.ttl_s <= 0:
            return None
        key = token_digest(token)
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            user, expires_at = entry
            if now >= expires_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
        return _copy(user)

    def put(self, token: str, user: Any) -> bool:
        """Cache ``user`` for ``min(ttl, token exp)``. True iff stored.

        CALL ONLY with a user the auth provider just verified — never for a
        failure (the callers have nothing to pass).
        """
        ttl = self.ttl_s
        if ttl <= 0 or user is None:
            return False
        exp = _token_exp(token)
        if exp is None:
            return False
        remaining = exp - time.time()
        if remaining <= 0:
            return False
        lifetime = min(ttl, remaining)
        key = token_digest(token)
        entry = (_copy(user), time.monotonic() + lifetime)
        with self._lock:
            self._store[key] = entry
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)
        return True

    def discard(self, token: str) -> bool:
        """Evict one token (the logout path). True iff it was cached."""
        with self._lock:
            return self._store.pop(token_digest(token), None) is not None

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
