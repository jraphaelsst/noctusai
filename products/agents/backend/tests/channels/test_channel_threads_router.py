"""The shared-thread + controls routes (Julia v2 A-THREAD): auth (strictly 401 / 403), org scoping, token binding, the
per-conversation pause/resume, append-without-a-turn, delete-by-lead, and the Studio controls. The REAL app, shared Fake
stores bound through ``app.dependency_overrides`` (the ``chan`` harness) -- nothing of ours is patched."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.channels.retention import FakeChannelRetention
from app.dependencies import SCOPE_CHANNEL_STATUS, SCOPE_CHANNEL_TURN, get_channel_retention_dep
from app.routers.channel_threads_router import get_agent_controle_store_dep, get_thread_store_dep
from app.stores.agent_controles import FakeAgentControleStore
from app.stores.threads import FakeThreadStore
from tests.channels.conftest import CONNECTION_ID, OTHER_ORG, chan  # noqa: F401 — fixture
from tests.routers.conftest import DEFAULT_USER_ID

_MISSING = object()
ACTOR = uuid4()
STATUS_ONLY = (SCOPE_CHANNEL_STATUS,)
TURN_ONLY = (SCOPE_CHANNEL_TURN,)


class Threads:
    def __init__(self, chan_) -> None:
        self.chan = chan_
        self.store = FakeThreadStore(chan_.rt.stores.conversations)
        self.controles = FakeAgentControleStore()
        chan_.retention = FakeChannelRetention(
            chan_.rt.stores.conversations, chan_.rt.stores.messages, chan_.inbound, self.store
        )

    @property
    def conversations(self):
        return self.chan.rt.stores.conversations

    def thread(self, *, ref="contato-1", chat="chat-1", agent=None, org=None, participante=True):
        agent = agent or self.chan.agent
        org = org or self.chan.org_id
        lead = self.store.upsert_lead_ref(org, ref, contato={"nome": "Fulano"})
        t = self.conversations.create_channel(
            org, agent.id, "whatsapp", {"connection_id": str(CONNECTION_ID), "chat_id": chat}, None, lead_ref_id=lead.id
        )
        if participante:
            self.store.add_participante(org, t.id, agent.id)
        return t

    def call(self, method, url, *scopes, **kw):
        with self.chan.as_token(*scopes, **kw.pop("token", {})):
            return self.chan.request(method, url, **kw)


@pytest.fixture
def thr(chan):
    from app.main import app

    chan.seed_agent()
    t = Threads(chan)
    bindings = {
        get_thread_store_dep: lambda: t.store,
        get_agent_controle_store_dep: lambda: t.controles,
        get_channel_retention_dep: lambda: chan.retention,
    }
    saved = {k: app.dependency_overrides.get(k, _MISSING) for k in bindings}
    app.dependency_overrides.update(bindings)
    try:
        yield t
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                app.dependency_overrides.pop(k, None)
            else:
                app.dependency_overrides[k] = v


def _code(resp):
    body = resp.json()
    return (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")


# ── auth: strictly 401 with no credentials, never a looser set ─────────────

CHANNEL_ROUTES = [
    ("GET", "/api/channels/threads?lead_ref=x"),
    ("GET", f"/api/channels/threads/{uuid4()}"),
    ("POST", f"/api/channels/threads/{uuid4()}/mensagens"),
    ("PATCH", f"/api/channels/threads/{uuid4()}/participantes/julia"),
    ("GET", "/api/channels/agents/julia/controle"),
    ("DELETE", "/api/channels/leads/contato-1"),
]
STUDIO_ROUTES = [
    ("GET", "/api/studio/agents/julia/controle"),
    ("PUT", "/api/studio/agents/julia/controle"),
    ("PATCH", f"/api/studio/threads/{uuid4()}/participantes/julia"),
]


@pytest.mark.parametrize("method,url", CHANNEL_ROUTES + STUDIO_ROUTES)
def test_no_credentials_is_exactly_401(thr, method, url):
    resp = thr.chan.client.raw().request(method, url, json={})
    assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


# ── GET thread ─────────────────────────────────────────────────────────────


def test_get_thread_by_id_lists_participants_with_names_and_the_lead_ref(thr):
    t = thr.thread()
    resp = thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["thread_id"] == str(t.id) and body["lead_ref"] == "contato-1" and body["channel"] == "whatsapp"
    [p] = body["participantes"]
    assert (p["agent_key"], p["estado"]) == ("julia", "ativo")
    assert "contato" not in body and "contact" not in body  # SW owns the contact


def test_get_thread_by_channel_identity_and_by_lead(thr):
    t = thr.thread()
    q = f"/api/channels/threads?channel=whatsapp&connection_id={CONNECTION_ID}&chat_id=chat-1"
    assert thr.call("GET", q, *STATUS_ONLY).json()["thread_id"] == str(t.id)
    assert thr.call("GET", "/api/channels/threads?lead_ref=contato-1", *STATUS_ONLY).json()["thread_id"] == str(t.id)


@pytest.mark.parametrize("qs", ["", "?channel=whatsapp", "?lead_ref=x&channel=whatsapp&connection_id=" + str(CONNECTION_ID) + "&chat_id=c"])
def test_get_thread_needs_exactly_one_lookup_form(thr, qs):
    resp = thr.call("GET", "/api/channels/threads" + qs, *STATUS_ONLY)
    assert resp.status_code == 422 and _code(resp) == "invalid_field"


def test_an_unknown_thread_is_404(thr):
    resp = thr.call("GET", f"/api/channels/threads/{uuid4()}", *STATUS_ONLY)
    assert resp.status_code == 404 and _code(resp) == "thread_not_found"
    resp = thr.call("GET", "/api/channels/threads?lead_ref=nope", *STATUS_ONLY)
    assert resp.status_code == 404


def test_a_thread_of_another_org_is_404_not_403(thr):
    t = thr.thread()
    resp = thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY, token={"org_id": OTHER_ORG})
    assert resp.status_code == 404 and _code(resp) == "thread_not_found"


def test_a_thread_the_tokens_agent_does_not_take_part_in_is_404(thr):
    other = thr.chan.rt.studio.create_studio_agent(thr.chan.org_id, "juridico", "Juridico", None)
    t = thr.thread(agent=other)
    resp = thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY)
    assert resp.status_code == 404


def test_a_user_conversation_is_never_a_thread(thr):
    conv = thr.chan.rt.stores.conversations.create(thr.chan.org_id, thr.chan.agent.id, DEFAULT_USER_ID, "meu chat")
    assert thr.call("GET", f"/api/channels/threads/{conv.id}", *STATUS_ONLY).status_code == 404


def test_the_status_scope_does_not_open_the_turn_scoped_routes(thr):
    t = thr.thread()
    resp = thr.call("PATCH", f"/api/channels/threads/{t.id}/participantes/julia", *STATUS_ONLY,
                    json={"estado": "pausado", "ator_user_id": str(ACTOR)})
    assert resp.status_code == 403 and _code(resp) == "scope_missing"
    assert thr.call("DELETE", "/api/channels/leads/contato-1", *STATUS_ONLY).status_code == 403
    assert thr.call("GET", f"/api/channels/threads/{t.id}", *TURN_ONLY).status_code == 403


# ── PATCH participant: the per-conversation on/off ─────────────────────────


def test_pause_then_resume_one_conversation_with_the_actor_recorded(thr):
    t = thr.thread()
    url = f"/api/channels/threads/{t.id}/participantes/julia"
    resp = thr.call("PATCH", url, *TURN_ONLY, json={"estado": "pausado", "ator_user_id": str(ACTOR), "motivo": "assumi o lead"})
    assert resp.status_code == 200 and resp.json()["estado"] == "pausado"
    assert thr.call("GET", f"/api/channels/threads/{t.id}", *STATUS_ONLY).json()["participantes"][0]["estado"] == "pausado"
    resp = thr.call("PATCH", url, *TURN_ONLY, json={"estado": "ativo", "ator_user_id": str(ACTOR)})
    assert resp.status_code == 200 and resp.json()["estado"] == "ativo"
    ev = thr.store.list_eventos(thr.chan.org_id, t.id)
    assert [(e.para, e.ator_tipo, e.ator_id) for e in ev[1:]] == [("pausado", "usuario", ACTOR), ("ativo", "usuario", ACTOR)]


def test_pause_is_idempotent(thr):
    t = thr.thread()
    url = f"/api/channels/threads/{t.id}/participantes/julia"
    body = {"estado": "pausado", "ator_user_id": str(ACTOR)}
    assert thr.call("PATCH", url, *TURN_ONLY, json=body).status_code == 200
    assert thr.call("PATCH", url, *TURN_ONLY, json=body).status_code == 200
    assert len(thr.store.list_eventos(thr.chan.org_id, t.id)) == 2


def test_resuming_a_concluded_thread_is_409(thr):
    t = thr.thread()
    thr.store.transicionar(thr.chan.org_id, t.id, thr.chan.agent.id, de=["ativo"], para="concluido", ator_tipo="agente")
    resp = thr.call("PATCH", f"/api/channels/threads/{t.id}/participantes/julia", *TURN_ONLY,
                    json={"estado": "ativo", "ator_user_id": str(ACTOR)})
    assert resp.status_code == 409 and _code(resp) == "transicao_invalida"


def test_resuming_while_another_agent_is_active_is_409(thr):
    t = thr.thread()
    url = f"/api/channels/threads/{t.id}/participantes/julia"
    thr.call("PATCH", url, *TURN_ONLY, json={"estado": "pausado", "ator_user_id": str(ACTOR)})
    other = thr.chan.rt.studio.create_studio_agent(thr.chan.org_id, "juridico", "Juridico", None)
    thr.store.add_participante(thr.chan.org_id, t.id, other.id)
    resp = thr.call("PATCH", url, *TURN_ONLY, json={"estado": "ativo", "ator_user_id": str(ACTOR)})
    assert resp.status_code == 409 and _code(resp) == "outro_agente_ativo"


def test_the_actor_is_required_and_unknown_fields_are_refused(thr):
    t = thr.thread()
    url = f"/api/channels/threads/{t.id}/participantes/julia"
    assert thr.call("PATCH", url, *TURN_ONLY, json={"estado": "pausado"}).status_code == 422
    assert thr.call("PATCH", url, *TURN_ONLY, json={"estado": "pausado", "ator_user_id": str(ACTOR), "extra": 1}).status_code == 422
    assert thr.call("PATCH", url, *TURN_ONLY, json={"estado": "concluido", "ator_user_id": str(ACTOR)}).status_code == 422


def test_a_token_bound_to_another_agent_cannot_toggle(thr):
    t = thr.thread()
    resp = thr.call("PATCH", f"/api/channels/threads/{t.id}/participantes/julia", *TURN_ONLY,
                    json={"estado": "pausado", "ator_user_id": str(ACTOR)}, token={"principal": uuid4()})
    assert resp.status_code == 403 and _code(resp) == "agent_not_allowed"


def test_toggling_an_unknown_agent_key_is_404(thr):
    t = thr.thread()
    resp = thr.call("PATCH", f"/api/channels/threads/{t.id}/participantes/ninguem", *TURN_ONLY,
                    json={"estado": "pausado", "ator_user_id": str(ACTOR)})
    assert resp.status_code == 404 and _code(resp) == "agent_not_found"


def test_studio_admin_pauses_a_thread_as_themselves(thr):
    t = thr.thread()
    resp = thr.chan.client.patch(f"/api/studio/threads/{t.id}/participantes/julia", json={"estado": "pausado"})
    assert resp.status_code == 200 and resp.json()["estado"] == "pausado"
    ev = thr.store.list_eventos(thr.chan.org_id, t.id)[-1]
    assert (ev.ator_tipo, ev.ator_id) == ("usuario", DEFAULT_USER_ID)


# ── POST mensagens: append without a turn ──────────────────────────────────


def test_append_a_human_attendant_message_without_replying(thr):
    t = thr.thread()
    body = {"role": "humano", "texto": "Oi, sou o corretor.", "provider_message_id": "wamid.h1", "autor_user_id": str(ACTOR)}
    resp = thr.call("POST", f"/api/channels/threads/{t.id}/mensagens", *TURN_ONLY, json=body)
    assert resp.status_code == 200 and resp.json()["duplicado"] is False
    [m] = thr.chan.rt.stores.messages.list(thr.chan.org_id, t.id)
    assert (m.role, m.autor_user_id, m.lead_ref_id) == ("humano", ACTOR, t.lead_ref_id)


def test_append_is_idempotent_and_conflicts_on_other_text(thr):
    t = thr.thread()
    url = f"/api/channels/threads/{t.id}/mensagens"
    body = {"role": "user", "texto": "oi", "provider_message_id": "wamid.1"}
    assert thr.call("POST", url, *TURN_ONLY, json=body).json()["duplicado"] is False
    again = thr.call("POST", url, *TURN_ONLY, json=body)
    assert again.status_code == 200 and again.json() == {"message_id": None, "duplicado": True}
    assert len(thr.chan.rt.stores.messages.list(thr.chan.org_id, t.id)) == 1
    clash = thr.call("POST", url, *TURN_ONLY, json={**body, "texto": "outro"})
    assert clash.status_code == 409 and _code(clash) == "idempotency_conflict"


def test_append_validates_the_role_and_the_author(thr):
    t = thr.thread()
    url = f"/api/channels/threads/{t.id}/mensagens"
    assert thr.call("POST", url, *TURN_ONLY, json={"role": "assistant", "texto": "x", "provider_message_id": "a"}).status_code == 422
    r = thr.call("POST", url, *TURN_ONLY, json={"role": "humano", "texto": "x", "provider_message_id": "a"})
    assert r.status_code == 422 and _code(r) == "invalid_field"


def test_append_during_a_running_turn_is_409_turn_in_progress_and_leaves_the_lock_alone(thr):
    t = thr.thread()
    assert thr.conversations.try_acquire_turn(thr.chan.org_id, t.id, "um-turno", 60)
    r = thr.call("POST", f"/api/channels/threads/{t.id}/mensagens", *TURN_ONLY,
                 json={"role": "user", "texto": "oi", "provider_message_id": "wamid.1"})
    assert r.status_code == 409 and _code(r) == "turn_in_progress"
    assert thr.conversations.try_acquire_turn(thr.chan.org_id, t.id, "outro", 60) is False  # still held by the turn


def test_append_releases_the_turn_lock_afterwards(thr):
    t = thr.thread()
    thr.call("POST", f"/api/channels/threads/{t.id}/mensagens", *TURN_ONLY,
             json={"role": "user", "texto": "oi", "provider_message_id": "wamid.1"})
    assert thr.conversations.try_acquire_turn(thr.chan.org_id, t.id, "proximo", 60) is True


def test_append_publishes_the_message_to_the_live_stream(thr):
    t = thr.thread()
    thr.call("POST", f"/api/channels/threads/{t.id}/mensagens", *TURN_ONLY,
             json={"role": "user", "texto": "oi", "provider_message_id": "wamid.1"})
    assert thr.chan.events(t.id)


# ── controls: SW reads, Studio writes ──────────────────────────────────────


def test_sw_reads_the_mode_and_the_drain_progress_read_only(thr):
    thr.controles.set(thr.chan.org_id, thr.chan.agent.id, modo="drenando", dreno_inatividade_dias=5)
    thr.thread()
    body = thr.call("GET", "/api/channels/agents/julia/controle", *STATUS_ONLY).json()
    assert (body["modo"], body["aceita_novos_leads"], body["dreno_inatividade_dias"], body["threads_abertas"]) == ("drenando", False, 5, 1)
    assert body["drenagem"]["abertas"] == 1 and body["drenagem"]["concluida"] is False
    # SW has no write path to the mode: not on the channel surface at all
    assert thr.call("PUT", "/api/channels/agents/julia/controle", *STATUS_ONLY, json={"modo": "ligado"}).status_code == 405


def test_a_fresh_agent_reads_as_off(thr):
    body = thr.call("GET", "/api/channels/agents/julia/controle", *STATUS_ONLY).json()
    assert (body["modo"], body["aceita_novos_leads"], body["threads_abertas"]) == ("desligado", False, 0)
    assert body["drenagem"]["concluida"] is True


def test_the_controle_read_is_bound_to_the_tokens_agent(thr):
    resp = thr.call("GET", "/api/channels/agents/julia/controle", *STATUS_ONLY, token={"principal": uuid4()})
    assert resp.status_code == 403 and _code(resp) == "agent_not_allowed"


def test_studio_admin_switches_the_mode_and_the_change_is_audited_with_the_actor(thr):
    c = thr.chan.client
    assert c.get("/api/studio/agents/julia/controle").json()["modo"] == "desligado"
    resp = c.put("/api/studio/agents/julia/controle", json={"modo": "ligado"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["modo"] == "ligado" and resp.json()["aceita_novos_leads"] is True
    resp = c.put("/api/studio/agents/julia/controle", json={"modo": "drenando", "dreno_inatividade_dias": 3})
    assert (resp.json()["modo"], resp.json()["dreno_inatividade_dias"]) == ("drenando", 3)
    assert [(a[1], a[3]["modo_operacao"]) for a in thr.controles.auditoria] == [(DEFAULT_USER_ID, "ligado"), (DEFAULT_USER_ID, "drenando")]
    assert c.put("/api/studio/agents/julia/controle", json={"modo": "desligado"}).json()["modo"] == "desligado"


def test_turning_on_needs_a_published_version_and_a_configured_key_but_turning_off_never_does(thr):
    c = thr.chan.client
    thr.chan.keys.clear()
    resp = c.put("/api/studio/agents/julia/controle", json={"modo": "ligado"})
    assert resp.status_code == 409 and _code(resp) == "llm_nao_configurado"
    assert c.put("/api/studio/agents/julia/controle", json={"modo": "desligado"}).status_code == 200


def test_turning_on_an_agent_without_a_published_version_is_409(thr):
    c = thr.chan.client
    thr.chan.rt.studio.create_studio_agent(thr.chan.org_id, "rascunho", "Rascunho", None, runtime="llm")
    resp = c.put("/api/studio/agents/rascunho/controle", json={"modo": "ligado"})
    assert resp.status_code == 409 and _code(resp) == "no_active_version"


def test_the_studio_controle_validates_the_body(thr):
    c = thr.chan.client
    assert c.put("/api/studio/agents/julia/controle", json={"modo": "pausado"}).status_code == 422
    assert c.put("/api/studio/agents/julia/controle", json={"modo": "ligado", "dreno_inatividade_dias": 0}).status_code == 422
    assert c.put("/api/studio/agents/julia/controle", json={"modo": "ligado", "extra": 1}).status_code == 422
    assert c.get("/api/studio/agents/ninguem/controle").status_code == 404


# ── DELETE lead (LGPD) ─────────────────────────────────────────────────────


def test_delete_by_lead_erases_every_thread_and_is_idempotent(thr):
    org = thr.chan.org_id
    a, b = thr.thread(chat="chat-1"), thr.thread(chat="chat-2")
    keep = thr.thread(ref="contato-2", chat="chat-3")
    thr.chan.rt.stores.messages.add(org, a.id, "user", "oi")
    assert thr.call("DELETE", "/api/channels/leads/contato-1", *TURN_ONLY).status_code == 204
    for t in (a, b):
        assert thr.conversations.find_thread(org, "whatsapp", t.channel_ref) is None
    assert thr.chan.rt.stores.messages.list(org, a.id) == []
    assert thr.store.get_lead_ref_by_externa(org, "contato-1") is None
    assert thr.conversations.get(org, keep.id)
    assert thr.call("DELETE", "/api/channels/leads/contato-1", *TURN_ONLY).status_code == 204  # idempotent
    assert thr.call("DELETE", "/api/channels/leads/nunca-existiu", *TURN_ONLY).status_code == 204  # no existence oracle


def test_delete_by_lead_is_org_scoped(thr):
    t = thr.thread()
    assert thr.call("DELETE", "/api/channels/leads/contato-1", *TURN_ONLY, token={"org_id": OTHER_ORG}).status_code == 204
    assert thr.conversations.get(thr.chan.org_id, t.id)


def test_delete_by_lead_during_a_running_turn_is_409_and_erases_nothing(thr):
    t = thr.thread()
    assert thr.conversations.try_acquire_turn(thr.chan.org_id, t.id, "um-turno", 60)
    r = thr.call("DELETE", "/api/channels/leads/contato-1", *TURN_ONLY)
    assert r.status_code == 409 and _code(r) == "turn_in_progress"
    assert thr.store.get_lead_ref_by_externa(thr.chan.org_id, "contato-1") is not None


# ── content readiness + IP tiering ─────────────────────────────────────────


def test_turning_on_needs_complete_content_and_names_what_is_missing(thr):
    from app.stores.studio_definitions_conteudo import FerramentaInput, SpecDefInput, TextoInput

    studio = thr.chan.rt.studio
    from dataclasses import replace

    # A-CONT's line-based content mode (the shape Julia v2 runs in): the compile then checks the org specs.
    studio._agents[(thr.chan.org_id, "julia")] = replace(studio.get_agent(thr.chan.org_id, "julia"), conteudo_modo="linhas")
    draft = studio.create_draft(thr.chan.org_id, thr.chan.agent.id, thr.chan.version.id, thr.chan.rt.user_id)
    from app.stores.studio_definitions import SectionInput

    studio.replace_sections(thr.chan.org_id, draft.id, [  # decisions are rows in this mode, not prompt sections
        SectionInput(chave=x.chave, titulo=x.titulo, ordem=x.ordem, conteudo=x.conteudo)
        for x in studio.list_sections(thr.chan.org_id, draft.id) if not x.chave.startswith("decisao-")
    ])
    studio.replace_spec_defs(thr.chan.org_id, draft.id, [SpecDefInput("agencia", "Nome da imobiliária")])
    studio.replace_textos(thr.chan.org_id, draft.id, [
        TextoInput("compilador.titulo_ferramentas", "Ferramentas"),
        TextoInput("compilador.ferramenta_linha.web_desativada", "- Web: desligada."),
        TextoInput("compilador.ferramenta_linha.conhecimento_desativada", "- Conhecimento: desligado."),
    ])
    studio.replace_ferramentas(thr.chan.org_id, draft.id, [FerramentaInput("handoff", "Passa a conversa para uma pessoa.")])
    thr.chan.rt.publish(thr.chan.agent, draft.id)  # v2 declares a required org spec nobody filled yet
    c = thr.chan.client
    resp = c.put("/api/studio/agents/julia/controle", json={"modo": "ligado"})
    assert resp.status_code == 409 and _code(resp) == "conteudo_incompleto" and "agencia" in resp.text
    assert c.put("/api/studio/agents/julia/controle", json={"modo": "drenando"}).status_code == 409
    assert c.put("/api/studio/agents/julia/controle", json={"modo": "desligado"}).status_code == 200  # off never needs content
    studio.upsert_org_specs(thr.chan.org_id, "julia", {"agencia": "Imobiliária Exemplo"})
    final = c.put("/api/studio/agents/julia/controle", json={"modo": "ligado"})
    assert final.status_code == 200, final.text


def test_the_member_readable_controle_carries_mode_and_counters_only_no_prompt_or_version_content(thr):
    thr.thread()
    thr.controles.set(thr.chan.org_id, thr.chan.agent.id, modo="ligado")
    body = thr.chan.client.get("/api/studio/agents/julia/controle").json()
    assert set(body) == {"agent_key", "modo", "aceita_novos_leads", "dreno_inatividade_dias", "threads_abertas", "drenagem"}
    assert set(body["drenagem"]) == {"abertas", "ociosas", "efetivas", "concluida", "idade_max_dias", "idades_dias"}
    flat = str(body)
    for forbidden in ("prompt", "compiled", "secao", "ferramenta", "versao", "hash"):
        assert forbidden not in flat.lower()
    sw = thr.call("GET", "/api/channels/agents/julia/controle", *STATUS_ONLY).json()
    assert set(sw) == set(body)


def test_an_org_admin_reads_a_thread_without_system_notices_tool_results_or_stamps(thr):
    org = thr.chan.org_id
    t = thr.thread()
    msgs = thr.chan.rt.stores.messages
    msgs.add(org, t.id, "user", "Quero um apartamento")
    msgs.add(org, t.id, "assistant", "Compra ou aluguel?", agent_id=thr.chan.agent.id,
             blocks=[{"type": "tool_result", "name": "buscar_imoveis", "content": "SEGREDO-DA-FERRAMENTA"}],
             token_usage={"in": 1}, compiled_hash="sha256:prompt", version_id=uuid4())
    msgs.add(org, t.id, "system", "O turno falhou: PROMPT-INTERNO")
    msgs.add(org, t.id, "assistant", "", agent_id=thr.chan.agent.id)  # cost-booking row of a silent turn
    msgs.add(org, t.id, "humano", "Sou o corretor", autor_user_id=ACTOR)
    msgs.add(org, t.id, "evento", "transferido")
    resp = thr.chan.client.get(f"/api/studio/threads/{t.id}/mensagens")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["role"] for r in rows] == ["user", "assistant", "humano", "evento"]
    assert rows[1]["agent_key"] == "julia" and rows[2]["autor_user_id"] == str(ACTOR)
    raw = resp.text
    for leak in ("SEGREDO-DA-FERRAMENTA", "PROMPT-INTERNO", "sha256:prompt", "blocks", "token_usage", "tool_result"):
        assert leak not in raw
    assert all(set(r) == {"id", "role", "texto", "agent_key", "agent_nome", "autor_user_id", "created_at"} for r in rows)


def test_the_admin_thread_read_is_admin_only_org_scoped_and_threads_only(thr):
    t = thr.thread()
    conv = thr.chan.rt.stores.conversations.create(thr.chan.org_id, thr.chan.agent.id, DEFAULT_USER_ID, "chat")
    assert thr.chan.client.get(f"/api/studio/threads/{conv.id}/mensagens").status_code == 404
    assert thr.chan.client.get(f"/api/studio/threads/{uuid4()}/mensagens").status_code == 404
    assert thr.chan.client.get(f"/api/studio/threads/{t.id}/mensagens").status_code == 200
    # a channel token is not an admin session
    assert thr.call("GET", f"/api/studio/threads/{t.id}/mensagens", *STATUS_ONLY).status_code == 403
    assert thr.chan.rt.client.raw().get(f"/api/studio/threads/{t.id}/mensagens").status_code == 401
