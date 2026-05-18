"""Factory for `GmailClient` — Fake or Real, by flag + credential presence.

Mirrors the canonical Protocol+Fake+Real+factory shape established by
`integrations/google_calendar` + `youtube` + `google_drive`. The
factory is the single seam consumers reach for.

**Gmail-specific routing** (the one deviation from the youtube/drive
factory, justified by Gmail being OAuth-only): Gmail has no API-key
path for a user mailbox, so when `use_fake=False` AND no
`oauth_credentials` were resolved, the factory returns
`FakeGmailClient` — the same "no credentials for this tenant → Fake"
fallback the Calendar resolver pattern uses (a missing per-tenant
OAuth token is the *expected* not-yet-connected state, not an error).
Constructing a Real client with no OAuth (e.g. an explicit
`use_fake=False` + an api-key-only call) still raises `ValueError`
inside `RealGmailClient.__init__` (fail loud — never a silent degrade
to an empty mailbox).
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.gmail.fake import FakeGmailClient
from noctusai_lib.integrations.gmail.protocol import GmailClient


def make_gmail_client(
    *,
    use_fake: bool = False,
    api_key: str | None = None,
    oauth_credentials: Any = None,
    fake_seed_data: dict[str, Any] | None = None,
) -> GmailClient:
    """Build a `GmailClient`.

    - `use_fake=True` → returns `FakeGmailClient`, optionally
      pre-populated by `fake_seed_data` with key `messages`
      (a list of `GmailMessage`). Useful for tests and local dev.
    - `use_fake=False` with `oauth_credentials` → returns
      `RealGmailClient`.
    - `use_fake=False` WITHOUT `oauth_credentials` → returns
      `FakeGmailClient` (the "tenant not yet connected" fallback;
      mirrors the Calendar resolver pattern — a missing per-tenant
      token is the expected not-connected state, not an error). To
      force a loud failure instead, construct `RealGmailClient`
      directly.

    `api_key` is accepted for factory-shape parity with the
    youtube/drive adapters but is inert for Gmail (no API-key path
    exists for a user mailbox).

    Lazy import of `RealGmailClient` keeps the fake path importable
    in slim environments that don't ship `google-api-python-client`."""
    if use_fake or oauth_credentials is None:
        seed = fake_seed_data or {}
        return FakeGmailClient(messages=seed.get("messages"))

    # Lazy import — googleapiclient is heavy.
    from noctusai_lib.integrations.gmail.real import RealGmailClient

    return RealGmailClient(api_key=api_key, oauth_credentials=oauth_credentials)


__all__ = ["make_gmail_client"]
