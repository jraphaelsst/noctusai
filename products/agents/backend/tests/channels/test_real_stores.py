"""The Real (PostgREST) halves of the channel stores, driven through a tiny
scripted client double — the query SHAPE each store sends and how it maps a
unique violation / an RPC answer. (Fakes are covered by the route suites; this
is the half a Fake-only suite never sees.)"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.channels.retention import SupabaseChannelRetention
from app.stores.channel_inbound import SupabaseChannelInboundStore
from app.stores.conversations import SupabaseConversationStore
from app.stores.errors import Conflict


class _Builder:
    """Records every chained call; ``execute()`` answers from the script."""

    def __init__(self, client: "ScriptedClient", table: str) -> None:
        self.client, self.table, self.calls = client, table, []

    def __getattr__(self, name):
        if name == "not_":
            self.calls.append(("not_",))
            return self

        def _chain(*a, **k):
            self.calls.append((name, a, k))
            return self

        return _chain

    def execute(self):
        self.client.log.append((self.table, self.calls))
        answer = self.client.script.pop(0) if self.client.script else SimpleNamespace(data=[])
        if isinstance(answer, Exception):
            raise answer
        return answer


class ScriptedClient:
    def __init__(self, *answers) -> None:
        self.script, self.log = list(answers), []

    def schema(self, name):
        assert name == "agents"
        return self

    def table(self, table):
        return _Builder(self, table)

    def rpc(self, fn, params):
        return _Builder(self, f"rpc:{fn}:{sorted(params)}")


def _unique_violation() -> APIError:
    return APIError({"code": "23505", "message": "duplicate key value", "details": "", "hint": ""})


def _conv_row(org, agent, **over):
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(uuid4()), "org_id": str(org), "agent_id": str(agent), "owner_user_id": None,
        "titulo": None, "sdk_session_id": None, "status": "ativa", "last_message_at": None,
        "created_at": now, "updated_at": now, "channel": "whatsapp",
        "channel_ref": {"connection_id": str(uuid4()), "chat_id": "c"}, "contact": {"display_name": "X"},
    }
    row.update(over)
    return row


def test_create_channel_reuses_the_row_a_concurrent_first_call_won():
    org, agent = uuid4(), uuid4()
    winner = _conv_row(org, agent)
    client = ScriptedClient(_unique_violation(), SimpleNamespace(data=[winner]))
    rec = SupabaseConversationStore(client).create_channel(
        org, agent, "whatsapp", winner["channel_ref"], {"display_name": "X"}
    )
    assert str(rec.id) == winner["id"] and rec.owner_user_id is None and rec.channel == "whatsapp"
    insert_table, insert_calls = client.log[0]
    assert insert_table == "conversations"
    payload = insert_calls[0][1][0]
    assert payload["owner_user_id"] is None and payload["channel"] == "whatsapp"
    assert [c[0] for c in client.log[1][1]][:1] == ["select"]  # then re-read the identity


def test_find_channel_filters_org_agent_channel_and_ref():
    org, agent = uuid4(), uuid4()
    row = _conv_row(org, agent)
    client = ScriptedClient(SimpleNamespace(data=[row]))
    rec = SupabaseConversationStore(client).find_channel(org, agent, "whatsapp", row["channel_ref"])
    assert rec is not None
    eqs = {c[1][0] for c in client.log[0][1] if c[0] == "eq"}
    assert eqs == {"org_id", "agent_id", "channel", "channel_ref"}


def test_list_channel_is_org_scoped_non_user_rows_only_and_paged():
    org, agent = uuid4(), uuid4()
    client = ScriptedClient(SimpleNamespace(data=[_conv_row(org, agent)]))
    items = SupabaseConversationStore(client).list_channel(org, agent_id=agent, channel="whatsapp")
    assert len(items) == 1
    names = [c[0] for c in client.log[0][1]]
    assert ("not_" in names) and "range" in names  # past PostgREST's silent 1000-row cap
    assert ("org_id", str(org)) in [(c[1][0], c[1][1]) for c in client.log[0][1] if c[0] == "eq"]


def test_inbound_add_maps_a_unique_violation_to_conflict():
    client = ScriptedClient(_unique_violation())
    with pytest.raises(Conflict):
        SupabaseChannelInboundStore(client).add(uuid4(), uuid4(), uuid4(), "wamid.1", "a" * 64)


def test_inbound_find_is_scoped_by_org_and_connection():
    org, conn, conv = uuid4(), uuid4(), uuid4()
    row = {
        "org_id": str(org), "connection_id": str(conn), "provider_message_id": "m1",
        "conversation_id": str(conv), "texto_sha256": "a" * 64, "reply": {"x": 1}, "replied_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client = ScriptedClient(SimpleNamespace(data=[row]))
    found = SupabaseChannelInboundStore(client).find(org, conn, ["m1", "m2"])
    assert set(found) == {"m1"} and found["m1"].reply == {"x": 1}
    eqs = {c[1][0] for c in client.log[0][1] if c[0] == "eq"}
    assert eqs == {"org_id", "connection_id"}


def test_retention_calls_the_two_sql_functions():
    org, conv = uuid4(), uuid4()
    client = ScriptedClient(SimpleNamespace(data=True), SimpleNamespace(data=7))
    retention = SupabaseChannelRetention(client)
    assert retention.delete_conversation(org, conv) is True
    assert retention.purge_older_than(datetime(2026, 1, 1, tzinfo=timezone.utc)) == 7
    assert client.log[0][0].startswith("rpc:delete_channel_conversation")
    assert client.log[1][0].startswith("rpc:purge_channel_conversations")
