"""Real Google Calendar adapter tests — service-account + OAuth.

Mocks `googleapiclient.discovery.build` and `google.oauth2.*` Credentials
so we exercise our adapter logic (Protocol → credentials → API call shape)
without making network calls."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from noctusai_lib.integrations.google_calendar import (
    EventAttendee,
    EventInput,
    OAuthCalendarCredentials,
    ServiceAccountCalendarCredentials,
    get_calendar_adapter,
)
from noctusai_lib.integrations.google_calendar.fake_adapter import FakeCalendarAdapter
from noctusai_lib.integrations.google_calendar.oauth_adapter import (
    GoogleCalendarOAuthAdapter,
)
from noctusai_lib.integrations.google_calendar.service_account_adapter import (
    GoogleCalendarServiceAccountAdapter,
)


# ---- Test fixtures ----------------------------------------------------------


def _sa_creds() -> ServiceAccountCalendarCredentials:
    return ServiceAccountCalendarCredentials(
        info={"type": "service_account", "client_email": "sa@example.iam"},
        scopes=["https://www.googleapis.com/auth/calendar"],
    )


def _sa_creds_with_delegate() -> ServiceAccountCalendarCredentials:
    return ServiceAccountCalendarCredentials(
        info={"type": "service_account"},
        delegate_email="user@workspace.example",
    )


def _oauth_creds() -> OAuthCalendarCredentials:
    return OAuthCalendarCredentials(
        refresh_token="rt-123",
        client_id="cid",
        client_secret="csecret",
        token="at-456",
    )


def _resolver(creds) -> MagicMock:
    r = MagicMock()
    r.get_credentials.return_value = creds
    return r


def _event() -> EventInput:
    return EventInput(
        summary="Property tour",
        start_at=datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
        timezone="America/Sao_Paulo",
        location="Av Paulista 100",
        attendees=[EventAttendee(email="buyer@example.com")],
        request_id="appt-42",
    )


# ---- Service-account adapter -----------------------------------------------


def test_sa_adapter_create_event_calls_insert_with_body() -> None:
    fake_service = MagicMock()
    fake_inserted = MagicMock()
    fake_inserted.execute.return_value = {
        "id": "evt-1",
        "htmlLink": "https://calendar.google.com/event?eid=evt-1",
        "summary": "Property tour",
    }
    fake_service.events.return_value.insert.return_value = fake_inserted

    with patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.service_account.Credentials.from_service_account_info"
    ), patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.build",
        return_value=fake_service,
    ):
        adapter = GoogleCalendarServiceAccountAdapter(resolver=_resolver(_sa_creds()))
        result = adapter.create_event("primary", _event())

    assert result.event_id == "evt-1"
    assert result.html_link == "https://calendar.google.com/event?eid=evt-1"
    insert_kwargs = fake_service.events.return_value.insert.call_args.kwargs
    assert insert_kwargs["calendarId"] == "primary"
    assert insert_kwargs["body"]["summary"] == "Property tour"


def test_sa_adapter_uses_with_subject_when_delegate_email_set() -> None:
    captured_creds = MagicMock()

    with patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.service_account.Credentials.from_service_account_info",
        return_value=captured_creds,
    ) as build_creds, patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.build"
    ):
        adapter = GoogleCalendarServiceAccountAdapter(
            resolver=_resolver(_sa_creds_with_delegate())
        )
        adapter._service()

    # When delegate_email is set, with_subject must be called.
    captured_creds.with_subject.assert_called_once_with("user@workspace.example")
    build_creds.assert_called_once()


def test_sa_adapter_get_event_returns_none_on_404() -> None:
    from googleapiclient.errors import HttpError

    fake_service = MagicMock()
    fake_resp = MagicMock()
    fake_resp.status = 404
    fake_service.events.return_value.get.return_value.execute.side_effect = HttpError(
        resp=fake_resp, content=b"not found"
    )

    with patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.service_account.Credentials.from_service_account_info"
    ), patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.build",
        return_value=fake_service,
    ):
        adapter = GoogleCalendarServiceAccountAdapter(resolver=_resolver(_sa_creds()))
        out = adapter.get_event("primary", "missing-id")

    assert out is None


def test_sa_adapter_list_events_passes_iso_time_bounds() -> None:
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "e1", "htmlLink": "h1", "summary": "tour"},
            {"id": "e2", "htmlLink": "h2", "summary": "tour 2"},
        ]
    }

    with patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.service_account.Credentials.from_service_account_info"
    ), patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.build",
        return_value=fake_service,
    ):
        adapter = GoogleCalendarServiceAccountAdapter(resolver=_resolver(_sa_creds()))
        events = adapter.list_events(
            "primary",
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 30, tzinfo=timezone.utc),
        )

    assert len(events) == 2
    list_kwargs = fake_service.events.return_value.list.call_args.kwargs
    assert list_kwargs["calendarId"] == "primary"
    assert list_kwargs["timeMin"].endswith("+00:00") or "Z" in list_kwargs["timeMin"]
    assert list_kwargs["singleEvents"] is True
    assert list_kwargs["orderBy"] == "startTime"


def test_sa_adapter_raises_on_wrong_credential_kind() -> None:
    adapter = GoogleCalendarServiceAccountAdapter(resolver=_resolver(_oauth_creds()))
    with pytest.raises(RuntimeError, match="ServiceAccountCalendarCredentials"):
        adapter.create_event("primary", _event())


def test_sa_adapter_supports_attendees_default_is_false() -> None:
    adapter = GoogleCalendarServiceAccountAdapter(resolver=_resolver(_sa_creds()))
    assert adapter.supports_attendees is False


def test_sa_adapter_supports_attendees_overridable() -> None:
    adapter = GoogleCalendarServiceAccountAdapter(
        resolver=_resolver(_sa_creds()), supports_attendees=True
    )
    assert adapter.supports_attendees is True


def test_sa_adapter_omits_send_updates_when_no_attendees() -> None:
    """Default supports_attendees=False → sendUpdates must NOT be set
    (lets Google default to "none", correct for no-attendees calendars).
    Regression test for the dropped request_id → sendUpdates="none"
    misuse — see PROJECT.md §11 #3."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-x",
        "htmlLink": "h",
        "summary": "tour",
    }
    with patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.service_account.Credentials.from_service_account_info"
    ), patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.build",
        return_value=fake_service,
    ):
        adapter = GoogleCalendarServiceAccountAdapter(resolver=_resolver(_sa_creds()))
        adapter.create_event("primary", _event())

    insert_kwargs = fake_service.events.return_value.insert.call_args.kwargs
    assert "sendUpdates" not in insert_kwargs


def test_sa_adapter_passes_send_updates_all_when_attendees_supported() -> None:
    """supports_attendees=True (DWD-delegated) → sendUpdates="all" on
    create AND delete, matching OAuth-adapter behavior."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-y",
        "htmlLink": "h",
        "summary": "tour",
    }
    with patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.service_account.Credentials.from_service_account_info"
    ), patch(
        "noctusai_lib.integrations.google_calendar.service_account_adapter.build",
        return_value=fake_service,
    ):
        adapter = GoogleCalendarServiceAccountAdapter(
            resolver=_resolver(_sa_creds()), supports_attendees=True
        )
        adapter.create_event("primary", _event())
        adapter.delete_event("primary", "evt-y")

    insert_kwargs = fake_service.events.return_value.insert.call_args.kwargs
    delete_kwargs = fake_service.events.return_value.delete.call_args.kwargs
    assert insert_kwargs["sendUpdates"] == "all"
    assert delete_kwargs["sendUpdates"] == "all"


# ---- OAuth adapter ----------------------------------------------------------


def test_oauth_adapter_create_event_uses_send_updates_all() -> None:
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "oauth-evt-1",
        "htmlLink": "https://calendar.google.com/event?eid=oauth-evt-1",
        "summary": "Property tour",
    }
    fake_creds = MagicMock()
    fake_creds.valid = True

    with patch(
        "noctusai_lib.integrations.google_calendar.oauth_adapter.Credentials",
        return_value=fake_creds,
    ), patch(
        "noctusai_lib.integrations.google_calendar.oauth_adapter.build",
        return_value=fake_service,
    ):
        adapter = GoogleCalendarOAuthAdapter(resolver=_resolver(_oauth_creds()))
        result = adapter.create_event("primary", _event())

    assert result.event_id == "oauth-evt-1"
    insert_kwargs = fake_service.events.return_value.insert.call_args.kwargs
    assert insert_kwargs["sendUpdates"] == "all"


def test_oauth_adapter_refreshes_token_when_invalid() -> None:
    fake_creds = MagicMock()
    fake_creds.valid = False
    fake_creds.refresh_token = "rt-123"

    with patch(
        "noctusai_lib.integrations.google_calendar.oauth_adapter.Credentials",
        return_value=fake_creds,
    ), patch(
        "noctusai_lib.integrations.google_calendar.oauth_adapter.build"
    ), patch(
        "noctusai_lib.integrations.google_calendar.oauth_adapter.Request"
    ):
        adapter = GoogleCalendarOAuthAdapter(resolver=_resolver(_oauth_creds()))
        adapter._service()

    fake_creds.refresh.assert_called_once()


def test_oauth_adapter_supports_attendees_is_true() -> None:
    adapter = GoogleCalendarOAuthAdapter(resolver=_resolver(_oauth_creds()))
    assert adapter.supports_attendees is True


def test_oauth_adapter_raises_on_wrong_credential_kind() -> None:
    adapter = GoogleCalendarOAuthAdapter(resolver=_resolver(_sa_creds()))
    with pytest.raises(RuntimeError, match="OAuthCalendarCredentials"):
        adapter.create_event("primary", _event())


# ---- Factory ---------------------------------------------------------------


def test_factory_returns_fake_when_no_resolver() -> None:
    assert isinstance(get_calendar_adapter(), FakeCalendarAdapter)


def test_factory_returns_fake_when_resolver_returns_none() -> None:
    resolver = _resolver(None)
    assert isinstance(get_calendar_adapter(resolver), FakeCalendarAdapter)


def test_factory_returns_service_account_for_sa_credentials() -> None:
    adapter = get_calendar_adapter(_resolver(_sa_creds()), tenant_id="org-1")
    assert isinstance(adapter, GoogleCalendarServiceAccountAdapter)


def test_factory_returns_oauth_for_oauth_credentials() -> None:
    adapter = get_calendar_adapter(_resolver(_oauth_creds()), tenant_id="org-1")
    assert isinstance(adapter, GoogleCalendarOAuthAdapter)


def test_factory_passes_tenant_id_to_adapter() -> None:
    adapter = get_calendar_adapter(_resolver(_oauth_creds()), tenant_id="org-42")
    assert adapter._tenant_id == "org-42"
