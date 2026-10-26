"""Monica's CRM wiring, end to end through the REAL seed organs (leads + WhatsApp inbox) over the Mock PostgREST.

* every new route is strictly 401 without auth (never a 404/422 that would hide a missing auth dep);
* the inbox -> leads seams: a NEW inbound number becomes ONE lead (replays and the message/message.any pair do
  not duplicate it), deleting the lead does not bring it back, and inbound AND outbound messages refresh the card;
* /api/contexto forwards the user's bearer unchanged and re-emits agents' 422.
"""
from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from noctusai_lib.integrations.agents import FakeAgentsOrgSpecsClient, OrgSpecDeclarada
from noctusai_lib.integrations.whatsapp.connection_store import WhatsAppConnectionRecord
from noctusai_lib.integrations.whatsapp.inbox import build_whatsapp_chat_store, ingest_waha_event

from app.config import settings
from app.crm import LEADS_CONFIG

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
CONN = uuid.UUID("33333333-3333-3333-3333-333333333333")
CHAT = "5511999990001@c.us"


@pytest.fixture
def auth_org_id():
    """A real UUID org: the leads router scopes by the raw org id, and the inbox record carries a UUID."""
    return str(ORG)


# --- auth boundary ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/leads"), ("POST", "/api/leads"), ("GET", "/api/leads/board"), ("GET", "/api/leads/config"),
        ("GET", f"/api/leads/{uuid.uuid4()}"), ("PATCH", f"/api/leads/{uuid.uuid4()}"),
        ("DELETE", f"/api/leads/{uuid.uuid4()}"),
        ("GET", "/api/whatsapp/connections"), ("POST", "/api/whatsapp/connections"),
        ("PUT", f"/api/whatsapp/connections/{CONN}/enabled"), ("POST", f"/api/whatsapp/connections/{CONN}/purge"),
        ("GET", f"/api/whatsapp/connections/{CONN}/chats"),
        ("GET", f"/api/whatsapp/connections/{CONN}/chats/{CHAT}/messages"),
        ("POST", f"/api/whatsapp/connections/{CONN}/chats/{CHAT}/messages"),
        ("GET", "/api/contexto"), ("PUT", "/api/contexto"),
    ],
)
def test_routes_are_strictly_401_without_auth(client, method, path):
    assert client.raw().request(method, path).status_code == 401


def test_the_inbound_webhook_is_public_and_an_unknown_token_is_a_generic_404(client):
    resp = client.raw().post("/api/whatsapp/webhook/not-a-real-token", json={"event": "message"})
    assert resp.status_code == 404


def test_connection_routes_are_admin_only(client):
    resp = client.post("/api/whatsapp/connections", json={"label": "Mônica", "api_key": "k"})
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("method,suffix,body", [("PUT", "enabled", {"enabled": False}), ("POST", "purge", {"confirm": "x"})])
def test_switch_and_purge_are_admin_only(client, method, suffix, body):
    call = client.put if method == "PUT" else client.post
    resp = call(f"/api/whatsapp/connections/{CONN}/{suffix}", json=body)
    assert resp.status_code == 403, resp.text


def test_connection_create_without_a_configured_waha_is_a_clear_503_not_a_fake(client, monkeypatch):
    from cryptography.fernet import Fernet

    from app.main import app
    from app.routers.whatsapp_router import _organ_auth

    # MONICA_WAHA_BASE_URL is unset in the test env: the seed router refuses, it never builds a Fake client.
    assert settings.monica_waha_base_url == ""
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())  # isolate the WAHA refusal
    app.dependency_overrides[_organ_auth.admin] = lambda: (None, "t", ORG)  # an org admin (the gate has its own test)
    try:
        resp = client.post("/api/whatsapp/connections", json={"label": "Mônica", "api_key": "k"})
    finally:
        app.dependency_overrides.pop(_organ_auth.admin, None)
    assert resp.status_code == 503, resp.text
    assert "WAHA" in resp.text


# --- leads config -------------------------------------------------------------------------------------------


def test_leads_config_is_the_monica_funnel(client):
    resp = client.get("/api/leads/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert [s["slug"] for s in body["stages"]] == ["lead", "atendimento", "negociacao", "fechado"]
    assert [s["label"] for s in body["stages"]] == ["Lead", "Atendimento", "Negociação", "Fechado"]
    assert [(o["slug"], o["label"]) for o in body["origins"]] == [
        ("whatsapp", "WhatsApp"), ("instagram", "Instagram"), ("indicacao", "Indicação"), ("outro", "Outro"),
    ]
    assert LEADS_CONFIG.whatsapp_origin == "whatsapp"


# --- inbox -> leads -----------------------------------------------------------------------------------------


def _record() -> WhatsAppConnectionRecord:
    return WhatsAppConnectionRecord(
        id=CONN, org_id=ORG, user_id=uuid.uuid4(), label="Mônica", base_url="http://waha:3000",
        session_name="default", webhook_url=None, created_at=None, updated_at=None, api_key="k", webhook_token="tok",
    )


def _event(mid, *, body="oi", from_me=False, event="message", ts=None):
    return {"event": event, "session": "default", "payload": {
        "id": mid, "timestamp": ts or int(time.time()), "from": CHAT if not from_me else "5511000000000@c.us",
        "to": "5511000000000@c.us" if not from_me else CHAT, "fromMe": from_me, "body": body,
        "hasMedia": False, "_data": {"notifyName": "Paciente"},
    }}


def _ingest(chat_store, body):
    from app.services.whatsapp_leads import on_message, on_new_chat

    return asyncio.run(ingest_waha_event(
        body, connection=_record(), chat_store=chat_store, on_new_chat=on_new_chat, on_message=on_message
    ))


def _leads(client):
    resp = client.get("/api/leads?limit=50")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_a_new_inbound_number_becomes_one_lead_at_the_first_stage_with_whatsapp_origin(client):
    chat_store = build_whatsapp_chat_store(None, schema="monica", allow_fake=True)
    for event in ("message", "message.any", "message"):  # replays + the message/message.any pair
        _ingest(chat_store, _event("m1", event=event))
    leads = _leads(client)
    assert len(leads) == 1
    lead = leads[0]
    assert (lead["stage"], lead["origin"], lead["name"]) == ("lead", "whatsapp", "Paciente")
    assert lead["phone"] == "+5511999990001" and lead["whatsapp_chat_id"] == CHAT
    assert lead["last_message_preview"] == "oi"


def test_deleting_the_lead_does_not_bring_it_back_on_the_next_message(client):
    chat_store = build_whatsapp_chat_store(None, schema="monica", allow_fake=True)
    _ingest(chat_store, _event("m1"))
    (lead,) = _leads(client)
    assert client.delete(f"/api/leads/{lead['id']}").status_code == 204
    _ingest(chat_store, _event("m2", body="ainda aqui", ts=int(time.time()) + 5))
    assert _leads(client) == []


def test_inbound_and_outbound_messages_both_refresh_the_card_preview(client):
    chat_store = build_whatsapp_chat_store(None, schema="monica", allow_fake=True)
    now = int(time.time())
    _ingest(chat_store, _event("m1", body="oi, quero marcar uma conversa", ts=now))
    _ingest(chat_store, _event("m2", body="Olá! Tenho horário na terça.", from_me=True, event="message.any", ts=now + 10))
    (lead,) = _leads(client)
    assert lead["last_message_preview"] == "Olá! Tenho horário na terça."
    _ingest(chat_store, _event("m3", body="Pode ser às 15h", ts=now + 20))
    (lead,) = _leads(client)
    assert lead["last_message_preview"] == "Pode ser às 15h"


def test_purge_seam_deletes_untouched_whatsapp_leads_and_keeps_the_edited_one_detached(client):
    from app.services.whatsapp_leads import on_purge

    chat_store = build_whatsapp_chat_store(None, schema="monica", allow_fake=True)
    _ingest(chat_store, _event("m1"))
    (lead,) = _leads(client)
    assert asyncio.run(on_purge(ORG, CONN)) == {"leads_deleted": 1, "leads_detached": 0}
    assert _leads(client) == []
    _ingest(chat_store, {**_event("m9"), "payload": {**_event("m9")["payload"], "from": "5511999990009@c.us"}})
    (lead,) = _leads(client)
    assert client.patch(f"/api/leads/{lead['id']}", json={"notes": "cliente real"}).status_code == 200
    assert asyncio.run(on_purge(ORG, CONN)) == {"leads_deleted": 0, "leads_detached": 1}
    (kept,) = _leads(client)
    assert kept["notes"] == "cliente real" and kept["whatsapp_connection_id"] is None
    assert kept["last_message_preview"] is None


# --- contexto proxy -----------------------------------------------------------------------------------------


@pytest.fixture
def agents_fake(client):
    from app.main import app
    from app.routers.contexto_router import get_agents_client

    fake = FakeAgentsOrgSpecsClient(
        declaradas=(OrgSpecDeclarada(chave="quem_sou", rotulo="Quem sou", descricao="", tipo="texto_longo",
                                     obrigatoria=False, exemplo=None),),
        agent_key=settings.monica_agent_key,
    )
    app.dependency_overrides[get_agents_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_agents_client, None)


def test_contexto_get_forwards_the_users_bearer_and_the_agent_key(client, agents_fake):
    resp = client.get("/api/contexto")
    assert resp.status_code == 200, resp.text
    assert resp.json()["agent_key"] == "monica-leads"
    assert [d["chave"] for d in resp.json()["declaradas"]] == ["quem_sou"]
    assert agents_fake.calls == [("get", "monica-leads", None, "test-token-valid")]


def test_contexto_put_saves_and_returns_the_view(client, agents_fake):
    resp = client.put("/api/contexto", json={"valores": {"quem_sou": "Psicanalista."}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["valores"] == [{"chave": "quem_sou", "valor": "Psicanalista."}]
    assert agents_fake.calls[0][0] == "put" and agents_fake.calls[0][3] == "test-token-valid"


def test_contexto_put_re_emits_agents_422_with_its_code(client, agents_fake):
    resp = client.put("/api/contexto", json={"valores": {"nao_existe": "x"}})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "spec_nao_declarada"


def test_contexto_without_the_agents_link_is_a_503_not_a_scripted_fake(client):
    assert settings.agents_allow_fake is False and settings.agents_url == ""
    resp = client.get("/api/contexto")
    assert resp.status_code == 503, resp.text


def test_contexto_when_the_agent_is_not_created_for_the_org_is_a_clear_404(client):
    from app.main import app
    from app.routers.contexto_router import get_agents_client
    from noctusai_lib.integrations.agents import AgentNotFound

    class _NoAgent:
        async def get_org_specs(self, agent_key, *, token):
            raise AgentNotFound("agent_not_found", code="agent_not_found")

    app.dependency_overrides[get_agents_client] = lambda: _NoAgent()
    try:
        resp = client.get("/api/contexto")
    finally:
        app.dependency_overrides.pop(get_agents_client, None)
    assert resp.status_code == 404, resp.text
