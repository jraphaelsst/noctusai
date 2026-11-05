"""Owner 2026-11-05: (1) the line switch only goes ON when agents has Julia PUBLISHED and ON; (2) Julia's allowlist ("lista de
permitidos", migration 323): CRUD, the inbound enforcement and the eligibility bypass; (3) the inbound triage fails CLOSED when
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


# ── 2a. allowlist routes ─────────────────────────────────────────────────────
@pytest.fixture
def adm(override_settings_factory):
    yield from eq._scene("owner")


@pytest.fixture
def mem(override_settings_factory):
    yield from eq._scene("member")


def _eq_tables(scene):
    scene.w.sw.set_table_data("julia_permitidos", [])


class TestPermitidosRoutes:
    URLS = [("get", f"{PROT}/permitidos"), ("post", f"{PROT}/permitidos"),
            ("delete", f"{PROT}/permitidos/00000000-0000-4000-8000-000000000001")]

    @pytest.mark.parametrize("method,url", URLS)
    def test_no_session_is_strictly_401(self, adm, method, url):
        assert getattr(adm.tc, method)(url).status_code == 401

    @pytest.mark.parametrize("method,url", URLS)
    def test_a_member_is_403(self, mem, method, url):
        _eq_tables(mem)
        assert mem.req(method, url, {"numero": OWNER_PHONE} if method == "post" else None).status_code == 403

    def test_crud_and_normalisation(self, adm):
        _eq_tables(adm)
        assert adm.req("get", f"{PROT}/permitidos").json()["data"] == {"ativo": False, "items": []}
        r = adm.req("post", f"{PROT}/permitidos", {"numero": "+55 (11) 98888-7777", "rotulo": "  Meu   número "})
        assert r.status_code == 201
        item = r.json()["data"]
        assert item["numero"] == OWNER_PHONE and item["rotulo"] == "Meu número" and item["criado_em"] is not None
        assert set(item) == {"id", "numero", "rotulo", "criado_em"}
        for dup in ("11988887777", "551188887777", "5511988887777@c.us"):  # the same number typed another way
            r = adm.req("post", f"{PROT}/permitidos", {"numero": dup})
            assert r.status_code == 409 and "numero_ja_permitido" in r.text, dup
        assert adm.req("post", f"{PROT}/permitidos", {"numero": "abc"}).status_code == 422
        assert "numero_invalido" in adm.req("post", f"{PROT}/permitidos", {"numero": "123456@lid"}).text
        assert adm.req("post", f"{PROT}/permitidos", {"numero": OWNER_PHONE, "inventado": 1}).status_code == 422
        assert len(adm.req("get", f"{PROT}/permitidos").json()["data"]["items"]) == 1
        assert adm.req("delete", f"{PROT}/permitidos/{item['id']}").json() == {"data": {"ok": True}}
        r = adm.req("delete", f"{PROT}/permitidos/{item['id']}")
        assert r.status_code == 404 and "permitido_nao_encontrado" in r.text
        assert adm.req("get", f"{PROT}/permitidos").json()["data"]["items"] == []

    def test_the_switch_lives_on_the_config(self, adm):
        _eq_tables(adm)
        assert adm.req("get", f"{PROT}/config").json()["data"]["permitidos_ativo"] is False
        r = adm.req("put", f"{PROT}/config", {"permitidos_ativo": True})
        assert r.status_code == 200 and r.json()["data"]["permitidos_ativo"] is True
        assert adm.req("get", f"{PROT}/permitidos").json()["data"]["ativo"] is True
        assert adm.req("put", f"{PROT}/config", {"permitidos_ativo": False}).json()["data"]["permitidos_ativo"] is False

    def test_another_orgs_entry_is_not_visible_or_deletable(self, adm):
        _eq_tables(adm)
        adm.w.sw.table("julia_permitidos").insert(
            {"id": "00000000-0000-4000-8000-00000000000a", "org_id": "00000000-0000-4000-8000-0000000000ff", "numero": OWNER_PHONE}).execute()
        assert adm.req("get", f"{PROT}/permitidos").json()["data"]["items"] == []
        assert adm.req("delete", f"{PROT}/permitidos/00000000-0000-4000-8000-00000000000a").status_code == 404


class TestChave:
    @pytest.mark.parametrize("entrada", ["11988887777", "+5511988887777", "551188887777", "5511988887777@s.whatsapp.net", "(11) 98888-7777"])
    def test_one_br_mobile_has_one_key(self, entrada):
        assert prot.chave_permitido(entrada) == OWNER_PHONE

    def test_landline_is_left_alone_and_non_phones_have_no_key(self):
        assert prot.chave_permitido("551133334444") == "551133334444"
        assert prot.chave_permitido("123456@lid") is None and prot.chave_permitido("x@g.us") is None


# ── 2b. enforcement ──────────────────────────────────────────────────────────
class _Entrada:
    def __init__(self, mapa=None):
        self.mapa, self.chamadas = mapa or {}, []

    async def phone_do_lid(self, lid):
        self.chamadas.append(lid)
        return self.mapa.get(lid)


class _TabelaQuebrada:
    """A DB client whose reads of `tabela` raise (a real fault in an injected collaborator); everything else goes through."""

    def __init__(self, root, tabela):
        self._root, self._tabela = root, tabela

    def schema(self, name):
        return _TabelaQuebrada(self._root.schema(name), self._tabela)

    def table(self, name):
        if name == self._tabela:
            raise RuntimeError("db down")
        return self._root.table(name)

    def __getattr__(self, item):
        return getattr(self._root, item)


@pytest.fixture
def mundo():
    w = World()
    w.seed_connection()
    w.sw.set_table_data("julia_protecao_config", [])
    w.sw.set_table_data("julia_permitidos", [])
    return w


def _config(w, ativo):
    w.sw.set_table_data("julia_protecao_config", [{"org_id": ORG_ID, "permitidos_ativo": ativo}])


def _permitir(w, numero=OWNER_PHONE):
    n = len(w.sw.table("julia_permitidos").select("*").execute().data)
    w.sw.table("julia_permitidos").insert({"id": f"00000000-0000-4000-8000-{n:012d}", "org_id": ORG_ID, "numero": numero}).execute()


@pytest.mark.asyncio
class TestSituacao:
    async def _s(self, w, chat, entrada=None):
        entrada = entrada or _Entrada()
        return await prot.situacao_permitidos(w.sw, ORG_ID, chat_id=chat, sender=chat, resolver_alias=entrada.phone_do_lid)

    async def test_switch_off_nobody_is_filtered_even_with_a_list(self, mundo):
        _config(mundo, False)
        _permitir(mundo)
        assert await self._s(mundo, "5511900001111@c.us") == "livre"

    async def test_no_config_row_is_off(self, mundo):
        _permitir(mundo)
        assert await self._s(mundo, "5511900001111@c.us") == "livre"

    async def test_on_with_an_empty_list_answers_everyone(self, mundo):
        _config(mundo, True)
        assert await self._s(mundo, "5511900001111@c.us") == "livre"

    async def test_on_with_a_list_outsider_is_fora_member_is_permitido(self, mundo):
        _config(mundo, True)
        _permitir(mundo)
        assert await self._s(mundo, "5511900001111@c.us") == "fora"
        assert await self._s(mundo, f"{OWNER_PHONE}@c.us") == "permitido"
        assert await self._s(mundo, f"{OWNER_PHONE}@s.whatsapp.net") == "permitido"
        assert await self._s(mundo, "551188887777@c.us") == "permitido"  # without the 9th digit

    async def test_a_lid_is_resolved_to_its_phone(self, mundo):
        _config(mundo, True)
        _permitir(mundo)
        ent = _Entrada({"123456@lid": f"{OWNER_PHONE}@c.us"})
        assert await self._s(mundo, "123456@lid", ent) == "permitido"
        assert ent.chamadas == ["123456@lid"]
        assert await self._s(mundo, "999@lid", ent) == "fora"  # unresolved => outsider

    async def test_a_read_failure_raises_so_the_caller_fails_closed(self, mundo):
        _config(mundo, True)
        with pytest.raises(RuntimeError):
            await prot.situacao_permitidos(_TabelaQuebrada(mundo.sw, prot.T_PERMITIDOS), ORG_ID,
                                           chat_id="5511900001111@c.us", sender="5511900001111@c.us")


@pytest.mark.asyncio
class TestElegibilidade:
    async def _ask(self, w, chat, **kw):
        row = w.chat_row(chat)
        state = {"agente_conversation_id": None, "created_at": row["created_at"]} if row else None
        return await julia.avaliar_elegibilidade(client=w.sw, connection=w.record(CONNECTION_ID), chat_id=chat, chat_state=state, **kw)

    async def test_without_the_flag_a_snapshot_chat_is_refused(self, mundo):
        julia.gravar_snapshot(mundo.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[LEAD_CHAT])
        mundo.seed_chat(created_at="2026-10-14T00:00:00+00:00")
        assert (await self._ask(mundo, LEAD_CHAT)).motivo == "snapshot"

    async def test_permitido_bypasses_snapshot_and_chat_anterior(self, mundo):
        julia.gravar_snapshot(mundo.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[LEAD_CHAT])
        mundo.seed_chat(created_at="2026-10-14T00:00:00+00:00")
        r = await self._ask(mundo, LEAD_CHAT, permitido=True)
        assert (r.elegivel, r.motivo) == (True, "permitido")

    async def test_a_chat_marked_staff_is_julias_when_listed(self, mundo):
        # Owner 2026-11-05: the owner's own number is an org member's, so its chat was staff before it was listed.
        r = await julia.avaliar_elegibilidade(
            client=mundo.sw, connection=mundo.record(CONNECTION_ID), chat_id=LEAD_CHAT, chat_state={"categoria": "equipe"}, permitido=True)
        assert (r.elegivel, r.motivo) == (True, "permitido")

    async def test_a_chat_marked_staff_is_refused_when_not_listed(self, mundo):
        r = await julia.avaliar_elegibilidade(
            client=mundo.sw, connection=mundo.record(CONNECTION_ID), chat_id=LEAD_CHAT, chat_state={"categoria": "equipe"})
        assert (r.elegivel, r.motivo) == (False, "equipe")

    async def test_permitido_does_not_waive_a_missing_ativado_em(self, mundo):
        from types import SimpleNamespace

        sem_ativado = SimpleNamespace(id=CONNECTION_ID, agente_leads_ativado_em=None)
        r = await julia.avaliar_elegibilidade(
            client=mundo.sw, connection=sem_ativado, chat_id=LEAD_CHAT, chat_state=None, permitido=True)
        assert (r.elegivel, r.motivo) == (False, "sem_ativado_em")


def _db(w, admin=None):
    return (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=admin or w.admin),
    )


@pytest.mark.asyncio
class TestLeadHandler:
    """`_handle_lead_message` end to end: True = Julia's, False = unchanged behaviour."""

    async def _run(self, w, chat, entrada=None, admin=None):
        p1, p2, p3 = _db(w, admin)
        with p1, p2, p3:
            return await whatsapp_router._handle_lead_message(
                connection=w.record(CONNECTION_ID), entrada=entrada or _Entrada(), chat_id=chat, sender=chat, message_body="oi",
                provider_message_id="m1", push_name="X", cfg=w.cfg,
            )

    async def test_switch_off_is_unchanged(self, mundo):
        _config(mundo, False)
        _permitir(mundo)
        assert await self._run(mundo, "5511900001111@c.us") is True

    async def test_on_and_empty_list_answers_everyone(self, mundo):
        _config(mundo, True)
        assert await self._run(mundo, "5511900001111@c.us") is True

    async def test_on_with_a_list_the_outsider_is_not_julias(self, mundo, caplog):
        _config(mundo, True)
        _permitir(mundo)
        with caplog.at_level("INFO"):
            assert await self._run(mundo, "5511900001111@c.us") is False
        assert "fora_da_lista_de_permitidos" in caplog.text

    async def test_a_listed_number_is_julias_even_when_in_the_snapshot_and_with_an_old_chat(self, mundo):
        _config(mundo, True)
        _permitir(mundo)
        chat = f"{OWNER_PHONE}@c.us"
        julia.gravar_snapshot(mundo.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[chat])
        mundo.seed_chat(chat, created_at="2026-10-14T00:00:00+00:00")
        assert await self._run(mundo, chat) is True

    async def test_the_same_snapshot_chat_is_refused_when_the_switch_is_off(self, mundo):
        _config(mundo, False)
        chat = f"{OWNER_PHONE}@c.us"
        julia.gravar_snapshot(mundo.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[chat])
        mundo.seed_chat(chat, created_at="2026-10-14T00:00:00+00:00")
        assert await self._run(mundo, chat) is False

    async def test_a_lid_chat_resolves_to_the_listed_phone(self, mundo):
        _config(mundo, True)
        _permitir(mundo)
        ent = _Entrada({"123456@lid": f"{OWNER_PHONE}@c.us"})
        assert await self._run(mundo, "123456@lid", ent) is True
        assert await self._run(mundo, "777@lid", ent) is False

    async def test_an_unreadable_list_fails_closed_and_logs_an_error(self, mundo, caplog):
        _config(mundo, True)
        quebrado = _TabelaQuebrada(mundo.admin, prot.T_PERMITIDOS)
        with caplog.at_level("ERROR"):
            assert await self._run(mundo, "5511900001111@c.us", admin=quebrado) is False
        assert "NOT eligible" in caplog.text


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


@pytest.mark.asyncio
class TestStaffOnTheAllowlist:
    """Owner 2026-11-05: a staff number listed on the allowlist (switch ON) is classified as a LEAD, so Julia answers it."""

    async def _classificar(self, w, chat):
        p1, p2, p3 = _db(w)
        with p1, p2, p3:
            return await whatsapp_router._classificar_remetente(w.record(CONNECTION_ID), entrada=_Entrada(), chat_id=chat, sender=chat)

    def _staff(self, w):
        w.sw.set_table_data("julia_staff", [{"id": "s1", "org_id": ORG_ID, "telefone": OWNER_PHONE, "ativo": True, "nome": "Dono", "papel": "outro"}])

    async def test_staff_not_listed_stays_staff(self, mundo):
        self._staff(mundo)
        _config(mundo, True)
        _permitir(mundo, "5511900001111")
        assert await self._classificar(mundo, f"{OWNER_PHONE}@c.us") is not None

    async def test_staff_listed_with_the_switch_on_is_a_lead(self, mundo):
        self._staff(mundo)
        _config(mundo, True)
        _permitir(mundo)
        assert await self._classificar(mundo, f"{OWNER_PHONE}@c.us") is None

    async def test_staff_listed_with_the_switch_off_stays_staff(self, mundo):
        self._staff(mundo)
        _config(mundo, False)
        _permitir(mundo)
        assert await self._classificar(mundo, f"{OWNER_PHONE}@c.us") is not None
