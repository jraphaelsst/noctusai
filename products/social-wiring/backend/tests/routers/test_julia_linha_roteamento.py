"""Routing on Julia's ONE line (CONTRACT julia-line B1/B2/B3): who is staff, what an internal echo is, and what is gone.

Driven through the REAL webhook with the product's own fakes (the scene of test_julia_agente_routing)."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from noctusai_lib.testing.migrations import migration_path

from app.services import julia_agente_service as julia
from app.services import julia_staff_service as staff
from app.services.message_store import MessageStore
from tests.routers.test_julia_agente_routing import (  # noqa: F401  (fixtures + builders of the shared scene)
    LEAD_CHAT, ORG_ID, OWNER_ID, Rt, _julia_scene, _msg, _servida, override_settings_factory, rt,
)
from tests.support.julia_world import ADMIN_ID, CONNECTION_ID, OWNER_TELEFONE

STAFF_PHONE = "5511977770009"
STAFF_CHAT = f"{STAFF_PHONE}@c.us"
MEMBER_CHAT = f"{OWNER_TELEFONE.lstrip('+')}@c.us"  # the owner's number as set in core (noctus_users.telefone)
MIGRATION = migration_path(Path(__file__).resolve().parents[2], "julia_linha_roteamento")


def _avisos(rt):
    return [n for n in rt.w.notifications() if (n.get("metadata") or {}).get("tipo") == "julia_staff_na_linha_publica"]


class TestStaffNeverReachesAgents:
    def test_a_julia_staff_number_is_stored_as_equipe_noticed_and_never_routed(self, rt):
        _julia_scene(rt)
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone=STAFF_PHONE)
        assert rt.post(_msg(chat=STAFF_CHAT, mid="s1", body="oi"), signed=True).status_code == 200
        assert rt.lead_memory(STAFF_CHAT) == [] and rt.w.agents.turns == [] and not rt.lead_keys_buffered()
        (row,) = rt.w.messages(STAFF_CHAT)
        assert row["origem"] == "interno" and row["direction"] == "inbound"
        assert rt.w.chat_row(STAFF_CHAT)["categoria"] == "equipe"
        assert avisos_para_admins(rt)

    def test_the_phone_of_an_active_member_of_the_line_owning_org_is_staff_too(self, rt):
        _julia_scene(rt)  # no julia_staff row at all: the owner is a member whose core phone matches
        assert rt.post(_msg(chat=MEMBER_CHAT, mid="m1", body="teste"), signed=True).status_code == 200
        assert rt.lead_memory(MEMBER_CHAT) == [] and rt.w.agents.turns == [] and not rt.lead_keys_buffered()
        assert rt.w.chat_row(MEMBER_CHAT)["categoria"] == "equipe"
        assert rt.w.contato(MEMBER_CHAT) is None
        assert avisos_para_admins(rt)

    def test_a_member_phone_in_a_LID_chat_is_resolved_before_deciding(self, rt):
        _julia_scene(rt)
        lid = "777000111@lid"
        rt.w.waha.fake_lid_phones[lid] = MEMBER_CHAT
        rt.post(_msg(chat=lid, mid="m-lid", body="sou eu"), signed=True)
        assert rt.lead_memory(lid) == [] and rt.w.agents.turns == []
        assert rt.w.chat_row(lid)["categoria"] == "equipe"

    def test_a_member_of_ANOTHER_org_is_not_staff_of_this_line(self, rt):
        _julia_scene(rt)
        rt.w.core.table("noctus_users").insert({"id": "00000000-0000-4000-8000-0000000000d9", "org_id": "00000000-0000-4000-8000-0000000000f1",
                                               "org_role": "owner", "nome": "Outro", "telefone": "+5511966664444"}).execute()
        rt.post(_msg(chat="5511966664444@c.us", mid="x1"), signed=True)
        assert len(rt.lead_memory("5511966664444@c.us")) == 1

    def test_a_member_without_a_phone_in_core_is_no_one(self, rt):
        _julia_scene(rt)
        assert staff.classificar_remetente(rt.w.sw, rt.w.core, ORG_ID, staff.formas_do_remetente("5511955550000@c.us")) is None

    def test_no_media_ai_call_for_staff(self, rt, monkeypatch):
        _julia_scene(rt)
        staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone=STAFF_PHONE)
        rt.settings(openai_api_key="sk-test")

        def _boom(**_kw):
            raise AssertionError("media AI must not run for staff")

        monkeypatch.setattr("app.routers.whatsapp_router.make_media_service", _boom)
        m = _msg(chat=STAFF_CHAT, mid="s-media", body="")
        m["payload"]["hasMedia"] = True
        m["payload"]["media"] = {"url": "http://localhost:3000/x.bin", "mimetype": "audio/ogg", "filename": "x"}
        assert rt.post(m, signed=True).status_code == 200
        assert rt.w.agents.turns == []

    def test_a_staff_chat_stays_equipe_but_a_removed_member_is_a_lead_and_the_category_follows(self, rt):
        _julia_scene(rt)
        row = staff.criar(rt.w.sw, rt.w.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone=STAFF_PHONE)
        rt.post(_msg(chat=STAFF_CHAT, mid="s1"), signed=True)
        assert rt.w.chat_row(STAFF_CHAT)["categoria"] == "equipe"
        staff.remover(rt.w.sw, ORG_ID, row["id"])
        rt.post(_msg(chat=STAFF_CHAT, mid="s2"), signed=True)
        assert rt.w.chat_row(STAFF_CHAT)["categoria"] == "lead"
        assert len(rt.lead_memory(STAFF_CHAT)) == 1


def avisos_para_admins(rt):
    avisos = _avisos(rt)
    return avisos and {n["user_id"] for n in avisos} >= {OWNER_ID}


class TestInternalEcho:
    """An internal (system-sent) message is pre-written with `origem='interno'` keyed by provider_message_id: WAHA's echo dedups on the
    UNIQUE constraint and is never a takeover -- with Redis up or down."""

    def _interno(self, rt, mid="wamid.int1", chat=STAFF_CHAT):
        store = MessageStore(admin_supabase=rt.w.admin, org_id=ORG_ID)
        return store.registrar_interno_enviado(connection_id=CONNECTION_ID, chat_id=chat, body="Relatório da Julia", provider_message_id=mid)

    def _echo(self, rt, mid="wamid.int1", chat=STAFF_CHAT):
        return rt.post(_msg(chat=chat, frm="5511000000000@c.us", to=chat, from_me=True, mid=mid, body="Relatório da Julia"), signed=True)

    def test_the_helper_writes_an_interno_outbound_row_and_marks_the_chat_equipe(self, rt):
        _julia_scene(rt)
        stored = self._interno(rt)
        assert stored is not None and stored.origem == "interno" and stored.direction == "outbound"
        (row,) = rt.w.messages(STAFF_CHAT)
        assert (row["origem"], row["provider_message_id"], row["connection_id"]) == ("interno", "wamid.int1", CONNECTION_ID)

    def test_the_helper_without_a_provider_id_writes_nothing_and_says_so(self, rt, caplog):
        _julia_scene(rt)
        with caplog.at_level("ERROR"):
            assert self._interno(rt, mid=None) is None
        assert rt.w.messages(STAFF_CHAT) == [] and any("no provider message id" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize("redis_down", [False, True])
    def test_the_echo_of_an_internal_send_is_one_row_and_not_a_takeover(self, rt, redis_down):
        _julia_scene(rt)
        rt.w.seed_chat(STAFF_CHAT)
        _servida(rt, STAFF_CHAT)
        self._interno(rt)
        if redis_down:
            with patch("redis.Redis.from_url", side_effect=ConnectionError("redis down")):
                assert self._echo(rt).status_code == 200
        else:
            assert self._echo(rt).status_code == 200
        # (the dedup itself is the DB UNIQUE constraint -- asserted on a real UNIQUE in tests/services/test_message_store.py; the mock
        # world has no constraint, so here the takeover rule alone must hold: it reads the stored `origem` of that provider id)
        assert rt.w.chat_row(STAFF_CHAT)["agente_pausado"] is False and rt.w.agents.participante_calls == []

    def test_the_old_one_hour_redis_key_is_no_longer_read(self, rt):
        """An id that only the retired Redis key knew is NOT Julia's own: the durable origem is the one source."""
        _julia_scene(rt)
        rt.w.seed_chat()
        _servida(rt)
        rt.w.redis.set("julia:julia_out:wamid.ghost", "1", ex=3600)
        rt.post(_msg(chat=LEAD_CHAT, frm="5511000000000@c.us", to=LEAD_CHAT, from_me=True, mid="wamid.ghost", body="oi"), signed=True)
        assert rt.w.chat_row()["agente_pausado"] is True


class TestEligibilityRefusesEquipe:
    def test_a_staff_chat_is_never_eligible_even_if_it_owns_a_conversation(self, rt):
        _julia_scene(rt)
        rec = rt.w.record(CONNECTION_ID)
        for estado in ({"categoria": "equipe"}, {"categoria": "equipe", "agente_conversation_id": "11111111-1111-4111-8111-111111111111"}):
            r = asyncio.run(julia.avaliar_elegibilidade(client=rt.w.sw, connection=rec, chat_id=STAFF_CHAT, chat_state={"created_at": None, **estado}))
            assert (r.elegivel, r.motivo) == (False, "equipe")

    def test_a_lead_chat_is_unchanged(self, rt):
        _julia_scene(rt)
        rec = rt.w.record(CONNECTION_ID)
        r = asyncio.run(julia.avaliar_elegibilidade(client=rt.w.sw, connection=rec, chat_id=LEAD_CHAT, chat_state={"categoria": "lead", "created_at": None}))
        assert r.elegivel and r.motivo == "new"


class TestJuliaNeedsNoAuthorizedNumbers:
    def test_the_lead_turn_runs_on_a_connection_with_no_authorized_numbers(self, rt):
        _julia_scene(rt, authorized_numbers=[])
        rt.w.seed_chat(created_at="2026-10-10T00:00:00+00:00")
        rt.post(_msg(mid="n1", body="oi, tenho interesse"), signed=True)
        from app.services.julia_lead_turn_service import process_lead_batch

        asyncio.run(process_lead_batch(julia.lead_key(CONNECTION_ID, LEAD_CHAT), rt.lead_memory(), deps=rt.w.deps(buffer=rt.module.buffer)))
        assert rt.w.agents.turns and rt.w.waha.sent_messages
        # and the bubbles Julia sent carry her durable origin
        assert {m["origem"] for m in rt.w.messages() if m["direction"] == "outbound"} == {"julia"}


class TestOneChatIsGone:
    def test_the_deleted_symbols_are_really_deleted(self):
        from app.routers import whatsapp_router as wr

        for nome in ("_build_intake_service", "build_intake_service_for_processor", "_staff_na_linha", "_triar_remetente",
                     "_lid_alias_phone", "whatsapp_webhook", "_resolve_default_org"):
            assert not hasattr(wr, nome), nome
        paths = {getattr(r, "path", "") for r in wr.router.routes}
        assert paths == {"/api/whatsapp/webhook/{token}"}

    def test_the_mirror_of_authorized_numbers_is_gone_from_the_staff_service(self):
        for nome in ("espelhar_conexoes", "sincronizar_de_lista", "lista_espelhada", "numeros_operadores", "exigir_que_a_julia_continue_autorizada"):
            assert not hasattr(staff, nome), nome

    def test_unsigned_webhooks_are_still_a_strict_401(self, rt):
        _julia_scene(rt)
        assert rt.post(_msg(), signed=False).status_code == 401
        assert rt.post(_msg(), signed=True, secret="wrong").status_code == 401
        assert rt.w.messages() == []


class TestMigrationLinhaRoteamento:
    sql = MIGRATION.read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", sql)

    def test_origem_categoria_and_the_dropped_check(self):
        assert "ADD COLUMN IF NOT EXISTS origem text" in self.flat
        assert "CHECK (origem IS NULL OR origem IN ('lead', 'julia', 'humano', 'interno'))" in self.flat
        assert "ADD COLUMN IF NOT EXISTS categoria text NOT NULL DEFAULT 'lead'" in self.flat
        assert "CHECK (categoria IN ('lead', 'equipe'))" in self.flat
        assert "DROP CONSTRAINT IF EXISTS whatsapp_connections_agente_exige_autorizados" in self.flat

    def test_it_is_idempotent_and_does_not_drop_the_legacy_columns(self):
        assert "DROP COLUMN" not in self.sql.upper()  # SW-B (S12) drops authorized_numbers / auto_reply_enabled / bound_chats after deploy
        assert "CREATE FUNCTION" not in self.sql.upper() and "CREATE OR REPLACE FUNCTION" not in self.sql.upper()
        assert self.flat.count("ADD CONSTRAINT") == self.flat.count("DROP CONSTRAINT IF EXISTS") - 1  # each added check is dropped first
