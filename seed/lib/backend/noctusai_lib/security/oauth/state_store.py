"""`OAuthStateStore` -- server-bound, single-use OAuth `state` (+ the PKCE verifier it carries).

WHY a seam (Protocol + Fake + Real + factory)
---------------------------------------------
`oauth_router` only checks that a `state` is one this product issued (`verify_state`); it neither remembers WHO
started the flow nor the PKCE `code_verifier` that `GoogleProvider(use_pkce=True).exchange_code` needs at the
callback. A stateless HMAC `state` cannot carry the verifier (it would travel through the browser, defeating PKCE),
so a product that wants PKCE + a replay-proof state needs a server-side record. This is that record:

* `issue(...)` -> `IssuedState(state, browser_nonce)`: an opaque random `state` (256 bits) AND a random
  `browser_nonce` the caller hands to the BROWSER that started the flow (a host-only HttpOnly cookie). Only SHA-256s
  are stored (state, nonce); the verifier is Fernet-encrypted. Issuing also deletes the user's earlier unconsumed
  rows for the same (provider, org, user): one flow in flight per user.
* `consume(state, provider=, binding=)` -> the record, ONCE. A second call, an unknown state, another provider, an
  expired one, or a `binding` that is missing / is not the nonce of that state all return `None` (the caller answers
  400). The binding is what stops login-CSRF / account-linking: without it, anyone who started a flow could hand the
  consent URL to a victim and the callback would store the VICTIM's grant under the attacker's org. Consumption is a
  single `DELETE ... RETURNING` (atomic: two concurrent callbacks cannot both win) and a wrong binding still burns
  the state; the binding is compared in constant time.

Expected table (the consumer owns the migration)::

    create table <schema>.oauth_states (
      state_hash text primary key,            -- sha256(state), hex
      binding_hash text not null,             -- sha256(browser nonce), hex
      provider text not null,
      org_id text not null,
      user_id text not null,
      redirect_uri text not null,
      encrypted_code_verifier text not null,  -- Fernet(verifier)
      expires_at timestamptz not null,
      created_at timestamptz not null default now()
    );
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, NamedTuple, Optional, Protocol

from noctusai_lib.security.encrypted_tokens import decrypt, encrypt

DEFAULT_TABLE = "oauth_states"
DEFAULT_TTL_SECONDS = 600


@dataclass(frozen=True)
class OAuthStateRecord:
    """What a consumed `state` was issued for."""

    provider: str
    org_id: str
    user_id: str
    redirect_uri: str
    code_verifier: str


class IssuedState(NamedTuple):
    state: str          # goes in the consent URL
    browser_nonce: str  # goes in the starting browser's cookie; presented back as `binding=` at the callback


class OAuthStateStore(Protocol):
    def issue(
        self, *, provider: str, org_id: str, user_id: str, redirect_uri: str, code_verifier: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> IssuedState: ...

    def consume(self, state: str, *, provider: str, binding: Optional[str]) -> Optional[OAuthStateRecord]: ...


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _binding_ok(binding_hash: str, binding: Optional[str]) -> bool:
    return bool(binding) and hmac.compare_digest(binding_hash, _hash(binding))


def _parse_ts(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


class FakeOAuthStateStore:
    """In-memory store (tests + FakeMode). Same single-use / expiry / provider semantics as the Real one."""

    def __init__(self, *, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._now = now
        self._rows: dict[str, tuple[OAuthStateRecord, datetime, str]] = {}

    def issue(self, *, provider, org_id, user_id, redirect_uri, code_verifier, ttl_seconds=DEFAULT_TTL_SECONDS) -> IssuedState:
        for key in [k for k, (r, _e, _b) in self._rows.items() if (r.provider, r.org_id, r.user_id) == (provider, org_id, user_id)]:
            del self._rows[key]
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._rows[_hash(state)] = (
            OAuthStateRecord(provider, org_id, user_id, redirect_uri, code_verifier),
            self._now() + timedelta(seconds=ttl_seconds),
            _hash(nonce),
        )
        return IssuedState(state, nonce)

    def consume(self, state: str, *, provider: str, binding: Optional[str]) -> Optional[OAuthStateRecord]:
        entry = self._rows.pop(_hash(state), None)
        if entry is None:
            return None
        record, expires_at, binding_hash = entry
        if record.provider != provider or expires_at <= self._now() or not _binding_ok(binding_hash, binding):
            return None
        return record


class SupabaseOAuthStateStore:
    """Supabase-backed store: hashed state, Fernet-encrypted verifier, atomic single-use consume."""

    def __init__(self, client, fernet_key: bytes, *, table: str = DEFAULT_TABLE) -> None:
        if not fernet_key:
            raise ValueError("SupabaseOAuthStateStore requires a non-empty fernet_key")
        self._client = client
        self._key = fernet_key
        self._table = table

    def issue(self, *, provider, org_id, user_id, redirect_uri, code_verifier, ttl_seconds=DEFAULT_TTL_SECONDS) -> IssuedState:
        now = datetime.now(timezone.utc)
        # housekeeping: expired rows never accumulate (consume() re-checks expiry anyway) ...
        self._client.table(self._table).delete().lt("expires_at", now.isoformat()).execute()
        # ... and ONE flow in flight per user: an older unconsumed state of the same (provider, org, user) dies here
        (self._client.table(self._table).delete().eq("provider", provider).eq("org_id", org_id)
            .eq("user_id", user_id).execute())
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._client.table(self._table).insert({
            "state_hash": _hash(state),
            "binding_hash": _hash(nonce),
            "provider": provider,
            "org_id": org_id,
            "user_id": user_id,
            "redirect_uri": redirect_uri,
            "encrypted_code_verifier": encrypt(code_verifier, self._key),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
        }).execute()
        return IssuedState(state, nonce)

    def consume(self, state: str, *, provider: str, binding: Optional[str]) -> Optional[OAuthStateRecord]:
        resp = self._client.table(self._table).delete().eq("state_hash", _hash(state)).execute()
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        expires_at = _parse_ts(row.get("expires_at"))
        if (row.get("provider") != provider or expires_at is None or expires_at <= datetime.now(timezone.utc)
                or not _binding_ok(str(row.get("binding_hash") or ""), binding)):
            return None
        try:
            verifier = decrypt(row["encrypted_code_verifier"], self._key)
        except ValueError:
            return None  # tampered / wrong key: refuse, never a half-valid state
        return OAuthStateRecord(provider, str(row["org_id"]), str(row["user_id"]), row["redirect_uri"], verifier)


def make_oauth_state_store(*, client=None, fernet_key: Optional[bytes] = None, table: str = DEFAULT_TABLE) -> OAuthStateStore:
    """Real when `client` AND `fernet_key` are set; else the Fake (same default as `make_credential_store`)."""
    if client is not None and fernet_key:
        return SupabaseOAuthStateStore(client, fernet_key, table=table)
    return FakeOAuthStateStore()


__all__ = [
    "DEFAULT_TABLE", "DEFAULT_TTL_SECONDS", "FakeOAuthStateStore", "IssuedState", "OAuthStateRecord", "OAuthStateStore",
    "SupabaseOAuthStateStore", "make_oauth_state_store",
]
