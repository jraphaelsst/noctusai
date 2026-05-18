"""Gmail API v1 client — canonical Protocol+Fake+Real+factory.

Lifted 2026-05-18 by `projects/mcp-connector-expansion/` to close the
last gap in the Google seed family: Calendar / Maps / YouTube / Drive
all shipped a seed adapter; Gmail did not. `noctusai_lib.integrations.email`
is a **Resend**-backed module (digest / invitation), NOT a Gmail
client — a product needing "send from the user's Gmail" or "read the
user's inbox" had nowhere in seed to consume from. This package is the
canonical adapter so any future Gmail-touching product inherits a
tested client instead of forking one.

**What ships:**
- `GmailMessage`, `GmailLabel`, `SendResult`, `GmailListResult[T]`
  value objects.
- `GmailClient` Protocol with quota-cost + scope-documented async
  methods:
  - `send_message(to=, subject=, body_text=, body_html=None, cc=None,
    bcc=None)` — 100 units; requires `gmail.send`.
  - `list_messages(query=None, label=None, page_token=None)` — 5 units
    / page + 5 / hydrated message; requires `gmail.readonly`.
  - `get_message(message_id)` — 5 units; requires `gmail.readonly`.
- `FakeGmailClient` — deterministic in-memory; records every send on
  `.sent`; `add_fake_message(...)` fixture seam; `PAGE_SIZE = 2` for
  testable paging. No network.
- `RealGmailClient(api_key=None, oauth_credentials=...)` — wraps
  `googleapiclient.discovery.build("gmail", "v1", ...)`; stdlib
  `EmailMessage` MIME-build → base64url `raw` for send. Logs HTTP
  errors at WARN+ before re-raising; never swallows silently.
- `make_gmail_client(use_fake=False, api_key=None,
  oauth_credentials=None, fake_seed_data=None)` — factory.
- `OAuthGmailCredentials` + `GmailCredentialResolver` Protocol —
  per-tenant OAuth credential lookup (mirrors Calendar's resolver
  shape; Gmail is OAuth-only — see below).

**Auth.** Gmail is **OAuth-only** — `users.messages.*` act on a
private user mailbox, so there is no API-key path (unlike YouTube /
Drive, which accept an API key for read-only *public* data).
`RealGmailClient` requires `oauth_credentials`; constructing it
without raises `ValueError` (fail loud, no silent degrade). The
factory, given no resolved credentials, falls back to
`FakeGmailClient` — the expected "tenant not yet connected" state,
mirroring the Calendar resolver pattern.

**Consumer pattern.** Inject a `GmailCredentialResolver` (per-tenant
OAuth lookup from Supabase / the seed `CredentialStore`); call
`make_gmail_client(oauth_credentials=resolver.get_credentials(tenant))`.
The OAuth dance itself is the generic `noctusai_lib.security.oauth`
router — do NOT duplicate it here (same rule the Meta + Calendar
packages follow).
"""

from noctusai_lib.integrations.gmail.credentials import (
    GmailCredentialResolver,
    OAuthGmailCredentials,
)
from noctusai_lib.integrations.gmail.factory import make_gmail_client
from noctusai_lib.integrations.gmail.fake import FakeGmailClient
from noctusai_lib.integrations.gmail.protocol import GmailClient
from noctusai_lib.integrations.gmail.real import RealGmailClient
from noctusai_lib.integrations.gmail.types import (
    GMAIL_MODIFY_SCOPE,
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    SUBJECT_MAX_LEN,
    GmailLabel,
    GmailListResult,
    GmailMessage,
    SendResult,
)

__all__ = [
    "GMAIL_MODIFY_SCOPE",
    "GMAIL_READONLY_SCOPE",
    "GMAIL_SEND_SCOPE",
    "SUBJECT_MAX_LEN",
    "FakeGmailClient",
    "GmailClient",
    "GmailCredentialResolver",
    "GmailLabel",
    "GmailListResult",
    "GmailMessage",
    "OAuthGmailCredentials",
    "RealGmailClient",
    "SendResult",
    "make_gmail_client",
]
