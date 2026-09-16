"""App-level encrypted key→value config store — Protocol+Fake+Real+factory.

WHY a seam (Protocol + Fake + Real + factory)
----------------------------------------------
Some product-wide settings are credential-shaped (a vendor App ID / App
Secret, a default sender key, …) but are NOT per-(org, provider) the way
`noctusai_lib.security.token_store` is — they apply to the whole product
deployment, one row per config key. Today these are env-only
(``META_APP_ID`` / ``META_APP_SECRET``); this module introduces a
DB-backed alternative so an admin can set them in-app (Settings → DB,
encrypted) with env as the fallback, without inventing a second crypto
primitive or a second IO shape. Per
`KB § PATTERNS/backend/seed-fake-real-adapter.md` it ships in the
canonical Protocol+Fake+Real+factory shape — this touches IO (a Supabase
table) so a Fake here exercises genuinely different code than the Real
(in-memory dict vs. encrypted Supabase UPSERT).

Mirrors `noctusai_lib.security.token_store` deliberately: same Fernet
helper (`noctusai_lib.security.encrypted_tokens`), same
Protocol/Fake/Real/factory shape, same UPSERT-on-natural-key semantics —
just keyed on a single ``key`` column instead of ``(org_id, provider)``.

Public surface (the contract Wave 2 — the product DB table + Settings UI
wiring — depends on)
--------------------------------------------------------------------------
- ``AppConfigStore`` — the 4-method Protocol
  (``get / put / delete / list_keys``).
- ``AppConfigDecryptError`` — raised on key mismatch (fail-loud; never a
  silent ``None``), mirroring ``CredentialDecryptError``.
- ``FakeAppConfigStore`` — in-memory; the dev/test default.
- ``RealAppConfigStore`` — Fernet-encrypted Supabase rows.
- ``build_app_config_store(client=, fernet_key=, table=)`` — factory.
  Returns ``RealAppConfigStore`` when BOTH ``client`` and ``fernet_key``
  are provided; otherwise ``FakeAppConfigStore`` (default-Fake mirrors
  `make_credential_store` / `google_maps` / `google_calendar`).
- ``CachedAppConfigStore(inner, ttl_seconds=)`` — a short-TTL read
  cache over any store, invalidated on this process's own writes, so a
  runtime can read a secret per use without a DB round-trip per call and
  still pick up a value changed in-app without a redeploy.
- ``resolve_app_config_value(store, key, *, env_value)`` — the general
  DB-first / env-fallback resolver (returns the value AND where it came
  from, for status UIs).
- ``resolve_meta_app_credentials(store, *, env_app_id, env_app_secret)``
  — pure helper: DB value wins per key, falls back to the env value for
  that key independently (partial DB config is honored, not
  all-or-nothing).

Method contract (exact — do not drift):
- ``get(key) -> str | None`` — decrypt-on-read.
- ``put(key, value) -> None`` — UPSERT on ``key``; encrypt-before-write.
- ``delete(key) -> bool`` — idempotent.
- ``list_keys() -> list[str]`` — KEY NAMES ONLY, never values, no
  decrypt (cheap; for a Settings-UI "which keys are configured" list).

Expected table shape (Wave 2 owns the migration — the store is
schema-agnostic beyond these columns)::

    create table <schema>.app_integration_config (
      key             text primary key,
      encrypted_value text not null,   -- Fernet(value)
      updated_at      timestamptz not null default now()
    );
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Literal, Optional, Protocol

from noctusai_lib.security.encrypted_tokens import decrypt, encrypt

logger = logging.getLogger(__name__)

DEFAULT_TABLE = "app_integration_config"

# The two well-known keys `resolve_meta_app_credentials` reads. Kept as
# module constants so Wave 2's migration + Settings UI reference the
# same literal the resolver does (no drift between "what the resolver
# reads" and "what the UI writes").
META_APP_ID_KEY = "meta_app_id"
META_APP_SECRET_KEY = "meta_app_secret"


class AppConfigStore(Protocol):
    """App-wide encrypted key→value config persistence.

    Contract (every implementation MUST honor this exactly):

    - ``get(key)`` → ``str`` or ``None``. Decrypts on read. Raises
      ``AppConfigDecryptError`` (NOT ``None``, NOT an empty string) when
      a row exists but cannot be decrypted with the configured key —
      fail-loud on key mismatch, mirroring `CredentialStore.get`.
    - ``put(key, value)`` → ``None``. UPSERT semantics on the ``key``
      natural key: a second call for the same key overwrites. Encrypts
      before write.
    - ``delete(key)`` → ``bool``. True if a row existed and was removed,
      False if nothing was there (idempotent).
    - ``list_keys()`` → ``list[str]``. Key NAMES this store has values
      for. Does NOT decrypt — never returns values in bulk (a Settings
      UI "which integrations are configured" list must not leak
      secrets).
    """

    def get(self, key: str) -> Optional[str]: ...

    def put(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> bool: ...

    def list_keys(self) -> list[str]: ...


class AppConfigDecryptError(RuntimeError):
    """Raised when a stored config row exists but cannot be decrypted.

    Signals a key mismatch / rotation gap / tampered ciphertext. The
    store NEVER returns ``None`` or an empty string in this case — a
    silently-empty app credential would make every downstream adapter
    fail obscurely far from the root cause. Fail loud, here. Mirrors
    `CredentialDecryptError`.
    """


class FakeAppConfigStore(AppConfigStore):
    """Process-memory app-config store keyed by ``key``.

    Deterministic, network-free, no encryption (the in-memory dict IS
    the storage substrate — there is nothing at rest to protect).
    Mirrors `FakeCredentialStore`.
    """

    def __init__(self) -> None:
        self._rows: dict[str, str] = {}

    def get(self, key: str) -> Optional[str]:
        return self._rows.get(key)

    def put(self, key: str, value: str) -> None:
        self._rows[key] = value

    def delete(self, key: str) -> bool:
        return self._rows.pop(key, None) is not None

    def list_keys(self) -> list[str]:
        return sorted(self._rows)


class RealAppConfigStore(AppConfigStore):
    """Supabase-backed `AppConfigStore` — Fernet-encrypted rows at rest.

    Composes `noctusai_lib.security.encrypted_tokens` (the crypto
    primitive) for the at-rest boundary — the SAME helper
    `SupabaseCredentialStore` uses; this module does not reinvent
    encryption.

    Args:
        client: a Supabase client (service-role / admin) the store uses
            for reads + writes. The store does NOT manage RLS — it is
            an admin-context persistence layer for product-wide config,
            not per-org data.
        fernet_key: the Fernet key (``bytes``) the at-rest encryption
            uses. Source it from the product's secret manager / env
            (``ENCRYPTION_KEY`` / ``FERNET_KEY``) — NEVER hardcode.
        table: physical table name. Defaults to
            ``app_integration_config``. Pass a schema-qualified name if
            the client is not already schema-bound.
    """

    def __init__(
        self,
        client,
        fernet_key: bytes,
        *,
        table: str = DEFAULT_TABLE,
    ) -> None:
        if not fernet_key:
            raise ValueError("RealAppConfigStore requires a non-empty fernet_key")
        self._client = client
        self._key = fernet_key
        self._table = table

    def get(self, key: str) -> Optional[str]:
        resp = (
            self._client.table(self._table)
            .select("*")
            .eq("key", key)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        try:
            return decrypt(row["encrypted_value"], self._key)
        except ValueError as exc:
            # decrypt() raises ValueError on tamper / wrong key. A
            # stored row that won't decrypt is NEVER returned as None
            # / empty — that would fail every downstream adapter far
            # from the root cause. Fail loud, here.
            logger.error(
                "app_config: config row exists for key=%s but failed to "
                "decrypt — key mismatch or tampered ciphertext",
                key,
            )
            raise AppConfigDecryptError(
                f"cannot decrypt stored app config for key={key!r}"
            ) from exc

    def put(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc)
        encrypted = encrypt(value, self._key)
        payload = {
            "key": key,
            "encrypted_value": encrypted,
            "updated_at": now.isoformat(),
        }
        # UPSERT on the `key` natural key — re-setting a value
        # overwrites in place rather than accumulating rows.
        (
            self._client.table(self._table)
            .upsert(payload, on_conflict="key")
            .execute()
        )

    def delete(self, key: str) -> bool:
        resp = (
            self._client.table(self._table).delete().eq("key", key).execute()
        )
        return bool(resp.data)

    def list_keys(self) -> list[str]:
        resp = self._client.table(self._table).select("key").execute()
        return sorted(r["key"] for r in (resp.data or []))


#: Where a resolved value came from. ``None`` = neither tier had one.
ConfigSource = Literal["db", "env"]

_MISS = object()


class CachedAppConfigStore(AppConfigStore):
    """Short-TTL read cache in front of any :class:`AppConfigStore`.

    WHY
    ---
    A runtime that must pick up a credential changed in-app WITHOUT a
    redeploy has two honest options: read the store on every use, or read
    it through a cache whose staleness is bounded and small. Per-use reads
    put a DB round-trip (plus a Fernet decrypt) on every request; this
    wrapper bounds the staleness to ``ttl_seconds`` instead.

    Semantics
    ---------
    - ``get`` caches hits AND misses for ``ttl_seconds`` (a miss means
      "fall back to env", which is itself a value worth caching).
    - ``put`` / ``delete`` write through and invalidate that key at once,
      so the process that made the change never serves the stale value.
      OTHER processes see it within ``ttl_seconds``.
    - A decrypt failure (``AppConfigDecryptError``) is NEVER cached — it
      propagates every time, loudly, like the inner store's own contract.
    - ``list_keys`` is not cached (status UIs only; never a hot path).

    ``clock`` is a DI seam (monotonic seconds) so tests advance time
    without sleeping.
    """

    def __init__(
        self,
        inner: AppConfigStore,
        *,
        ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self._inner = inner
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> Optional[str]:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
        if entry is not None and now - entry[0] < self._ttl:
            cached = entry[1]
            return None if cached is _MISS else cached  # type: ignore[return-value]
        value = self._inner.get(key)
        with self._lock:
            self._entries[key] = (now, _MISS if value is None else value)
        return value

    def put(self, key: str, value: str) -> None:
        self._inner.put(key, value)
        self.invalidate(key)

    def delete(self, key: str) -> bool:
        removed = self._inner.delete(key)
        self.invalidate(key)
        return removed

    def list_keys(self) -> list[str]:
        return self._inner.list_keys()

    def invalidate(self, key: Optional[str] = None) -> None:
        """Drop one cached key (or every key when ``key`` is ``None``)."""
        with self._lock:
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)


def resolve_app_config_value(
    store: AppConfigStore,
    key: str,
    *,
    env_value: Optional[str],
) -> tuple[Optional[str], Optional[ConfigSource]]:
    """DB value wins; the env value is the fallback. Returns ``(value, source)``.

    The general form of :func:`resolve_meta_app_credentials` — one key,
    resolved independently. An empty-string env value counts as unset (a
    compose ``${VAR:-}`` expansion yields ``""``, never ``None``).

    A stored row that cannot be decrypted raises ``AppConfigDecryptError``
    — it does NOT silently fall back to env: an operator who stored a new
    value believes it is in effect, and serving the old env value instead
    would be a false green.
    """
    value = store.get(key)
    if value:
        return value, "db"
    if env_value:
        return env_value, "env"
    return None, None


def build_app_config_store(
    *,
    client=None,
    fernet_key: Optional[bytes] = None,
    table: str = DEFAULT_TABLE,
) -> AppConfigStore:
    """Real when ``client`` AND ``fernet_key`` are set; else Fake.

    Mirrors `make_credential_store` — the default is the Fake so a
    product that hasn't wired a key/client still boots and tests
    deterministically.
    """
    if client is not None and fernet_key:
        return RealAppConfigStore(client, fernet_key, table=table)
    return FakeAppConfigStore()


def resolve_meta_app_credentials(
    store: AppConfigStore,
    *,
    env_app_id: Optional[str],
    env_app_secret: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the Meta App ID/Secret pair: DB value wins, env is fallback.

    Each of the two keys (``meta_app_id`` / ``meta_app_secret``) is
    resolved INDEPENDENTLY — a store with only one of the two keys set
    still returns the DB value for that key and the env fallback for
    the other (partial DB config is honored, not all-or-nothing). Pure
    function of ``store.get(...)`` + the two env args — no IO beyond
    what the injected ``store`` performs, so it is trivially unit
    tested against a `FakeAppConfigStore`.

    Returns:
        ``(app_id, app_secret)`` — either element may be ``None`` if
        neither the DB nor the env supplied a value for that key.
    """
    app_id, _ = resolve_app_config_value(store, META_APP_ID_KEY, env_value=env_app_id)
    app_secret, _ = resolve_app_config_value(
        store, META_APP_SECRET_KEY, env_value=env_app_secret
    )
    return app_id, app_secret
