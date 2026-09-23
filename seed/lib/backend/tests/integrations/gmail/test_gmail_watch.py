"""Gmail push-watch surface — Fake + Real + push helpers + provisioning + matching.

Network-free. The Real adapter and the Pub/Sub provisioner receive their
googleapiclient service via constructor/argument injection (DI seam) and
the OIDC verifier via `verify_push_token(verifier=...)` — nothing of ours
is patched.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError

from noctusai_lib.integrations.gmail import (
    GMAIL_PUSH_SERVICE_ACCOUNT,
    REPLY_MATCH_HEADERS,
    FakeGmailClient,
    GmailHistoryExpiredError,
    GmailHistoryResult,
    GmailPushAuthError,
    GmailPushEnvelopeError,
    PubSubProvisioningError,
    RealGmailClient,
    WatchResult,
    ensure_push_subscription,
    match_reply,
    normalize_message_id,
    parse_push_envelope,
    verify_push_token,
)
from noctusai_lib.integrations.gmail.fake import FAKE_NOW

TOPIC = "projects/noctus-prod/topics/gmail-replies"


def _http_error(status: int) -> HttpError:
    return HttpError(resp=MagicMock(status=status, reason="x"), content=b"")


class _GoogleShapedCreds:
    """Minimal google-credentials double (has `before_request`)."""

    def before_request(self, *args, **kwargs) -> None:  # pragma: no cover
        return None


# ============================================================================
# FakeGmailClient — watch / history / metadata
# ============================================================================


class TestFakeWatch:
    @pytest.mark.asyncio
    async def test_watch_returns_current_history_and_7d_expiry(self) -> None:
        fake = FakeGmailClient()
        result = await fake.watch(TOPIC)
        assert result == WatchResult(
            history_id=str(FakeGmailClient.INITIAL_HISTORY_ID),
            expiration=FAKE_NOW + timedelta(days=7),
        )
        assert fake.active_watch == (TOPIC, ("INBOX",))
        assert fake.watches == [(TOPIC, ("INBOX",))]

    @pytest.mark.asyncio
    async def test_watch_custom_labels_and_stop(self) -> None:
        fake = FakeGmailClient()
        await fake.watch(TOPIC, label_ids=["INBOX", "UNREAD"])
        assert fake.active_watch == (TOPIC, ("INBOX", "UNREAD"))
        await fake.stop()
        await fake.stop()  # idempotent
        assert fake.active_watch is None
        assert fake.stop_calls == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad", ["gmail-replies", "projects/p/subscriptions/s", "projects//topics/t", ""]
    )
    async def test_watch_rejects_non_resource_topic(self, bad: str) -> None:
        with pytest.raises(ValueError, match="projects/<project>/topics/<topic>"):
            await FakeGmailClient().watch(bad)


class TestFakeHistory:
    @pytest.mark.asyncio
    async def test_history_returns_only_messages_after_cursor(self) -> None:
        fake = FakeGmailClient()
        fake.add_fake_message("old")
        watch = await fake.watch(TOPIC)
        fake.add_fake_message("r1", thread_id="t1")
        fake.add_fake_message("r2", thread_id="t2", label_ids=("INBOX", "UNREAD"))

        messages, new_cursor = await fake.list_history(watch.history_id)
        assert [m.id for m in messages] == ["r1", "r2"]
        assert messages[1].thread_id == "t2"
        assert messages[1].label_ids == ("INBOX", "UNREAD")
        assert int(new_cursor) == int(watch.history_id) + 2

        again = await fake.list_history(new_cursor)
        assert again == GmailHistoryResult(messages=[], history_id=new_cursor)

    @pytest.mark.asyncio
    async def test_history_label_filter_skips_sent_copies(self) -> None:
        fake = FakeGmailClient()
        start = fake.history_id
        await fake.send_message(to="c@x.com", subject="Orçamento", body_text="b")
        fake.add_fake_message("reply")
        all_msgs, _ = await fake.list_history(start)
        inbox, _ = await fake.list_history(start, label_id="INBOX")
        assert [m.id for m in all_msgs] == ["fake-sent-1", "reply"]
        assert [m.id for m in inbox] == ["reply"]

    @pytest.mark.asyncio
    async def test_history_other_types_contribute_nothing(self) -> None:
        fake = FakeGmailClient()
        start = fake.history_id
        fake.add_fake_message("m")
        result = await fake.list_history(start, history_types=["labelAdded"])
        assert result.messages == []
        assert result.history_id == fake.history_id

    @pytest.mark.asyncio
    async def test_expired_cursor_raises_typed_error(self) -> None:
        fake = FakeGmailClient()
        old = fake.history_id
        fake.add_fake_message("a")
        fake.expire_history_before(fake.history_id)
        with pytest.raises(GmailHistoryExpiredError) as info:
            await fake.list_history(old)
        assert info.value.start_history_id == old
        # a fresh cursor still works
        assert (await fake.list_history(fake.history_id)).messages == []

    @pytest.mark.asyncio
    async def test_seeded_messages_are_history_before_first_watch(self) -> None:
        from noctusai_lib.integrations.gmail import make_gmail_client

        client = make_gmail_client(use_fake=True)
        assert isinstance(client, FakeGmailClient)
        client.add_fake_message("x")
        watch = await client.watch(TOPIC)
        assert (await client.list_history(watch.history_id)).messages == []


class TestFakeMetadata:
    @pytest.mark.asyncio
    async def test_default_headers_all_present(self) -> None:
        fake = FakeGmailClient()
        fake.add_fake_message(
            "r1",
            from_="cliente@x.com",
            subject="Re: Orçamento",
            headers={"message-id": "<r1@x.com>", "In-Reply-To": "<o1@noctus>"},
        )
        meta = await fake.get_message_metadata("r1")
        assert meta is not None
        assert tuple(meta.headers) == REPLY_MATCH_HEADERS
        assert meta.headers["From"] == "cliente@x.com"
        assert meta.headers["Subject"] == "Re: Orçamento"
        assert meta.headers["Message-ID"] == "<r1@x.com>"
        assert meta.headers["In-Reply-To"] == "<o1@noctus>"
        assert meta.headers["References"] == ""

    @pytest.mark.asyncio
    async def test_custom_headers_and_missing(self) -> None:
        fake = FakeGmailClient()
        fake.add_fake_message("m")
        meta = await fake.get_message_metadata("m", headers=["To", "X-Nope"])
        assert meta is not None and meta.headers == {"To": "me@example.com", "X-Nope": ""}
        assert await fake.get_message_metadata("absent") is None

    @pytest.mark.asyncio
    async def test_sent_message_has_rfc_message_id(self) -> None:
        fake = FakeGmailClient()
        sent = await fake.send_message(to="c@x.com", subject="s", body_text="b")
        meta = await fake.get_message_metadata(sent.message_id, ["Message-ID"])
        assert meta is not None
        assert meta.headers["Message-ID"] == "<fake-sent-1@fake.gmail.local>"


class TestFakeEndToEndReplyLoop:
    @pytest.mark.asyncio
    async def test_send_watch_reply_match(self) -> None:
        fake = FakeGmailClient()
        sent = await fake.send_message(to="c@x.com", subject="Orçamento #7", body_text="b")
        sent_meta = await fake.get_message_metadata(sent.message_id, ["Message-ID"])
        assert sent_meta is not None
        known = {sent_meta.headers["Message-ID"]: "orcamento-7"}
        watch = await fake.watch(TOPIC)

        fake.add_fake_message(
            "reply-1",
            thread_id=sent.thread_id,
            headers={
                "Message-ID": "<reply-1@cliente.com>",
                "In-Reply-To": sent_meta.headers["Message-ID"],
            },
        )
        messages, _ = await fake.list_history(watch.history_id, label_id="INBOX")
        assert [m.id for m in messages] == ["reply-1"]
        meta = await fake.get_message_metadata(messages[0].id)
        assert meta is not None
        matched = match_reply(meta.headers, known)
        assert matched is not None and known[matched] == "orcamento-7"


# ============================================================================
# RealGmailClient — watch / stop / history / metadata (injected service)
# ============================================================================


def _real(service: MagicMock) -> RealGmailClient:
    return RealGmailClient(oauth_credentials=_GoogleShapedCreds(), service=service)


class TestRealWatch:
    @pytest.mark.asyncio
    async def test_watch_sends_body_and_parses_response(self) -> None:
        svc = MagicMock()
        svc.users.return_value.watch.return_value.execute.return_value = {
            "historyId": "12345",
            "expiration": "1767225600000",
        }
        result = await _real(svc).watch(TOPIC)
        svc.users.return_value.watch.assert_called_once_with(
            userId="me",
            body={
                "topicName": TOPIC,
                "labelIds": ["INBOX"],
                "labelFilterBehavior": "include",
            },
        )
        assert result == WatchResult(
            history_id="12345",
            expiration=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_watch_bad_topic_fails_before_api_call(self) -> None:
        svc = MagicMock()
        with pytest.raises(ValueError):
            await _real(svc).watch("gmail-replies")
        svc.users.assert_not_called()

    @pytest.mark.asyncio
    async def test_watch_incomplete_response_is_loud(self) -> None:
        svc = MagicMock()
        svc.users.return_value.watch.return_value.execute.return_value = {"historyId": "1"}
        with pytest.raises(RuntimeError, match="incomplete"):
            await _real(svc).watch(TOPIC)

    @pytest.mark.asyncio
    async def test_watch_http_error_reraises(self) -> None:
        svc = MagicMock()
        svc.users.return_value.watch.return_value.execute.side_effect = _http_error(403)
        with pytest.raises(HttpError):
            await _real(svc).watch(TOPIC)

    @pytest.mark.asyncio
    async def test_stop_calls_users_stop(self) -> None:
        svc = MagicMock()
        await _real(svc).stop()
        svc.users.return_value.stop.assert_called_once_with(userId="me")


class TestRealHistory:
    @pytest.mark.asyncio
    async def test_drains_pages_dedups_and_advances_cursor(self) -> None:
        svc = MagicMock()
        history = svc.users.return_value.history.return_value
        pages = [
            {
                "history": [
                    {"messagesAdded": [{"message": {"id": "a", "threadId": "t", "labelIds": ["INBOX"]}}]},
                    {"messages": [{"id": "ignored"}]},
                ],
                "nextPageToken": "p2",
                "historyId": "110",
            },
            {
                "history": [
                    {"messagesAdded": [
                        {"message": {"id": "a", "threadId": "t"}},
                        {"message": {"id": "b", "threadId": "u"}},
                    ]}
                ],
                "historyId": "120",
            },
        ]
        calls: list[dict] = []

        def _list(**kwargs):
            calls.append(dict(kwargs))
            call = MagicMock()
            call.execute.return_value = pages[len(calls) - 1]
            return call

        history.list.side_effect = _list
        messages, cursor = await _real(svc).list_history("100", label_id="INBOX")
        assert [m.id for m in messages] == ["a", "b"]
        assert messages[0].label_ids == ("INBOX",)
        assert cursor == "120"
        assert calls[0] == {
            "userId": "me",
            "startHistoryId": "100",
            "historyTypes": ["messageAdded"],
            "labelId": "INBOX",
        }
        assert calls[1]["pageToken"] == "p2"

    @pytest.mark.asyncio
    async def test_empty_history_keeps_cursor_from_response(self) -> None:
        svc = MagicMock()
        svc.users.return_value.history.return_value.list.return_value.execute.return_value = {
            "historyId": "105"
        }
        result = await _real(svc).list_history("100")
        assert result == GmailHistoryResult(messages=[], history_id="105")

    @pytest.mark.asyncio
    async def test_404_raises_history_expired(self) -> None:
        svc = MagicMock()
        svc.users.return_value.history.return_value.list.return_value.execute.side_effect = (
            _http_error(404)
        )
        with pytest.raises(GmailHistoryExpiredError) as info:
            await _real(svc).list_history("7")
        assert info.value.start_history_id == "7"

    @pytest.mark.asyncio
    async def test_other_http_error_reraises(self) -> None:
        svc = MagicMock()
        svc.users.return_value.history.return_value.list.return_value.execute.side_effect = (
            _http_error(500)
        )
        with pytest.raises(HttpError):
            await _real(svc).list_history("7")


class TestRealMetadata:
    @pytest.mark.asyncio
    async def test_requests_metadata_format_and_maps_headers(self) -> None:
        svc = MagicMock()
        get = svc.users.return_value.messages.return_value.get
        get.return_value.execute.return_value = {
            "id": "m1",
            "threadId": "t1",
            "labelIds": ["INBOX"],
            "snippet": "ok",
            "internalDate": "1767225600000",
            "payload": {
                "headers": [
                    {"name": "FROM", "value": "c@x.com"},
                    {"name": "In-Reply-To", "value": "<o@n>"},
                ]
            },
        }
        meta = await _real(svc).get_message_metadata("m1")
        get.assert_called_once_with(
            userId="me", id="m1", format="metadata", metadataHeaders=list(REPLY_MATCH_HEADERS)
        )
        assert meta is not None
        assert meta.headers["From"] == "c@x.com"
        assert meta.headers["In-Reply-To"] == "<o@n>"
        assert meta.headers["References"] == ""
        assert meta.thread_id == "t1" and meta.label_ids == ("INBOX",)
        assert meta.received_at == datetime(2026, 1, 1, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_404_none_and_empty_id_none(self) -> None:
        svc = MagicMock()
        svc.users.return_value.messages.return_value.get.return_value.execute.side_effect = (
            _http_error(404)
        )
        client = _real(svc)
        assert await client.get_message_metadata("gone") is None
        assert await client.get_message_metadata("") is None

    @pytest.mark.asyncio
    async def test_5xx_reraises(self) -> None:
        svc = MagicMock()
        svc.users.return_value.messages.return_value.get.return_value.execute.side_effect = (
            _http_error(503)
        )
        with pytest.raises(HttpError):
            await _real(svc).get_message_metadata("m")


# ============================================================================
# push.parse_push_envelope
# ============================================================================


def _envelope(payload: object, **message_extra: object) -> dict:
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return {
        "message": {"data": data, "messageId": "pm-1", "publishTime": "2026-09-23T00:00:00Z", **message_extra},
        "subscription": "projects/p/subscriptions/s",
    }


class TestParsePushEnvelope:
    def test_parses_bytes_str_and_mapping(self) -> None:
        env = _envelope({"emailAddress": "me@x.com", "historyId": 9876543210})
        for body in (json.dumps(env).encode(), json.dumps(env), env):
            note = parse_push_envelope(body)
            assert note.email_address == "me@x.com"
            assert note.history_id == "9876543210"
            assert note.pubsub_message_id == "pm-1"
            assert note.subscription == "projects/p/subscriptions/s"

    def test_accepts_urlsafe_unpadded_data_and_string_history(self) -> None:
        raw = json.dumps({"emailAddress": "a@b.c", "historyId": "42"}).encode()
        env = {"message": {"data": base64.urlsafe_b64encode(raw).decode().rstrip("=")}}
        assert parse_push_envelope(env).history_id == "42"

    @pytest.mark.parametrize(
        "body",
        [
            b"not json",
            b"[]",
            {"nope": 1},
            {"message": {}},
            {"message": {"data": "***"}},
            {"message": {"data": base64.b64encode(b"[1]").decode()}},
            _envelope({"historyId": 1}),
            _envelope({"emailAddress": "a@b.c"}),
            _envelope({"emailAddress": "a@b.c", "historyId": True}),
            _envelope({"emailAddress": "a@b.c", "historyId": "12x"}),
        ],
    )
    def test_malformed_bodies_raise_typed_error(self, body: object) -> None:
        with pytest.raises(GmailPushEnvelopeError):
            parse_push_envelope(body)  # type: ignore[arg-type]


# ============================================================================
# push.verify_push_token
# ============================================================================

AUD = "https://igig.noctusai.com/api/gmail/push"
SA = "gmail-push@noctus-prod.iam.gserviceaccount.com"


def _verifier(claims: dict | None = None, raises: Exception | None = None):
    seen: list[tuple[str, str]] = []

    def _verify(token: str, audience: str) -> dict:
        seen.append((token, audience))
        if raises is not None:
            raise raises
        return claims or {}

    _verify.seen = seen  # type: ignore[attr-defined]
    return _verify


_GOOD = {"aud": AUD, "iss": "https://accounts.google.com", "email": SA, "email_verified": True}


class TestVerifyPushToken:
    def test_valid_token_with_pinned_service_account(self) -> None:
        v = _verifier(_GOOD)
        claims = verify_push_token("Bearer abc.def.ghi", AUD, SA, verifier=v)
        assert claims["email"] == SA
        assert v.seen == [("abc.def.ghi", AUD)]  # type: ignore[attr-defined]

    def test_audience_only_accepts_but_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        claims = verify_push_token("bearer t", AUD, verifier=_verifier(_GOOD))
        assert claims["aud"] == AUD
        assert "push_token_audience_only" in caplog.text

    @pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer", "Bearer   "])
    def test_missing_or_malformed_header(self, header: str | None) -> None:
        v = _verifier(_GOOD)
        with pytest.raises(GmailPushAuthError):
            verify_push_token(header, AUD, SA, verifier=v)
        assert v.seen == []  # type: ignore[attr-defined]

    def test_empty_audience_refused(self) -> None:
        with pytest.raises(GmailPushAuthError):
            verify_push_token("Bearer t", "", SA, verifier=_verifier(_GOOD))

    @pytest.mark.parametrize(
        "exc", [ValueError("Token expired"), TransportError("certs fetch failed")]
    )
    def test_verifier_failures_become_auth_error(self, exc: Exception) -> None:
        with pytest.raises(GmailPushAuthError):
            verify_push_token("Bearer t", AUD, SA, verifier=_verifier(raises=exc))

    @pytest.mark.parametrize(
        "override",
        [
            {"aud": "https://evil.example"},
            {"iss": "https://evil.example"},
            {"email": "attacker@evil.iam.gserviceaccount.com"},
            {"email_verified": False},
            {"email_verified": "true"},
        ],
    )
    def test_claim_mismatches_rejected(self, override: dict) -> None:
        with pytest.raises(GmailPushAuthError):
            verify_push_token("Bearer t", AUD, SA, verifier=_verifier({**_GOOD, **override}))

    def test_default_verifier_rejects_garbage_token_offline(self) -> None:
        # google-auth fails to decode a non-JWT before any cert fetch.
        with pytest.raises(GmailPushAuthError):
            verify_push_token("Bearer not-a-jwt", AUD, SA)


# ============================================================================
# pubsub_provisioning.ensure_push_subscription
# ============================================================================


class _PubSubDouble:
    """Stateful double of the Pub/Sub v1 discovery service."""

    def __init__(
        self,
        *,
        topic_exists: bool = False,
        policy: dict | None = None,
        subscription: dict | None = None,
    ) -> None:
        self.topic_exists = topic_exists
        self.policy = policy if policy is not None else {"etag": "E1"}
        self.subscription = subscription
        self.calls: list[str] = []
        self.set_policy_body: dict | None = None
        self.created_sub_body: dict | None = None
        self.modified_push: dict | None = None
        self.svc = MagicMock()
        topics = self.svc.projects.return_value.topics.return_value
        subs = self.svc.projects.return_value.subscriptions.return_value
        topics.get.side_effect = self._topic_get
        topics.create.side_effect = self._topic_create
        topics.getIamPolicy.side_effect = self._get_policy
        topics.setIamPolicy.side_effect = self._set_policy
        subs.get.side_effect = self._sub_get
        subs.create.side_effect = self._sub_create
        subs.modifyPushConfig.side_effect = self._sub_modify

    @staticmethod
    def _ok(value: object = None) -> MagicMock:
        call = MagicMock()
        call.execute.return_value = value if value is not None else {}
        return call

    @staticmethod
    def _err(status: int) -> MagicMock:
        call = MagicMock()
        call.execute.side_effect = _http_error(status)
        return call

    def _topic_get(self, topic: str) -> MagicMock:
        self.calls.append("topic.get")
        return self._ok({"name": topic}) if self.topic_exists else self._err(404)

    def _topic_create(self, name: str, body: dict) -> MagicMock:
        self.calls.append("topic.create")
        self.topic_exists = True
        return self._ok({"name": name})

    def _get_policy(self, resource: str) -> MagicMock:
        self.calls.append("topic.getIamPolicy")
        return self._ok(json.loads(json.dumps(self.policy)))

    def _set_policy(self, resource: str, body: dict) -> MagicMock:
        self.calls.append("topic.setIamPolicy")
        self.set_policy_body = body
        self.policy = body["policy"]
        return self._ok(body["policy"])

    def _sub_get(self, subscription: str) -> MagicMock:
        self.calls.append("sub.get")
        return self._ok(self.subscription) if self.subscription else self._err(404)

    def _sub_create(self, name: str, body: dict) -> MagicMock:
        self.calls.append("sub.create")
        self.created_sub_body = body
        self.subscription = {"name": name, **body}
        return self._ok(self.subscription)

    def _sub_modify(self, subscription: str, body: dict) -> MagicMock:
        self.calls.append("sub.modifyPushConfig")
        self.modified_push = body
        assert self.subscription is not None
        self.subscription["pushConfig"] = body["pushConfig"]
        return self._ok()


def _ensure(double: _PubSubDouble, **overrides: object):
    kwargs: dict = {
        "project_id": "noctus-prod",
        "topic": "gmail-replies",
        "push_endpoint": AUD,
        "audience": AUD,
        "credentials": None,
        "push_service_account": SA,
        "service": double.svc,
    }
    kwargs.update(overrides)
    return ensure_push_subscription(**kwargs)


class TestEnsurePushSubscription:
    def test_fresh_project_creates_everything(self) -> None:
        d = _PubSubDouble()
        result = _ensure(d)
        assert result.topic_name == TOPIC
        assert result.subscription_name == "projects/noctus-prod/subscriptions/gmail-replies-push"
        assert (result.created_topic, result.granted_publisher, result.created_subscription) == (
            True,
            True,
            True,
        )
        assert result.changed and not result.updated_push_config
        assert d.set_policy_body == {
            "policy": {
                "etag": "E1",
                "bindings": [
                    {
                        "role": "roles/pubsub.publisher",
                        "members": [f"serviceAccount:{GMAIL_PUSH_SERVICE_ACCOUNT}"],
                    }
                ],
            }
        }
        assert d.created_sub_body == {
            "topic": TOPIC,
            "pushConfig": {
                "pushEndpoint": AUD,
                "oidcToken": {"serviceAccountEmail": SA, "audience": AUD},
            },
            "ackDeadlineSeconds": 60,
        }

    def test_second_run_is_a_no_op(self) -> None:
        d = _PubSubDouble()
        _ensure(d)
        d.calls.clear()
        result = _ensure(d)
        assert not result.changed
        assert d.calls == ["topic.get", "topic.getIamPolicy", "sub.get"]

    def test_existing_publisher_binding_gets_member_appended(self) -> None:
        d = _PubSubDouble(
            topic_exists=True,
            policy={"etag": "E2", "bindings": [{"role": "roles/pubsub.publisher", "members": ["user:a@b.c"]}]},
        )
        result = _ensure(d)
        assert result.granted_publisher and not result.created_topic
        assert d.policy["bindings"] == [
            {
                "role": "roles/pubsub.publisher",
                "members": ["user:a@b.c", f"serviceAccount:{GMAIL_PUSH_SERVICE_ACCOUNT}"],
            }
        ]
        assert d.policy["etag"] == "E2"

    def test_drifted_push_config_is_modified(self) -> None:
        d = _PubSubDouble()
        _ensure(d)
        result = _ensure(d, push_endpoint="https://new.example/api/gmail/push")
        assert result.updated_push_config and not result.created_subscription
        assert d.modified_push is not None
        assert d.modified_push["pushConfig"]["pushEndpoint"] == "https://new.example/api/gmail/push"

    def test_subscription_on_other_topic_refused(self) -> None:
        d = _PubSubDouble(
            topic_exists=True,
            subscription={"topic": "projects/noctus-prod/topics/other", "pushConfig": {}},
        )
        with pytest.raises(PubSubProvisioningError, match="refusing to repoint"):
            _ensure(d)
        assert "sub.modifyPushConfig" not in d.calls

    def test_topic_read_failure_is_typed(self) -> None:
        d = _PubSubDouble()
        d.svc.projects.return_value.topics.return_value.get.side_effect = (
            lambda topic: _PubSubDouble._err(403)
        )
        with pytest.raises(PubSubProvisioningError):
            _ensure(d)

    def test_topic_create_conflict_counts_as_converged(self) -> None:
        d = _PubSubDouble()
        d.svc.projects.return_value.topics.return_value.create.side_effect = (
            lambda name, body: _PubSubDouble._err(409)
        )
        result = _ensure(d)
        assert result.created_topic is False and result.created_subscription

    def test_full_resource_names_and_custom_subscription(self) -> None:
        d = _PubSubDouble()
        result = _ensure(d, topic=TOPIC, subscription="igig-gmail")
        assert result.topic_name == TOPIC
        assert result.subscription_name == "projects/noctus-prod/subscriptions/igig-gmail"

    @pytest.mark.parametrize(
        "override",
        [
            {"push_endpoint": "http://insecure/x"},
            {"audience": ""},
            {"push_service_account": "not-an-email"},
            {"ack_deadline_seconds": 5},
            {"project_id": ""},
            {"topic": "projects/other/topics/t"},
            {"topic": "a/b"},
        ],
    )
    def test_bad_arguments_fail_before_any_call(self, override: dict) -> None:
        d = _PubSubDouble()
        with pytest.raises(ValueError):
            _ensure(d, **override)
        assert d.calls == []


# ============================================================================
# reply_matching
# ============================================================================


class TestMatchReply:
    KNOWN = ["<orc-1@mail.gmail.com>", "<orc-2@mail.gmail.com>"]

    def test_in_reply_to_wins(self) -> None:
        headers = {
            "In-Reply-To": "<orc-2@mail.gmail.com>",
            "References": "<orc-1@mail.gmail.com> <orc-2@mail.gmail.com>",
        }
        assert match_reply(headers, self.KNOWN) == "<orc-2@mail.gmail.com>"

    def test_references_newest_first(self) -> None:
        headers = {"references": "<orc-1@mail.gmail.com>\r\n <x@y> <orc-2@MAIL.gmail.com> <z@w>"}
        assert match_reply(headers, self.KNOWN) == "<orc-2@mail.gmail.com>"

    def test_case_insensitive_header_names_and_domain(self) -> None:
        assert match_reply({"IN-REPLY-TO": "<orc-1@MAIL.GMAIL.COM>"}, self.KNOWN) == self.KNOWN[0]

    def test_local_part_is_case_sensitive(self) -> None:
        assert match_reply({"In-Reply-To": "<ORC-1@mail.gmail.com>"}, self.KNOWN) is None

    def test_bare_ids_without_brackets(self) -> None:
        assert match_reply({"In-Reply-To": "orc-1@mail.gmail.com"}, self.KNOWN) == self.KNOWN[0]

    def test_thread_fallback_only_when_headers_miss(self) -> None:
        threads = {"thr-9": "<orc-1@mail.gmail.com>"}
        assert match_reply({}, self.KNOWN, thread_id="thr-9", known_threads=threads) == self.KNOWN[0]
        assert match_reply({}, self.KNOWN, thread_id="thr-0", known_threads=threads) is None
        assert match_reply({}, self.KNOWN, thread_id="thr-9") is None

    def test_our_own_sent_copy_never_matches(self) -> None:
        headers = {"Message-ID": "<orc-1@mail.gmail.com>", "In-Reply-To": "<orc-2@mail.gmail.com>"}
        assert match_reply(headers, self.KNOWN, thread_id="t", known_threads={"t": "x"}) is None

    def test_no_evidence_returns_none(self) -> None:
        assert match_reply({"In-Reply-To": "<other@x>"}, self.KNOWN) is None
        assert match_reply({"In-Reply-To": "<a@b>"}, []) is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (" <Abc@Mail.Example.COM> ", "Abc@mail.example.com"),
            ("", ""),
            ("<no-at-sign>", "no-at-sign"),
        ],
    )
    def test_normalize_message_id(self, raw: str, expected: str) -> None:
        assert normalize_message_id(raw) == expected
