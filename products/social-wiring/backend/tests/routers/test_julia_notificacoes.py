"""Julia wave 6 -- Notificacoes (contract 8): recipient resolution (responsavel -> owner -> admins), per-user
prefs, org isolation, member-sees-only-own, strict `== 401`, no double handoff, cobranca from the episode resumo.

Seams: mock DB + the `julia_eventos_service` sink; nothing of ours is patched."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import ResumoResult
from app.services import julia_acoes_service as acoes
from app.services import julia_contatos_service as contatos
from app.services import julia_eventos_service as eventos
from app.services import julia_notificacoes_service as svc

from tests.support.julia_world import (
    ADMIN_ID, CONNECTION_ID, LEAD_CHAT, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, CORRETOR_ID, World,
)

BASE = "/api/julia/notificacoes"
H = {"Authorization": "Bearer test-token"}


@contextmanager
def _core_injetado(w):
    """Bind the world's core client through the service's own seam (never a patch of the module under test)."""
    svc.registrar_core_provider(lambda: w.core)
    try:
        yield
    finally:
        svc.registrar_core_provider(None)


def _mundo(**contato_over):
    w = World()
    w.sw.set_table_data("julia_notificacao_prefs", [])
    w.seed_connection()
    contato = contatos.obter_ou_criar_contato(w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, telefone_e164="+5511988887777")
    if contato_over:
        contatos.atualizar_contato(w.sw, contato["id"], contato_over)
        contato = w.contato()
    return w, contato


def _evento(w, contato, tipo="novo_lead", **payload):
    return eventos.emitir(w.sw, ORG_ID, tipo, contato["id"], payload)


def _para(w):
    return sorted(n["user_id"] for n in w.notifications())


# ── recipients ──────────────────────────────────────────────────────────────
class TestDestinatarios:
    def test_responsavel_wins(self):
        w, c = _mundo(responsavel_user_id=CORRETOR_ID)
        svc.notificar(w.sw, _evento(w, c), core=w.core)
        assert _para(w) == [CORRETOR_ID]

    def test_connection_owner_when_no_responsavel(self):
        w, c = _mundo()
        svc.notificar(w.sw, _evento(w, c), core=w.core)
        assert _para(w) == [OWNER_ID]

    def test_org_admins_when_no_owner(self):
        w, c = _mundo()
        w.seed_connection  # connection exists; point it at a user outside the org
        w.sw.set_table_data("whatsapp_connections", [{**w._connections[0], "user_id": str(uuid4())}])
        svc.notificar(w.sw, _evento(w, c), core=w.core)
        assert _para(w) == sorted([OWNER_ID, ADMIN_ID])  # owner + admin roles, never corretor/member

    def test_stale_responsavel_outside_org_falls_through(self):
        w, c = _mundo(responsavel_user_id=str(uuid4()))
        svc.notificar(w.sw, _evento(w, c), core=w.core)
        assert _para(w) == [OWNER_ID]

    def test_notification_shape_and_kind(self):
        w, c = _mundo(operacao="aluguel")
        svc.notificar(w.sw, _evento(w, c, "captacao"), core=w.core)
        (n,) = w.notifications()
        assert n["metadata"]["tipo"] == "julia_captacao" and n["metadata"]["operacao"] == "aluguel"
        assert n["org_id"] == ORG_ID and n["title"] == "Captação"


class TestPreferencias:
    def test_pref_off_suppresses_only_that_user_and_type(self):
        w, c = _mundo()
        w.sw.set_table_data("julia_notificacao_prefs", [{"org_id": ORG_ID, "user_id": OWNER_ID, "tipo": "novo_lead", "in_app": False}])
        svc.notificar(w.sw, _evento(w, c, "novo_lead"), core=w.core)
        assert w.notifications() == []
        svc.notificar(w.sw, _evento(w, c, "nova_mensagem"), core=w.core)
        assert len(w.notifications()) == 1

    def test_lead_pronto_toggle_gates_novo_atendimento(self):
        w, c = _mundo()
        w.sw.set_table_data("julia_notificacao_prefs", [{"org_id": ORG_ID, "user_id": OWNER_ID, "tipo": "lead_pronto", "in_app": False}])
        svc.notificar(w.sw, _evento(w, c, "novo_atendimento"), core=w.core)
        assert w.notifications() == []

    def test_prefs_of_another_org_do_not_apply(self):
        w, c = _mundo()
        w.sw.set_table_data("julia_notificacao_prefs", [{"org_id": OTHER_ORG_ID, "user_id": OWNER_ID, "tipo": "novo_lead", "in_app": False}])
        svc.notificar(w.sw, _evento(w, c), core=w.core)
        assert len(w.notifications()) == 1


class TestSinkEHandoff:
    def test_emitir_fans_out_through_the_registered_sink(self):
        w, c = _mundo()
        svc.registrar()
        with _core_injetado(w):
            _evento(w, c, "novo_lead")
        assert _para(w) == [OWNER_ID]

    def test_diagnostic_and_handoff_events_never_fan_out(self):
        w, c = _mundo()
        for t in ("acao_falhou", "reengajamento", "handoff"):
            assert svc.notificar(w.sw, {"org_id": ORG_ID, "tipo": t, "contato_id": c["id"], "payload": {}}, core=w.core) == 0
        assert w.notifications() == []

    def test_failing_sink_never_reaches_the_caller(self):
        w, c = _mundo()
        boom = MagicMock(side_effect=RuntimeError("x"))
        eventos._SINKS.append(boom)
        try:
            assert _evento(w, c) is not None
        finally:
            eventos._SINKS.remove(boom)

    def test_cobranca_from_the_episode_resumo(self):
        w, c = _mundo()
        inter = contatos.abrir_interacao(w.sw, ORG_ID, c)
        w.agents.resumo_result = None
        svc.registrar()
        with _core_injetado(w):
            svc.avisar_cobranca(w.sw, ORG_ID, c, inter, ["pergunta_preco", "cobranca_atendimento"])
            svc.avisar_cobranca(w.sw, ORG_ID, c, inter, ["pergunta_preco"])
        assert [n["metadata"]["tipo"] for n in w.notifications()] == ["julia_cobranca_atendimento"]
        assert [e["tipo"] for e in w.rows("julia_eventos")] == ["cobranca_atendimento"]

    def test_fechar_interacao_emits_cobranca_via_hook(self):
        w, c = _mundo()
        inter = contatos.abrir_interacao(w.sw, ORG_ID, c)

        class Agents:
            async def resumo(self, conversation_id, req):
                return ResumoResult(resumo="r", slots={}, intencoes=("cobranca",), desfecho=None, custo_usd=0.0, operacao=None)

        svc.registrar()
        with _core_injetado(w):
            asyncio.run(acoes.fechar_interacao(w.sw, org_id=ORG_ID, contato=c, interacao=inter, agents_client=Agents(), conversation_id="conv"))
        assert [n["metadata"]["tipo"] for n in w.notifications()] == ["julia_cobranca_atendimento"]


# ── routes ──────────────────────────────────────────────────────────────────
class Scene:
    def __init__(self, tc, world):
        self.tc, self.w = tc, world

    def get(self, url, **kw):
        return self.tc.get(url, headers=H, **kw)

    def put(self, url, json, **kw):
        return self.tc.put(url, json=json, headers=H, **kw)

    def post(self, url, json=None, **kw):
        return self.tc.post(url, json=json if json is not None else {}, headers=H, **kw)


def _notif(user, tipo="julia_novo_lead", *, org=ORG_ID, read=False, created="2026-10-14T10:00:00+00:00", operacao=None):
    return {"id": str(uuid4()), "user_id": user, "org_id": org, "type": "system", "title": "t", "message": "m",
            "metadata": {"tipo": tipo, "operacao": operacao}, "read": read, "created_at": created}


@pytest.fixture
def scene():
    w, _ = _mundo()
    w.core.set_table_data("noctus_users", [*w.core.table("noctus_users").select("*").execute().data,
                                           {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "corretor"}])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role="corretor")))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app

        bind_consent_module_to_mock(w.root)
        yield Scene(TestClient(app), w)


class TestRotas:
    def test_unauthenticated_is_strict_401(self):
        from app.main import app

        tc = TestClient(app)
        assert tc.get(BASE).status_code == 401
        assert tc.post(f"{BASE}/lidas", json={"todas": True}).status_code == 401
        assert tc.get(f"{BASE}/preferencias").status_code == 401
        assert tc.put(f"{BASE}/preferencias", json={"tipos": {}}).status_code == 401

    def test_member_sees_only_own_and_org_isolation(self, scene):
        w = scene.w
        w.core.set_table_data("notifications", [
            _notif(TEST_USER_ID), _notif(OWNER_ID), _notif(TEST_USER_ID, org=OTHER_ORG_ID),
            {**_notif(TEST_USER_ID), "metadata": {"tipo": "team_invite"}},  # not a Julia kind
        ])
        d = scene.get(BASE).json()["data"]
        assert d["total"] == 1 and d["nao_lidas"] == 1 and len(d["items"]) == 1
        assert d["items"][0]["tipo"] == "novo_lead"

    def test_filters_and_pagination(self, scene):
        scene.w.core.set_table_data("notifications", [
            _notif(TEST_USER_ID, "julia_captacao", operacao="compra", created="2026-10-10T10:00:00+00:00"),
            _notif(TEST_USER_ID, "julia_novo_lead", operacao="aluguel", created="2026-10-12T10:00:00+00:00"),
            _notif(TEST_USER_ID, "julia_novo_lead", operacao="compra", created="2026-10-14T10:00:00+00:00"),
        ])
        g = lambda q: scene.get(f"{BASE}?{q}").json()["data"]
        assert [i["tipo"] for i in g("tipo=novo_lead")["items"]] == ["novo_lead", "novo_lead"]
        assert g("operacao=compra")["total"] == 2
        assert g("de=2026-10-11&ate=2026-10-13")["total"] == 1
        p = g("page=2&page_size=2")
        assert p["total"] == 3 and len(p["items"]) == 1
        assert scene.get(f"{BASE}?tipo=bogus").status_code == 422
        assert scene.get(f"{BASE}?operacao=x").status_code == 422

    def test_mark_read_ids_and_all_only_own(self, scene):
        w = scene.w
        mine, mine2, other = _notif(TEST_USER_ID), _notif(TEST_USER_ID), _notif(OWNER_ID)
        w.core.set_table_data("notifications", [mine, mine2, other])
        r = scene.post(f"{BASE}/lidas", {"ids": [mine["id"], other["id"]]})
        assert r.status_code == 204 and r.content == b""
        lidas = {n["id"]: n["read"] for n in w.notifications()}
        assert lidas == {mine["id"]: True, mine2["id"]: False, other["id"]: False}
        assert scene.post(f"{BASE}/lidas", {"todas": True}).status_code == 204
        assert {n["id"]: n["read"] for n in w.notifications()} == {mine["id"]: True, mine2["id"]: True, other["id"]: False}
        assert scene.post(f"{BASE}/lidas", {}).status_code == 422
        assert scene.post(f"{BASE}/lidas", {"todas": True, "x": 1}).status_code == 422

    def test_preferences_roundtrip_and_validation(self, scene):
        d = scene.get(f"{BASE}/preferencias").json()["data"]
        assert d["lead_pronto"] is True and len(d["tipos"]) == 12 and all(t["in_app"] for t in d["tipos"])
        d = scene.put(f"{BASE}/preferencias", {"tipos": {"novo_lead": False, "lead_pronto": False}}).json()["data"]
        assert d["lead_pronto"] is False and {t["tipo"]: t["in_app"] for t in d["tipos"]}["novo_lead"] is False
        assert scene.put(f"{BASE}/preferencias", {"tipos": {"bogus": True}}).status_code == 422
        assert scene.put(f"{BASE}/preferencias", {"tipos": {}, "extra": 1}).status_code == 422
