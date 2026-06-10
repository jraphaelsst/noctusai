"""Mailchimp Marketing API v3 adapter — Protocol + Fake + Real + factory.

Public surface:
- ``MailchimpClient`` Protocol (async methods, all operations).
- ``FakeMailchimpClient`` — deterministic in-memory implementation for
  dev + tests.  Seeds audience ``"fake-audience-1"``; deterministic ids.
- ``HttpxMailchimpClient`` — real httpx-backed adapter (Basic auth,
  dc-based base URL).
- ``get_mailchimp_client(api_key=None, *, server_prefix=None)`` —
  returns ``FakeMailchimpClient`` when ``api_key`` is absent/empty,
  ``HttpxMailchimpClient`` otherwise.  ``server_prefix`` is derived
  from the key suffix when not explicitly supplied.
- Error hierarchy: ``MailchimpError`` → ``MailchimpAuthError`` /
  ``MailchimpNotFoundError`` / ``MailchimpRateLimitedError`` /
  ``MailchimpRejectedError`` / ``MailchimpUnreachableError``.
- Value objects: ``Audience``, ``Member``, ``Segment``, ``Template``,
  ``Campaign``, ``Page[T]``.
- Pure helpers: ``subscriber_hash``, ``parse_server_prefix``,
  ``template_edit_url``.

See ``KB § PATTERNS/seed-fake-real-adapter.md`` for the wiring recipe.
"""

from noctusai_lib.integrations.mailchimp.client import HttpxMailchimpClient
from noctusai_lib.integrations.mailchimp.fake_adapter import FakeMailchimpClient
from noctusai_lib.integrations.mailchimp.mappers import (
    parse_server_prefix,
    raw_to_audience,
    raw_to_campaign,
    raw_to_member,
    raw_to_segment,
    raw_to_template,
    subscriber_hash,
    template_edit_url,
)
from noctusai_lib.integrations.mailchimp.types import (
    Audience,
    Campaign,
    MailchimpAuthError,
    MailchimpError,
    MailchimpNotFoundError,
    MailchimpRateLimitedError,
    MailchimpRejectedError,
    MailchimpUnreachableError,
    Member,
    Page,
    Segment,
    Template,
    MailchimpClient,
)


def get_mailchimp_client(
    api_key: str | None = None,
    *,
    server_prefix: str | None = None,
) -> MailchimpClient:
    """Return a real ``HttpxMailchimpClient`` when ``api_key`` is set;
    ``FakeMailchimpClient`` otherwise.

    ``server_prefix`` (e.g. ``"us6"``) is required when ``api_key`` is
    provided; when omitted it is parsed from the key suffix automatically.
    Raises ``ValueError`` when ``api_key`` is provided but its suffix is
    malformed.

    Mirrors ``get_whatsapp_client()`` and ``get_calendar_adapter()`` per
    ``KB § PATTERNS/seed-fake-real-adapter.md``.

    Usage::

        # Dev / test: no real credentials needed
        client = get_mailchimp_client()

        # Production: key read from credential vault
        client = get_mailchimp_client(api_key="mykey-us6")
        # or with explicit prefix:
        client = get_mailchimp_client(api_key="mykey-us6", server_prefix="us6")
    """
    if not api_key:
        return FakeMailchimpClient()

    dc = server_prefix if server_prefix else parse_server_prefix(api_key)
    return HttpxMailchimpClient(api_key, server_prefix=dc)


__all__ = [
    # Factory
    "get_mailchimp_client",
    # Adapters
    "FakeMailchimpClient",
    "HttpxMailchimpClient",
    # Protocol
    "MailchimpClient",
    # Error hierarchy
    "MailchimpError",
    "MailchimpAuthError",
    "MailchimpNotFoundError",
    "MailchimpRateLimitedError",
    "MailchimpRejectedError",
    "MailchimpUnreachableError",
    # Value objects
    "Audience",
    "Campaign",
    "Member",
    "Page",
    "Segment",
    "Template",
    # Pure helpers
    "parse_server_prefix",
    "raw_to_audience",
    "raw_to_campaign",
    "raw_to_member",
    "raw_to_segment",
    "raw_to_template",
    "subscriber_hash",
    "template_edit_url",
]
