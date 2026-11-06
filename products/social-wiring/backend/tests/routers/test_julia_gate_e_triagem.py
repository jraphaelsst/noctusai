"""Owner 2026-11-05: (1) the line switch only goes ON when agents has Julia PUBLISHED and ON; (2) the SW allowlist (migration 323) is
gone -- its routes 404; (3) the inbound triage fails CLOSED when
Redis is down. Seams: the mock DB and `FakeAgentsClient` through the routes' own `Depends` factories; faults are injected as
failing collaborators (a DB client / a dead Redis URL), nothing of ours is patched."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.clients.agents import AgentNotFound, AgentsTimeout, AgentsTokenInvalid, AgentStatus
from app.routers import whatsapp_router
from app.services import julia_agente_service as julia
from app.services import julia_protecao_service as prot

from tests.routers.test_julia_agente_routes import (  # noqa: F401  (fixtures + helpers of the line-switch suite)
    BASE, ROT_URL, _off_connection, admin, member, override_settings_factory,
)
from tests.routers import test_julia_equipe_protecao as eq
from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, World

PROT = "/api/julia/protecao"
OWNER_PHONE = "5511988887777"


def _status(**over) -> AgentStatus:
    base = dict(agent_key="julia", nome="Julia", ativo=True, versao_ativa=3, provider="openai", model="m", llm_configurado=True,
                modo="ligado", aceita_novos_leads=True, threads_abertas=0, conteudo_completo=True, desligado_plataforma=False)
    base.update(over)
    return AgentStatus(**base)


# ── 1. the agents gate on the per-line switch ────────────────────────────────
class TestGate:
    def _on(self, scene):
        _off_connection(scene.w)
        return scene.put(ROT_URL, {"alimenta": True})

    def _assert_refused(self, scene, r, status, code):
        assert r.status_code == status and code in r.text
        assert scene.conn()["agente_leads_ativo"] is False
        assert scene.snapshot_ids() == set()  # refused BEFORE the snapshot work

    def test_not_published_is_409_julia_nao_publicada(self, admin):
        admin.w.agents._status = _status(versao_ativa=None)
        self._assert_refused(admin, self._on(admin), 409, "julia_nao_publicada")

    @pytest.mark.parametrize("modo", ["drenando", "desligado", None])
    def test_not_ligada_is_409_julia_desligada_no_agents(self, admin, modo):
        admin.w.agents._status = _status(modo=modo)
        self._assert_refused(admin, self._on(admin), 409, "julia_desligada_no_agents")

    def test_platform_kill_is_409_julia_desligada_no_agents(self, admin):
        admin.w.agents._status = _status(desligado_plataforma=True)
        self._assert_refused(admin, self._on(admin), 409, "julia_desligada_no_agents")

    @pytest.mark.parametrize("erro", [AgentsTimeout("t"), AgentsTokenInvalid("x")])
    def test_status_unreadable_fails_closed_503(self, admin, erro):
        admin.w.agents._status_error = erro
        self._assert_refused(admin, self._on(admin), 503, "agents_indisponivel")

    def test_agent_unknown_to_agents_is_nao_publicada(self, admin):
        admin.w.agents._status_error = AgentNotFound("x")
        self._assert_refused(admin, self._on(admin), 409, "julia_nao_publicada")

    def test_no_client_or_token_fails_closed_503(self, admin):
        from app.main import app
        from app.routers.julia_agente_router import get_agents_client_factory

        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: None)
        self._assert_refused(admin, self._on(admin), 503, "agents_indisponivel")

    def test_published_and_ligada_turns_on(self, admin):
        admin.w.agents._status = _status()
        r = self._on(admin)
        assert r.status_code == 200 and admin.conn()["agente_leads_ativo"] is True
        assert admin.w.agents.status_calls == ["julia"]

    def test_turning_off_always_works_with_no_check(self, admin):
        admin.w.agents._status_error = AgentsTimeout("down")
        admin.w.seed_connection()  # ON
        r = admin.put(ROT_URL, {"alimenta": False})
        assert r.status_code == 200 and admin.conn()["agente_leads_ativo"] is False
        assert admin.w.agents.status_calls == []

    def test_already_on_key_or_handoff_change_is_not_gated(self, admin):
        admin.w.agents._status_error = AgentsTimeout("down")
        admin.w.seed_connection()
        assert admin.put(ROT_URL, {"alimenta": True}).status_code == 200
        assert admin.w.agents.status_calls == []

    def test_get_agente_exposes_pode_ligar_and_motivo(self, admin):
        admin.w.agents._status = _status()
        d = admin.get(BASE).json()["data"]
        assert d["pode_ligar"] is True and d["motivo_bloqueio"] is None
        admin.w.agents._status = _status(versao_ativa=None)
        d = admin.get(BASE).json()["data"]
        assert d["pode_ligar"] is False and d["motivo_bloqueio"] == "julia_nao_publicada"
        admin.w.agents._status = _status(modo="desligado")
        assert admin.get(BASE).json()["data"]["motivo_bloqueio"] == "julia_desligada_no_agents"
        admin.w.agents._status, admin.w.agents._status_error = None, AgentsTimeout("t")
        d = admin.get(BASE).json()["data"]
        assert d["pode_ligar"] is False and d["motivo_bloqueio"] == "agents_indisponivel"


# ── 2. the SW allowlist is GONE (owner 2026-11-05: testing = agents' evaluation mode only) ────────────────
@pytest.fixture
def adm(override_settings_factory):
    yield from eq._scene("owner")


class TestAllowlistIsGone:
    URLS = [("get", f"{PROT}/permitidos"), ("post", f"{PROT}/permitidos"),
            ("delete", f"{PROT}/permitidos/00000000-0000-4000-8000-000000000001")]

    @pytest.mark.parametrize("method,url", URLS)
    def test_the_routes_are_404_for_an_admin(self, adm, method, url):
        assert adm.req(method, url, {"numero": OWNER_PHONE} if method == "post" else None).status_code == 404

    def test_the_config_no_longer_carries_or_accepts_the_switch(self, adm):
        assert "permitidos_ativo" not in adm.req("get", f"{PROT}/config").json()["data"]
        assert adm.req("put", f"{PROT}/config", {"permitidos_ativo": True}).status_code == 422

    def test_no_allowlist_api_is_left_in_the_service(self):
        for nome in ("situacao_permitidos", "listar_permitidos", "adicionar_permitido", "remover_permitido", "chave_permitido", "T_PERMITIDOS"):
            assert not hasattr(prot, nome), nome


@pytest.fixture
def mundo():
    w = World()
    w.seed_connection()
    w.sw.set_table_data("julia_protecao_config", [])
    return w


def _db(w):
    return (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    )


# ── triage with Redis down: the rate limit must FAIL CLOSED (estado `erro`), never `livre` ──────────────────────
class _RedisCaido:
    def __getattr__(self, nome):
        def _falha(*a, **kw):
            raise ConnectionError("redis down")
        return _falha


class TestTriagemSemRedis:
    def test_a_dead_redis_is_erro_not_livre_and_logs_an_error(self, mundo, caplog):
        with caplog.at_level("ERROR"):
            t = prot.triar_entrada(mundo.sw, _RedisCaido(), mundo.core, mundo.record(CONNECTION_ID),
                                   chat_id="5511900001111@c.us", sender="5511900001111@c.us")
        assert t.estado == "erro" and t.bloqueia_ia is True
        assert "inbound triage failed" in caplog.text

    @pytest.mark.asyncio
    async def test_triar_lead_does_not_swallow_a_dead_redis_into_livre(self, mundo):
        cfg = mundo.cfg.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"})  # nothing listens: a real dead Redis
        p1, p2, p3 = _db(mundo)
        with p1, p2, p3:
            t = await whatsapp_router._triar_lead(mundo.record(CONNECTION_ID), chat_id="5511900001111@c.us",
                                                  sender="5511900001111@c.us", cfg=cfg)
        assert t.estado == "erro" and t.bloqueia_ia is True
