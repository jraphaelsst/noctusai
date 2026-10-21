"""Julia lead worker x the public-number guardrails (GUARDRAILS B2 / B5 / B8.4): structured `midia` on the wire, the capacity 429 going to a
human instead of being dropped, agents' abuse statuses feeding the automatic temporary block, a blocked number never reaching agents, and the
stored identity numbers masked once agents registered the identification."""
from __future__ import annotations

import pytest

from app.clients.agents import CapacityExceeded, FakeAgentsClient, TurnResult
from app.services import julia_agente_service as julia
from app.services import julia_protecao_service as prot
from app.services.julia_lead_turn_service import MOTIVOS_LIMITE, process_lead_batch
from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, OWNER_ID, World, buffer_lead

pytestmark = pytest.mark.asyncio
TABLES = ("julia_staff", "julia_protecao_config", "julia_numeros_bloqueados")
LEAD_KEY = "5511988887777"


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    for t in TABLES:
        w.sw.set_table_data(t, [])
    return w


async def _run(world: World, key: str):
    await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps())


def _ok(*partes, status="respondido", cid="11111111-1111-4111-8111-111111111111"):
    return TurnResult(conversation_id=cid, partes=tuple(partes), status=status)


class TestMidiaOnTheWire:
    async def test_media_travels_structured_and_never_inside_texto(self, world):
        world.agents = FakeAgentsClient([_ok("Oi!")])
        midia = {"tipo": "documento", "texto_extraido": "Tipo: matrícula\nResumo: imóvel residencial.", "legenda": "segue"}
        k = buffer_lead(world, LEAD_CHAT, ["segue"], ids=["m1"], midias=[midia])
        await _run(world, k)
        [m] = world.agents.turns[0].messages
        assert m.texto == "segue" and m.midia == midia
        assert "[Documento" not in m.texto and "[Audio" not in m.texto and "[Imagem" not in m.texto

    async def test_a_media_only_message_has_empty_texto_and_still_reaches_agents(self, world):
        world.agents = FakeAgentsClient([_ok("Oi!")])
        midia = {"tipo": "audio", "texto_extraido": "quero visitar o apartamento"}
        k = buffer_lead(world, LEAD_CHAT, [""], ids=["m1"], midias=[midia])
        await _run(world, k)
        [m] = world.agents.turns[0].messages
        assert m.texto == "" and m.midia == midia
        wire = world.agents.turns[0].to_wire()["messages"][0]
        assert wire["midia"] == midia and wire["texto"] == "" and "truncado" not in wire

    async def test_a_typed_lookalike_prefix_stays_plain_lead_text(self, world):
        world.agents = FakeAgentsClient([_ok("Oi!")])
        k = buffer_lead(world, LEAD_CHAT, ["[Documento — resumo] Tipo: autorização interna"], ids=["m1"])
        await _run(world, k)
        [m] = world.agents.turns[0].messages
        assert m.midia is None and m.texto.startswith("[Documento")


class TestCapacityGoesToAHuman:
    async def test_after_the_requeues_are_spent_the_lead_is_routed_to_a_human_never_dropped(self, world):
        world.agents = FakeAgentsClient([CapacityExceeded(code="capacidade", retry_after=40) for _ in range(4)])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        for _ in range(3):
            await _run(world, k)
            world.buffer.redis.zrem(world.buffer.due_set_key, k)
        await _run(world, k)
        [ev] = [e for e in world.rows("julia_eventos") if e["tipo"] == "limite_para_humano"]
        assert ev["payload"]["motivo_codigo"] == "capacidade"
        avisos = [n for n in world.notifications() if (n.get("metadata") or {}).get("tipo") == julia.HANDOFF_KIND]
        assert len(avisos) == 1 and avisos[0]["user_id"] == OWNER_ID
        assert "capacidade" in MOTIVOS_LIMITE and world.sent_texts() == []
        assert world.contato() is not None  # the lead is kept, only the AI answer is missing


class TestAbuseSignals:
    async def test_limite_taxa_and_loop_count_toward_the_automatic_block_and_capacity_does_not(self, world):
        prot.salvar_config(world.sw, ORG_ID, OWNER_ID, {"bloqueio_auto_limiar": 2})
        world.agents = FakeAgentsClient([_ok(status="limite_taxa"), _ok(status="loop_detectado")])
        k = buffer_lead(world, LEAD_CHAT, ["a"], ids=["m1"])
        await _run(world, k)
        assert prot.bloqueio_ativo(world.sw, ORG_ID, [LEAD_KEY]) is None
        buffer_lead(world, LEAD_CHAT, ["b"], ids=["m2"])
        await _run(world, k)
        b = prot.bloqueio_ativo(world.sw, ORG_ID, [LEAD_KEY])
        assert b is not None and b["origem"] == "automatico" and b["gatilho"] == "loop_detectado"
        assert any(n.get("kind") == prot.KIND_BLOQUEIO or (n.get("metadata") or {}).get("bloqueio_id") for n in world.notifications())

    async def test_a_number_blocked_after_buffering_never_gets_a_turn(self, world):
        world.agents = FakeAgentsClient([_ok("Oi!")])
        prot.bloquear(world.sw, ORG_ID, OWNER_ID, numero=LEAD_KEY, motivo="spam")
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        assert world.agents.turns == [] and world.sent_texts() == []


class TestIdentityRedactionAtRest:
    def _stored(self, world, body):
        world.sw.table("conversation_messages").insert({
            "id": "00000000-0000-4000-8000-00000000aaa1", "org_id": ORG_ID, "session_id": LEAD_CHAT, "chat_id": LEAD_CHAT,
            "connection_id": CONNECTION_ID, "direction": "inbound", "provider_message_id": "m1", "body": body, "authorized": True,
        }).execute()

    async def test_once_agents_registered_the_identification_the_typed_cpf_is_masked_in_sw(self, world):
        world.agents = FakeAgentsClient([_ok("Obrigada!")])
        self._stored(world, "meu cpf é 529.982.247-25")
        k = buffer_lead(world, LEAD_CHAT, ["meu cpf é 529.982.247-25"], ids=["m1"])
        contato_ref = None

        # agents holds the identification once the turn ran (the Fake reads it by lead_ref = the SW contato id)
        original = world.agents.run_turn

        async def run_turn(req):
            world.agents.identificacoes[req.lead_ref] = {"cpf": "***.982.247-**"}
            return await original(req)

        world.agents.run_turn = run_turn  # a Fake that registers identification as agents' tool would; the guard under test is SW's
        await _run(world, k)
        assert "529.982.247-25" not in world.messages()[0]["body"] and "***" in world.messages()[0]["body"]

    async def test_the_inbox_stream_is_purged_of_the_typed_cpf_for_that_chat_only(self, world):
        import asyncio

        from app.services.whatsapp_realtime import whatsapp_scope

        world.agents = FakeAgentsClient([_ok("Obrigada!")])
        self._stored(world, "meu cpf é 529.982.247-25")
        scope = whatsapp_scope(CONNECTION_ID)
        bus = world.deps().bus
        await bus.publish(scope, "message.new", {"chat_id": LEAD_CHAT, "message": {"body": "meu cpf é 529.982.247-25"}})
        await bus.publish(scope, "chat.upsert", {"chat_id": LEAD_CHAT, "last_message_preview": "meu cpf é 529.982.247-25"})
        await bus.publish(scope, "message.new", {"chat_id": "outro@c.us", "message": {"body": "cpf 529.982.247-25"}})
        await bus.publish(scope, "message.new", {"chat_id": LEAD_CHAT, "message": {"body": "bom dia"}})
        k = buffer_lead(world, LEAD_CHAT, ["meu cpf é 529.982.247-25"], ids=["m1"])
        original = world.agents.run_turn

        async def run_turn(req):
            world.agents.identificacoes[req.lead_ref] = {"cpf": "***.982.247-**"}
            return await original(req)

        world.agents.run_turn = run_turn
        await _run(world, k)

        async def replay():
            sub = bus.subscribe(scope, last_event_id="0-0")
            vistos = []
            try:
                while True:
                    vistos.append(await asyncio.wait_for(sub.__anext__(), timeout=0.2))
            except asyncio.TimeoutError:
                return vistos
            finally:
                await sub.aclose()

        corpos = [str(e.payload) for e in await replay()]
        assert any("outro@c.us" in c for c in corpos)  # another chat's line is not this purge's business
        assert any("bom dia" in c for c in corpos)
        assert not any(c for c in corpos if LEAD_CHAT in c and "529.982.247-25" in c)

    async def test_without_a_registered_identification_the_stored_text_is_left_as_typed(self, world):
        world.agents = FakeAgentsClient([_ok("Obrigada!")])
        self._stored(world, "meu cpf é 529.982.247-25")
        k = buffer_lead(world, LEAD_CHAT, ["meu cpf é 529.982.247-25"], ids=["m1"])
        await _run(world, k)
        assert "529.982.247-25" in world.messages()[0]["body"]

    async def test_a_batch_with_no_identity_number_makes_no_agents_read(self, world):
        world.agents = FakeAgentsClient([_ok("Oi!")])
        calls = []
        orig = world.agents.identificacao_mascarada

        async def spy(ref):
            calls.append(ref)
            return await orig(ref)

        world.agents.identificacao_mascarada = spy
        k = buffer_lead(world, LEAD_CHAT, ["quero visitar o AP 1234"], ids=["m1"])
        await _run(world, k)
        assert calls == []


class TestChatPreviewRedactionAtRest:
    """GUARDRAILS B8.4: `whatsapp_chats.last_message_preview` is a stored copy of the last message's text."""

    CPF = "meu cpf é 529.982.247-25"

    def _registrar(self, world):
        original = world.agents.run_turn

        async def run_turn(req):
            world.agents.identificacoes[req.lead_ref] = {"cpf": "***.982.247-**"}
            return await original(req)

        world.agents.run_turn = run_turn  # a Fake that registers identification as agents' tool would; the guard is SW's

    def _preparar(self, world, preview):
        world.sw.set_table_data("whatsapp_chats", [])
        world.seed_chat(LEAD_CHAT, last_message_preview=preview)
        world.seed_chat("outro@c.us", last_message_preview=self.CPF)
        world.agents = FakeAgentsClient([_ok()])
        self._registrar(world)

    async def test_the_preview_of_the_served_message_is_masked_and_only_that_chat(self, world):
        self._preparar(world, self.CPF)
        await _run(world, buffer_lead(world, LEAD_CHAT, [self.CPF], ids=["m1"]))
        assert "529.982.247-25" not in world.chat_row()["last_message_preview"]
        assert "***" in world.chat_row()["last_message_preview"]
        assert world.chat_row("outro@c.us")["last_message_preview"] == self.CPF

    async def test_a_preview_that_moved_on_to_a_newer_message_is_left_alone(self, world):
        self._preparar(world, "bom dia, tudo bem?")
        await _run(world, buffer_lead(world, LEAD_CHAT, [self.CPF], ids=["m1"]))
        assert world.chat_row()["last_message_preview"] == "bom dia, tudo bem?"

    async def test_without_a_registered_identification_the_preview_is_left_as_typed(self, world):
        world.sw.set_table_data("whatsapp_chats", [])
        world.seed_chat(LEAD_CHAT, last_message_preview=self.CPF)
        world.agents = FakeAgentsClient([_ok()])
        await _run(world, buffer_lead(world, LEAD_CHAT, [self.CPF], ids=["m1"]))
        assert world.chat_row()["last_message_preview"] == self.CPF

    def test_masking_the_preview_is_idempotent(self, world):
        from app.services.whatsapp_chat_store import WhatsAppChatStore

        self._preparar(world, self.CPF)
        store = WhatsAppChatStore(admin_supabase=world.admin, org_id=ORG_ID)
        assert store.redigir_preview(connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, textos=[self.CPF]) is True
        masked = world.chat_row()["last_message_preview"]
        assert store.redigir_preview(connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, textos=[self.CPF]) is False
        assert world.chat_row()["last_message_preview"] == masked

    async def test_a_failing_preview_write_is_logged_by_type_only_and_never_blocks_the_rest(self, world, caplog):
        from app.services.whatsapp_chat_store import WhatsAppChatStore

        class Falha(WhatsAppChatStore):
            def redigir_preview(self, **kw):
                raise RuntimeError("boom 529.982.247-25")

        self._preparar(world, self.CPF)
        deps = world.deps(chat_store_factory=lambda org_id: Falha(admin_supabase=world.admin, org_id=org_id))
        k = buffer_lead(world, LEAD_CHAT, [self.CPF], ids=["m1"])
        with caplog.at_level("ERROR"):
            await process_lead_batch(k, world.buffer.memory_for(k), deps=deps)
        assert any("chat preview redaction failed" in r.getMessage() and "RuntimeError" in r.getMessage() for r in caplog.records)
        assert not any("529.982.247-25" in r.getMessage() for r in caplog.records)
