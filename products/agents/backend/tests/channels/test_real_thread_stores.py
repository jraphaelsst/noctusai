"""The Real (PostgREST) halves of the thread / controls stores and the v2 additions to the conversation, message and
retention stores, driven through the scripted client double of ``test_real_stores`` -- the query SHAPE each store sends
and how it maps a unique violation / an RPC answer. (The Fakes are covered by the service suites; this is the half a
Fake-only suite never sees.)"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.channels.retention import SupabaseChannelRetention
from app.stores.agent_controles import SupabaseAgentControleStore
from app.stores.conversations import SupabaseConversationStore
from app.stores.errors import NotFound
from app.stores.messages import SupabaseMessageStore
from app.stores.threads import OutroAgenteAtivo, SupabaseThreadStore
from tests.channels.test_real_stores import ScriptedClient, _conv_row, _unique_violation

NOW = datetime.now(timezone.utc).isoformat()


def _part_row(org, thread, agent, estado="ativo"):
    return {
        "thread_id": str(thread), "agent_id": str(agent), "org_id": str(org), "estado": estado,
        "entrou_em": NOW, "saiu_em": None, "motivo": None, "ultimo_turno_em": None,
    }


def _lead_row(org, ref="contato-1"):
    return {
        "id": str(uuid4()), "org_id": str(org), "produto": "social-wiring", "ref_externa": ref,
        "crm_lead_id": None, "contato": None, "created_at": NOW, "updated_at": NOW,
    }


def _eqs(call_list):
    return {c[1][0]: c[1][1] for c in call_list if c[0] == "eq"}


# ── participants ───────────────────────────────────────────────────────────


def test_transicionar_is_one_rpc_with_the_compare_and_set_and_the_actor():
    org, thread, agent, actor = uuid4(), uuid4(), uuid4(), uuid4()
    client = ScriptedClient(SimpleNamespace(data=True), SimpleNamespace(data=False))
    store = SupabaseThreadStore(client)
    assert store.transicionar(org, thread, agent, de=["ativo"], para="pausado", ator_tipo="usuario", ator_id=actor, motivo="m") is True
    assert store.transicionar(org, thread, agent, de=["ativo"], para="pausado", ator_tipo="usuario") is False
    assert client.log[0][0].startswith("rpc:set_participante_estado")
    assert "p_de" in client.log[0][0] and "p_ator_id" in client.log[0][0]


def test_transicionar_to_active_while_another_agent_is_active_is_the_one_active_conflict():
    client = ScriptedClient(_unique_violation())
    with pytest.raises(OutroAgenteAtivo):
        SupabaseThreadStore(client).transicionar(
            uuid4(), uuid4(), uuid4(), de=["encerrado"], para="ativo", ator_tipo="sistema"
        )


def test_transicionar_for_a_missing_participant_is_not_found():
    from postgrest.exceptions import APIError

    client = ScriptedClient(APIError({"code": "P0001", "message": "participante_not_found", "details": "", "hint": ""}))
    with pytest.raises(NotFound):
        SupabaseThreadStore(client).transicionar(uuid4(), uuid4(), uuid4(), de=["ativo"], para="pausado", ator_tipo="sistema")


def test_transicionar_refuses_an_unknown_state_before_touching_the_database():
    client = ScriptedClient()
    with pytest.raises(ValueError):
        SupabaseThreadStore(client).transicionar(uuid4(), uuid4(), uuid4(), de=["ativo"], para="hibernando", ator_tipo="sistema")
    assert client.log == []


def test_add_participante_joins_as_active_and_writes_the_join_event():
    org, thread, agent = uuid4(), uuid4(), uuid4()
    client = ScriptedClient(
        SimpleNamespace(data=[]),                                 # get_participante: not there yet
        SimpleNamespace(data=[_part_row(org, thread, agent)]),    # insert participant
        SimpleNamespace(data=[{}]),                               # insert event
    )
    rec = SupabaseThreadStore(client).add_participante(org, thread, agent, motivo="novo_lead")
    assert rec.estado == "ativo"
    tables = [t for t, _ in client.log]
    assert tables == ["thread_participantes", "thread_participantes", "thread_participante_eventos"]
    event = client.log[2][1][0][1][0]
    assert (event["de"], event["para"], event["ator_tipo"]) == (None, "ativo", "sistema")


def test_add_participante_returns_the_row_a_concurrent_join_of_the_same_agent_won():
    org, thread, agent = uuid4(), uuid4(), uuid4()
    client = ScriptedClient(
        SimpleNamespace(data=[]), _unique_violation(), SimpleNamespace(data=[_part_row(org, thread, agent)])
    )
    assert SupabaseThreadStore(client).add_participante(org, thread, agent).agent_id == agent


def test_add_participante_when_another_agent_is_active_raises_the_one_active_conflict():
    client = ScriptedClient(SimpleNamespace(data=[]), _unique_violation(), SimpleNamespace(data=[]))
    with pytest.raises(OutroAgenteAtivo):
        SupabaseThreadStore(client).add_participante(uuid4(), uuid4(), uuid4())


def test_list_abertos_asks_for_the_active_participants_with_the_last_lead_message_in_one_paged_query():
    org, agent, thread = uuid4(), uuid4(), uuid4()
    row = {"thread_id": str(thread), "agent_id": str(agent), "entrou_em": NOW,
           "conversations": {"ultima_mensagem_lead_em": NOW}}
    client = ScriptedClient(SimpleNamespace(data=[row]))
    [aberto] = SupabaseThreadStore(client).list_abertos(org, agent)
    assert aberto.thread_id == thread and aberto.ultima_mensagem_lead_em == NOW
    names = [c[0] for c in client.log[0][1]]
    assert "range" in names  # past PostgREST's silent 1000-row cap
    assert _eqs(client.log[0][1]) == {"org_id": str(org), "agent_id": str(agent), "estado": "ativo"}
    assert "conversations!inner" in client.log[0][1][0][1][0]


# ── lead identity ──────────────────────────────────────────────────────────


def test_upsert_lead_ref_creates_it_when_unknown():
    org = uuid4()
    row = _lead_row(org)
    client = ScriptedClient(SimpleNamespace(data=[]), SimpleNamespace(data=[row]))
    rec = SupabaseThreadStore(client).upsert_lead_ref(org, "contato-1", contato={"nome": "F"})
    assert rec.ref_externa == "contato-1"
    payload = client.log[1][1][0][1][0]
    assert payload["produto"] == "social-wiring" and payload["contato"] == {"nome": "F"} and "crm_lead_id" not in payload


def test_upsert_lead_ref_never_erases_what_an_earlier_call_stored():
    org = uuid4()
    existing = _lead_row(org)
    client = ScriptedClient(SimpleNamespace(data=[existing]))
    rec = SupabaseThreadStore(client).upsert_lead_ref(org, "contato-1")
    assert str(rec.id) == existing["id"]
    assert len(client.log) == 1  # a read only: nothing to patch, nothing written


def test_upsert_lead_ref_patches_only_what_was_given():
    org = uuid4()
    existing = _lead_row(org)
    crm = uuid4()
    client = ScriptedClient(SimpleNamespace(data=[existing]), SimpleNamespace(data=[{**existing, "crm_lead_id": str(crm)}]))
    rec = SupabaseThreadStore(client).upsert_lead_ref(org, "contato-1", crm_lead_id=crm)
    assert rec.crm_lead_id == crm
    assert client.log[1][1][0] == ("update", ({"crm_lead_id": str(crm)},), {})


def test_upsert_lead_ref_reuses_the_row_a_concurrent_first_call_won():
    org = uuid4()
    winner = _lead_row(org)
    client = ScriptedClient(SimpleNamespace(data=[]), _unique_violation(), SimpleNamespace(data=[winner]))
    assert str(SupabaseThreadStore(client).upsert_lead_ref(org, "contato-1").id) == winner["id"]


def test_skill_opening_is_an_idempotent_upsert_and_a_scoped_read():
    org, thread = uuid4(), uuid4()
    client = ScriptedClient(SimpleNamespace(data=[]), SimpleNamespace(data=[{"thread_id": str(thread)}]))
    store = SupabaseThreadStore(client)
    store.registrar_abertura_skill(org, thread, "qualificar", "sha256:x")
    assert store.skill_aberta(org, thread, "qualificar", "sha256:x") is True
    assert client.log[0][1][0][2] == {"on_conflict": "thread_id,skill,compiled_hash", "ignore_duplicates": True}
    assert _eqs(client.log[1][1])["compiled_hash"] == "sha256:x"


# ── conversations: the v2 additions ────────────────────────────────────────


def test_create_channel_opens_a_thread_lead_linked_to_its_lead_ref():
    org, agent, lead = uuid4(), uuid4(), uuid4()
    row = _conv_row(org, agent, tipo="thread_lead", lead_ref_id=str(lead))
    client = ScriptedClient(SimpleNamespace(data=[row]))
    rec = SupabaseConversationStore(client).create_channel(org, agent, "whatsapp", row["channel_ref"], None, lead_ref_id=lead)
    assert rec.tipo == "thread_lead" and rec.lead_ref_id == lead
    payload = client.log[0][1][0][1][0]
    assert payload["tipo"] == "thread_lead" and payload["lead_ref_id"] == str(lead)


def test_find_thread_is_agent_agnostic():
    org, agent = uuid4(), uuid4()
    row = _conv_row(org, agent, tipo="thread_lead")
    client = ScriptedClient(SimpleNamespace(data=[row]))
    assert SupabaseConversationStore(client).find_thread(org, "whatsapp", row["channel_ref"]) is not None
    assert set(_eqs(client.log[0][1])) == {"org_id", "tipo", "channel", "channel_ref"}


def test_link_lead_ref_only_links_an_unlinked_thread():
    org, agent, lead = uuid4(), uuid4(), uuid4()
    row = _conv_row(org, agent, tipo="thread_lead", lead_ref_id=str(lead))
    client = ScriptedClient(SimpleNamespace(data=[row]), SimpleNamespace(data=[row]))
    SupabaseConversationStore(client).link_lead_ref(org, __import__("uuid").UUID(row["id"]), lead)
    names = [c[0] for c in client.log[0][1]]
    assert "is_" in names  # conditional on lead_ref_id IS NULL: a linked thread never moves


def test_touch_lead_message_stamps_both_clocks():
    org, agent = uuid4(), uuid4()
    row = _conv_row(org, agent, tipo="thread_lead")
    client = ScriptedClient(SimpleNamespace(data=[row]))
    SupabaseConversationStore(client).touch_lead_message(org, __import__("uuid").UUID(row["id"]))
    patch = client.log[0][1][0][1][0]
    assert {"ultima_mensagem_lead_em", "last_message_at"} <= set(patch)


# ── messages: author agent, lead, human attendant ──────────────────────────


def test_message_add_carries_the_v2_columns_only_when_given():
    org, conv, agent, lead, user = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    base = {"id": str(uuid4()), "org_id": str(org), "conversation_id": str(conv), "texto": "x", "blocks": [],
            "created_at": NOW, "updated_at": NOW}
    client = ScriptedClient(
        SimpleNamespace(data=[{**base, "role": "assistant", "agent_id": str(agent), "lead_ref_id": str(lead)}]),
        SimpleNamespace(data=[{**base, "role": "humano", "autor_user_id": str(user)}]),
        SimpleNamespace(data=[{**base, "role": "user"}]),
    )
    store = SupabaseMessageStore(client)
    a = store.add(org, conv, "assistant", "x", agent_id=agent, lead_ref_id=lead)
    h = store.add(org, conv, "humano", "x", autor_user_id=user)
    plain = store.add(org, conv, "user", "x")
    assert (a.agent_id, a.lead_ref_id) == (agent, lead) and h.autor_user_id == user
    payloads = [log[1][0][1][0] for log in client.log]
    assert payloads[0]["agent_id"] == str(agent) and payloads[0]["lead_ref_id"] == str(lead)
    assert payloads[1]["autor_user_id"] == str(user)
    assert not ({"agent_id", "lead_ref_id", "autor_user_id"} & set(payloads[2]))  # a pre-v2 insert is unchanged
    assert plain.agent_id is None


def test_message_add_refuses_a_role_outside_the_check():
    with pytest.raises(ValueError):
        SupabaseMessageStore(ScriptedClient()).add(uuid4(), uuid4(), "robo", "x")


def test_link_thread_lead_only_touches_unlinked_messages():
    client = ScriptedClient(SimpleNamespace(data=[{}, {}]))
    assert SupabaseMessageStore(client).link_thread_lead(uuid4(), uuid4(), uuid4()) == 2
    assert "is_" in [c[0] for c in client.log[0][1]]


# ── retention + controls ───────────────────────────────────────────────────


def test_delete_lead_calls_apagar_lead_and_reads_found():
    org = uuid4()
    client = ScriptedClient(SimpleNamespace(data={"encontrado": True, "threads": 2}), SimpleNamespace(data={"encontrado": False}))
    retention = SupabaseChannelRetention(client)
    assert retention.delete_lead(org, "contato-1") is True
    assert retention.delete_lead(org, "contato-1") is False
    assert client.log[0][0].startswith("rpc:apagar_lead")
    assert "p_produto" in client.log[0][0] and "p_ref_externa" in client.log[0][0]


def test_controle_get_reads_the_mode_columns_scoped_by_org():
    org, agent = uuid4(), uuid4()
    client = ScriptedClient(SimpleNamespace(data=[
        {"id": str(agent), "org_id": str(org), "modo_operacao": "drenando", "dreno_inatividade_dias": 5}
    ]))
    rec = SupabaseAgentControleStore(client).get(org, agent)
    assert (rec.modo, rec.dreno_inatividade_dias, rec.aceita_novos_leads) == ("drenando", 5, False)
    assert _eqs(client.log[0][1]) == {"id": str(agent), "org_id": str(org)}


def test_controle_get_of_an_unknown_agent_is_not_found():
    with pytest.raises(NotFound):
        SupabaseAgentControleStore(ScriptedClient(SimpleNamespace(data=[]))).get(uuid4(), uuid4())


def test_controle_set_is_one_rpc_then_a_read_and_validates_first():
    org, agent, actor = uuid4(), uuid4(), uuid4()
    client = ScriptedClient(
        SimpleNamespace(data=None),
        SimpleNamespace(data=[{"id": str(agent), "org_id": str(org), "modo_operacao": "ligado", "dreno_inatividade_dias": 7}]),
    )
    store = SupabaseAgentControleStore(client)
    assert store.set(org, agent, modo="ligado", actor=actor).aceita_novos_leads is True
    assert client.log[0][0].startswith("rpc:set_agent_modo") and "p_actor" in client.log[0][0]
    with pytest.raises(ValueError):
        store.set(org, agent, modo="pausado")
    with pytest.raises(ValueError):
        store.set(org, agent, modo="ligado", dreno_inatividade_dias=0)
    assert len(client.log) == 2  # the two refusals never reached the database
