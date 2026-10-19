"""``POST /api/channels/turns`` — the auth matrix and the request contract
(Lais §3.1, §10.1 M1/M4/L1). Strict statuses: a bad credential is exactly 401,
never ``in (401, ...)``."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.dependencies import SCOPE_CHANNEL_STATUS, SCOPE_CHANNEL_TURN
from tests.channels.conftest import OTHER_ORG, turn_body


def _code(resp) -> str:
    return resp.json()["code"]


class TestAuthMatrix:
    def test_no_credential_is_401(self, chan):
        chan.seed_agent()
        resp = chan.request("POST", "/api/channels/turns", json=turn_body())
        assert resp.status_code == 401

    def test_unknown_product_token_is_401(self, chan):
        chan.seed_agent()
        resp = chan.request(
            "POST", "/api/channels/turns", json=turn_body(),
            headers={"Authorization": "Bearer pk_" + "0" * 64},
        )
        assert resp.status_code == 401

    def test_status_route_without_credential_is_401(self, chan):
        chan.seed_agent()
        assert chan.request("GET", "/api/channels/agents/julia/status").status_code == 401

    def test_delete_route_without_credential_is_401(self, chan):
        chan.seed_agent()
        body = {k: turn_body()[k] for k in ("agent_key", "channel", "channel_ref")}
        assert chan.request("DELETE", "/api/channels/conversations", json=body).status_code == 401

    def test_a_human_session_is_403_product_required(self, chan):
        chan.seed_agent()
        resp = chan.client.post("/api/channels/turns", json=turn_body())  # the default user bearer
        assert resp.status_code == 403
        assert _code(resp) == "product_required"

    def test_token_without_the_turn_scope_is_403_scope_missing(self, chan):
        chan.seed_agent()
        resp = chan.turn(scopes=(SCOPE_CHANNEL_STATUS,))
        assert resp.status_code == 403
        assert _code(resp) == "scope_missing"

    def test_scopes_are_split_the_turn_scope_does_not_open_status(self, chan):
        chan.seed_agent()
        with chan.as_token(SCOPE_CHANNEL_TURN):
            resp = chan.request("GET", "/api/channels/agents/julia/status")
        assert resp.status_code == 403
        assert _code(resp) == "scope_missing"

    def test_scopes_are_split_the_status_scope_does_not_open_delete(self, chan):
        chan.seed_agent()
        body = {k: turn_body()[k] for k in ("agent_key", "channel", "channel_ref")}
        with chan.as_token(SCOPE_CHANNEL_STATUS):
            resp = chan.request("DELETE", "/api/channels/conversations", json=body)
        assert resp.status_code == 403
        assert _code(resp) == "scope_missing"

    @pytest.mark.parametrize("issuer", [None, "agents", "academia-de-reciclagem", "social-wiring-evil"])
    def test_wrong_issuer_is_403_issuer_not_allowed_on_every_route(self, chan, issuer):
        chan.seed_agent()
        resp = chan.turn(issuer=issuer)
        assert resp.status_code == 403
        assert _code(resp) == "issuer_not_allowed"
        with chan.as_token(issuer=issuer):
            status_resp = chan.request("GET", "/api/channels/agents/julia/status")
        assert status_resp.status_code == 403
        assert _code(status_resp) == "issuer_not_allowed"

    def test_a_token_bound_to_another_agent_is_403_agent_not_allowed(self, chan):
        chan.seed_agent()
        resp = chan.turn(principal=uuid4())
        assert resp.status_code == 403
        assert _code(resp) == "agent_not_allowed"

    def test_a_token_with_no_principal_is_refused_too(self, chan):
        chan.seed_agent()
        resp = chan.turn(principal=None)
        assert resp.status_code == 403
        assert _code(resp) == "agent_not_allowed"

    def test_unknown_agent_key_is_404(self, chan):
        chan.seed_agent()
        resp = chan.turn(turn_body(agent_key="nope"))
        assert resp.status_code == 404
        assert _code(resp) == "agent_not_found"

    def test_a_claude_sdk_studio_agent_is_not_reachable_from_a_channel(self, chan):
        chan.seed_agent()
        agent, _ = chan.rt.make_agent("isa", publish=True)
        resp = chan.turn(turn_body(agent_key="isa"), principal=agent.id)
        assert resp.status_code == 404
        assert _code(resp) == "agent_not_found"

    def test_org_comes_from_the_token_agent_is_resolved_inside_it(self, chan):
        """Org B's token naming `julia` finds nothing in org B — it never sees org A's."""
        chan.seed_agent()
        resp = chan.turn(principal=chan.agent.id, org_id=OTHER_ORG)
        assert resp.status_code == 404
        assert _code(resp) == "agent_not_found"
        assert chan.provider.calls == []


class TestRequestContract:
    @pytest.mark.parametrize(
        "mutate",
        [
            lambda b: b.update(messages=[]),
            lambda b: b.update(messages=b["messages"] * 21),
            lambda b: b["messages"][0].update(texto=""),
            lambda b: b["messages"][0].update(texto="   "),
            lambda b: b["messages"][0].update(texto="x" * 8001),
            lambda b: b["messages"][0].pop("provider_message_id"),
            lambda b: b.update(channel="sms"),
            lambda b: b.update(surprise=1),
            lambda b: b["channel_ref"].update(chat_id=""),
            lambda b: b["channel_ref"].update(connection_id="not-a-uuid"),
            lambda b: b.pop("agent_key"),
        ],
    )
    def test_schema_violations_are_422_invalid_field_and_run_nothing(self, chan, mutate):
        chan.seed_agent()
        body = turn_body("um", "dois", ids=["a", "b"])
        mutate(body)
        resp = chan.turn(body)
        assert resp.status_code == 422
        assert _code(resp) == "invalid_field"
        assert chan.provider.calls == []
        assert chan.rt.stores.conversations.list_channel(chan.org_id) == []

    def test_batch_total_over_16k_characters_is_422(self, chan):
        chan.seed_agent()
        resp = chan.turn(turn_body("a" * 6000, "b" * 6000, "c" * 6000))  # each fine, 18 000 together
        assert resp.status_code == 422
        assert _code(resp) == "invalid_field"
        assert chan.provider.calls == []

    def test_batch_at_the_caps_is_accepted(self, chan):
        chan.seed_agent()
        texts = ["x" * 800] * 20  # 20 messages, 16 000 characters
        resp = chan.turn(turn_body(*texts, ids=[f"id-{i}" for i in range(20)]))
        assert resp.status_code == 200, resp.text

    def test_duplicate_ids_inside_a_batch_are_422(self, chan):
        chan.seed_agent()
        resp = chan.turn(turn_body("um", "dois", ids=["same", "same"]))
        assert resp.status_code == 422
        assert _code(resp) == "invalid_field"

    def test_validation_never_beats_auth(self, chan):
        chan.seed_agent()
        resp = chan.request("POST", "/api/channels/turns", json={"garbage": True})
        assert resp.status_code == 401
