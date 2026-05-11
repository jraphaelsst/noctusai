"""Google Calendar wiring for the Imobi Scheduling bot — Phase 8.

**Why this module exists** — Phase 8 of `projects/imobi-scheduling-bot-creation/`
wires the seed `noctusai_lib.integrations.google_calendar` into the product.
The seed ships the full Protocol + Fake + Real + factory shape
(`get_calendar_adapter(resolver, tenant_id=...)`); this module supplies:

  1. The product-side ``SupabaseCalendarCredentialResolver`` —
     `CalendarCredentialResolver` impl that reads + writes the
     ``imobi_scheduling.oauth_credentials`` table (refresh-token cache
     persistence, folded from sibling's ``google-oauth-activation`` runbook).
  2. ``make_calendar_client(settings, admin_client, org_id)`` — builds the
     adapter through the seed factory.
  3. ``create_calendar_event(...)`` — wraps the adapter's ``create_event``
     and stamps a deterministic ``request_id`` derived from
     ``(appointment_request_id, start_at)`` so retries don't double-book
     (folded from sibling's ``idempotency-keys`` runbook).
  4. ``configure_calendar_module(...)`` — top-level entry-point consumed by
     ``app/lifespan.py`` at startup. Mirrors the chatbot framework's
     ``configure_conversation_module`` shape.

**Verify-the-seed-ships-it test (2026-05-11).** Re-read the seed's
``noctusai_lib/integrations/google_calendar/__init__.py`` + ``oauth_adapter.py``:
ships Protocol+Fake+Real+factory in canonical shape. No carve-out
required; the consumer-side work here is the credential-resolver +
``request_id`` idempotency wrapping (both of which are product-specific
by design — the seed's ``EventInput.request_id`` is a documented hook).

**Idempotency note** — the seed's ``EventInput.request_id`` is metadata
only (the seed types docstring documents this). True wire-level
idempotency (deriving ``body["id"]`` from ``request_id`` + swallowing
409) is deferred at the seed level. Until then, this module enforces
idempotency at THIS call site by hashing
``(appointment_request_id, start_at_iso)`` into a stable ``request_id``;
the FakeCalendarAdapter stores it as ``x_request_id`` on the body so
tests can verify stability across retries. Real-adapter wire-level
idempotency is filed as a P1 seed-side follow-up (see PROJECT.md §6
Phase 8 Improvements).

**OAuth refresh-token persistence.** ``SupabaseCalendarCredentialResolver``
reads the latest row from ``oauth_credentials`` for ``(org_id, provider='google_calendar')``
and returns ``OAuthCalendarCredentials``. The seed's
``GoogleCalendarOAuthAdapter`` triggers ``google.oauth2.credentials.Credentials.refresh(Request())``
on 401 / expired-access-token; this module exposes ``save_refreshed_token(...)``
so callers can persist the new access token + expiry back. The
``Credentials`` object's ``token`` + ``expiry`` attributes are populated
post-refresh; consumer wires the save back in production.

LGPD: the ``oauth_credentials`` table is flagged sensitive — refresh
tokens must be encrypted at rest by the application layer before INSERT.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.google_calendar import (
    CalendarAdapter,
    CalendarCredentials,
    CreatedEvent,
    EventAttendee,
    EventInput,
    FakeCalendarAdapter,
    OAuthCalendarCredentials,
    ServiceAccountCalendarCredentials,
    get_calendar_adapter,
)

logger = logging.getLogger(__name__)


SCHEMA = "imobi_scheduling"
TABLE = "oauth_credentials"
PROVIDER = "google_calendar"


# ---------------------------------------------------------------------------
# Credential resolver — Supabase-backed
# ---------------------------------------------------------------------------


class SupabaseCalendarCredentialResolver:
    """`CalendarCredentialResolver` impl backed by the
    ``imobi_scheduling.oauth_credentials`` table.

    Reads the row for ``(org_id, provider='google_calendar')`` and maps
    it onto an `OAuthCalendarCredentials` dataclass the seed's OAuth
    adapter consumes. Service-account flow is supported through a separate
    ``service_account_info`` constructor argument — the seed picks the
    adapter kind by ``isinstance``.

    The ``tenant_id`` argument is ignored at v1 (single-agency org_id is
    fixed at deployment) — the resolver always returns credentials for
    the configured ``org_id``. Multi-tenant variants can subclass + map
    ``tenant_id → org_id`` if needed.
    """

    def __init__(
        self,
        admin_client: Any,
        *,
        org_id: UUID | str,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        service_account_info: Optional[dict] = None,
    ) -> None:
        self._client = admin_client
        self._scoped = admin_client.schema(SCHEMA)
        self._org_id = str(org_id)
        self._oauth_client_id = oauth_client_id
        self._oauth_client_secret = oauth_client_secret
        self._service_account_info = service_account_info

    def get_credentials(
        self, tenant_id: str | None = None
    ) -> CalendarCredentials | None:
        """Return credentials for the configured org_id, or ``None`` →
        seed factory falls back to ``FakeCalendarAdapter``.

        Service-account path: if ``service_account_info`` was passed at
        construction time, return it. Otherwise look up the OAuth refresh
        token from the DB.
        """
        if self._service_account_info is not None:
            return ServiceAccountCalendarCredentials(
                info=self._service_account_info,
            )

        if not self._oauth_client_id or not self._oauth_client_secret:
            # No OAuth client config → can't refresh tokens → drop to Fake.
            return None

        try:
            response = (
                self._scoped
                .table(TABLE)
                .select(
                    "id, refresh_token, access_token, access_token_expires_at, "
                    "scopes, account_email"
                )
                .eq("org_id", self._org_id)
                .eq("provider", PROVIDER)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — surface loud.
            logger.warning(
                "OAuth credential lookup failed: org_id=%s err=%s",
                self._org_id, exc,
            )
            return None

        rows = response.data or []
        if not rows:
            logger.info(
                "No google_calendar OAuth row for org_id=%s; falling back to Fake.",
                self._org_id,
            )
            return None

        row = rows[0]
        scopes_raw = row.get("scopes") or ""
        scopes = (
            [s.strip() for s in scopes_raw.split(",") if s.strip()]
            if scopes_raw
            else ["https://www.googleapis.com/auth/calendar"]
        )

        return OAuthCalendarCredentials(
            refresh_token=row["refresh_token"],
            client_id=self._oauth_client_id,
            client_secret=self._oauth_client_secret,
            token=row.get("access_token"),
            scopes=scopes,
        )

    def save_refreshed_token(
        self,
        *,
        access_token: str,
        expires_at_iso: str,
    ) -> None:
        """Persist a refreshed access token + expiry back to the DB.

        Called by the OAuth flow after ``Credentials.refresh(Request())``
        succeeds (the consumer must wire this — the seed adapter performs
        the refresh in-memory but doesn't know how to persist).

        Best-effort — DB exceptions WARN and swallow; the next request
        will trigger another refresh.
        """
        try:
            (
                self._scoped
                .table(TABLE)
                .update({
                    "access_token": access_token,
                    "access_token_expires_at": expires_at_iso,
                })
                .eq("org_id", self._org_id)
                .eq("provider", PROVIDER)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — best-effort persist.
            logger.warning(
                "Failed to persist refreshed access token: org_id=%s err=%s",
                self._org_id, exc,
            )


# ---------------------------------------------------------------------------
# Calendar module — top-level wiring object
# ---------------------------------------------------------------------------


@dataclass
class CalendarModule:
    """Wired calendar adapter + default calendar id.

    Attributes:
        adapter: A `CalendarAdapter` (Fake | OAuth | ServiceAccount). The
            seed factory selects based on the resolver's return.
        default_calendar_id: Calendar ID to insert events on by default
            (the bot's working calendar; e.g. the agency's shared
            Google Calendar address).
        resolver: The credential resolver in play (None for the Fake
            fallback path). Exposed so test fixtures + admin tooling
            can introspect.
    """

    adapter: CalendarAdapter
    default_calendar_id: str
    resolver: Optional[SupabaseCalendarCredentialResolver] = None


# Module-level singleton populated by ``configure_calendar_module(...)``.
_module: Optional[CalendarModule] = None


def get_calendar_module() -> CalendarModule:
    """Return the configured `CalendarModule`. Raises if not wired."""
    if _module is None:
        raise RuntimeError(
            "Calendar module is not configured. "
            "Call `configure_calendar_module(...)` from lifespan startup."
        )
    return _module


def configure_calendar_module(
    *,
    admin_client: Any,
    org_id: UUID | str,
    default_calendar_id: Optional[str] = None,
    oauth_client_id: Optional[str] = None,
    oauth_client_secret: Optional[str] = None,
    service_account_info: Optional[dict] = None,
    adapter: Optional[CalendarAdapter] = None,
) -> CalendarModule:
    """Build + cache the `CalendarModule`.

    Called once at lifespan startup (or in tests). Two ways to wire:

      1. **Real adapter via resolver** (default path) — pass
         ``oauth_client_id`` + ``oauth_client_secret`` (OAuth) OR
         ``service_account_info`` (service-account). The resolver reads
         credentials from ``oauth_credentials``.
      2. **Test path** — pass ``adapter=FakeCalendarAdapter(...)``
         directly. ``resolver`` is skipped + the supplied adapter is
         held verbatim.

    Args:
        admin_client: Supabase admin client (for the OAuth resolver lookup).
        org_id: Single-agency v1 org UUID.
        default_calendar_id: Where events land. Defaults to ``"primary"``
            when not configured — only useful in tests / dev (production
            should set ``GOOGLE_CALENDAR_DEFAULT_CALENDAR_ID``).
        oauth_client_id / oauth_client_secret: OAuth client credentials.
        service_account_info: Service-account JSON dict (pre-parsed).
        adapter: Pre-built adapter (test path). When supplied, the
            resolver is not constructed.

    Returns:
        The configured module (cached at module-level).
    """
    global _module

    resolver: Optional[SupabaseCalendarCredentialResolver] = None
    if adapter is None:
        if oauth_client_id and oauth_client_secret:
            resolver = SupabaseCalendarCredentialResolver(
                admin_client=admin_client,
                org_id=org_id,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
            )
        elif service_account_info is not None:
            resolver = SupabaseCalendarCredentialResolver(
                admin_client=admin_client,
                org_id=org_id,
                service_account_info=service_account_info,
            )
        # else: no real-credential config → factory returns Fake.

        adapter = get_calendar_adapter(resolver=resolver, tenant_id=str(org_id))

    _module = CalendarModule(
        adapter=adapter,
        default_calendar_id=default_calendar_id or "primary",
        resolver=resolver,
    )
    logger.info(
        "Calendar module configured: adapter=%s default_calendar_id=%s",
        type(adapter).__name__,
        _module.default_calendar_id,
    )
    return _module


def _reset_for_tests() -> None:
    """Test helper — clears the module-level singleton."""
    global _module
    _module = None


# ---------------------------------------------------------------------------
# Idempotent event creation
# ---------------------------------------------------------------------------


def make_request_id(*, appointment_request_id: str, start_at_iso: str) -> str:
    """Derive a stable ``request_id`` for an event.

    Hashes ``(appointment_request_id, start_at_iso)`` so retries of the
    same logical confirmation use an identical ``request_id``. The
    FakeCalendarAdapter stamps it onto the body as ``x_request_id``;
    real adapters carry it as metadata until wire-level idempotency is
    folded in at the seed (see seed types.py ``EventInput.request_id``
    docstring).

    Returns:
        A 32-char hex digest (truncated SHA-256) — long enough to be
        collision-resistant under any realistic retry-burst, short
        enough to fit Google Calendar's ``id`` field constraints if a
        future seed-side wire-idempotency wrapper consumes it.
    """
    payload = f"{appointment_request_id}|{start_at_iso}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def create_calendar_event(
    *,
    summary: str,
    start_at: Any,  # datetime (avoid hard import in signature)
    end_at: Any,
    timezone: str,
    appointment_request_id: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendee_emails: Optional[list[str]] = None,
    calendar_id: Optional[str] = None,
) -> CreatedEvent:
    """Wrap the configured adapter's ``create_event`` with idempotency.

    The ``request_id`` is derived from ``(appointment_request_id, start_at_iso)``
    — same logical call → same ``request_id`` across retries. Today this
    is metadata only; if a retry storm hits and the seed-side wire-level
    idempotency lands, the same value will gate de-duplication at the
    Google API.

    Args:
        summary: Event title.
        start_at: tz-aware datetime.
        end_at: tz-aware datetime.
        timezone: IANA tz string (e.g. ``"America/Sao_Paulo"``).
        appointment_request_id: Stable handle from the bot — used for the
            idempotency key.
        description: Optional body text.
        location: Optional human-readable location string.
        attendee_emails: List of attendee email strings (mapped to
            ``EventAttendee(email=...)``).
        calendar_id: Override default; falls back to module's
            ``default_calendar_id``.

    Returns:
        The seed's ``CreatedEvent`` value object (event_id + html_link + raw).

    Raises:
        RuntimeError: If the module is not configured.
    """
    module = get_calendar_module()
    target_calendar = calendar_id or module.default_calendar_id

    request_id = make_request_id(
        appointment_request_id=appointment_request_id,
        start_at_iso=start_at.isoformat(),
    )
    attendees = (
        [EventAttendee(email=email) for email in attendee_emails]
        if attendee_emails
        else []
    )
    event = EventInput(
        summary=summary,
        start_at=start_at,
        end_at=end_at,
        timezone=timezone,
        description=description,
        location=location,
        attendees=attendees,
        request_id=request_id,
    )
    return module.adapter.create_event(target_calendar, event)


# ---------------------------------------------------------------------------
# Phase 9 — cancel + update wrappers
# ---------------------------------------------------------------------------


def cancel_calendar_event(
    *,
    event_id: str,
    calendar_id: Optional[str] = None,
) -> None:
    """Delete a previously-created Calendar event.

    Phase 9 wires this into ``SchedulingService.cancel_appointment`` as the
    ``calendar_event_canceler`` seam. Failure during deletion is LOGGED but
    NOT raised back through the service — the DB-side status flip to
    ``cancelled`` must succeed even when Calendar deletion fails (the user
    can clean up stale events manually; double-cancellation would leave the
    DB in an inconsistent state).

    Args:
        event_id: The Google Calendar event id (``google_calendar_event_id``
            on the appointment row).
        calendar_id: Override default; falls back to module's
            ``default_calendar_id``.

    Raises:
        RuntimeError: If the module is not configured.
    """
    module = get_calendar_module()
    target_calendar = calendar_id or module.default_calendar_id
    module.adapter.delete_event(target_calendar, event_id)


def update_calendar_event(
    *,
    event_id: str,
    summary: str,
    start_at: Any,
    end_at: Any,
    timezone: str,
    appointment_request_id: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendee_emails: Optional[list[str]] = None,
    calendar_id: Optional[str] = None,
) -> CreatedEvent:
    """Update a Calendar event (used by reschedule).

    Same ``request_id`` derivation as ``create_calendar_event`` — the
    seed adapters keep the existing event_id intact and mutate
    start/end/description/etc. The ``EventInput.request_id`` is stamped on
    the body so Fake-adapter tests can verify stability.

    Args:
        event_id: The existing event id to update.
        summary / start_at / end_at / timezone / appointment_request_id /
        description / location / attendee_emails: Same as
        ``create_calendar_event``.
        calendar_id: Override default; falls back to module's
            ``default_calendar_id``.

    Returns:
        The seed's ``CreatedEvent`` value object reflecting the post-update
        body (event_id + html_link + raw).

    Raises:
        RuntimeError: If the module is not configured.
    """
    module = get_calendar_module()
    target_calendar = calendar_id or module.default_calendar_id

    request_id = make_request_id(
        appointment_request_id=appointment_request_id,
        start_at_iso=start_at.isoformat(),
    )
    attendees = (
        [EventAttendee(email=email) for email in attendee_emails]
        if attendee_emails
        else []
    )
    event = EventInput(
        summary=summary,
        start_at=start_at,
        end_at=end_at,
        timezone=timezone,
        description=description,
        location=location,
        attendees=attendees,
        request_id=request_id,
    )
    return module.adapter.update_event(target_calendar, event_id, event)


__all__ = [
    "CalendarModule",
    "SupabaseCalendarCredentialResolver",
    "cancel_calendar_event",
    "configure_calendar_module",
    "create_calendar_event",
    "get_calendar_module",
    "make_request_id",
    "update_calendar_event",
]
