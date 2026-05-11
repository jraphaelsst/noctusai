"""Tests for `app.services.calendar` — Phase 8 Google Calendar wiring.

Verifies:
  * ``SupabaseCalendarCredentialResolver`` reads the OAuth row +
    falls back to ``None`` when missing.
  * Service-account credential path returns
    `ServiceAccountCalendarCredentials`.
  * ``configure_calendar_module`` builds a ``CalendarModule`` with a
    Fake adapter when no credentials are provided + with an injected
    adapter when supplied directly.
  * ``make_request_id`` is deterministic across calls with the same
    inputs and differs when start_at differs.
  * ``create_calendar_event`` invokes the adapter, stamps the
    derived ``request_id`` onto the created event (verifiable via the
    Fake's stored ``x_request_id`` body field).

Per the rule "No monkey-patching of our own code" — patches target
the Supabase boundary via `MockSupabaseClient`. Calendar adapter swaps
are done via the explicit ``adapter=`` injection seam.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from noctusai_lib.integrations.google_calendar import (
    FakeCalendarAdapter,
    OAuthCalendarCredentials,
    ServiceAccountCalendarCredentials,
)
from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse


ORG_ID = "00000000-0000-0000-0000-000000000001"
TZ_BR = ZoneInfo("America/Sao_Paulo")


# ---------------------------------------------------------------------------
# Module reset fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_calendar_module():
    """Each test starts with a clean module singleton."""
    from app.services import calendar as calendar_mod

    calendar_mod._reset_for_tests()
    yield
    calendar_mod._reset_for_tests()


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class TestSupabaseCalendarCredentialResolver:
    """`SupabaseCalendarCredentialResolver` reads OAuth row from DB."""

    def test_returns_oauth_credentials_when_row_present(self):
        from app.services.calendar import SupabaseCalendarCredentialResolver

        db = MockSupabaseClient(data=[])
        resolver = SupabaseCalendarCredentialResolver(
            admin_client=db,
            org_id=ORG_ID,
            oauth_client_id="client-id-xyz",
            oauth_client_secret="client-secret-abc",
        )
        # `MockSupabaseClient.schema(...)` returns a fresh instance each
        # call — the resolver caches its own scoped client in `_scoped`.
        # Seed sequential responses on that same instance.
        resolver._scoped.set_sequential_responses(
            "oauth_credentials",
            [
                MockSupabaseResponse(
                    data=[
                        {
                            "id": "11111111-0000-0000-0000-000000000001",
                            "refresh_token": "rt-abc-123",
                            "access_token": "at-current",
                            "access_token_expires_at": "2026-12-31T23:59:00+00:00",
                            "scopes": "https://www.googleapis.com/auth/calendar",
                            "account_email": "agency@example.com",
                        }
                    ]
                )
            ],
        )

        creds = resolver.get_credentials()
        assert isinstance(creds, OAuthCalendarCredentials)
        assert creds.refresh_token == "rt-abc-123"
        assert creds.client_id == "client-id-xyz"
        assert creds.client_secret == "client-secret-abc"
        assert creds.token == "at-current"
        assert "https://www.googleapis.com/auth/calendar" in creds.scopes

    def test_returns_none_when_no_row(self):
        from app.services.calendar import SupabaseCalendarCredentialResolver

        db = MockSupabaseClient(data=[])
        resolver = SupabaseCalendarCredentialResolver(
            admin_client=db,
            org_id=ORG_ID,
            oauth_client_id="client-id",
            oauth_client_secret="client-secret",
        )
        resolver._scoped.set_sequential_responses(
            "oauth_credentials",
            [MockSupabaseResponse(data=[])],
        )

        creds = resolver.get_credentials()
        assert creds is None

    def test_returns_none_when_oauth_client_config_missing(self):
        """No client_id/secret → resolver can't build a refresh-capable
        credential → returns None so seed factory drops to Fake."""
        from app.services.calendar import SupabaseCalendarCredentialResolver

        db = MockSupabaseClient(data=[])
        resolver = SupabaseCalendarCredentialResolver(
            admin_client=db,
            org_id=ORG_ID,
            oauth_client_id=None,
            oauth_client_secret=None,
        )
        creds = resolver.get_credentials()
        assert creds is None

    def test_returns_service_account_when_info_provided(self):
        from app.services.calendar import SupabaseCalendarCredentialResolver

        db = MockSupabaseClient(data=[])
        sa_info = {
            "type": "service_account",
            "client_email": "bot@example.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
        }
        resolver = SupabaseCalendarCredentialResolver(
            admin_client=db,
            org_id=ORG_ID,
            service_account_info=sa_info,
        )

        creds = resolver.get_credentials()
        assert isinstance(creds, ServiceAccountCalendarCredentials)
        assert creds.info == sa_info

    def test_save_refreshed_token_updates_row(self):
        from app.services.calendar import SupabaseCalendarCredentialResolver

        db = MockSupabaseClient(data=[])
        resolver = SupabaseCalendarCredentialResolver(
            admin_client=db,
            org_id=ORG_ID,
            oauth_client_id="cid",
            oauth_client_secret="csec",
        )
        resolver._scoped.set_sequential_responses(
            "oauth_credentials",
            [MockSupabaseResponse(data=[])],
        )

        resolver.save_refreshed_token(
            access_token="at-new-456",
            expires_at_iso="2027-01-01T00:00:00+00:00",
        )
        # Read back via the resolver's bound scoped client (same path
        # the production code wrote through).
        updates = resolver._scoped.table("oauth_credentials").updated_payloads
        assert any(
            payload.get("access_token") == "at-new-456"
            and payload.get("access_token_expires_at") == "2027-01-01T00:00:00+00:00"
            for payload in updates
        )


# ---------------------------------------------------------------------------
# configure_calendar_module
# ---------------------------------------------------------------------------


class TestConfigureCalendarModule:
    def test_defaults_to_fake_when_no_credentials(self):
        from app.services.calendar import (
            FakeCalendarAdapter as ImportedFake,  # noqa: F401
            configure_calendar_module,
            get_calendar_module,
        )

        db = MockSupabaseClient(data=[])
        module = configure_calendar_module(
            admin_client=db,
            org_id=ORG_ID,
        )
        # No resolver was built (no oauth creds + no service-account).
        assert module.resolver is None
        # Default fallback: a FakeCalendarAdapter.
        assert isinstance(module.adapter, FakeCalendarAdapter)
        assert module.default_calendar_id == "primary"
        # The getter returns the same instance.
        assert get_calendar_module() is module

    def test_uses_supplied_adapter(self):
        from app.services.calendar import configure_calendar_module

        db = MockSupabaseClient(data=[])
        custom = FakeCalendarAdapter(supports_attendees=True)
        module = configure_calendar_module(
            admin_client=db,
            org_id=ORG_ID,
            default_calendar_id="agency-cal-id",
            adapter=custom,
        )
        # Pre-built adapter is held verbatim, no resolver.
        assert module.adapter is custom
        assert module.default_calendar_id == "agency-cal-id"
        assert module.resolver is None

    def test_get_raises_when_not_configured(self):
        from app.services.calendar import get_calendar_module

        with pytest.raises(RuntimeError, match="not configured"):
            get_calendar_module()


# ---------------------------------------------------------------------------
# make_request_id
# ---------------------------------------------------------------------------


class TestMakeRequestId:
    def test_stable_across_repeated_calls(self):
        from app.services.calendar import make_request_id

        a = make_request_id(
            appointment_request_id="req-abc",
            start_at_iso="2026-05-15T10:00:00-03:00",
        )
        b = make_request_id(
            appointment_request_id="req-abc",
            start_at_iso="2026-05-15T10:00:00-03:00",
        )
        assert a == b
        assert len(a) == 32

    def test_differs_when_start_at_differs(self):
        from app.services.calendar import make_request_id

        a = make_request_id(
            appointment_request_id="req-abc",
            start_at_iso="2026-05-15T10:00:00-03:00",
        )
        b = make_request_id(
            appointment_request_id="req-abc",
            start_at_iso="2026-05-15T11:30:00-03:00",
        )
        assert a != b

    def test_differs_when_request_id_differs(self):
        from app.services.calendar import make_request_id

        a = make_request_id(
            appointment_request_id="req-A",
            start_at_iso="2026-05-15T10:00:00-03:00",
        )
        b = make_request_id(
            appointment_request_id="req-B",
            start_at_iso="2026-05-15T10:00:00-03:00",
        )
        assert a != b


# ---------------------------------------------------------------------------
# create_calendar_event
# ---------------------------------------------------------------------------


class TestCreateCalendarEvent:
    def test_creates_event_via_adapter_and_stamps_request_id(self):
        from app.services.calendar import (
            configure_calendar_module,
            create_calendar_event,
            make_request_id,
        )

        db = MockSupabaseClient(data=[])
        fake = FakeCalendarAdapter()
        configure_calendar_module(
            admin_client=db,
            org_id=ORG_ID,
            default_calendar_id="primary",
            adapter=fake,
        )

        start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)

        created = create_calendar_event(
            summary="Visita técnica — Edifício Aurora — AP-2034",
            start_at=start,
            end_at=end,
            timezone="America/Sao_Paulo",
            appointment_request_id="req-001",
            attendee_emails=["client@example.com"],
        )

        assert created.event_id  # adapter returns a non-empty id
        # Fake stores the request_id as x_request_id on the body — verify
        # it matches our derived stable value.
        expected_rid = make_request_id(
            appointment_request_id="req-001",
            start_at_iso=start.isoformat(),
        )
        assert created.raw["x_request_id"] == expected_rid

    def test_idempotent_request_id_across_retries(self):
        """The same logical confirmation MUST derive the same request_id
        every time. Two create_calendar_event invocations with identical
        inputs produce events whose ``x_request_id`` matches."""
        from app.services.calendar import (
            configure_calendar_module,
            create_calendar_event,
        )

        db = MockSupabaseClient(data=[])
        fake = FakeCalendarAdapter()
        configure_calendar_module(
            admin_client=db,
            org_id=ORG_ID,
            adapter=fake,
        )

        start = datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR)
        end = datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR)
        kwargs = dict(
            summary="Visita técnica",
            start_at=start,
            end_at=end,
            timezone="America/Sao_Paulo",
            appointment_request_id="req-stable",
        )

        first = create_calendar_event(**kwargs)
        second = create_calendar_event(**kwargs)

        # Both events were created (no wire-level dedup at Fake level —
        # the seed types doc states that's deferred), but the
        # request_id ON each event matches → consumer can detect
        # duplicate post-hoc.
        assert first.raw["x_request_id"] == second.raw["x_request_id"]

    def test_raises_when_module_not_configured(self):
        from app.services.calendar import create_calendar_event

        with pytest.raises(RuntimeError, match="not configured"):
            create_calendar_event(
                summary="X",
                start_at=datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR),
                end_at=datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR),
                timezone="America/Sao_Paulo",
                appointment_request_id="req-x",
            )

    def test_uses_calendar_id_override(self):
        from app.services.calendar import (
            configure_calendar_module,
            create_calendar_event,
        )

        db = MockSupabaseClient(data=[])
        fake = FakeCalendarAdapter()
        configure_calendar_module(
            admin_client=db,
            org_id=ORG_ID,
            default_calendar_id="default-cal",
            adapter=fake,
        )

        created = create_calendar_event(
            summary="X",
            start_at=datetime(2026, 5, 15, 10, 0, tzinfo=TZ_BR),
            end_at=datetime(2026, 5, 15, 11, 30, tzinfo=TZ_BR),
            timezone="America/Sao_Paulo",
            appointment_request_id="req",
            calendar_id="override-cal",
        )
        # Verify the event landed on the overridden calendar by inspecting
        # the fake's internal storage.
        assert "override-cal" in fake._events
        assert created.event_id in fake._events["override-cal"]
