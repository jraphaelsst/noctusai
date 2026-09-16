"""Rotating shared-secret key ring — one value, two readers (signer + verifier).

WHY
---
An HMAC shared secret (e.g. the `X-Approval-Assertion` key, contract §D of
`projects/julia-agents-academia-CONTRACT.md`) has two holders: the product
that SIGNS and the product that VERIFIES. Rotating it by hand means
"prepend the new key on both sides, deploy both, then drop the old one" —
two env edits, two redeploys, and a window where a half-done rotation breaks
every signed call.

This module makes the rotation a single stored value both sides read
through the same resolver, so it can be done from a UI:

- Each key carries ``active_from`` and an optional ``retire_at``.
- The SIGNER uses :meth:`KeyRing.signing_key` — the newest key already
  active. A freshly rotated key is NOT signed with until ``active_from``,
  which gives every verifier's read cache time to learn it first.
- The VERIFIER accepts :meth:`KeyRing.accepted` — every key not yet
  retired, INCLUDING a staged one. So by the time the signer switches, the
  verifier already accepts the new key; and the old key stays accepted
  until ``retire_at``, so an assertion minted just before the switch still
  verifies.

Legacy / env form
-----------------
A plain comma-separated value (the ``APPROVAL_ASSERTION_SECRETS`` env
shape) decodes to a ring whose keys are all active since the epoch and
never retire; :meth:`signing_key` then returns element ``[0]`` — exactly
the contract's historical "sign with element [0], accept any element".

Pure module (no IO) — resolution composes an injected
`noctusai_lib.security.app_config.AppConfigStore`; the crypto-/pure-logic
exemption from Protocol+Fake+Real applies
(`KB § PATTERNS/backend/seed-fake-real-adapter.md`).
"""

from __future__ import annotations

import hashlib
import json
import secrets as _secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional

from noctusai_lib.config.csv_settings import parse_csv_setting
from noctusai_lib.security.app_config import AppConfigStore, resolve_app_config_value

__all__ = [
    "KeyRing",
    "RingKey",
    "fingerprint",
    "generate_ring_secret",
    "resolve_key_ring",
]

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_FORMAT_VERSION = 1


def fingerprint(secret: str) -> str:
    """A non-reversible 12-hex identifier for a secret, safe to display.

    A PREFIX of an HMAC key is key material; a digest prefix is not. UIs
    and logs identify ring keys by this, never by any slice of the key.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def generate_ring_secret() -> str:
    """A fresh 256-bit URL-safe secret (no commas — the CSV form stays valid)."""
    return _secrets.token_urlsafe(32)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class RingKey:
    secret: str
    active_from: datetime
    retire_at: Optional[datetime] = None

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.secret)

    def is_retired(self, now: datetime) -> bool:
        return self.retire_at is not None and self.retire_at <= now

    def is_active(self, now: datetime) -> bool:
        return self.active_from <= now and not self.is_retired(now)


@dataclass(frozen=True)
class KeyRing:
    keys: tuple[RingKey, ...] = ()

    # ── decode / encode ────────────────────────────────────────────────

    @classmethod
    def from_value(cls, value: Optional[str]) -> "KeyRing":
        """Decode the stored JSON form, or the legacy CSV form.

        Raises ``ValueError`` on a JSON value that does not match the
        schema — a malformed ring is never read as "no keys" (that would
        silently stop every signed call).
        """
        if not value or not value.strip():
            return cls()
        text = value.strip()
        if text.startswith("{"):
            data = json.loads(text)
            if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
                raise ValueError("key ring JSON must be an object with a 'keys' list")
            keys = []
            for raw in data["keys"]:
                if not isinstance(raw, dict) or not raw.get("secret"):
                    raise ValueError("every key ring entry needs a non-empty 'secret'")
                keys.append(
                    RingKey(
                        secret=str(raw["secret"]),
                        active_from=_parse_ts(raw.get("active_from")) or _EPOCH,
                        retire_at=_parse_ts(raw.get("retire_at")),
                    )
                )
            return cls(tuple(keys))
        return cls(tuple(RingKey(secret=s, active_from=_EPOCH) for s in parse_csv_setting(text)))

    def to_value(self) -> str:
        return json.dumps(
            {
                "v": _FORMAT_VERSION,
                "keys": [
                    {
                        "secret": k.secret,
                        "active_from": k.active_from.isoformat(),
                        "retire_at": k.retire_at.isoformat() if k.retire_at else None,
                    }
                    for k in self.keys
                ],
            },
            separators=(",", ":"),
        )

    # ── reads ──────────────────────────────────────────────────────────

    def signing_key(self, now: datetime) -> Optional[RingKey]:
        """The newest ACTIVE key; ties keep list order (legacy CSV → ``[0]``)."""
        best: Optional[RingKey] = None
        for key in self.keys:
            if key.is_active(now) and (best is None or key.active_from > best.active_from):
                best = key
        return best

    def accepted(self, now: datetime) -> list[str]:
        """Every secret a verifier must accept at ``now`` (staged keys included)."""
        return [k.secret for k in self.keys if not k.is_retired(now)]

    # ── transitions ────────────────────────────────────────────────────

    def rotate(
        self,
        new_secret: str,
        *,
        now: datetime,
        activation_delay: timedelta,
        retire_after: timedelta,
    ) -> "KeyRing":
        """Stage ``new_secret`` (signing starts at ``now + activation_delay``)
        and schedule every other un-retired key to retire at
        ``now + activation_delay + retire_after``.

        ``retire_after`` must cover how long an assertion signed with the
        OLD key can still be in flight — it is measured from the moment the
        signer switches, not from ``now``.
        """
        if not new_secret or "," in new_secret:
            raise ValueError("a ring secret must be non-empty and contain no comma")
        if any(k.secret == new_secret for k in self.keys):
            raise ValueError("that secret is already in the ring")
        switch_at = now + activation_delay
        retire_at = switch_at + retire_after
        kept = tuple(
            k if k.is_retired(now) else replace(
                k, retire_at=min(k.retire_at, retire_at) if k.retire_at else retire_at
            )
            for k in self.keys
        )
        return KeyRing((RingKey(secret=new_secret, active_from=switch_at),) + kept)

    def prune(self, now: datetime) -> "KeyRing":
        """Drop keys whose ``retire_at`` has passed."""
        return KeyRing(tuple(k for k in self.keys if not k.is_retired(now)))


def resolve_key_ring(
    store: AppConfigStore,
    key: str,
    *,
    env_value: Optional[str],
) -> KeyRing:
    """DB-first / env-fallback ring. BOTH the signer and the verifier call
    this with the same ``key`` — that single resolution rule is what keeps
    a UI-driven rotation consistent on both sides by construction."""
    value, _ = resolve_app_config_value(store, key, env_value=env_value)
    return KeyRing.from_value(value)
