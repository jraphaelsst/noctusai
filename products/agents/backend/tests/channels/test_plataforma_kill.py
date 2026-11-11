"""The platform kill switch (Julia v3 contract section 12.1) 
every row of the decision, the turn endpoint, the status endpoint, the Studio API auth (strict 401 / 403) and the audit. Fake stores bound through ``dependency_overrides`` -- nothing of ours is patched."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.channels.controles import (
    STATUS_AGENTE_DESLIGADO_PLATAFORMA,
    STATUS_CONTROLE_INDISPONIVEL,
    STATUS_NORMAL,
    ParticipanteView,
    ThreadView,
    decidir,
)
from app.dependencies import get_auth_context
from app.routers.channel_threads_router import get_plataforma_controle_store_dep
from app.stores.errors import NotFound
from app.stores.plataforma_controles import FakePlataformaControleStore
from noctusai_lib.api.auth.session import AuthContext
from tests.channels.conftest import chan, turn_body  # noqa: F401 — fixture
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

AGORA = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
THREAD = ThreadView(ultima_mensagem_lead_em=AGORA)
PART = ParticipanteView(estado="ativo", entrou_em=AGORA)


# ── decidir: the kill is read FIRST ─────────────────────────────────────────


@pytest.mark.parametrize("modo", ["ligado", "drenando", "desligado"])
@pytest.mark.parametrize("gatilho", ["mensagem", "reengajamento"])
@pytest.mark.parametrize("thread", [None, THREAD])
def test_the_platform_kill_refuses_every_trigger_in_every_mode_without_the_model(modo, gatilho, thread):
    d = decidir(modo, thread, PART if thread else None, gatilho, AGORA, desligado_plataforma=True)
    assert d.status == STATUS_AGENTE_DESLIGADO_PLATAFORMA
    assert d.executar_llm is False and d.transicao is None and not d.criar_thread and d.http_status == 200
    # the inbound is stored only for an existing thread, and only for a lead message
    assert d.persistir_inbound is (thread is not None and gatilho == "mensagem")


def test_the_kill_wins_over_an_unreadable_org_mode_and_over_opt_out():
    assert decidir(None, None, None, "mensagem", AGORA, desligado_plataforma=True).status == STATUS_AGENTE_DESLIGADO_PLATAFORMA
    opt = ThreadView(ultima_mensagem_lead_em=AGORA, lead_opt_out=True)
    assert decidir("ligado", opt, PART, "mensagem", AGORA, desligado_plataforma=True).status == STATUS_AGENTE_DESLIGADO_PLATAFORMA


@pytest.mark.parametrize("gatilho", ["mensagem", "reengajamento"])
def test_an_unreadable_kill_is_a_503_whatever_the_org_mode(gatilho):
    d = decidir("ligado", THREAD, PART, gatilho, AGORA, desligado_plataforma=None)
    assert (d.status, d.http_status, d.persistir_inbound, d.executar_llm) == (STATUS_CONTROLE_INDISPONIVEL, 503, False, False)


def test_kill_off_leaves_the_table_as_it_was():
    assert decidir("ligado", THREAD, PART, "mensagem", AGORA, desligado_plataforma=False).status == STATUS_NORMAL


# ── the turn endpoint ───────────────────────────────────────────────────────


def test_a_turn_for_a_killed_agent_answers_the_status_and_never_calls_the_model(chan):
    chan.seed_agent()
    chan.plataforma.set("julia", desligado=True, motivo="incidente")
    resp = chan.turn(turn_body("Oi"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "agente_desligado_plataforma" and body["reply"]["partes"] == []
    assert body["thread_id"] is None  # a lead never served is not stored
    assert not [c for c in chan.provider.calls if c["method"] == "chat_with_tools"]


def test_a_killed_agent_with_an_existing_thread_records_the_message_and_stays_silent(chan):
    chan.seed_agent()
    chan.controles.set(chan.org_id, chan.agent.id, modo="ligado")
    assert chan.turn(turn_body("Oi", ids=["w1"])).json()["status"] == "respondido"
    chat_calls = len(chan.provider.calls)
    chan.plataforma.set("julia", desligado=True)
    resp = chan.turn(turn_body("Alguém aí?", ids=["w2"]))
    assert resp.json()["status"] == "agente_desligado_plataforma" and resp.json()["thread_id"] is not None
    assert len(chan.provider.calls) == chat_calls
    rows = chan.rt.stores.messages.list(chan.org_id, UUID(resp.json()["thread_id"]), limite=50)
    assert any(m.role == "user" and "Alguém aí?" in m.texto for m in rows)
    assert [m for m in rows if m.role == "assistant"] and len([m for m in rows if m.role == "assistant"]) == 1


def test_an_unreadable_kill_is_a_503_and_nothing_is_stored(chan):
    chan.seed_agent()
    chan.controles.set(chan.org_id, chan.agent.id, modo="ligado")
    chan.plataforma.falha = RuntimeError("db down")
    resp = chan.turn(turn_body("Oi"))
    assert resp.status_code == 503 and resp.json()["code"] == "controle_indisponivel"


def test_re_enabling_resumes_normal_turns(chan):
    chan.seed_agent()
    chan.controles.set(chan.org_id, chan.agent.id, modo="ligado")
    chan.plataforma.set("julia", desligado=True)
    chan.plataforma.set("julia", desligado=False)
    assert chan.turn(turn_body("Oi")).json()["status"] == "respondido"


def test_status_reports_desligado_plataforma(chan):
    from app.dependencies import SCOPE_CHANNEL_STATUS

    chan.seed_agent()
    with chan.as_token(SCOPE_CHANNEL_STATUS):
        assert chan.request("GET", "/api/channels/agents/julia/status").json()["desligado_plataforma"] is False
    chan.plataforma.set("julia", desligado=True)
    with chan.as_token(SCOPE_CHANNEL_STATUS):
        assert chan.request("GET", "/api/channels/agents/julia/status").json()["desligado_plataforma"] is True


# ── the Studio API: platform admin only ─────────────────────────────────────

URL = "/api/studio/plataforma/agentes/julia/controle"


@pytest.fixture
def plat(chan):
    from app.main import app

    chan.seed_agent()
    store = FakePlataformaControleStore(conhecidos={"julia"})
    chan.plataforma_api = store
    saved = app.dependency_overrides.get(get_plataforma_controle_store_dep)
    app.dependency_overrides[get_plataforma_controle_store_dep] = lambda: store
    try:
        yield chan
    finally:
        if saved is None:
            app.dependency_overrides.pop(get_plataforma_controle_store_dep, None)
        else:
            app.dependency_overrides[get_plataforma_controle_store_dep] = saved


def _papel(chan, role: str, org_role: str = "owner") -> None:
    chan.rt.client.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": role, "org_role": org_role}]
    )


def test_unauthenticated_is_401(plat):
    c = plat.rt.client.raw()
    assert c.get(URL).status_code == 401
    assert c.put(URL, json={"desligado": True}).status_code == 401


def test_a_channel_token_is_403(plat):
    with plat.as_token("agents:channel-turn"):
        assert plat.request("GET", URL).status_code == 403
        assert plat.request("PUT", URL, json={"desligado": True}).status_code == 403


def test_an_org_owner_who_is_not_a_platform_admin_is_403(plat):
    _papel(plat, "user")
    for method, kw in (("get", {}), ("put", {"json": {"desligado": True}})):
        resp = getattr(plat.rt.client, method)(URL, **kw)
        assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required", method
    assert plat.plataforma_api.get("julia").desligado is False


def test_a_platform_admin_switches_off_and_on_with_an_audit_row(plat):
    _papel(plat, "admin")
    c = plat.rt.client
    assert c.get(URL).json() == {
        "agent_key": "julia", "desligado": False, "motivo": None, "alterado_em": None, "alterado_por": None}
    resp = c.put(URL, json={"desligado": True, "motivo": "incidente"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["desligado"], body["motivo"], body["alterado_por"]) == (True, "incidente", str(DEFAULT_USER_ID))
    assert body["alterado_em"] is not None
    assert c.get(URL).json()["desligado"] is True
    assert c.put(URL, json={"desligado": False}).json()["desligado"] is False
    assert [(a[1], a[2]) for a in plat.plataforma_api.auditoria] == [
        ("plataforma_desligada", DEFAULT_USER_ID), ("plataforma_religada", DEFAULT_USER_ID)]


def test_the_write_validates_its_body_and_the_agent(plat):
    _papel(plat, "admin")
    c = plat.rt.client
    assert c.put(URL, json={"desligado": True, "motivo": "x" * 501}).status_code == 422
    assert c.put(URL, json={"desligado": True, "extra": 1}).status_code == 422
    assert c.put(URL, json={}).status_code == 422
    resp = c.put("/api/studio/plataforma/agentes/nao-existe/controle", json={"desligado": True})
    assert resp.status_code == 404 and resp.json()["code"] == "agent_not_found"


def test_the_fake_refuses_an_unknown_key():
    with pytest.raises(NotFound):
        FakePlataformaControleStore(conhecidos={"julia"}).set("outra", desligado=True)
