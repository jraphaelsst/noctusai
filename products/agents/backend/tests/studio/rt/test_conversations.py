"""Conversations for studio agents (Agent Studio §D6, §E2, §E4, §A7) through
the REAL product app, with Julia's shape kept (default list = julia)."""
from __future__ import annotations

import hashlib
from uuid import UUID

from app.stores.studio_definitions import SectionInput
from app.runtime.fake_runtime import studio_echo_text
from tests.routers.conftest import (
    install_runtime,
    seed_active_agent_and_persona,
    wait_turn_released,
    wait_until,
)


def _studio_conv(rt, key="isa", **body):
    resp = rt.post("/api/conversations", json={"agent_key": key, **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreateAndList:
    def test_list_defaults_to_julia(self, rt):
        seed_active_agent_and_persona(rt.client)
        rt.make_agent()
        julia = rt.post("/api/conversations", json={"titulo": "J"}).json()
        studio = _studio_conv(rt)

        items = rt.get("/api/conversations").json()["items"]
        assert [c["id"] for c in items] == [julia["id"]]
        assert items[0]["agent_key"] == "julia" and items[0]["version_id"] is None

        items = rt.get("/api/conversations", params={"agent_key": "isa"}).json()["items"]
        assert [c["id"] for c in items] == [studio["id"]]

    def test_studio_create_pins_the_active_version_and_client(self, rt):
        agent, v1 = rt.make_agent()
        client = rt.studio.create_client(rt.org_id, agent.id, slug="loja", nome="Loja")
        conv = _studio_conv(rt, client_id=str(client.id))
        assert conv["agent_key"] == "isa"
        assert conv["version_id"] == str(v1.id)
        assert conv["client_id"] == str(client.id)
        assert rt.get(f"/api/conversations/{conv['id']}").json()["agent_key"] == "isa"

    def test_client_must_belong_to_the_agent_and_be_active(self, rt):
        agent, _ = rt.make_agent()
        other, _ = rt.make_agent("outro")
        foreign = rt.studio.create_client(rt.org_id, other.id, slug="x", nome="X")
        inactive = rt.studio.create_client(rt.org_id, agent.id, slug="y", nome="Y", ativo=False)
        for cid in (foreign.id, inactive.id, "00000000-0000-0000-0000-000000000001"):
            resp = rt.post("/api/conversations", json={"agent_key": "isa", "client_id": str(cid)})
            assert resp.status_code == 422
            assert resp.json()["code"] == "invalid_client"

    def test_julia_takes_no_client(self, rt):
        resp = rt.post("/api/conversations", json={"client_id": "00000000-0000-0000-0000-000000000001"})
        assert resp.status_code == 422
        assert resp.json()["code"] == "invalid_client"

    def test_unknown_and_legacy_agent_keys(self, rt):
        assert rt.post("/api/conversations", json={"agent_key": "ninguem"}).json()["code"] == "agent_not_found"
        rt.studio.add_legacy_agent(rt.org_id, "one-chat", "One Chat")
        resp = rt.post("/api/conversations", json={"agent_key": "one-chat"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "not_studio_agent"
        assert rt.get("/api/conversations", params={"agent_key": "ninguem"}).status_code == 404


class TestStudioTurn:
    def _post(self, rt, conv_id, texto="Crie um roteiro"):
        return rt.post(f"/api/conversations/{conv_id}/messages", json={"texto": texto})

    def test_turn_stamps_version_and_the_exact_compiled_hash(self, rt):
        runtime, _ = install_runtime(rt.client, [])
        agent, v1 = rt.make_agent()
        conv = _studio_conv(rt)
        resp = self._post(rt, conv["id"])
        assert resp.status_code == 202, resp.text
        assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))

        spec, ctx, prompt = runtime.calls[0]
        assert spec.toolset == "studio" and spec.prompt_mode == "custom" and not ctx.ephemeral
        expected = "sha256:" + hashlib.sha256(spec.prompt_append.encode("utf-8")).hexdigest()
        assert spec.compiled_hash == expected

        msgs = rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"]
        assistant = [m for m in msgs if m["role"] == "assistant"]
        assert len(assistant) == 1
        assert assistant[0]["version_id"] == str(v1.id)
        assert assistant[0]["compiled_hash"] == expected
        assert assistant[0]["texto"] == studio_echo_text(spec, "Crie um roteiro")
        user = [m for m in msgs if m["role"] == "user"][0]
        assert user["version_id"] is None and user["compiled_hash"] is None

        # Proof of use: the exact text is retrievable by the stamped hash.
        stored = rt.get(f"/api/studio/prompts/{expected}")
        assert stored.status_code == 200
        assert stored.json()["texto"] == spec.prompt_append

    def test_client_brain_is_compiled_into_the_turn(self, rt):
        runtime, _ = install_runtime(rt.client, [])
        agent, _ = rt.make_agent()
        client = rt.studio.create_client(rt.org_id, agent.id, slug="loja", nome="Loja Azul", resumo="Marca de moda.")
        conv = _studio_conv(rt, client_id=str(client.id))
        assert self._post(rt, conv["id"]).status_code == 202
        assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))
        assert "# Cliente em foco: Loja Azul" in runtime.calls[0][0].prompt_append

    def test_pinned_version_does_not_move_after_a_new_publish(self, rt):
        runtime, _ = install_runtime(rt.client, [])
        agent, v1 = rt.make_agent()
        conv = _studio_conv(rt)
        v2 = rt.studio.create_draft(rt.org_id, agent.id, v1.id, rt.user_id)
        rt.studio.replace_sections(rt.org_id, v2.id, [SectionInput(chave="nova", titulo="Nova", ordem=1, conteudo="v2")])
        rt.studio.publish_version(rt.org_id, v2.id, rt.user_id, None, "publicação de teste do BE-RT")
        assert self._post(rt, conv["id"]).status_code == 202
        assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))
        assert runtime.calls[0][0].version_id == v1.id
        # A NEW conversation picks the new version.
        assert _studio_conv(rt)["version_id"] == str(v2.id)

    def test_agent_inactive_409(self, rt):
        install_runtime(rt.client, [])
        rt.make_agent(ativo=False)
        conv = _studio_conv(rt)
        resp = self._post(rt, conv["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "agent_inactive"
        assert rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"] == []

    def test_no_active_version_409_then_pins_at_first_turn(self, rt):
        runtime, _ = install_runtime(rt.client, [])
        agent, draft = rt.make_agent(publish=False)
        conv = _studio_conv(rt)
        assert conv["version_id"] is None
        resp = self._post(rt, conv["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "no_active_version"

        v1 = rt.studio.publish_version(rt.org_id, draft.id, rt.user_id, None, "publicação de teste do BE-RT")
        assert self._post(rt, conv["id"]).status_code == 202
        assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))
        assert rt.get(f"/api/conversations/{conv['id']}").json()["version_id"] == str(v1.id)

    def test_prompt_too_large_is_refused_never_truncated(self, rt):
        runtime, _ = install_runtime(rt.client, [])
        rt.make_agent(secoes=[("gigante", "Gigante", "x" * 60_001)])
        conv = _studio_conv(rt)
        resp = self._post(rt, conv["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "prompt_too_large"
        assert runtime.calls == []
        assert rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"] == []

    def test_client_deactivated_after_creation_refuses_the_turn(self, rt):
        install_runtime(rt.client, [])
        agent, _ = rt.make_agent()
        client = rt.studio.create_client(rt.org_id, agent.id, slug="loja", nome="Loja")
        conv = _studio_conv(rt, client_id=str(client.id))
        rt.studio.update_client(rt.org_id, client.id, {"ativo": False})
        resp = self._post(rt, conv["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "client_inactive"

    def test_capacity_message_does_not_name_julia(self, rt):
        runtime, _ = install_runtime(rt.client, [], capacity=1)
        rt.make_agent()
        conv = _studio_conv(rt)
        held = runtime.try_reserve()
        assert held is not None
        resp = self._post(rt, conv["id"])
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "julia_capacidade"
        assert "Julia" not in body["detail"] and "Isa" in body["detail"]

    def test_julia_turn_is_not_stamped(self, rt):
        seed_active_agent_and_persona(rt.client)
        install_runtime(rt.client, [
            {"event": "message.new", "payload": {"role": "assistant", "texto": "Oi", "blocks": []}},
        ])
        conv = rt.post("/api/conversations", json={}).json()
        assert self._post(rt, conv["id"]).status_code == 202
        assert wait_until(lambda: any(
            m.role == "assistant" for m in rt.stores.messages.list(rt.org_id, UUID(conv["id"]))
        ))
        assert wait_turn_released(rt.stores.conversations, rt.org_id, UUID(conv["id"]))
        assistant = [m for m in rt.get(f"/api/conversations/{conv['id']}/messages").json()["items"] if m["role"] == "assistant"]
        assert assistant[0]["version_id"] is None and assistant[0]["compiled_hash"] is None
