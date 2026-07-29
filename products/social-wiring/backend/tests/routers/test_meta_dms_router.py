"""Tests for meta_dms_router — IG conversations/messages/send.

Account-scoped (Wave 3). Covers the WhatsApp-aligned ``direction``
field (inbound|outbound, derived by comparing sender_id to the
resolved ig_user_id), honest-null fields Graph doesn't expose
(``last_message``/``unread`` on the conversations edge), and the
uniform ``MetaGraphError`` gate."""
from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.meta import (
    Conversation,
    DirectMessage,
    FakeInstagramLoginAdapter,
    FakeMetaAdapter,
    InstagramAccount,
    MetaGraphError,
)
from noctusai_lib.testing import MockSupabaseClient, bind_consent_module_to_mock

_ACCOUNT = "00000000-0000-4000-8000-0000000000ac"
_ORG = "00000000-0000-4000-8000-000000000099"
_QS = f"account_id={_ACCOUNT}&org_id={_ORG}"
_IG_USER = "17841400000000000"
_PAGE = "1122334455"
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
        ig_accounts=[InstagramAccount(id=_IG_USER, username="one", page_id=_PAGE)],
        conversations_by_page={
            _PAGE: [
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
    """Override the DM gateway with the FACEBOOK-LOGIN one over ``adapter``.

    Deliberately wraps the real ``FacebookLoginDmGateway`` rather than
    overriding it away: every existing test below then exercises the gateway's
    page/account resolution too (including the no-linked-page 404), so the S3
    refactor is proven behaviour-identical instead of merely compiling."""
    from app.main import app
    from app.routers._dm_gateway import FacebookLoginDmGateway
    from app.routers._meta_common import get_dm_gateway

    gateway = FacebookLoginDmGateway(adapter)
    app.dependency_overrides[get_dm_gateway] = lambda: gateway
    return adapter


def _override_ig_login(adapter):
    """Override with the INSTAGRAM-LOGIN gateway over an IG-Login adapter."""
    from app.main import app
    from app.routers._dm_gateway import InstagramLoginDmGateway
    from app.routers._meta_common import get_dm_gateway

    gateway = InstagramLoginDmGateway(adapter)
    app.dependency_overrides[get_dm_gateway] = lambda: gateway
    return adapter


class TestConversations:
    def test_conversations_404_when_ig_account_has_no_linked_page(self, client):
        # Facebook-Login model: IG Direct is served through the linked
        # Page. An IG account with no page_id can't reach conversations —
        # surfaced as a structured 404, never a silent empty list.
        adapter = FakeMetaAdapter()
        adapter.seed(
            ig_accounts=[InstagramAccount(id=_IG_USER, username="one", page_id=None)]
        )
        _override(adapter)
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 404, resp.text
        assert "page" in resp.json()["error"]["message"].lower()

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
        gated.seed(ig_accounts=[InstagramAccount(id=_IG_USER, username="one", page_id=_PAGE)])
        _override(gated)
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 502, resp.text

    def test_list_conversations_advanced_access_timeout_returns_app_review_gate(
        self, client
    ):
        # Standard-Access `instagram_manage_messages` on a busy inbox makes
        # Graph EXPIRE the conversations query (code -2 / subcode 2534084;
        # in prod the httpx read-timeout → http_status 504 fires first). It
        # is a cacheable Advanced-Access (App Review) gate — the DMs read
        # must fail fast into a structured 200 `{requires_app_review: true}`
        # with an actionable message, never a 30s skeleton → raw 502.
        for err in (
            MetaGraphError(
                "Timeout", code=-2, error_subcode=2534084, http_status=400
            ),
            MetaGraphError("Graph API request timed out", http_status=504),
        ):
            gated = _GatedAdapter(error=err)
            gated.seed(
                ig_accounts=[
                    InstagramAccount(id=_IG_USER, username="one", page_id=_PAGE)
                ]
            )
            _override(gated)  # re-override replaces the prior binding
            resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["requires_app_review"] is True
            assert "instagram_manage_messages" in body["error"]

    def test_list_conversations_capability_gate_returns_200_structured(self, client):
        # Graph #3 ("Application does not have the capability") is a
        # Meta-side SETUP gate (Messenger/IG-messaging product not wired up),
        # not a server failure — it must surface as a structured 200
        # `{requires_setup: true}` so the DMs tab renders an actionable
        # "finish Meta setup" card, NOT a raw 502 toast.
        gated = _GatedAdapter(
            error=MetaGraphError(
                "Application does not have the capability to make this API call.",
                code=3,
                http_status=400,
            )
        )
        gated.seed(ig_accounts=[InstagramAccount(id=_IG_USER, username="one", page_id=_PAGE)])
        _override(gated)
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["requires_setup"] is True
        assert "requires_app_review" not in body  # distinct gate


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
        gated.seed(ig_accounts=[InstagramAccount(id=_IG_USER, username="one", page_id=_PAGE)])
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


# ─── Instagram-Login model (roadmap S3) ─────────────────────────────────
# The SAME three routes, served from an account connected through Instagram
# Business Login: no Facebook Page anywhere in the chain. Before S3 this
# model was unreachable — the router only spoke the Page-token shape, so an
# account stored by S2's OAuth callback had no route that could read it.


def _seeded_ig_login():
    fake = FakeInstagramLoginAdapter()
    fake.seed(
        me={"id": _IG_USER, "username": "one"},
        conversations=[Conversation(id="conv-1", participant_ids=[_IG_USER, _OTHER])],
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
    return fake


class TestInstagramLoginModel:
    def test_list_conversations_without_any_page(self, client):
        # The point of the model: no page_id is seeded, none is resolved,
        # and the conversations still come back. On the Facebook-Login
        # gateway this exact absence is a 404.
        _override_ig_login(_seeded_ig_login())
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["conversations"]) == 1
        assert body["conversations"][0]["contact_id"] == _OTHER

    def test_direction_derives_from_me_not_a_page(self, client):
        # `self_id` comes from /me on this model. If the gateway resolved it
        # from anything else, BOTH messages would read inbound.
        _override_ig_login(_seeded_ig_login())
        resp = client.get(
            f"/api/meta/instagram/messages?{_QS}&conversation_id=conv-1"
        )
        assert resp.status_code == 200, resp.text
        by_id = {m["id"]: m for m in resp.json()["messages"]}
        assert by_id["m1"]["direction"] == "inbound"
        assert by_id["m2"]["direction"] == "outbound"

    def test_send_round_trips_through_the_ig_user_node(self, client):
        adapter = _override_ig_login(_seeded_ig_login())
        resp = client.post(
            f"/api/meta/instagram/messages?{_QS}",
            json={"recipient_id": _OTHER, "text": "enviando"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["direction"] == "outbound"
        assert body["body"] == "enviando"
        assert body["sender_id"] == _IG_USER
        # Readable back through the read path, not just returned.
        assert any(
            m.text == "enviando"
            for m in adapter.list_instagram_messages(_OTHER)
        )

    def test_graph_error_still_maps_to_502(self, client):
        class _Gated(FakeInstagramLoginAdapter):
            def list_instagram_conversations(self, *a, **kw):
                raise MetaGraphError("boom", code=4, http_status=500)

        _override_ig_login(_Gated().seed(me={"id": _IG_USER, "username": "one"}))
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 502, resp.text

    def test_advanced_access_gate_maps_the_same_on_this_model(self, client):
        # Advanced Access gates BOTH models (it is an App-Review gate, not a
        # model artifact) — the honest notice must not regress to a raw 502
        # just because the account was connected the other way.
        class _Gated(FakeInstagramLoginAdapter):
            def list_instagram_conversations(self, *a, **kw):
                raise MetaGraphError(
                    "Timeout", code=-2, error_subcode=2534084, http_status=400
                )

        _override_ig_login(_Gated().seed(me={"id": _IG_USER, "username": "one"}))
        resp = client.get(f"/api/meta/instagram/conversations?{_QS}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["requires_app_review"] is True


class TestGatewayModelResolution:
    """``build_dm_gateway`` picks the model from the stored ``provider``."""

    def test_meta_provider_yields_facebook_login_gateway(self):
        from app.routers._dm_gateway import FacebookLoginDmGateway, build_dm_gateway

        with patch(
            "app.routers._dm_gateway.get_dm_adapter_for_account",
            return_value=("facebook_login", FakeMetaAdapter()),
        ):
            gw = build_dm_gateway(UUID(_ACCOUNT), UUID(_ORG))
        assert isinstance(gw, FacebookLoginDmGateway)
        assert gw.model == "facebook_login"

    def test_instagram_provider_yields_instagram_login_gateway(self):
        from app.routers._dm_gateway import InstagramLoginDmGateway, build_dm_gateway

        with patch(
            "app.routers._dm_gateway.get_dm_adapter_for_account",
            return_value=("instagram_login", FakeInstagramLoginAdapter()),
        ):
            gw = build_dm_gateway(UUID(_ACCOUNT), UUID(_ORG))
        assert isinstance(gw, InstagramLoginDmGateway)
        assert gw.model == "instagram_login"

    def test_unknown_model_raises_rather_than_returning_none(self):
        from app.routers._dm_gateway import build_dm_gateway

        with patch(
            "app.routers._dm_gateway.get_dm_adapter_for_account",
            return_value=("carrier_pigeon", object()),
        ):
            with pytest.raises(ValueError):
                build_dm_gateway(UUID(_ACCOUNT), UUID(_ORG))
