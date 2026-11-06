"""`julia_agente_service` -- the policy shared by the webhook, the worker and the routes.

Contract: 11.1 (eligibility; the snapshot was removed 2026-11-05), 10.1 H3 (switch invariants), M4 (limiter), L3 (own echo),
11.3 (disclosure/link), 11.4 (handoff target), the org's `api_key:agents` token.
"""
from __future__ import annotations

import pytest
from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_agente_service as julia

from tests.support.julia_world import (
    ADMIN_ID,
    ATIVADO_EM,
    CONNECTION_ID,
    CORRETOR_ID,
    LEAD_CHAT,
    MEMBER_ID,
    ORG_ID,
    OTHER_ORG_ID,
    OWNER_ID,
    World,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    return w


# ── eligibility: "answer anyone who writes AFTER go-live" (owner 2026-11-05) ─────────────────────────────
DEPOIS = "2026-10-10T12:00:00+00:00"
ANTES = "2026-09-30T23:59:59+00:00"


class TestEligibility:
    def _ask(self, world, *, state=None, quando=DEPOIS, avaliacao=False):
        return julia.avaliar_elegibilidade(
            connection=world.record(CONNECTION_ID), chat_state=state, mensagem_em=quando, avaliacao=avaliacao)

    async def test_a_brand_new_chat_writing_after_go_live_is_eligible(self, world):
        r = self._ask(world)
        assert (r.elegivel, r.motivo) == (True, "new")

    async def test_a_chat_that_existed_before_go_live_is_answered_when_it_writes_after(self, world):
        r = self._ask(world, state={"agente_conversation_id": None, "created_at": "2026-09-01T00:00:00+00:00"})
        assert (r.elegivel, r.motivo) == (True, "new")

    async def test_a_chat_listed_in_the_old_snapshot_table_is_still_answered(self, world):
        # nothing reads the dead snapshot table any more (NOC-REMEDIATE[drop-julia-snapshot])
        world.sw.table("julia_agente_chats_preexistentes").insert(
            {"org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT, "capturado_em": ATIVADO_EM}).execute()
        assert self._ask(world).elegivel is True

    async def test_a_message_stamped_before_go_live_is_never_answered(self, world):
        r = self._ask(world, quando=ANTES)
        assert (r.elegivel, r.motivo) == (False, "mensagem_anterior")

    async def test_the_cut_off_also_binds_a_chat_Julia_already_owns(self, world):
        r = self._ask(world, quando=ANTES, state={"agente_conversation_id": "11111111-1111-4111-8111-111111111111"})
        assert (r.elegivel, r.motivo) == (False, "mensagem_anterior")

    @pytest.mark.parametrize("quando", [None, "lixo"])
    async def test_an_unreadable_message_time_fails_closed(self, world, quando):
        r = self._ask(world, quando=quando)
        assert (r.elegivel, r.motivo) == (False, "mensagem_sem_horario")

    async def test_a_chat_Julia_already_owns_stays_eligible(self, world):
        r = self._ask(world, state={"agente_conversation_id": "11111111-1111-4111-8111-111111111111"})
        assert (r.elegivel, r.motivo) == (True, "owned")

    async def test_no_ativado_em_fails_closed(self, world):
        world.sw.set_table_data("whatsapp_connections", [])
        world._connections = []
        world.seed_connection(agente_leads_ativado_em=None)
        r = self._ask(world)
        assert (r.elegivel, r.motivo) == (False, "sem_ativado_em")

    async def test_a_staff_chat_is_refused(self, world):
        r = self._ask(world, state={"categoria": "equipe"})
        assert (r.elegivel, r.motivo) == (False, "equipe")

    async def test_an_evaluation_listed_staff_chat_is_eligible_but_only_past_the_equipe_rule(self, world):
        r = self._ask(world, state={"categoria": "equipe"}, avaliacao=True)
        assert (r.elegivel, r.motivo) == (True, "avaliacao")
        assert self._ask(world, state={"categoria": "equipe"}, avaliacao=True, quando=ANTES).motivo == "mensagem_anterior"
        sem = julia.avaliar_elegibilidade(connection=_sem_ativado(), chat_state=None, mensagem_em=DEPOIS, avaliacao=True)
        assert (sem.elegivel, sem.motivo) == (False, "sem_ativado_em")


def _sem_ativado():
    from types import SimpleNamespace

    return SimpleNamespace(id=CONNECTION_ID, agente_leads_ativado_em=None)


# ── H3 / H1 / 11.3 switch preconditions ─────────────────────────────────────
class TestSwitchPreconditions:
    @pytest.mark.parametrize("secret", ["", "   ", None])
    def test_no_hmac_secret_is_a_409(self, world, secret):
        cfg = world.cfg.model_copy(update={"waha_webhook_hmac_secret": secret or ""})
        with pytest.raises(AppException) as ei:
            julia.exigir_hmac_configurado(cfg)
        assert (ei.value.status_code, ei.value.code) == (409, "webhook_hmac_required")

    def test_a_hmac_secret_passes(self, world):
        julia.exigir_hmac_configurado(world.cfg.model_copy(update={"waha_webhook_hmac_secret": "s3cret"}))

    def test_an_aviso_without_empresa_nome_is_aviso_incompleto(self):
        with pytest.raises(AppException) as ei:
            julia.exigir_aviso_completo({"empresa_nome": None, "mensagem_inicial": "Oi {link}", "slug": "x"})
        assert (ei.value.status_code, ei.value.code) == (409, "aviso_incompleto")

    def test_an_aviso_without_the_link_placeholder_is_incomplete(self):
        with pytest.raises(AppException):
            julia.exigir_aviso_completo({"empresa_nome": "X", "mensagem_inicial": "Oi", "slug": "x"})

    def test_a_complete_aviso_passes(self):
        julia.exigir_aviso_completo({"empresa_nome": "X", "mensagem_inicial": "Oi {link}", "slug": "x"})

    def test_the_public_link_is_built_from_the_product_url_resolver(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test/")
        assert julia.public_privacy_link({"slug": "one-consultoria"}) == "https://sw.example.test/privacidade/one-consultoria"

    def test_an_unresolvable_public_url_is_a_409_never_a_made_up_domain(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SOCIAL_WIRING", raising=False)
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        with pytest.raises(AppException) as ei:
            julia.public_privacy_link({"slug": "x"})
        assert ei.value.code == "url_publica_indisponivel"

    def test_mensagem_inicial_pronta_fills_empresa_and_link(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")
        out = julia.mensagem_inicial_pronta({
            "empresa_nome": "One Consultoria", "slug": "one", "mensagem_inicial": "Oi! Sou a Julia da {empresa}. {link}"})
        assert out == "Oi! Sou a Julia da One Consultoria. https://sw.example.test/privacidade/one"


# ── 11.4 target validation ──────────────────────────────────────────────────
class TestHandoffTarget:
    def test_admin_and_owner_targets_are_valid(self, world):
        julia.exigir_destinatario_valido(world.core, ORG_ID, ADMIN_ID, dono_id=OWNER_ID)
        julia.exigir_destinatario_valido(world.core, ORG_ID, OWNER_ID, dono_id="someone-else")

    @pytest.mark.parametrize("uid", [MEMBER_ID, CORRETOR_ID])
    def test_member_corretor_and_any_other_role_is_422_destinatario_invalido(self, world, uid):
        with pytest.raises(AppException) as ei:
            julia.exigir_destinatario_valido(world.core, ORG_ID, uid, dono_id=OWNER_ID)
        assert (ei.value.status_code, ei.value.code) == (422, "destinatario_invalido")

    @pytest.mark.parametrize("role", ["dev", "juridico", "viewer", None])
    def test_dev_juridico_and_unknown_roles_are_refused(self, world, role):
        world.core.table("noctus_users").update({"org_role": role}).eq("id", MEMBER_ID).execute()
        with pytest.raises(AppException):
            julia.exigir_destinatario_valido(world.core, ORG_ID, MEMBER_ID, dono_id=OWNER_ID)

    def test_an_admin_of_ANOTHER_org_is_refused(self, world):
        world.core.table("noctus_users").insert({"id": "00000000-0000-4000-8000-0000000000d1", "org_id": OTHER_ORG_ID, "org_role": "admin"}).execute()
        with pytest.raises(AppException):
            julia.exigir_destinatario_valido(world.core, ORG_ID, "00000000-0000-4000-8000-0000000000d1", dono_id=OWNER_ID)

    def test_a_user_who_left_the_org_is_refused(self, world):
        with pytest.raises(AppException):
            julia.exigir_destinatario_valido(world.core, ORG_ID, "00000000-0000-4000-8000-0000000000dd", dono_id=OWNER_ID)

    def test_the_connection_owner_is_always_allowed(self, world):
        world.core.table("noctus_users").update({"org_role": "member"}).eq("id", OWNER_ID).execute()
        julia.exigir_destinatario_valido(world.core, ORG_ID, OWNER_ID, dono_id=OWNER_ID)

    def test_a_lookup_failure_fails_closed(self):
        class Boom:
            def table(self, *_a):
                raise RuntimeError("db down")

        assert julia.usuario_e_admin_da_org(Boom(), ORG_ID, ADMIN_ID) is False

    def test_destinatario_do_handoff_default_is_the_owner(self, world):
        assert str(julia.destinatario_do_handoff(world.core, world.record(CONNECTION_ID))) == OWNER_ID


# ── M4 limiter / L3 own echo ────────────────────────────────────────────────
class TestLimiter:
    def test_allows_up_to_the_limit_then_refuses(self, world):
        clock = [1000.0]
        lim = julia.SlidingWindowLimiter(world.buffer.redis, clock=lambda: clock[0])
        assert [lim.allow("k", limit=3, window_s=60) for _ in range(4)] == [True, True, True, False]

    def test_the_window_slides(self, world):
        clock = [1000.0]
        lim = julia.SlidingWindowLimiter(world.buffer.redis, clock=lambda: clock[0])
        for _ in range(3):
            assert lim.allow("k", limit=3, window_s=60)
        clock[0] += 61
        assert lim.allow("k", limit=3, window_s=60)

    def test_keys_are_independent(self, world):
        lim = julia.SlidingWindowLimiter(world.buffer.redis)
        assert lim.allow("a", limit=1, window_s=60) and lim.allow("b", limit=1, window_s=60)
        assert not lim.allow("a", limit=1, window_s=60)

    def test_stale_entries_are_pruned_not_accumulated(self, world):
        clock = [1000.0]
        lim = julia.SlidingWindowLimiter(world.buffer.redis, clock=lambda: clock[0])
        for _ in range(5):
            lim.allow("k", limit=100, window_s=10)
            clock[0] += 11
        assert len(world.buffer.redis.zrangebyscore("k", "-inf", "+inf")) <= 2


class TestOwnEcho:
    @pytest.mark.parametrize("origem,eco", [("julia", True), ("interno", True), ("humano", False), ("lead", False), (None, False)])
    def test_only_what_sw_itself_produced_is_its_own_echo(self, origem, eco):
        assert julia.origem_e_eco_proprio(origem) is eco

    def test_with_no_send_in_flight_it_is_a_human(self, world):
        assert not julia.envio_em_curso(world.redis, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT)

    def test_an_echo_beating_our_bookkeeping_is_covered_by_the_in_flight_flag(self, world):
        julia.marcar_envio_em_curso(world.redis, CONNECTION_ID, LEAD_CHAT)
        assert julia.envio_em_curso(world.redis, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT)
        assert not julia.envio_em_curso(world.redis, connection_id=CONNECTION_ID, chat_id="other@c.us")

    def test_redis_is_optional_none_or_failing_reads_as_not_in_flight(self):
        class Down:
            def get(self, *_a):
                raise ConnectionError("down")

        assert julia.envio_em_curso(None, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT) is False
        assert julia.envio_em_curso(Down(), connection_id=CONNECTION_ID, chat_id=LEAD_CHAT) is False

    def test_the_flag_is_shortened_not_dropped_when_the_send_ends(self, world):
        julia.marcar_envio_em_curso(world.redis, CONNECTION_ID, LEAD_CHAT)
        julia.encerrar_envio(world.redis, CONNECTION_ID, LEAD_CHAT)
        assert 0 < world.redis.ttl(f"julia:julia_sending:{CONNECTION_ID}:{LEAD_CHAT}") <= 15


# ── keys, phones, motivo ────────────────────────────────────────────────────
class TestKeysAndText:
    def test_lead_key_round_trips(self):
        assert julia.parse_lead_key(julia.lead_key(CONNECTION_ID, "5511@c.us")) == (
            __import__("uuid").UUID(CONNECTION_ID), "5511@c.us")

    @pytest.mark.parametrize("key", ["5511@c.us", "lead:", "lead:not-a-uuid:x", f"lead:{CONNECTION_ID}:", f"lead:{CONNECTION_ID}"])
    def test_foreign_or_malformed_keys_do_not_parse(self, key):
        assert julia.parse_lead_key(key) is None

    @pytest.mark.parametrize("chat,expected", [
        ("5511988887777@c.us", "5511988887777"), ("5511988887777@s.whatsapp.net", "5511988887777"),
        ("123@lid", None), ("1203@g.us", None), ("abc@c.us", None),
    ])
    def test_phone_digits(self, chat, expected):
        assert julia.phone_digits(chat) == expected

    def test_group_and_lid_detection(self):
        assert julia.is_group_chat("1203@g.us") and not julia.is_group_chat("5511@c.us") and not julia.is_group_chat(None)
        assert julia.is_lid("1@lid") and not julia.is_lid("1@c.us")

    def test_sanitize_motivo_caps_and_strips_control_characters(self):
        out = julia.sanitize_motivo("a\x00b\x1bc\n\n  d" + "x" * 400)
        assert "\x00" not in out and "\x1b" not in out and len(out) == 280 and out.startswith("abc d")
        assert julia.sanitize_motivo(None) == ""


def _store(world):
    from app.services import api_keys_store

    return api_keys_store.build_api_key_store(world.admin, encryption_key=world.cfg.encryption_key)


# ── the org's agents token ──────────────────────────────────────────────────
class TestAgentsToken:
    def test_reads_only_the_local_api_key_agents_row_of_THAT_org(self, world):
        from app.services import api_keys_store

        store = api_keys_store.build_api_key_store(world.admin, encryption_key=world.cfg.encryption_key)
        api_keys_store.put_api_key(store, ORG_ID, "agents", "pk_org_a")
        assert julia.agents_token_for_org(ORG_ID, store=store) == "pk_org_a"
        assert julia.agents_token_for_org(OTHER_ORG_ID, store=store) is None

    def test_agents_is_an_allowed_managed_key(self):
        from app.services import api_keys_store

        assert "agents" in api_keys_store.MANAGED_API_KEYS
        assert api_keys_store.provider_for("agents") == "api_key:agents"
        assert api_keys_store.get_spec("agents").is_secret is True

    def test_prod_without_a_token_resolves_no_client_never_a_fake(self, world, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.example.test")
        assert julia.resolve_agents_client(ORG_ID, cfg=world.cfg, store=_store(world)) is None

    def test_with_a_token_and_a_url_it_is_the_real_client(self, world, monkeypatch):
        from app.clients.agents import HttpAgentsClient
        from app.services import api_keys_store

        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.example.test")
        store = _store(world)
        api_keys_store.put_api_key(store, ORG_ID, "agents", "pk_org_a")
        from app.services.julia_grant_sink import HealthRecordingAgentsClient

        client = julia.resolve_agents_client(ORG_ID, cfg=world.cfg, store=store)
        # the real client, wrapped so every agents call records the connection health (S8)
        assert isinstance(client, HealthRecordingAgentsClient) and isinstance(client.inner, HttpAgentsClient)
        assert julia.resolve_agents_client(OTHER_ORG_ID, cfg=world.cfg, store=store) is None  # prod: org B has none

    def test_dev_without_a_token_resolves_the_fake(self, world, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        for k in [k for k in __import__("os").environ if k.startswith("PRODUCT_URL_")]:
            monkeypatch.delenv(k)
        from app.clients.agents import FakeAgentsClient

        assert isinstance(julia.resolve_agents_client(ORG_ID, cfg=world.cfg, store=_store(world)), FakeAgentsClient)
