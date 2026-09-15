"""Contract §E.3 canonical fixture — the real published SSE sequence for
one Julia escrita turn, asserted against
``products/agents/contract-fixtures/escrita-turn.events.json`` using its
own ``comparison_rule``.

Drives the REAL route (``POST /api/conversations/{id}/messages`` +
``POST /api/approvals/{id}/decision``), G2's REAL broker
(``StoreApprovalBroker``) and bus (``FakeRealtimeBus``), with G2's
``FakeAgentRuntime`` standing in for the LLM. The fixture is loaded from
the repo path — never copied — and its ``comparison_rule`` string names
exactly what this file compares.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.realtime import conversation_scope
from tests.routers.conftest import (
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    install_runtime,
    seed_active_agent_and_persona,
    seed_org_role,
    wait_for_pending_approval,
    wait_turn_released,
)

# `contract-fixtures/` lives at the `agents` product root:
# products/agents/{backend/tests/routers/THIS_FILE, contract-fixtures/...}
FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "contract-fixtures" / "escrita-turn.events.json"
)


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _published_events(bus, conversation_id) -> list[dict[str, Any]]:
    """The real sequence a subscriber would have seen, in publish order —
    read from ``FakeRealtimeBus``'s own stream (no public "dump" method
    exists; this mirrors the same internal-introspection idiom the store
    tests already use, e.g. ``FakeApprovalStore._rows``)."""
    scope = conversation_scope(conversation_id)
    stream = bus._streams.get(scope, [])
    return [{"event": e.event, "payload": e.payload} for e in stream]


def _is_uuid(value: Any) -> bool:
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _is_iso8601(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def assert_matches_canonical_fixture(actual: list[dict[str, Any]], fixture_events: list[dict[str, Any]]) -> None:
    """Implements the fixture's own ``comparison_rule`` (verbatim, see
    ``escrita-turn.events.json``): event names in order; payload key
    sets; message role/blocks (kind, status, decision); and id cross-
    references. UUIDs/timestamps/texto/resumo/diff/tool_input/
    sdk_session_id are compared by shape only.
    """
    # 1. Event names, in order.
    actual_names = [e["event"] for e in actual]
    fixture_names = [e["event"] for e in fixture_events]
    assert actual_names == fixture_names, f"event order mismatch: {actual_names} != {fixture_names}"

    # 2. Payload key sets, per event.
    for i, (act, exp) in enumerate(zip(actual, fixture_events)):
        assert set(act["payload"].keys()) == set(exp["payload"].keys()), (
            f"event #{i} ({act['event']}) key-set mismatch: "
            f"{sorted(act['payload'].keys())} != {sorted(exp['payload'].keys())}"
        )

    # 3. Message role/blocks (kind, status, decision) for message.new /
    #    message.updated — shape-checked structurally, not by literal id.
    for i, (act, exp) in enumerate(zip(actual, fixture_events)):
        if act["event"] not in ("message.new", "message.updated"):
            continue
        assert act["payload"]["role"] == exp["payload"]["role"], f"event #{i} role mismatch"
        act_blocks = act["payload"].get("blocks") or []
        exp_blocks = exp["payload"].get("blocks") or []
        assert len(act_blocks) == len(exp_blocks), f"event #{i} block count mismatch"
        for b_i, (ab, eb) in enumerate(zip(act_blocks, exp_blocks)):
            assert ab.get("kind") == eb.get("kind"), f"event #{i} block #{b_i} kind mismatch"
            if ab.get("kind") == "tool":
                assert ab.get("status") == eb.get("status"), f"event #{i} block #{b_i} status mismatch"
            elif ab.get("kind") == "approval":
                assert ab.get("decision") == eb.get("decision"), f"event #{i} block #{b_i} decision mismatch"

    # 4. Id cross-references.
    message_ids: set[str] = set()
    for act in actual:
        if act["event"] == "message.new":
            message_ids.add(str(act["payload"]["id"]))

    tool_use_ids_started: dict[str, int] = {}
    tool_use_ids_finished: dict[str, int] = {}
    approval_ids_requested: list[str] = []
    approval_ids_resolved: list[str] = []

    for act in actual:
        payload = act["payload"]
        if "message_id" in payload:
            assert str(payload["message_id"]) in message_ids, (
                f"{act['event']} message_id {payload['message_id']!r} never "
                f"published by an earlier message.new"
            )
        if act["event"] == "tool.started":
            tool_use_ids_started[payload["tool_use_id"]] = tool_use_ids_started.get(
                payload["tool_use_id"], 0
            ) + 1
        elif act["event"] == "tool.finished":
            tool_use_ids_finished[payload["tool_use_id"]] = tool_use_ids_finished.get(
                payload["tool_use_id"], 0
            ) + 1
        elif act["event"] == "approval.requested":
            approval_ids_requested.append(str(payload["id"]))
            assert _is_uuid(payload["id"]), "approval.requested.id must be a real uuid"
        elif act["event"] == "approval.resolved":
            approval_ids_resolved.append(str(payload["approval_id"]))

    assert tool_use_ids_started == tool_use_ids_finished, (
        "every tool.started must pair with exactly one tool.finished sharing "
        f"the same tool_use_id: {tool_use_ids_started} != {tool_use_ids_finished}"
    )
    assert approval_ids_requested == approval_ids_resolved, (
        "approval.resolved.approval_id must equal the id the matching "
        f"approval.requested carried: {approval_ids_requested} != {approval_ids_resolved}"
    )

    # Every approval block's `approvalId` across message.updated events
    # must be one of the ids actually requested.
    for act in actual:
        if act["event"] not in ("message.new", "message.updated"):
            continue
        for block in act["payload"].get("blocks") or []:
            if block.get("kind") == "approval" and block.get("approvalId") is not None:
                assert str(block["approvalId"]) in approval_ids_requested


class TestApprovedEscritaTurnMatchesCanonicalFixture:
    def test_approved_turn_matches_the_fixture_exactly(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        script = [
            {"event": "message.delta", "payload": {"message_temp_id": "tmp-1", "texto_parcial": "Vou atualizar"}},
            {
                "event": "message.new",
                "payload": {"role": "assistant", "texto": "Vou atualizar a entrada exemplo.", "blocks": []},
            },
            (
                "escrita",
                "mcp__academia__kb_escrever",
                {"slug": "exemplo", "corpo_md": "Texto novo."},
                {"antes": "Texto antigo.", "depois": "Texto novo."},
            ),
            {
                "event": "message.new",
                "payload": {
                    "role": "assistant",
                    "texto": "Pronto, a entrada exemplo foi atualizada.",
                    "blocks": [],
                },
            },
        ]
        install_runtime(agents_client, script)

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "Atualize a entrada exemplo."}
        )
        assert resp.status_code == 202, resp.text

        approval = wait_for_pending_approval(agents_client.stores.approvals, DEFAULT_ORG_ID)
        decide_resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": True}
        )
        assert decide_resp.status_code == 200, decide_resp.text

        assert wait_turn_released(agents_client.stores.conversations, DEFAULT_ORG_ID, conv.id)

        published = _published_events(agents_client.stores.bus, conv.id)
        fixture = _load_fixture()
        assert_matches_canonical_fixture(published, fixture["events"])


def _assert_message_updated_follows_every_block_change(published: list[dict[str, Any]]) -> None:
    """Contract §E.9 point 3: "the ordering is exactly as in the canonical
    fixture: the granular event first, then message.updated." Checked
    generically here (not against the fixture, since a denied/timeout turn
    has no fixture of its own) — every ``tool.*``/``approval.*`` event
    must be immediately followed by a ``message.updated``."""
    names = [e["event"] for e in published]
    for i, name in enumerate(names):
        if name in ("tool.started", "tool.finished", "approval.requested", "approval.resolved"):
            assert names[i + 1] == "message.updated", (
                f"{name} at position {i} not immediately followed by message.updated: {names}"
            )


class TestDeniedEscritaTurn:
    def test_denied_turn_is_negada_throughout_with_message_updated_after_each_block(
        self, agents_client
    ):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        script = [("escrita", "mcp__academia__kb_escrever", {"slug": "exemplo", "corpo_md": "x"})]
        install_runtime(agents_client, script)

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "Atualize a entrada exemplo."}
        )
        assert resp.status_code == 202, resp.text

        approval = wait_for_pending_approval(agents_client.stores.approvals, DEFAULT_ORG_ID)
        decide_resp = agents_client.post(
            f"/api/approvals/{approval.id}/decision", json={"aprovada": False}
        )
        assert decide_resp.status_code == 200, decide_resp.text
        assert decide_resp.json()["decision"] == "negada"

        assert wait_turn_released(agents_client.stores.conversations, DEFAULT_ORG_ID, conv.id)

        published = _published_events(agents_client.stores.bus, conv.id)
        names = [e["event"] for e in published]
        assert names == [
            "message.new",  # user
            "session.status",  # pensando
            "message.new",  # placeholder assistant — no text preceded the tool call
            "tool.started",
            "message.updated",
            "approval.requested",
            "message.updated",
            "approval.resolved",
            "message.updated",
            "tool.finished",
            "message.updated",
            "session.status",  # ociosa
            "conversation.upsert",
        ]
        _assert_message_updated_follows_every_block_change(published)

        finished = next(e for e in published if e["event"] == "tool.finished")
        assert finished["payload"]["resultado"] == "negada"
        resolved = next(e for e in published if e["event"] == "approval.resolved")
        assert resolved["payload"]["decision"] == "negada"

        final_blocks = published[-3]["payload"]["blocks"]  # last message.updated
        tool_block = next(b for b in final_blocks if b["kind"] == "tool")
        approval_block = next(b for b in final_blocks if b["kind"] == "approval")
        assert tool_block["status"] == "negada"
        assert approval_block["decision"] == "negada"


class TestTimeoutEscritaTurn:
    def test_unanswered_approval_times_out_negada(self, agents_client):
        seed_org_role(agents_client, role="member")
        agent = seed_active_agent_and_persona(agents_client)
        conv = agents_client.stores.conversations.create(DEFAULT_ORG_ID, agent.id, DEFAULT_USER_ID)

        script = [("escrita", "mcp__academia__kb_escrever", {"slug": "exemplo", "corpo_md": "x"})]
        # A short broker timeout — nobody ever decides.
        install_runtime(agents_client, script, timeout_seconds=0.05)

        resp = agents_client.post(
            f"/api/conversations/{conv.id}/messages", json={"texto": "Atualize a entrada exemplo."}
        )
        assert resp.status_code == 202, resp.text

        assert wait_turn_released(agents_client.stores.conversations, DEFAULT_ORG_ID, conv.id)

        published = _published_events(agents_client.stores.bus, conv.id)
        names = [e["event"] for e in published]
        assert names == [
            "message.new",
            "session.status",
            "message.new",  # placeholder assistant — no text preceded the tool call
            "tool.started",
            "message.updated",
            "approval.requested",
            "message.updated",
            "approval.resolved",
            "message.updated",
            "tool.finished",
            "message.updated",
            "session.status",
            "conversation.upsert",
        ]
        _assert_message_updated_follows_every_block_change(published)

        resolved = next(e for e in published if e["event"] == "approval.resolved")
        assert resolved["payload"]["decision"] == "negada"
        assert resolved["payload"]["decided_by"] is None
        finished = next(e for e in published if e["event"] == "tool.finished")
        assert finished["payload"]["resultado"] == "negada"

        approval_row = agents_client.stores.approvals.get(DEFAULT_ORG_ID, UUID(
            next(e["payload"]["id"] for e in published if e["event"] == "approval.requested")
        ))
        assert approval_row.decision == "expirada"
