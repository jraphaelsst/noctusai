"""Gmail API v1 client tests — Fake + Real (mocked transport).

Covers:
- **Fake adapter** — send records on `.sent` + round-trips via list;
  list filtering (label / query) + paging; get hit/miss;
  `add_fake_message` fixture seam; subject clipping.
- **Factory** — `use_fake=True` → Fake; `use_fake=False` without
  oauth → Fake fallback (Gmail OAuth-only "tenant not connected");
  `use_fake=False` WITH oauth → Real; `fake_seed_data` seeding.
- **Real adapter** — `googleapiclient.discovery.build` patched at the
  boundary (external-service carve-out per the no-monkeypatching
  rule); send builds base64url raw; list hydrates via get; 404 → None;
  5xx re-raises; constructing WITHOUT oauth raises the typed error.

Network-free: no real googleapiclient calls.
"""

from __future__ import annotations

import base64
import email
from datetime import datetime, timezone
from email.header import decode_header, make_header
from unittest.mock import MagicMock, patch

import pytest

from noctusai_lib.integrations.gmail import (
    FakeGmailClient,
    GmailMessage,
    OAuthGmailCredentials,
    SendResult,
    make_gmail_client,
)
from noctusai_lib.integrations.gmail.types import SUBJECT_MAX_LEN


def _msg(
    mid: str,
    *,
    subject: str = "",
    label_ids: tuple[str, ...] = ("INBOX",),
    body_text: str = "",
) -> GmailMessage:
    return GmailMessage(
        id=mid,
        thread_id=f"t-{mid}",
        from_="a@example.com",
        to="me@example.com",
        subject=subject,
        snippet=subject,
        body_text=body_text,
        body_html="",
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        label_ids=label_ids,
    )


# ============================================================================
# FakeGmailClient
# ============================================================================


class TestFakeGmailClient:
    @pytest.mark.asyncio
    async def test_send_records_on_sent(self) -> None:
        fake = FakeGmailClient()
        result = await fake.send_message(
            to="x@example.com", subject="Hi", body_text="hello"
        )
        assert isinstance(result, SendResult)
        assert result.message_id == "fake-sent-1"
        assert result.thread_id == "fake-thread-1"
        assert len(fake.sent) == 1
        assert fake.sent[0].to == "x@example.com"
        assert fake.sent[0].body_text == "hello"
        assert fake.sent[0].label_ids == ("SENT",)

    @pytest.mark.asyncio
    async def test_send_then_list_sent_round_trips(self) -> None:
        fake = FakeGmailClient()
        await fake.send_message(to="x@example.com", subject="S", body_text="b")
        result = await fake.list_messages(label="SENT")
        assert result.items[0].id == "fake-sent-1"
        assert result.items[0].subject == "S"

    @pytest.mark.asyncio
    async def test_send_clips_overlong_subject(self) -> None:
        fake = FakeGmailClient()
        long_subject = "z" * (SUBJECT_MAX_LEN + 50)
        await fake.send_message(
            to="x@example.com", subject=long_subject, body_text="b"
        )
        assert len(fake.sent[0].subject) == SUBJECT_MAX_LEN

    @pytest.mark.asyncio
    async def test_send_is_deterministic_sequence(self) -> None:
        fake = FakeGmailClient()
        r1 = await fake.send_message(to="a@x.com", subject="1", body_text="b")
        r2 = await fake.send_message(to="b@x.com", subject="2", body_text="b")
        assert r1.message_id == "fake-sent-1"
        assert r2.message_id == "fake-sent-2"

    @pytest.mark.asyncio
    async def test_add_fake_message_and_get(self) -> None:
        fake = FakeGmailClient()
        seeded = fake.add_fake_message(
            "m1", subject="Hello", body_text="body", from_="boss@x.com"
        )
        got = await fake.get_message("m1")
        assert got == seeded
        assert got is not None
        assert got.from_ == "boss@x.com"
        assert got.thread_id == "thread-m1"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self) -> None:
        fake = FakeGmailClient()
        assert await fake.get_message("nope") is None

    @pytest.mark.asyncio
    async def test_list_filters_by_label(self) -> None:
        fake = FakeGmailClient(
            messages=[
                _msg("a", label_ids=("INBOX",)),
                _msg("b", label_ids=("SENT",)),
            ]
        )
        result = await fake.list_messages(label="SENT")
        assert [m.id for m in result.items] == ["b"]

    @pytest.mark.asyncio
    async def test_list_filters_by_query_substring(self) -> None:
        fake = FakeGmailClient(
            messages=[
                _msg("a", subject="Invoice March"),
                _msg("b", subject="Holiday plans"),
            ]
        )
        result = await fake.list_messages(query="invoice")
        assert [m.id for m in result.items] == ["a"]

    @pytest.mark.asyncio
    async def test_list_paginates(self) -> None:
        fake = FakeGmailClient(
            messages=[_msg("a"), _msg("b"), _msg("c"), _msg("d"), _msg("e")]
        )
        p1 = await fake.list_messages()
        assert [m.id for m in p1.items] == ["a", "b"]
        assert p1.next_page_token == "2"
        assert p1.result_size_estimate == 5
        p2 = await fake.list_messages(page_token=p1.next_page_token)
        assert [m.id for m in p2.items] == ["c", "d"]
        assert p2.next_page_token == "4"
        p3 = await fake.list_messages(page_token=p2.next_page_token)
        assert [m.id for m in p3.items] == ["e"]
        assert p3.next_page_token is None

    @pytest.mark.asyncio
    async def test_list_empty_inbox(self) -> None:
        fake = FakeGmailClient()
        result = await fake.list_messages()
        assert result.items == []
        assert result.next_page_token is None


# ============================================================================
# Factory
# ============================================================================


class TestFactory:
    def test_use_fake_returns_fake(self) -> None:
        client = make_gmail_client(use_fake=True)
        assert isinstance(client, FakeGmailClient)

    def test_use_fake_with_seed_data(self) -> None:
        client = make_gmail_client(
            use_fake=True,
            fake_seed_data={"messages": [_msg("seeded", subject="X")]},
        )
        assert isinstance(client, FakeGmailClient)

    @pytest.mark.asyncio
    async def test_use_fake_with_seed_data_round_trips(self) -> None:
        client = make_gmail_client(
            use_fake=True,
            fake_seed_data={"messages": [_msg("seeded", subject="X")]},
        )
        got = await client.get_message("seeded")
        assert got is not None
        assert got.subject == "X"

    def test_no_oauth_falls_back_to_fake(self) -> None:
        # Gmail OAuth-only: no resolved creds → expected "not connected"
        # state → Fake fallback (mirrors the Calendar resolver pattern).
        client = make_gmail_client(use_fake=False)
        assert isinstance(client, FakeGmailClient)

    def test_api_key_only_still_fake_no_oauth(self) -> None:
        # api_key is inert for Gmail; no oauth → still Fake.
        client = make_gmail_client(use_fake=False, api_key="inert")
        assert isinstance(client, FakeGmailClient)

    def test_with_oauth_returns_real(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        creds = MagicMock(name="creds")
        client = make_gmail_client(use_fake=False, oauth_credentials=creds)
        assert isinstance(client, RealGmailClient)


# ============================================================================
# RealGmailClient — typed-error + transport mocked at the boundary
# ============================================================================


class TestRealGmailClientConstruction:
    def test_init_requires_oauth_credentials(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        with pytest.raises(ValueError, match="requires oauth_credentials"):
            RealGmailClient()

    def test_init_api_key_only_raises_typed_error(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        with pytest.raises(ValueError, match="no API-key path"):
            RealGmailClient(api_key="k")

    def test_init_with_oauth_credentials_ok(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        creds = MagicMock(name="creds")
        client = RealGmailClient(oauth_credentials=creds)
        assert client._oauth_credentials is creds


def _build_mock_service(
    *,
    send_response: dict | None = None,
    list_response: dict | None = None,
    get_responses: dict[str, dict] | None = None,
    get_raises: Exception | None = None,
) -> MagicMock:
    """Mock matching googleapiclient's chain:

        service.users().messages().send(userId=, body=).execute()
        service.users().messages().list(**kwargs).execute()
        service.users().messages().get(userId=, id=, format=).execute()
    """
    service = MagicMock()
    messages = service.users.return_value.messages.return_value

    messages.send.return_value.execute.return_value = send_response or {}
    messages.list.return_value.execute.return_value = list_response or {}

    def _get(*, userId: str, id: str, format: str) -> MagicMock:  # noqa: A002,N803
        call = MagicMock()
        if get_raises is not None:
            call.execute.side_effect = get_raises
        else:
            call.execute.return_value = (get_responses or {}).get(id, {})
        return call

    messages.get.side_effect = _get
    return service


def _full_message_payload(mid: str, *, subject: str, body: str) -> dict:
    raw_text = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return {
        "id": mid,
        "threadId": f"thread-{mid}",
        "snippet": subject,
        "internalDate": "1700000000000",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": "text/plain",
            "body": {"data": raw_text},
        },
    }


class TestRealGmailClientTransport:
    @pytest.mark.asyncio
    async def test_send_builds_raw_and_returns_result(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        mock_service = _build_mock_service(
            send_response={"id": "sent-1", "threadId": "thr-1"}
        )
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            result = await client.send_message(
                to="x@example.com",
                subject="Hello",
                body_text="plain",
                body_html="<b>rich</b>",
            )

        assert result.message_id == "sent-1"
        assert result.thread_id == "thr-1"
        # The send body carried a base64url `raw` MIME blob.
        send_call = (
            mock_service.users.return_value.messages.return_value.send
        )
        _, kwargs = send_call.call_args
        assert kwargs["userId"] == "me"
        raw = kwargs["body"]["raw"]
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        assert b"x@example.com" in decoded
        assert b"Hello" in decoded
        assert b"plain" in decoded
        assert b"rich" in decoded

    @pytest.mark.asyncio
    async def test_send_clips_subject(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        mock_service = _build_mock_service(send_response={"id": "s", "threadId": "t"})
        long_subject = "z" * (SUBJECT_MAX_LEN + 100)
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            await client.send_message(
                to="x@example.com", subject=long_subject, body_text="b"
            )
        send_call = mock_service.users.return_value.messages.return_value.send
        _, kwargs = send_call.call_args
        raw = kwargs["body"]["raw"]
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        # Re-parse the MIME (EmailMessage RFC-2047-encodes + folds long
        # headers, so a raw byte-substring check is wrong) and assert the
        # decoded Subject header is clipped to exactly SUBJECT_MAX_LEN.
        parsed = email.message_from_bytes(decoded)
        subject = str(make_header(decode_header(parsed["Subject"])))
        assert subject == "z" * SUBJECT_MAX_LEN
        assert len(subject) == SUBJECT_MAX_LEN

    @pytest.mark.asyncio
    async def test_get_message_parses_full(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        mock_service = _build_mock_service(
            get_responses={
                "m1": _full_message_payload("m1", subject="Hi", body="world")
            }
        )
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            msg = await client.get_message("m1")

        assert msg is not None
        assert msg.id == "m1"
        assert msg.subject == "Hi"
        assert msg.body_text == "world"
        assert msg.from_ == "sender@example.com"
        assert msg.label_ids == ("INBOX", "UNREAD")
        assert msg.received_at.year == 2023  # 1700000000 epoch → 2023

    @pytest.mark.asyncio
    async def test_get_message_empty_id_returns_none(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        mock_service = _build_mock_service()
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            assert await client.get_message("") is None

    @pytest.mark.asyncio
    async def test_get_message_404_returns_none(self) -> None:
        from googleapiclient.errors import HttpError

        from noctusai_lib.integrations.gmail.real import RealGmailClient

        resp = MagicMock(status=404, reason="Not Found")
        err = HttpError(resp=resp, content=b"")
        mock_service = _build_mock_service(get_raises=err)
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            assert await client.get_message("missing") is None

    @pytest.mark.asyncio
    async def test_get_message_5xx_reraises(self) -> None:
        from googleapiclient.errors import HttpError

        from noctusai_lib.integrations.gmail.real import RealGmailClient

        resp = MagicMock(status=500, reason="Server Error")
        err = HttpError(resp=resp, content=b"")
        mock_service = _build_mock_service(get_raises=err)
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            with pytest.raises(HttpError):
                await client.get_message("m1")

    @pytest.mark.asyncio
    async def test_list_hydrates_each_id_via_get(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        mock_service = _build_mock_service(
            list_response={
                "messages": [{"id": "m1"}, {"id": "m2"}],
                "nextPageToken": "PAGE2",
                "resultSizeEstimate": 2,
            },
            get_responses={
                "m1": _full_message_payload("m1", subject="One", body="b1"),
                "m2": _full_message_payload("m2", subject="Two", body="b2"),
            },
        )
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            result = await client.list_messages(query="is:unread")

        assert [m.id for m in result.items] == ["m1", "m2"]
        assert [m.subject for m in result.items] == ["One", "Two"]
        assert result.next_page_token == "PAGE2"
        assert result.result_size_estimate == 2

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty_result(self) -> None:
        from noctusai_lib.integrations.gmail.real import RealGmailClient

        mock_service = _build_mock_service(list_response={"resultSizeEstimate": 0})
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            result = await client.list_messages()
        assert result.items == []
        assert result.next_page_token is None

    @pytest.mark.asyncio
    async def test_list_http_error_reraises(self) -> None:
        from googleapiclient.errors import HttpError

        from noctusai_lib.integrations.gmail.real import RealGmailClient

        resp = MagicMock(status=403, reason="Forbidden")
        err = HttpError(resp=resp, content=b"")
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = (
            err
        )
        with patch(
            "noctusai_lib.integrations.gmail.real.build",
            return_value=mock_service,
        ):
            client = RealGmailClient(oauth_credentials=MagicMock())
            with pytest.raises(HttpError):
                await client.list_messages()


# ============================================================================
# Credentials value object
# ============================================================================


class TestOAuthGmailCredentials:
    def test_defaults_to_send_scope(self) -> None:
        creds = OAuthGmailCredentials(
            refresh_token="rt", client_id="cid", client_secret="cs"
        )
        assert creds.scopes == ["https://www.googleapis.com/auth/gmail.send"]
        assert creds.token_uri == "https://oauth2.googleapis.com/token"

    def test_scopes_overridable(self) -> None:
        creds = OAuthGmailCredentials(
            refresh_token="rt",
            client_id="cid",
            client_secret="cs",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        assert creds.scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


# ── OAuthGmailCredentials → google Credentials conversion (2026-08-06) ─────
# The seed shipped Protocol + dataclass + Fake + Real + factory, and its own
# docstrings named
#   make_gmail_client(oauth_credentials=resolver.get_credentials(tenant))
# as THE usage — but nothing converted the dataclass into what
# googleapiclient needs. The documented path died at the first real send:
#   'OAuthGmailCredentials' object has no attribute 'authorize'
# Found by the first production consumer, whose email silently never sent.

from noctusai_lib.integrations.gmail.real import (  # noqa: E402
    _as_google_credentials,
)


class _AlreadyGoogleShaped:
    """Duck-types a real `Credentials` — must pass through untouched.

    `before_request` is the marker, NOT `authorize`: the latter belongs to
    the retired `oauth2client` and is absent from every modern
    `google.auth.credentials.Credentials`.
    """
    def before_request(self, *_a, **_k):  # pragma: no cover - marker only
        return None


def test_an_already_google_shaped_credential_passes_through_unchanged():
    """Re-converting a live credential would re-refresh its token on every
    call — silent quota burn, not a visible failure."""
    creds = _AlreadyGoogleShaped()
    assert _as_google_credentials(creds) is creds


def test_none_passes_through_so_the_loud_ValueError_still_fires():
    """RealGmailClient raises on None by design — the converter must not
    turn that into a confusing TypeError first."""
    assert _as_google_credentials(None) is None


def test_the_dataclass_is_converted_to_a_google_credentials():
    """🔴 The regression. If this stops converting, every Gmail send fails
    with an AttributeError at the API boundary."""
    from noctusai_lib.integrations.gmail import OAuthGmailCredentials

    carrier = OAuthGmailCredentials(
        refresh_token="rt", client_id="cid", client_secret="sec",
        token="at", scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    out = _as_google_credentials(carrier)
    assert out is not carrier
    # The whole point: the result speaks the interface googleapiclient needs.
    assert hasattr(out, "before_request")
    assert out.refresh_token == "rt"
    assert out.client_id == "cid"
    assert "gmail.send" in " ".join(out.scopes or [])
