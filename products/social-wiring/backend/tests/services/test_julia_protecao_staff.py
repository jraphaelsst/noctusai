"""The org STAFF list, the abuse protection (rate limit, media budget, blocklist, automatic temporary block) and the identity
masking of Julia's public line (migration 298; owner 2026-10-21, GUARDRAILS B5 / B8 / B10). Fakes only: the mock DB, fakeredis."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_protecao_service as prot
from app.services import julia_staff_service as staff
from app.services.identidade_mascara import MASCARA, mascarar_identificadores, redigir_valores
from tests.support.julia_world import ADMIN_ID, CONNECTION_ID, CORRETOR_ID, LEAD_CHAT, OPERATOR, ORG_ID, OWNER_ID, World

TABLES = ("julia_staff", "julia_protecao_config", "julia_numeros_bloqueados")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    for t in TABLES:
        w.sw.set_table_data(t, [])
    return w


class TestMascara:
    def test_formatted_cpf_and_a_valid_bare_cpf_are_masked_a_phone_is_not(self):
        assert mascarar_identificadores("meu cpf 529.982.247-25 ok") == f"meu cpf {MASCARA} ok"
        assert MASCARA in mascarar_identificadores("52998224725")
        assert mascarar_identificadores("liga 11988887777") == "liga 11988887777"  # an 11-digit phone fails the CPF check digits

    def test_a_number_after_a_document_label_is_masked_whatever_its_shape(self):
        assert mascarar_identificadores("CNH: 04512345678").endswith(MASCARA)
        assert mascarar_identificadores("RG 12.345.678-9") == f"RG {MASCARA}"
        assert mascarar_identificadores("passaporte FY123456").count(MASCARA) in (0, 1)

    def test_text_without_identifiers_is_untouched_and_redigir_valores_masks_explicit_values(self):
        assert mascarar_identificadores("quero visitar o AP 1234 amanhã") == "quero visitar o AP 1234 amanhã"
        assert MASCARA in redigir_valores("registro 98.765.432-1", ["987654321"])


class TestConfig:
    def test_an_org_without_a_row_gets_the_defaults_and_is_flagged_padrao(self, world):
        cfg = prot.obter_config(world.sw, ORG_ID)
        assert cfg["padrao"] is True
        assert (cfg["entrada_limite"], cfg["midia_limite_chat_dia"], cfg["midia_limite_conexao_dia"]) == (20, 10, 200)

    def test_saving_validates_every_range_and_the_row_overrides_the_defaults(self, world):
        out = prot.salvar_config(world.sw, ORG_ID, ADMIN_ID, {"entrada_limite": 5, "midia_limite_chat_dia": 0})
        assert out["padrao"] is False and out["entrada_limite"] == 5 and out["midia_limite_chat_dia"] == 0
        assert out["midia_limite_conexao_dia"] == 200  # untouched keys keep their default
        for ruim in ({"entrada_limite": 0}, {"entrada_janela_s": 5}, {"bloqueio_auto_limiar": "3"}, {"entrada_limite": True}):
            with pytest.raises(AppException) as exc:
                prot.salvar_config(world.sw, ORG_ID, ADMIN_ID, ruim)
            assert exc.value.status_code == 422

    def test_the_lead_document_prompt_is_operator_editable_and_bounded(self, world):
        texto = "Diga só o tipo do documento e um resumo curto sem dados pessoais."
        assert prot.salvar_config(world.sw, ORG_ID, ADMIN_ID, {"prompt_documento_lead": texto})["prompt_documento_lead"] == texto
        with pytest.raises(AppException):
            prot.salvar_config(world.sw, ORG_ID, ADMIN_ID, {"prompt_documento_lead": "curto"})
        assert prot.salvar_config(world.sw, ORG_ID, ADMIN_ID, {"prompt_documento_lead": ""})["prompt_documento_lead"] is None


class TestBlocklist:
    def test_a_manual_block_records_reason_who_and_is_found_by_the_number(self, world):
        b = prot.bloquear(world.sw, ORG_ID, ADMIN_ID, numero="+55 11 97777-0001", motivo="spam")
        assert b["numero"] == "5511977770001" and b["criado_por"] == ADMIN_ID and b["origem"] == "manual"
        assert prot.bloqueio_ativo(world.sw, ORG_ID, ["5511977770001"]) is not None
        assert prot.bloqueio_ativo(world.sw, ORG_ID, ["5511977770002"]) is None
        with pytest.raises(AppException) as exc:
            prot.bloquear(world.sw, ORG_ID, ADMIN_ID, numero="5511977770001", motivo="de novo")
        assert exc.value.code == "numero_ja_bloqueado"

    def test_a_reason_is_required_and_a_staff_number_cannot_be_blocked(self, world):
        with pytest.raises(AppException):
            prot.bloquear(world.sw, ORG_ID, ADMIN_ID, numero="5511977770001", motivo="  ")
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone="5511977770009")
        with pytest.raises(AppException) as exc:
            prot.bloquear(world.sw, ORG_ID, ADMIN_ID, numero="5511977770009", motivo="x")
        assert exc.value.code == "numero_da_equipe"

    def test_unblocking_keeps_the_row_as_history(self, world):
        b = prot.bloquear(world.sw, ORG_ID, ADMIN_ID, numero="5511977770001", motivo="spam")
        out = prot.desbloquear(world.sw, ORG_ID, OWNER_ID, b["id"])
        assert out["ativo"] is False and out["desbloqueado_por"] == OWNER_ID
        assert prot.bloqueio_ativo(world.sw, ORG_ID, ["5511977770001"]) is None
        assert prot.listar_bloqueios(world.sw, ORG_ID) == []
        assert len(prot.listar_bloqueios(world.sw, ORG_ID, somente_ativos=False)) == 1
        with pytest.raises(AppException) as exc:
            prot.desbloquear(world.sw, ORG_ID, OWNER_ID, b["id"])
        assert exc.value.code == "bloqueio_ja_desfeito"

    def test_an_expired_automatic_block_lifts_itself(self, world):
        passado = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        world.sw.table("julia_numeros_bloqueados").insert({
            "id": "b1", "org_id": ORG_ID, "numero": "5511977770001", "motivo": "auto", "origem": "automatico", "gatilho": "loop_detectado",
            "ativo": True, "expira_em": passado}).execute()
        assert prot.bloqueio_ativo(world.sw, ORG_ID, ["5511977770001"]) is None
        assert prot.listar_bloqueios(world.sw, ORG_ID) == []

    def test_the_blocklist_is_per_org(self, world):
        prot.bloquear(world.sw, ORG_ID, ADMIN_ID, numero="5511977770001", motivo="spam")
        assert prot.bloqueio_ativo(world.sw, "00000000-0000-4000-8000-0000000000f1", ["5511977770001"]) is None


class TestLimits:
    def test_the_inbound_rate_limit_is_per_number_and_per_org_config(self, world):
        cfg = {**prot.PADRAO, "entrada_limite": 3}
        kw = dict(org_id=ORG_ID, connection_id=CONNECTION_ID)
        assert [prot.permitir_entrada(world.redis, cfg, chave="5511977770001", **kw) for _ in range(4)] == [True, True, True, False]
        assert prot.permitir_entrada(world.redis, cfg, chave="5511977770002", **kw) is True  # another number is unaffected

    def test_the_media_budget_is_10_per_chat_and_200_per_connection_a_day(self, world):
        cfg = dict(prot.PADRAO)
        kw = dict(connection_id=CONNECTION_ID, agora=1_000_000.0)
        assert [prot.reservar_midia(world.redis, cfg, chat_id="a@c.us", **kw) for _ in range(10)] == [None] * 10
        assert prot.reservar_midia(world.redis, cfg, chat_id="a@c.us", **kw) == "chat"
        assert prot.reservar_midia(world.redis, cfg, chat_id="b@c.us", **kw) is None  # another chat has its own budget
        # a day later the window has slid
        assert prot.reservar_midia(world.redis, cfg, chat_id="a@c.us", connection_id=CONNECTION_ID, agora=1_000_000.0 + 86401) is None

    def test_the_connection_budget_refuses_across_chats_without_consuming_the_chat_counter(self, world):
        cfg = {**prot.PADRAO, "midia_limite_conexao_dia": 2}
        kw = dict(connection_id=CONNECTION_ID, agora=2_000_000.0)
        assert prot.reservar_midia(world.redis, cfg, chat_id="a@c.us", **kw) is None
        assert prot.reservar_midia(world.redis, cfg, chat_id="b@c.us", **kw) is None
        assert prot.reservar_midia(world.redis, cfg, chat_id="c@c.us", **kw) == "conexao"
        assert world.redis.zcard(f"julia:prot:midia:chat:{CONNECTION_ID}:c@c.us") == 0


class TestBloqueioAutomatico:
    def _infracao(self, world, gatilho="loop_detectado", n=1, chave="5511977770001"):
        cfg = {**prot.PADRAO, "bloqueio_auto_limiar": 3}
        out = None
        for i in range(n):
            out = prot.registrar_infracao(world.redis, world.sw, world.core, cfg, org_id=ORG_ID, connection_id=CONNECTION_ID, chave=chave,
                                          gatilho=gatilho, agora=time.time() + i)
        return out

    def test_below_the_threshold_nothing_happens(self, world):
        assert self._infracao(world, n=2) is None
        assert prot.listar_bloqueios(world.sw, ORG_ID) == []

    def test_reaching_the_threshold_blocks_temporarily_and_notifies_the_admins(self, world):
        b = self._infracao(world, "limite_taxa", n=3)
        assert b is not None and b["origem"] == "automatico" and b["gatilho"] == "limite_taxa" and b["expira_em"]
        assert b["notificacao_status"] == "enviada"
        assert prot.bloqueio_ativo(world.sw, ORG_ID, ["5511977770001"]) is not None
        destinatarios = {n["user_id"] for n in world.notifications()}
        assert {ADMIN_ID, OWNER_ID} <= destinatarios

    def test_a_notice_that_could_not_be_delivered_is_recorded_not_swallowed(self, world):
        world.core.set_table_data("noctus_users", [])  # nobody to tell
        b = self._infracao(world, n=3)
        assert b is not None and b["notificacao_status"] == "falhou"

    def test_the_org_can_switch_the_automatic_block_off_and_staff_is_never_auto_blocked(self, world):
        off = {**prot.PADRAO, "bloqueio_auto_ativo": False, "bloqueio_auto_limiar": 1}
        assert prot.registrar_infracao(world.redis, world.sw, world.core, off, org_id=ORG_ID, connection_id=CONNECTION_ID,
                                       chave="5511977770001", gatilho="entrada_flood") is None
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone="5511977770009")
        assert self._infracao(world, n=3, chave="5511977770009") is None

    def test_capacity_and_new_lead_limits_are_not_abuse_signals(self, world):
        with pytest.raises(ValueError):
            self._infracao(world, "capacidade")


class TestTriagem:
    def _conn(self, world):
        return world.record(CONNECTION_ID)

    def test_a_blocked_number_is_triaged_blocked_and_a_flood_is_limited_then_blocked(self, world):
        prot.salvar_config(world.sw, ORG_ID, ADMIN_ID, {"entrada_limite": 2, "bloqueio_auto_limiar": 2})
        conn = self._conn(world)
        run = lambda: prot.triar_entrada(world.sw, world.redis, world.core, conn, chat_id=LEAD_CHAT, sender=LEAD_CHAT)
        assert [run().estado for _ in range(2)] == ["livre", "livre"]
        assert run().estado == "limitado"
        assert run().estado == "limitado"  # second signal trips the automatic block
        assert run().estado == "bloqueado"
        assert prot.listar_bloqueios(world.sw, ORG_ID)[0]["gatilho"] == "entrada_flood"

    def test_an_unreadable_config_fails_closed_for_the_expensive_work(self, world):
        class Boom:
            def table(self, *_a):
                raise RuntimeError("db down")

        t = prot.triar_entrada(Boom(), world.redis, world.core, self._conn(world), chat_id=LEAD_CHAT, sender=LEAD_CHAT)
        assert t.estado == "erro" and t.bloqueia_ia


class TestStaff:
    def test_text_never_makes_staff_only_a_registered_number_does(self, world):
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Bia", papel="corretor", telefone="5511977770009")
        assert staff.buscar_por_telefone(world.sw, ORG_ID, staff.formas_do_remetente("5511977770009@c.us")) is not None
        assert staff.buscar_por_telefone(world.sw, ORG_ID, staff.formas_do_remetente("5511977770010@c.us")) is None  # not listed => a lead

    def test_roles_validation_and_duplicates(self, world):
        with pytest.raises(AppException) as exc:
            staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="X", papel="rei", telefone="5511977770009")
        assert exc.value.code == "papel_invalido"
        with pytest.raises(AppException) as exc:
            staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="X", papel="outro", telefone="12")
        assert exc.value.code == "telefone_invalido"
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Bia", papel="outro", telefone="5511977770009")
        with pytest.raises(AppException) as exc:
            staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Bia 2", papel="outro", telefone="+55 11 97777-0009")
        assert exc.value.status_code == 409

    def test_a_user_from_another_org_cannot_be_linked(self, world):
        with pytest.raises(AppException) as exc:
            staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="X", papel="outro", telefone="5511977770009",
                        user_id="00000000-0000-4000-8000-00000000dead")
        assert exc.value.code == "usuario_fora_da_org"

    def test_a_blocked_number_cannot_be_registered_as_staff(self, world):
        prot.bloquear(world.sw, ORG_ID, ADMIN_ID, numero="5511977770001", motivo="spam")
        with pytest.raises(AppException) as exc:
            staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="X", papel="outro", telefone="5511977770001")
        assert exc.value.code == "numero_bloqueado"

    def test_operator_roles_are_mirrored_into_authorized_numbers_and_others_are_not(self, world):
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Op", papel="operador", telefone="5511977770003")
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Cor", papel="corretor", telefone="5511977770004")
        auth = world.rows("whatsapp_connections")[0]["authorized_numbers"]
        assert "+5511977770003" in auth and "+5511977770004" not in auth
        assert OPERATOR not in auth  # the old hand-edited list is replaced by the mirror of the staff list (the mock row was not in it)

    def test_the_last_operator_of_a_julia_line_cannot_be_removed(self, world):
        op = staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Op", papel="operador", telefone="5511977770003")
        with pytest.raises(AppException) as exc:
            staff.remover(world.sw, ORG_ID, op["id"])
        assert exc.value.code == "ultimo_operador"
        with pytest.raises(AppException):
            staff.atualizar(world.sw, world.core, ORG_ID, op["id"], {"papel": "corretor"})
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Op2", papel="admin", telefone="5511977770005")
        staff.remover(world.sw, ORG_ID, op["id"])  # a second operator exists now
        assert staff.buscar_por_telefone(world.sw, ORG_ID, ["5511977770003"]) is None

    def test_removing_staff_makes_the_number_a_lead_again(self, world):
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Op", papel="operador", telefone="5511977770003")
        c = staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Cor", papel="corretor", telefone="5511977770004")
        staff.remover(world.sw, ORG_ID, c["id"])
        assert staff.buscar_por_telefone(world.sw, ORG_ID, ["5511977770004"]) is None

    def test_the_connection_patch_goes_through_the_staff_list(self, world):
        espelho = staff.sincronizar_de_lista(world.sw, world.core, ORG_ID, ADMIN_ID, ["+55 11 97777-0003", "5511977770003"])
        assert espelho[CONNECTION_ID] == ["+5511977770003"]
        assert [r["papel"] for r in staff.listar(world.sw, ORG_ID)] == ["operador"]
        espelho = staff.sincronizar_de_lista(world.sw, world.core, ORG_ID, ADMIN_ID, ["5511977770003", "5511977770006"])
        assert espelho[CONNECTION_ID] == ["+5511977770003", "+5511977770006"]
        with pytest.raises(AppException) as exc:
            staff.sincronizar_de_lista(world.sw, world.core, ORG_ID, ADMIN_ID, [])
        assert exc.value.code == "ultimo_operador"

    def test_the_author_of_a_human_line_is_the_registered_name_and_role_else_the_core_role(self, world):
        staff.criar(world.sw, world.core, ORG_ID, ADMIN_ID, nome="Bia Souza", papel="corretor", telefone="5511977770009", user_id=CORRETOR_ID)
        a = staff.autor_de_usuario(world.sw, world.core, ORG_ID, CORRETOR_ID)
        assert (a["nome"], a["papel"], a["na_lista"]) == ("Bia Souza", "corretor", True)
        b = staff.autor_de_usuario(world.sw, world.core, ORG_ID, ADMIN_ID)
        assert b["papel"] == "admin" and b["na_lista"] is False
        assert staff.autor_de_usuario(world.sw, world.core, ORG_ID, "00000000-0000-4000-8000-00000000dead") is None
