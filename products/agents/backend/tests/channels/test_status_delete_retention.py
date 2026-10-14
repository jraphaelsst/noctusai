"""Status (§3.2), deletion on request and the 180-day purge (§10.1 M5), and the
read-only channel listing of the agents UI API (§3.3)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.channels.retention import purge_expired
from app.config import settings
from tests.channels.conftest import CONNECTION_ID, OTHER_ORG, turn_body
from tests.routers.conftest import DEFAULT_USER_ID, bind_user, seed_org_role


def _status(chan, key="lead-imob", **kw):
    with chan.as_token(**kw):
        return chan.request("GET", f"/api/channels/agents/{key}/status")


class TestStatus:
    def test_shape_for_a_published_active_agent_with_a_key(self, chan):
        chan.seed_agent()
        resp = _status(chan)
        assert resp.status_code == 200
        assert resp.json() == {
            "agent_key": "lead-imob", "nome": "Julia", "ativo": True, "versao_ativa": 1,
            "provider": "openai", "model": "gpt-5.6-terra", "llm_configurado": True,
        }

    def test_org_without_a_key_reports_llm_configurado_false(self, chan):
        chan.seed_agent()
        chan.keys.clear()
        assert _status(chan).json()["llm_configurado"] is False

    def test_unpublished_agent_has_null_version_provider_and_model(self, chan):
        chan.seed_agent(ativo=False, publish=False)
        body = _status(chan).json()
        assert body["ativo"] is False
        assert (body["versao_ativa"], body["provider"], body["model"]) == (None, None, None)
        assert body["llm_configurado"] is True  # follows the draft's provider

    def test_unknown_agent_404_other_agent_403(self, chan):
        chan.seed_agent()
        assert _status(chan, "nope").status_code == 404
        resp = _status(chan, principal=uuid4())
        assert resp.status_code == 403 and resp.json()["code"] == "agent_not_allowed"

    def test_other_orgs_token_does_not_see_this_orgs_agent(self, chan):
        chan.seed_agent()
        resp = _status(chan, org_id=OTHER_ORG, principal=chan.agent.id)
        assert resp.status_code == 404


def _delete(chan, body=None, scopes=("agents:channel-turn",), **kw):
    body = body or {k: turn_body()[k] for k in ("agent_key", "channel", "channel_ref")}
    with chan.as_token(*scopes, **kw):
        return chan.request("DELETE", "/api/channels/conversations", json=body)


class TestDeletionOnRequest:
    def test_erases_messages_contact_and_ledger_and_is_204(self, chan):
        chan.seed_agent()
        cid = chan.turn(turn_body("Oi", ids=["m1"])).json()["conversation_id"]
        convs, msgs = chan.rt.stores.conversations, chan.rt.stores.messages
        assert msgs.list(chan.org_id, UUID(cid))
        resp = _delete(chan)
        assert resp.status_code == 204 and resp.content == b""
        assert msgs.list(chan.org_id, UUID(cid)) == []
        assert convs.list_channel(chan.org_id) == []  # the conversation row (and its contact) is gone
        assert chan.inbound.find(chan.org_id, CONNECTION_ID, ["m1"]) == {}

    def test_after_erasure_the_same_ids_start_a_fresh_conversation(self, chan):
        chan.seed_agent()
        first = chan.turn(turn_body("Oi", ids=["m1"])).json()["conversation_id"]
        _delete(chan)
        again = chan.turn(turn_body("Oi", ids=["m1"]))
        assert again.status_code == 200
        assert again.json()["conversation_id"] != first
        assert len(chan.provider.calls) == 2

    def test_is_idempotent_204_when_nothing_exists(self, chan):
        chan.seed_agent()
        assert _delete(chan).status_code == 204
        assert _delete(chan).status_code == 204

    def test_only_the_named_conversation_is_erased(self, chan):
        chan.seed_agent()
        keep = chan.turn(turn_body("Oi", chat_id="keep", ids=["k1"])).json()["conversation_id"]
        chan.turn(turn_body("Oi", chat_id="gone", ids=["g1"]))
        body = {k: turn_body(chat_id="gone")[k] for k in ("agent_key", "channel", "channel_ref")}
        assert _delete(chan, body).status_code == 204
        remaining = [str(c.id) for c in chan.rt.stores.conversations.list_channel(chan.org_id)]
        assert remaining == [keep]

    def test_a_running_turn_blocks_it_409(self, chan):
        chan.seed_agent()
        cid = chan.turn().json()["conversation_id"]
        convs = chan.rt.stores.conversations
        assert convs.try_acquire_turn(chan.org_id, UUID(cid), "other", 60)
        resp = _delete(chan)
        assert resp.status_code == 409 and resp.json()["code"] == "turn_in_progress"
        assert convs.list_channel(chan.org_id)  # untouched

    def test_token_of_another_org_erases_nothing(self, chan):
        chan.seed_agent()
        chan.turn()
        resp = _delete(chan, org_id=OTHER_ORG, principal=chan.agent.id)
        assert resp.status_code == 404  # no such agent in org B
        assert len(chan.rt.stores.conversations.list_channel(chan.org_id)) == 1

    def test_needs_the_turn_scope_and_the_issuer(self, chan):
        chan.seed_agent()
        chan.turn()
        assert _delete(chan, scopes=("agents:channel-status",)).status_code == 403
        assert _delete(chan, issuer="agents").status_code == 403
        assert len(chan.rt.stores.conversations.list_channel(chan.org_id)) == 1

    def test_a_user_conversation_can_never_be_erased_through_this_route(self, chan):
        chan.seed_agent()
        convs = chan.rt.stores.conversations
        user_conv = convs.create(chan.org_id, chan.agent.id, DEFAULT_USER_ID)
        assert convs.purge_conversation(chan.org_id, user_conv.id) is False


class TestRetentionPurge:
    def _age(self, chan, conversation_id: str, days: int):
        row = chan.rt.stores.conversations._rows[UUID(conversation_id)]
        row["last_message_at"] = datetime.now(timezone.utc) - timedelta(days=days)

    def test_conversations_idle_over_180_days_are_purged_with_messages_and_ledger(self, chan):
        chan.seed_agent()
        old = chan.turn(turn_body("velha", chat_id="old", ids=["o1"])).json()["conversation_id"]
        recent = chan.turn(turn_body("nova", chat_id="new", ids=["n1"])).json()["conversation_id"]
        self._age(chan, old, 181)
        self._age(chan, recent, 179)
        purged = purge_expired(chan.retention, retention_days=settings.channel_retention_days)
        assert purged == 1
        convs = chan.rt.stores.conversations
        assert [str(c.id) for c in convs.list_channel(chan.org_id)] == [recent]
        assert chan.rt.stores.messages.list(chan.org_id, UUID(old)) == []
        assert chan.rt.stores.messages.list(chan.org_id, UUID(recent))
        assert chan.inbound.find(chan.org_id, CONNECTION_ID, ["o1"]) == {}
        assert chan.inbound.find(chan.org_id, CONNECTION_ID, ["n1"]) != {}

    def test_retention_is_180_days_by_default(self, chan):
        assert settings.channel_retention_days == 180

    def test_user_conversations_are_never_purged(self, chan):
        chan.seed_agent()
        convs = chan.rt.stores.conversations
        user_conv = convs.create(chan.org_id, chan.agent.id, DEFAULT_USER_ID)
        convs._rows[user_conv.id]["created_at"] = datetime.now(timezone.utc) - timedelta(days=999)
        assert purge_expired(chan.retention, retention_days=180) == 0
        assert convs.get(chan.org_id, user_conv.id)

    def test_a_conversation_with_a_live_turn_is_skipped(self, chan):
        chan.seed_agent()
        cid = chan.turn().json()["conversation_id"]
        self._age(chan, cid, 400)
        assert chan.rt.stores.conversations.try_acquire_turn(chan.org_id, UUID(cid), "live", 60)
        assert purge_expired(chan.retention, retention_days=180) == 0

    def test_the_cron_is_registered_daily(self):
        import app.scheduler as scheduler
        from noctusai_lib.api import scheduler as seed_scheduler

        scheduler.configure()
        job = seed_scheduler.scheduler.get_job(scheduler.CHANNEL_PURGE_JOB_NAME)
        assert job is not None
        assert "hour='3'" in str(job.trigger) and "minute='30'" in str(job.trigger)


class TestChannelConversationsInTheAgentsUi:
    def test_admin_lists_channel_conversations_filterable_by_channel(self, chan):
        chan.seed_agent()
        chan.turn(turn_body("Oi", chat_id="c1", ids=["a"]))
        chan.turn(turn_body("Oi", chat_id="c2", ids=["b"]))
        resp = chan.client.get("/api/conversations/channel", params={"agent_key": "lead-imob"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        item = body["items"][0]
        assert item["channel"] == "whatsapp" and item["owner_user_id"] is None
        assert item["agent_key"] == "lead-imob"
        assert item["channel_ref"]["connection_id"] == str(CONNECTION_ID)
        assert chan.client.get("/api/conversations/channel", params={"agent_key": "lead-imob", "channel": "whatsapp"}).json()["total"] == 2
        assert chan.client.get("/api/conversations/channel", params={"agent_key": "lead-imob", "channel": "telegram"}).json()["total"] == 0

    def test_members_cannot_list_leads(self, chan):
        chan.seed_agent()
        seed_org_role(chan.client, role="member")
        resp = chan.client.get("/api/conversations/channel", params={"agent_key": "lead-imob"})
        assert resp.status_code == 403

    def test_channel_conversations_are_read_only_in_the_ui(self, chan):
        chan.seed_agent()
        cid = chan.turn().json()["conversation_id"]
        # an admin reads the conversation and its messages...
        assert chan.client.get(f"/api/conversations/{cid}").status_code == 200
        msgs = chan.client.get(f"/api/conversations/{cid}/messages").json()["items"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        # ...but cannot write to it (no owner ⇒ the owner-only write routes 404)
        assert chan.client.post(f"/api/conversations/{cid}/messages", json={"texto": "oi"}).status_code == 404
        assert chan.client.patch(f"/api/conversations/{cid}", json={"titulo": "x"}).status_code == 404

    def test_a_member_cannot_read_a_lead_conversation_by_id(self, chan):
        chan.seed_agent()
        cid = chan.turn().json()["conversation_id"]
        other_member = uuid4()
        seed_org_role(chan.client, user_id=other_member, role="member")
        bind_user(chan.client, user_id=other_member)
        assert chan.client.get(f"/api/conversations/{cid}").status_code == 404
