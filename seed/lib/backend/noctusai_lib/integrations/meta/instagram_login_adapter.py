"""Instagram API **with Instagram Login** — read adapter for IG Direct.

The agency-model sibling of ``MetaOAuthAdapter`` (which is the Facebook-Login /
Page-token model). This adapter talks to ``graph.instagram.com`` with a
**per-client Instagram User access token** and needs **no Facebook Page** — the
model Meta recommends for agencies reading many clients' inboxes (see roadmap
``ig-login-messaging-migration-2026-07`` + memory
``reference_meta_ig_dm_facebook_login_model``).

Model contrast (do NOT cross the two):

| | Facebook-Login (``MetaOAuthAdapter``) | Instagram-Login (this) |
|---|---|---|
| Host | ``graph.facebook.com`` | ``graph.instagram.com`` (``IG_GRAPH_BASE``) |
| Token | Page access token | IG **User** access token |
| FB Page | required | not required |
| Conversations node | ``/{PAGE-ID}/conversations`` | ``/me/conversations`` |
| Permissions | ``instagram_manage_messages`` + ``pages_manage_metadata`` | ``instagram_business_basic`` + ``instagram_business_manage_messages`` |

S1 (this file) covers the **read** surface — list conversations + list
messages. Send (``POST /me/messages``) is roadmap S4. The conversation/message
JSON shapes match the Facebook-Login model, so the same ``conversation_from_body``
/ ``direct_message_from_body`` mappers + ``Conversation`` / ``DirectMessage``
dataclasses are reused (no second copy).
"""
from __future__ import annotations

from typing import Any, Protocol

from noctusai_lib.integrations.meta import _meta_api
from noctusai_lib.integrations.meta._meta_api import IG_GRAPH_BASE, MetaGraphError
from noctusai_lib.integrations.meta.mappers import (
    IG_CONVERSATION_FIELDS,
    IG_DM_FIELDS,
    conversation_from_body,
    direct_message_from_body,
)
from noctusai_lib.integrations.meta.types import Conversation, DirectMessage

__all__ = [
    "InstagramLoginMessagingAdapter",
    "InstagramLoginOAuthAdapter",
    "FakeInstagramLoginAdapter",
]


class InstagramLoginMessagingAdapter(Protocol):
    """Read-only IG Direct contract for the Instagram-Login model.

    Concrete: ``InstagramLoginOAuthAdapter`` (live ``graph.instagram.com``),
    ``FakeInstagramLoginAdapter`` (deterministic in-memory; dev/test)."""

    def me(self) -> dict[str, Any]: ...

    def list_instagram_conversations(self, limit: int = ...) -> list[Conversation]: ...

    def list_instagram_messages(
        self, conversation_id: str, limit: int = ...
    ) -> list[DirectMessage]: ...

    def send_instagram_message(
        self, recipient_id: str, text: str
    ) -> DirectMessage: ...


class InstagramLoginOAuthAdapter:
    """Live Instagram-Login read adapter over ``graph.instagram.com``.

    Bound to ONE client's Instagram User access token — there is no Page and
    no ``/me/accounts`` fan-out here; ``/me`` IS the IG professional account.
    Needs ``instagram_business_basic`` + ``instagram_business_manage_messages``
    on the token (granted via Instagram Business Login — roadmap S2)."""

    def __init__(
        self,
        ig_user_token: str,
        *,
        version: str = _meta_api.DEFAULT_GRAPH_VERSION,
    ) -> None:
        self._token = ig_user_token
        self._version = version

    def me(self) -> dict[str, Any]:
        """The authenticated IG professional account (`/me`): `id`,
        `username`. Used as a best-effort label probe after OAuth (or to
        validate a manually-pasted token) — never the primary auth
        boundary (Graph itself is the source of truth on token validity;
        a probe failure raises `MetaGraphError`, never a silent pass)."""

        return _meta_api.graph_get(
            "me",
            access_token=self._token,
            params={"fields": "id,username"},
            version=self._version,
            base=IG_GRAPH_BASE,
        )

    def list_instagram_conversations(self, limit: int = 25) -> list[Conversation]:
        """List IG Direct threads — ``GET /me/conversations?platform=instagram``
        with the IG User token. Lean fields (``participants{id}``) to keep the
        query cheap, same as the Facebook-Login path."""
        rows = _meta_api.graph_paged(
            "me/conversations",
            access_token=self._token,
            params={
                "platform": "instagram",
                "fields": IG_CONVERSATION_FIELDS,
                "limit": limit,
            },
            version=self._version,
            base=IG_GRAPH_BASE,
            limit=limit,
        )
        return [conversation_from_body(r) for r in rows]

    def list_instagram_messages(
        self, conversation_id: str, limit: int = 25
    ) -> list[DirectMessage]:
        """Messages inside one thread. ``GET /{conversation}/messages`` returns
        bare ``{"id": ...}`` rows, so each is re-fetched for its body — the same
        link-probe-then-detail shape the Facebook-Login adapter uses."""
        rows = _meta_api.graph_paged(
            f"{conversation_id}/messages",
            access_token=self._token,
            params={"limit": limit},
            version=self._version,
            base=IG_GRAPH_BASE,
            limit=limit,
        )
        messages: list[DirectMessage] = []
        for row in rows:
            msg_id = str(row.get("id") or "")
            if not msg_id:
                continue
            detail = _meta_api.graph_get(
                msg_id,
                access_token=self._token,
                params={"fields": IG_DM_FIELDS},
                version=self._version,
                base=IG_GRAPH_BASE,
            )
            messages.append(
                direct_message_from_body(detail, conversation_id=conversation_id)
            )
        return messages

    def send_instagram_message(self, recipient_id: str, text: str) -> DirectMessage:
        """Send an IG Direct message — ``POST /me/messages`` on
        ``graph.instagram.com`` with the IG User token.

        The Instagram-Login twin of ``MetaOAuthAdapter.send_instagram_message``
        (which posts to ``/{PAGE-ID}/messages`` with a Page token). Same Send-API
        body shape — nested ``recipient``/``message`` objects are JSON-encoded
        form fields — but there is **no page id**: ``/me`` IS the professional
        account, which is the whole point of this model.

        ``sender_id`` on the returned message is the IG user id resolved from
        ``me()``, NOT a page id, so the read path's
        ``direction = outbound if sender_id == self_id`` comparison stays true
        for a just-sent message on this model.

        **Production gate:** ``instagram_business_manage_messages`` needs
        Advanced Access to message people who hold no role on the app. Absent
        it, Graph returns a permission error and this raises ``MetaGraphError``
        with ``requires_app_review`` true — never a faked success."""

        import json

        # Resolved BEFORE the send, deliberately. Graph's send response carries
        # no sender, so the id has to come from `/me` — and doing that first
        # means a token/permission failure raises with NOTHING sent, instead of
        # leaving a delivered message behind an error the caller will retry.
        sender_id = str(self.me().get("id") or "")

        created = _meta_api.graph_post(
            "me/messages",
            access_token=self._token,
            data={
                "recipient": json.dumps({"id": recipient_id}),
                "message": json.dumps({"text": text}),
            },
            version=self._version,
            base=IG_GRAPH_BASE,
        )
        message_id = str(created.get("message_id") or created.get("id") or "")
        if not message_id:
            raise MetaGraphError(
                f"IG Direct send to {recipient_id} returned no message id",
                code=200,
            )
        return DirectMessage(
            id=message_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=text,
        )


class FakeInstagramLoginAdapter:
    """Deterministic in-memory Instagram-Login adapter (dev/test default).

    Mirrors ``FakeMetaAdapter``'s seed-then-serve shape but for the single
    IG-user (no page) model: conversations are keyed by nothing (one inbox per
    token), messages by conversation id."""

    def __init__(self) -> None:
        self._conversations: list[Conversation] = []
        self._messages_by_conversation: dict[str, list[DirectMessage]] = {}
        self._me: dict[str, Any] = {"id": "FAKE_IG_USER", "username": "fake_ig_user"}
        self._counter = 0

    def seed(
        self,
        *,
        conversations: list[Conversation] | None = None,
        messages_by_conversation: dict[str, list[DirectMessage]] | None = None,
        me: dict[str, Any] | None = None,
    ) -> "FakeInstagramLoginAdapter":
        if conversations is not None:
            self._conversations = list(conversations)
        if messages_by_conversation is not None:
            self._messages_by_conversation = {
                k: list(v) for k, v in messages_by_conversation.items()
            }
        if me is not None:
            self._me = dict(me)
        return self

    def me(self) -> dict[str, Any]:
        return dict(self._me)

    def list_instagram_conversations(self, limit: int = 25) -> list[Conversation]:
        return list(self._conversations)[:limit]

    def list_instagram_messages(
        self, conversation_id: str, limit: int = 25
    ) -> list[DirectMessage]:
        return list(self._messages_by_conversation.get(conversation_id, []))[:limit]

    def send_instagram_message(self, recipient_id: str, text: str) -> DirectMessage:
        """Append an outbound message to the recipient's thread and return it.

        The thread is keyed by ``recipient_id`` — on this model a conversation
        IS the other participant, so a send with no prior thread creates one
        (which is what Graph does too). Sent messages are readable back through
        ``list_instagram_messages``, so a test can assert the round trip rather
        than just the return value."""
        self._counter += 1
        message = DirectMessage(
            id=f"FAKE_IG_SENT_{self._counter}",
            sender_id=str(self._me.get("id") or ""),
            recipient_id=recipient_id,
            text=text,
        )
        self._messages_by_conversation.setdefault(recipient_id, []).append(message)
        return message


# Re-export MetaGraphError so consumers importing from this module have the
# error type without reaching into `_meta_api` (same failure contract).
__all__.append("MetaGraphError")
