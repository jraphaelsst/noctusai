"""`lais_agente_service` -- the policy shared by the webhook, the worker and the routes.

Contract: 11.1 (snapshot + eligibility), 10.1 H3 (switch invariants), M4 (limiter), L3 (own echo),
11.3 (disclosure/link), 11.4 (handoff target), the org's `api_key:agents` token.
"""
from __future__ import annotations

import pytest
from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_agente_service as lais

from tests.support.lais_world import (
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


def _chats(n: int, *, suffix: str = "@c.us", start: int = 0):
    return [{"id": {"_serialized": f"55119{i:08d}{suffix}"}, "name": f"c{i}"} for i in range(start, start + n)]


# ── 11.1 snapshot ───────────────────────────────────────────────────────────
class TestSnapshotListing:
    async def test_pages_to_the_END(self):
        waha = FakeWahaClient()
        waha.fake_chat_list = _chats(250)
        ids = await lais.listar_todos_os_chats(waha, page_size=100)
        assert len(ids) == 250 and len(set(ids)) == 250

    async def test_an_exact_multiple_of_the_page_size_needs_the_empty_page_to_stop(self):
        waha = FakeWahaClient()
        waha.fake_chat_list = _chats(200)
        assert len(await lais.listar_todos_os_chats(waha, page_size=100)) == 200

    async def test_zero_chats_is_a_valid_complete_snapshot(self):
        assert await lais.listar_todos_os_chats(FakeWahaClient()) == []

    async def test_accepts_plain_string_ids_and_serialized_ids(self):
        waha = FakeWahaClient()
        waha.fake_chat_list = [{"id": "5511900000001@c.us"}, {"id": {"_serialized": "5511900000002@c.us"}}]
        assert await lais.listar_todos_os_chats(waha) == ["5511900000001@c.us", "5511900000002@c.us"]

    async def test_a_listing_error_fails_closed(self):
        class Down(FakeWahaClient):
            async def list_chats(self, limit=50, offset=0):
                raise RuntimeError("WAHA 422: session not WORKING")

        with pytest.raises(lais.SnapshotFalhou):
            await lais.listar_todos_os_chats(Down())

    async def test_an_error_on_a_LATER_page_fails_closed_never_a_partial_snapshot(self):
        class FlakyOnSecondPage(FakeWahaClient):
            async def list_chats(self, limit=50, offset=0):
                if offset >= limit:
                    raise TimeoutError("read timeout")
                return await super().list_chats(limit, offset)

        waha = FlakyOnSecondPage()
        waha.fake_chat_list = _chats(150)
        with pytest.raises(lais.SnapshotFalhou):
            await lais.listar_todos_os_chats(waha, page_size=100)

    async def test_a_chat_with_no_id_is_incomplete(self):
        waha = FakeWahaClient()
        waha.fake_chat_list = [{"id": "5511900000001@c.us"}, {"name": "ghost"}]
        with pytest.raises(lais.SnapshotFalhou):
            await lais.listar_todos_os_chats(waha)

    async def test_a_server_that_ignores_offset_is_detected_not_looped_forever(self):
        class IgnoresOffset(FakeWahaClient):
            async def list_chats(self, limit=50, offset=0):
                return self.fake_chat_list[:limit]

        waha = IgnoresOffset()
        waha.fake_chat_list = _chats(300)
        with pytest.raises(lais.SnapshotFalhou):
            await lais.listar_todos_os_chats(waha, page_size=100)

    async def test_running_out_of_pages_is_incomplete(self):
        waha = FakeWahaClient()
        waha.fake_chat_list = _chats(500)
        with pytest.raises(lais.SnapshotFalhou):
            await lais.listar_todos_os_chats(waha, page_size=100, max_pages=3)

    async def test_a_non_list_body_fails_closed(self):
        class Weird(FakeWahaClient):
            async def list_chats(self, limit=50, offset=0):
                return {"error": "x"}

        with pytest.raises(lais.SnapshotFalhou):
            await lais.listar_todos_os_chats(Weird())


class TestAliases:
    def test_phone_chat_gets_the_other_suffix_and_its_lid(self):
        out = lais.expandir_aliases(
            ["5511988887777@c.us"], [{"lid": "123@lid", "pn": "5511988887777@c.us"}]
        )
        assert set(out) == {"5511988887777@c.us", "5511988887777@s.whatsapp.net", "123@lid"}

    def test_lid_chat_gets_its_phone_forms(self):
        out = lais.expandir_aliases(["123@lid"], [{"lid": "123@lid", "pn": "5511988887777@c.us"}])
        assert {"123@lid", "5511988887777@c.us", "5511988887777@s.whatsapp.net"} <= set(out)

    def test_no_lid_map_keeps_only_the_phone_forms(self):
        assert set(lais.expandir_aliases(["5511988887777@c.us"], [])) == {
            "5511988887777@c.us", "5511988887777@s.whatsapp.net"}

    def test_groups_and_unmapped_lids_are_kept_verbatim(self):
        assert lais.expandir_aliases(["120363@g.us", "999@lid"], []) == ["120363@g.us", "999@lid"]

    def test_order_preserving_and_deduplicated(self):
        out = lais.expandir_aliases(["a@c.us", "a@c.us"], [])
        assert len(out) == len(set(out))

    async def test_the_snapshot_stores_every_form_once_and_is_insert_only(self, world):
        ids = lais.expandir_aliases(["5511988887777@c.us"], [{"lid": "123@lid", "pn": "5511988887777@c.us"}])
        n1 = lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=ids)
        n2 = lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=ids)
        assert (n1, n2) == (3, 0)
        rows = world.sw.table("lais_agente_chats_preexistentes").select("*").execute().data
        assert {r["chat_id"] for r in rows} == set(ids)
        assert all(r["org_id"] == ORG_ID and r["connection_id"] == CONNECTION_ID for r in rows)

    async def test_a_big_snapshot_is_inserted_in_batches(self, world):
        ids = [f"55119{i:08d}@c.us" for i in range(1203)]
        assert lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=ids) == 1203


# ── 11.1 eligibility ────────────────────────────────────────────────────────
class TestEligibility:
    async def _ask(self, world, chat_id=LEAD_CHAT, *, state="auto", resolver=None):
        conn = world.record(CONNECTION_ID)
        if state == "auto":
            row = world.chat_row(chat_id)
            state = {"agente_conversation_id": row.get("agente_conversation_id"), "created_at": row["created_at"]} if row else None
        return await lais.avaliar_elegibilidade(
            client=world.sw, connection=conn, chat_id=chat_id, chat_state=state, resolver_alias=resolver)

    async def test_a_brand_new_chat_is_eligible(self, world):
        r = await self._ask(world, "5511900001111@c.us", state=None)
        assert (r.elegivel, r.motivo) == (True, "new")

    async def test_a_chat_in_the_snapshot_is_not(self, world):
        lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[LEAD_CHAT])
        world.seed_chat(created_at="2026-10-14T00:00:00+00:00")
        r = await self._ask(world)
        assert (r.elegivel, r.motivo) == (False, "snapshot")

    async def test_the_other_phone_suffix_of_a_snapshotted_chat_is_not(self, world):
        lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=["5511988887777@s.whatsapp.net"])
        r = await self._ask(world, "5511988887777@c.us", state=None)
        assert r.elegivel is False and r.motivo == "snapshot"

    async def test_a_lid_alias_of_a_snapshotted_phone_chat_is_not(self, world):
        lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=["5511988887777@c.us"])

        async def resolver(lid):
            return "5511988887777"

        r = await self._ask(world, "123@lid", state=None, resolver=resolver)
        assert (r.elegivel, r.motivo) == (False, "snapshot")

    async def test_a_lid_whose_phone_is_unknown_and_not_snapshotted_is_eligible(self, world):
        async def resolver(lid):
            return None

        assert (await self._ask(world, "777@lid", state=None, resolver=resolver)).elegivel is True

    async def test_a_chat_row_older_than_ativado_em_is_not_even_if_the_snapshot_missed_it(self, world):
        world.seed_chat(created_at="2026-09-01T00:00:00+00:00")
        assert ATIVADO_EM > "2026-09-01"
        r = await self._ask(world)
        assert (r.elegivel, r.motivo) == (False, "chat_anterior")

    async def test_a_chat_row_newer_than_ativado_em_is_eligible(self, world):
        world.seed_chat(created_at="2026-10-10T00:00:00+00:00")
        assert (await self._ask(world)).elegivel is True

    async def test_a_chat_Julia_already_owns_stays_eligible_even_if_it_is_in_the_snapshot(self, world):
        lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_ids=[LEAD_CHAT])
        world.seed_chat(created_at="2026-09-01T00:00:00+00:00", agente_conversation_id="11111111-1111-4111-8111-111111111111")
        r = await self._ask(world)
        assert (r.elegivel, r.motivo) == (True, "owned")

    async def test_no_ativado_em_fails_closed(self, world):
        world.sw.set_table_data("whatsapp_connections", [])
        world._connections = []
        world.seed_connection(agente_leads_ativado_em=None)
        r = await self._ask(world, "5511900001111@c.us", state=None)
        assert (r.elegivel, r.motivo) == (False, "sem_ativado_em")

    async def test_the_snapshot_is_per_connection(self, world):
        lais.gravar_snapshot(world.sw, org_id=ORG_ID, connection_id="00000000-0000-4000-8000-0000000000ff", chat_ids=["5511900001111@c.us"])
        assert (await self._ask(world, "5511900001111@c.us", state=None)).elegivel is True


# ── H3 / H1 / 11.3 switch preconditions ─────────────────────────────────────
class TestSwitchPreconditions:
    @pytest.mark.parametrize("numbers", [[], None, ["", "  "]])
    def test_empty_authorized_numbers_is_a_409(self, numbers):
        with pytest.raises(AppException) as ei:
            lais.exigir_autorizados(numbers)
        assert (ei.value.status_code, ei.value.code) == (409, "authorized_numbers_required")

    def test_a_listed_number_passes(self):
        lais.exigir_autorizados(["+5511999990000"])
        lais.exigir_autorizados(["123@lid"])  # operators may list raw @lid ids

    @pytest.mark.parametrize("secret", ["", "   ", None])
    def test_no_hmac_secret_is_a_409(self, world, secret):
        cfg = world.cfg.model_copy(update={"waha_webhook_hmac_secret": secret or ""})
        with pytest.raises(AppException) as ei:
            lais.exigir_hmac_configurado(cfg)
        assert (ei.value.status_code, ei.value.code) == (409, "webhook_hmac_required")

    def test_a_hmac_secret_passes(self, world):
        lais.exigir_hmac_configurado(world.cfg.model_copy(update={"waha_webhook_hmac_secret": "s3cret"}))

    def test_an_aviso_without_empresa_nome_is_aviso_incompleto(self):
        with pytest.raises(AppException) as ei:
            lais.exigir_aviso_completo({"empresa_nome": None, "mensagem_inicial": "Oi {link}", "slug": "x"})
        assert (ei.value.status_code, ei.value.code) == (409, "aviso_incompleto")

    def test_an_aviso_without_the_link_placeholder_is_incomplete(self):
        with pytest.raises(AppException):
            lais.exigir_aviso_completo({"empresa_nome": "X", "mensagem_inicial": "Oi", "slug": "x"})

    def test_a_complete_aviso_passes(self):
        lais.exigir_aviso_completo({"empresa_nome": "X", "mensagem_inicial": "Oi {link}", "slug": "x"})

    def test_the_public_link_is_built_from_the_product_url_resolver(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test/")
        assert lais.public_privacy_link({"slug": "one-consultoria"}) == "https://sw.example.test/privacidade/one-consultoria"

    def test_an_unresolvable_public_url_is_a_409_never_a_made_up_domain(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SOCIAL_WIRING", raising=False)
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        with pytest.raises(AppException) as ei:
            lais.public_privacy_link({"slug": "x"})
        assert ei.value.code == "url_publica_indisponivel"

    def test_mensagem_inicial_pronta_fills_empresa_and_link(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")
        out = lais.mensagem_inicial_pronta({
            "empresa_nome": "One Consultoria", "slug": "one", "mensagem_inicial": "Oi! Sou a Julia da {empresa}. {link}"})
        assert out == "Oi! Sou a Julia da One Consultoria. https://sw.example.test/privacidade/one"


# ── 11.4 target validation ──────────────────────────────────────────────────
class TestHandoffTarget:
    def test_admin_and_owner_targets_are_valid(self, world):
        lais.exigir_destinatario_valido(world.core, ORG_ID, ADMIN_ID, dono_id=OWNER_ID)
        lais.exigir_destinatario_valido(world.core, ORG_ID, OWNER_ID, dono_id="someone-else")

    @pytest.mark.parametrize("uid", [MEMBER_ID, CORRETOR_ID])
    def test_member_corretor_and_any_other_role_is_422_destinatario_invalido(self, world, uid):
        with pytest.raises(AppException) as ei:
            lais.exigir_destinatario_valido(world.core, ORG_ID, uid, dono_id=OWNER_ID)
        assert (ei.value.status_code, ei.value.code) == (422, "destinatario_invalido")

    @pytest.mark.parametrize("role", ["dev", "juridico", "viewer", None])
    def test_dev_juridico_and_unknown_roles_are_refused(self, world, role):
        world.core.table("noctus_users").update({"org_role": role}).eq("id", MEMBER_ID).execute()
        with pytest.raises(AppException):
            lais.exigir_destinatario_valido(world.core, ORG_ID, MEMBER_ID, dono_id=OWNER_ID)

    def test_an_admin_of_ANOTHER_org_is_refused(self, world):
        world.core.table("noctus_users").insert({"id": "00000000-0000-4000-8000-0000000000d1", "org_id": OTHER_ORG_ID, "org_role": "admin"}).execute()
        with pytest.raises(AppException):
            lais.exigir_destinatario_valido(world.core, ORG_ID, "00000000-0000-4000-8000-0000000000d1", dono_id=OWNER_ID)

    def test_a_user_who_left_the_org_is_refused(self, world):
        with pytest.raises(AppException):
            lais.exigir_destinatario_valido(world.core, ORG_ID, "00000000-0000-4000-8000-0000000000dd", dono_id=OWNER_ID)

    def test_the_connection_owner_is_always_allowed(self, world):
        world.core.table("noctus_users").update({"org_role": "member"}).eq("id", OWNER_ID).execute()
        lais.exigir_destinatario_valido(world.core, ORG_ID, OWNER_ID, dono_id=OWNER_ID)

    def test_a_lookup_failure_fails_closed(self):
        class Boom:
            def table(self, *_a):
                raise RuntimeError("db down")

        assert lais.usuario_e_admin_da_org(Boom(), ORG_ID, ADMIN_ID) is False

    def test_destinatario_do_handoff_default_is_the_owner(self, world):
        assert str(lais.destinatario_do_handoff(world.core, world.record(CONNECTION_ID))) == OWNER_ID


# ── M4 limiter / L3 own echo ────────────────────────────────────────────────
class TestLimiter:
    def test_allows_up_to_the_limit_then_refuses(self, world):
        clock = [1000.0]
        lim = lais.SlidingWindowLimiter(world.buffer.redis, clock=lambda: clock[0])
        assert [lim.allow("k", limit=3, window_s=60) for _ in range(4)] == [True, True, True, False]

    def test_the_window_slides(self, world):
        clock = [1000.0]
        lim = lais.SlidingWindowLimiter(world.buffer.redis, clock=lambda: clock[0])
        for _ in range(3):
            assert lim.allow("k", limit=3, window_s=60)
        clock[0] += 61
        assert lim.allow("k", limit=3, window_s=60)

    def test_keys_are_independent(self, world):
        lim = lais.SlidingWindowLimiter(world.buffer.redis)
        assert lim.allow("a", limit=1, window_s=60) and lim.allow("b", limit=1, window_s=60)
        assert not lim.allow("a", limit=1, window_s=60)

    def test_stale_entries_are_pruned_not_accumulated(self, world):
        clock = [1000.0]
        lim = lais.SlidingWindowLimiter(world.buffer.redis, clock=lambda: clock[0])
        for _ in range(5):
            lim.allow("k", limit=100, window_s=10)
            clock[0] += 11
        assert len(world.buffer.redis.zrangebyscore("k", "-inf", "+inf")) <= 2


class TestOwnEcho:
    def test_a_registered_id_is_her_own(self, world):
        lais.registrar_envio_proprio(world.redis, "wamid.1")
        assert lais.eh_eco_proprio(world.redis, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, provider_message_id="wamid.1")

    def test_an_unknown_id_with_no_send_in_flight_is_a_human(self, world):
        assert not lais.eh_eco_proprio(world.redis, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, provider_message_id="wamid.9")

    def test_an_echo_beating_our_bookkeeping_is_covered_by_the_in_flight_flag(self, world):
        lais.marcar_envio_em_curso(world.redis, CONNECTION_ID, LEAD_CHAT)
        assert lais.eh_eco_proprio(world.redis, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, provider_message_id="not-yet-registered")
        assert not lais.eh_eco_proprio(world.redis, connection_id=CONNECTION_ID, chat_id="other@c.us", provider_message_id="x")

    def test_the_flag_is_shortened_not_dropped_when_the_send_ends(self, world):
        lais.marcar_envio_em_curso(world.redis, CONNECTION_ID, LEAD_CHAT)
        lais.encerrar_envio(world.redis, CONNECTION_ID, LEAD_CHAT)
        assert 0 < world.redis.ttl(f"lais:julia_sending:{CONNECTION_ID}:{LEAD_CHAT}") <= 15


# ── keys, phones, motivo ────────────────────────────────────────────────────
class TestKeysAndText:
    def test_lead_key_round_trips(self):
        assert lais.parse_lead_key(lais.lead_key(CONNECTION_ID, "5511@c.us")) == (
            __import__("uuid").UUID(CONNECTION_ID), "5511@c.us")

    @pytest.mark.parametrize("key", ["5511@c.us", "lead:", "lead:not-a-uuid:x", f"lead:{CONNECTION_ID}:", f"lead:{CONNECTION_ID}"])
    def test_foreign_or_malformed_keys_do_not_parse(self, key):
        assert lais.parse_lead_key(key) is None

    @pytest.mark.parametrize("chat,expected", [
        ("5511988887777@c.us", "5511988887777"), ("5511988887777@s.whatsapp.net", "5511988887777"),
        ("123@lid", None), ("1203@g.us", None), ("abc@c.us", None),
    ])
    def test_phone_digits(self, chat, expected):
        assert lais.phone_digits(chat) == expected

    def test_group_and_lid_detection(self):
        assert lais.is_group_chat("1203@g.us") and not lais.is_group_chat("5511@c.us") and not lais.is_group_chat(None)
        assert lais.is_lid("1@lid") and not lais.is_lid("1@c.us")

    def test_sanitize_motivo_caps_and_strips_control_characters(self):
        out = lais.sanitize_motivo("a\x00b\x1bc\n\n  d" + "x" * 400)
        assert "\x00" not in out and "\x1b" not in out and len(out) == 280 and out.startswith("abc d")
        assert lais.sanitize_motivo(None) == ""


def _store(world):
    from app.services import api_keys_store

    return api_keys_store.build_api_key_store(world.admin, encryption_key=world.cfg.encryption_key)


# ── the org's agents token ──────────────────────────────────────────────────
class TestAgentsToken:
    def test_reads_only_the_local_api_key_agents_row_of_THAT_org(self, world):
        from app.services import api_keys_store

        store = api_keys_store.build_api_key_store(world.admin, encryption_key=world.cfg.encryption_key)
        api_keys_store.put_api_key(store, ORG_ID, "agents", "pk_org_a")
        assert lais.agents_token_for_org(ORG_ID, store=store) == "pk_org_a"
        assert lais.agents_token_for_org(OTHER_ORG_ID, store=store) is None

    def test_agents_is_an_allowed_managed_key(self):
        from app.services import api_keys_store

        assert "agents" in api_keys_store.MANAGED_API_KEYS
        assert api_keys_store.provider_for("agents") == "api_key:agents"
        assert api_keys_store.get_spec("agents").is_secret is True

    def test_prod_without_a_token_resolves_no_client_never_a_fake(self, world, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.example.test")
        assert lais.resolve_agents_client(ORG_ID, cfg=world.cfg, store=_store(world)) is None

    def test_with_a_token_and_a_url_it_is_the_real_client(self, world, monkeypatch):
        from app.clients.agents import HttpAgentsClient
        from app.services import api_keys_store

        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.example.test")
        store = _store(world)
        api_keys_store.put_api_key(store, ORG_ID, "agents", "pk_org_a")
        assert isinstance(lais.resolve_agents_client(ORG_ID, cfg=world.cfg, store=store), HttpAgentsClient)
        assert lais.resolve_agents_client(OTHER_ORG_ID, cfg=world.cfg, store=store) is None  # prod: org B has none

    def test_dev_without_a_token_resolves_the_fake(self, world, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        for k in [k for k in __import__("os").environ if k.startswith("PRODUCT_URL_")]:
            monkeypatch.delenv(k)
        from app.clients.agents import FakeAgentsClient

        assert isinstance(lais.resolve_agents_client(ORG_ID, cfg=world.cfg, store=_store(world)), FakeAgentsClient)
