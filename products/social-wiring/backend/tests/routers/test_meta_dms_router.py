"""Tests for meta_dms_router — IG conversations/messages/send.

Account-scoped (Wave 3). Covers the WhatsApp-aligned ``direction``
field (inbound|outbound, derived by comparing sender_id to the
resolved ig_user_id), honest-null fields Graph doesn't expose
(``last_message``/``unread`` on the conversations edge), and the
uniform ``MetaGraphError`` gate."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    Conversation,
    DirectMessage,
    FakeMetaAdapter,
    InstagramAccount,
    MetaGraphError,
)
from noctusai_lib.testing import MockSupabaseClient, bind_consent_module_to_mock

_ACCOUNT = "00000000-0000-4000-8000-0000000000ac"
_ORG = "00000000-0000-4000-8000-000000000099"
_QS = f"account_id={_ACCOUNT}&org_id={_ORG}"
_IG_USER = "17841400000000000"
_OTHER = "999888777"


class _GatedAdapter(FakeMetaAdapter):
    def __init__(self, *, error: MetaGraphError) -> None:
        super().__init__()
        self._error = error

    def send_instagram_message(self, *a, **kw):
        raise self._error

    def list_instagram_conversations(self, *a, **kw):
        raise self._error


def _seeded():
    adapter = FakeMetaAdapter()
    adapter.seed(
        ig_accounts=[InstagramAccount(id=_IG_USER, username="one")],
        conversations_by_ig_user={
            _IG_USER: [
                Conversation(id="conv-1", participant_ids=[_IG_USER, _OTHER])
            ]
        },
        messages_by_conversation={
            "conv-1": [
                DirectMessage(
                    id="m1", conversation_id="conv-1",
                    sender_id=_OTHER, recipient_id=_IG_USER, text="oi",
                ),
                DirectMessage(
                    id="m2", conversation_id="conv-1",
                    sender_id=_IG_USER, recipient_id=_OTHER, text="hello back",
                ),
            ]
        },
    )
    return adapter


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    from app.main import app

    app.dependency_overrides.clear()


def _override(adapter):
    from app.main import app
    from app.routers._meta_common import get_account_adapter

    app.dependency_overrides[get_account_adapter] = lambda: adapter
    return adapter


class TestConversations:
    def test_list_conversations(self, client):
        _override(_seeded())
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["conversations"]) == 1
        conv = body["conversations"][0]
        assert conv["id"] == "conv-1"
        assert conv["contact_id"] == _OTHER
        # Honest-null: Graph's conversations edge has no message body /
        # unread count — never faked.
        assert conv["last_message"] is None
        assert conv["unread"] is None

    def test_list_conversations_graph_error_502(self, client):
        gated = _GatedAdapter(error=MetaGraphError("boom", code=4, http_status=500))
        gated.seed(ig_accounts=[InstagramAccount(id=_IG_USER, username="one")])
        _override(gated)
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 502, resp.text


class TestMessages:
    def test_list_messages_direction(self, client):
        _override(_seeded())
        resp = client.get(
            f"/api/meta/instagram/messages?{_QS}&conversation_id=conv-1"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        by_id = {m["id"]: m for m in body["messages"]}
        assert by_id["m1"]["direction"] == "inbound"
        assert by_id["m1"]["body"] == "oi"
        assert by_id["m2"]["direction"] == "outbound"

    def test_send_message(self, client):
        adapter = _seeded()
        _override(adapter)
        resp = client.post(
            f"/api/meta/instagram/messages?{_QS}",
            json={"recipient_id": _OTHER, "text": "sending"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["direction"] == "outbound"
        assert body["body"] == "sending"
        assert len(adapter.sent_instagram_messages) == 1

    def test_send_message_app_review_gate_returns_200_structured(self, client):
        gated = _GatedAdapter(
            error=MetaGraphError("permission denied", code=10, http_status=400)
        )
        gated.seed(ig_accounts=[InstagramAccount(id=_IG_USER, username="one")])
        _override(gated)
        resp = client.post(
            f"/api/meta/instagram/messages?{_QS}",
            json={"recipient_id": _OTHER, "text": "sending"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["requires_app_review"] is True

    def test_send_message_empty_text_rejected_422(self, client):
        _override(_seeded())
        resp = client.post(
            f"/api/meta/instagram/messages?{_QS}",
            json={"recipient_id": _OTHER, "text": ""},
        )
        assert resp.status_code == 422, resp.text
