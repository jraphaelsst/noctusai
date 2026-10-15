"""Lais foundation (lais-build-contract 0.2 / 2.2): contatos + episodes + the `gen` stale guard,
the `contexto` builder and its provider registry, the action ledger + handler registry, the events
service, and the whole thing wired through the lead worker (`process_lead_batch`).

Seams are the Fakes the product and seed ship: mock DB, `FakeAgentsClient`, `FakeWahaClient`, the
in-memory buffer. Nothing of ours is patched. No personal data in fixtures.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.clients.agents import (
    AgentsUpstreamError,
    FakeAgentsClient,
    HandoffAction,
    LaisAction,
    ResumoResult,
    TurnResult,
)
from app.services import lais_acoes_service as acoes
from app.services import lais_contatos_service as contatos
from app.services import lais_contexto_service as ctxsvc
from app.services import lais_eventos_service as eventos
from app.services.lais_lead_turn_service import process_lead_batch

from tests.support.lais_world import (
    CONNECTION_ID,
    LEAD_CHAT,
    ORG_ID as ORG,
    OTHER_ORG_ID,
    World,
    buffer_lead,
)

CONV = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    return w


def _mk_contato(world: World, chat: str = "chat-1", **over) -> dict:
    return contatos.obter_ou_criar_contato(
        world.sw, org_id=ORG, connection_id=CONNECTION_ID, chat_id=chat, telefone_e164=over.pop("phone", None), nome=over.pop("nome", None),
    )


def _turn(*actions, partes=("Certo!",), status="respondido") -> TurnResult:
    return TurnResult(conversation_id=CONV, partes=tuple(partes), status=status, actions=tuple(actions))


# ── contatos ────────────────────────────────────────────────────────────────
class TestContatos:
    def test_get_or_create_is_idempotent_and_fills_only_missing_fields(self, world):
        a = _mk_contato(world, phone="+5511900000001")
        b = contatos.obter_ou_criar_contato(
            world.sw, org_id=ORG, connection_id=CONNECTION_ID, chat_id="chat-1", telefone_e164="+5511900000002", nome="Ana",
        )
        assert a["id"] == b["id"]
        row = world.rows("lais_contatos")[0]
        assert len(world.rows("lais_contatos")) == 1
        assert row["telefone_e164"] == "+5511900000001"  # never overwritten
        assert row["nome"] == "Ana"  # was missing -> filled
        assert (row["gen"], row["status_envio"], row["canal"], row["slots"]) == (0, "nao_pronto", "whatsapp", {})

    def test_the_same_chat_in_another_org_or_connection_is_another_contato(self, world):
        _mk_contato(world)
        contatos.obter_ou_criar_contato(world.sw, org_id=OTHER_ORG_ID, connection_id=CONNECTION_ID, chat_id="chat-1")
        contatos.obter_ou_criar_contato(world.sw, org_id=ORG, connection_id="00000000-0000-4000-8000-0000000000e9", chat_id="chat-1")
        assert len(world.rows("lais_contatos")) == 3

    def test_inbound_bumps_gen_stamps_last_inbound_and_reopens_a_closed_contato(self, world):
        c = _mk_contato(world)
        contatos.atualizar_contato(world.sw, c["id"], {"encerrado_at": "2026-10-01T00:00:00+00:00"})
        c = world.rows("lais_contatos")[0]
        now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        c2, anterior = contatos.registrar_inbound(world.sw, c, agora=now)
        row = world.rows("lais_contatos")[0]
        assert (row["gen"], c2["gen"]) == (1, 1)
        assert row["ultimo_inbound_at"] == now.isoformat() and row["encerrado_at"] is None
        assert anterior is None
        _c3, anterior2 = contatos.registrar_inbound(world.sw, c2, agora=now + timedelta(hours=1))
        assert world.rows("lais_contatos")[0]["gen"] == 2 and anterior2 == now

    def test_bump_gen_is_a_compare_and_set_that_applies_the_extra_fields(self, world):
        c = _mk_contato(world)
        assert contatos.bump_gen(world.sw, c["id"], encerrado_at="2026-10-15T00:00:00+00:00") == 1
        assert contatos.bump_gen(world.sw, c["id"]) == 2
        assert world.rows("lais_contatos")[0]["encerrado_at"] == "2026-10-15T00:00:00+00:00"

    def test_bump_gen_of_an_unknown_contato_is_loud(self, world):
        with pytest.raises(LookupError):
            contatos.bump_gen(world.sw, "00000000-0000-4000-8000-00000000dead")

    def test_bump_by_chat_is_a_noop_without_a_contato(self, world):
        assert contatos.bump_gen_do_chat(world.sw, ORG, CONNECTION_ID, "nobody") is None
        c = _mk_contato(world)
        assert contatos.bump_gen_do_chat(world.sw, ORG, CONNECTION_ID, "chat-1") == 1
        assert world.rows("lais_contatos")[0]["id"] == c["id"]

    # the stale guard (0.2)
    def test_a_job_with_an_older_gen_is_obsolete_and_the_current_one_is_not(self, world):
        c = _mk_contato(world)
        payload = contatos.payload_job(world.rows("lais_contatos")[0], "lead:k")
        assert payload == {"org_id": ORG, "chat_key": "lead:k", "gen": 0}
        assert contatos.job_obsoleto(world.sw, ORG, c["id"], payload["gen"]) is False
        contatos.registrar_inbound(world.sw, world.rows("lais_contatos")[0])  # an inbound arrives
        assert contatos.job_obsoleto(world.sw, ORG, c["id"], payload["gen"]) is True

    def test_a_job_of_another_org_or_a_vanished_contato_is_obsolete(self, world):
        c = _mk_contato(world)
        assert contatos.job_obsoleto(world.sw, OTHER_ORG_ID, c["id"], 0) is True
        assert contatos.job_obsoleto(world.sw, ORG, "00000000-0000-4000-8000-00000000dead", 0) is True


class TestEpisodes:
    def test_only_the_first_open_call_creates_an_episode(self, world):
        c = _mk_contato(world)
        a = contatos.abrir_interacao(world.sw, ORG, c)
        b = contatos.abrir_interacao(world.sw, ORG, c)
        assert a["id"] == b["id"] and len(world.rows("lais_interacoes")) == 1
        assert contatos.interacao_aberta(world.sw, c["id"])["id"] == a["id"]

    @pytest.mark.parametrize("silencio_h,vencido", [(23, False), (24, False), (25, True), (500, True)])
    def test_more_than_24h_of_silence_ends_the_episode(self, silencio_h, vencido):
        now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        assert contatos.episodio_vencido(now - timedelta(hours=silencio_h), agora=now) is vencido

    def test_no_prior_activity_is_never_stale(self):
        assert contatos.episodio_vencido(None) is False


# ── events ──────────────────────────────────────────────────────────────────
class TestEventos:
    def test_emit_stores_the_row_scoped_to_the_org(self, world):
        c = _mk_contato(world)
        ev = eventos.emitir(world.sw, ORG, "novo_lead", c["id"], {"x": 1})
        row = world.rows("lais_eventos")[0]
        assert ev is not None and (row["org_id"], row["tipo"], row["contato_id"], row["payload"]) == (ORG, "novo_lead", c["id"], {"x": 1})

    def test_an_unknown_type_writes_nothing_and_returns_none(self, world):
        assert eventos.emitir(world.sw, ORG, "tipo_inventado") is None
        assert eventos.emitir(world.sw, ORG, "NOVO LEAD") is None
        assert world.rows("lais_eventos") == []

    def test_the_catalogue_covers_the_contract_8_types(self):
        assert {"pre_agendamento_visita", "cobranca_atendimento", "relatorio", "remarketing", "captacao",
                "atualizacao_base_imoveis", "novo_lead", "novo_atendimento", "nova_mensagem",
                "avaliacao_google", "handoff"} <= eventos.TIPOS

    def test_a_failing_insert_is_logged_and_never_raised(self, world, caplog):
        class Boom:
            def table(self, _):
                raise RuntimeError("db down")

        with caplog.at_level("ERROR"):
            assert eventos.emitir(Boom(), ORG, "novo_lead") is None
        assert "could not write event" in caplog.text


# ── contexto ────────────────────────────────────────────────────────────────
class TestContexto:
    def _base(self, world):
        c = _mk_contato(world)
        i = contatos.abrir_interacao(world.sw, ORG, c)
        return world.rows("lais_contatos")[0], i

    def test_default_shape_matches_contract_2_1_a(self, world):
        c, i = self._base(world)
        now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        ctx = ctxsvc.montar(world.sw, ORG, c, interacao=i, agora=now, ferramentas_habilitadas=False)
        assert set(ctx) == {"hash", "conhecimento_md", "perguntas", "estado", "ferramentas", "acoes", "agora", "fuso"}
        assert (ctx["conhecimento_md"], ctx["perguntas"], ctx["ferramentas"]) == ("", [], [])
        assert ctx["estado"] == {"slots": {}, "operacao": None, "interacao_id": i["id"], "encerrado": False}
        assert ctx["acoes"] == ["salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "captacao", "encerrar", "handoff"]
        assert (ctx["agora"], ctx["fuso"]) == (now.isoformat(), "America/Sao_Paulo")
        assert len(ctx["hash"]) == 64 and int(ctx["hash"], 16) >= 0

    def test_hash_is_stable_for_equal_input_even_across_clock_ticks_and_changes_with_content(self, world):
        c, i = self._base(world)
        t1, t2 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc), datetime(2026, 10, 15, 12, 5, tzinfo=timezone.utc)
        a = ctxsvc.montar(world.sw, ORG, c, interacao=i, agora=t1, ferramentas_habilitadas=True)
        b = ctxsvc.montar(world.sw, ORG, c, interacao=i, agora=t2, ferramentas_habilitadas=True)
        assert a["hash"] == b["hash"] and a["agora"] != b["agora"]
        c_slots = {**c, "slots": {"bairro": "Granja"}}
        assert ctxsvc.montar(world.sw, ORG, c_slots, interacao=i, agora=t1, ferramentas_habilitadas=True)["hash"] != a["hash"]
        assert ctxsvc.montar(world.sw, ORG, c, interacao=i, agora=t1, ferramentas_habilitadas=False)["hash"] != a["hash"]

    def test_hash_is_the_sha256_of_the_rest_of_the_contexto(self, world):
        import hashlib, json

        c, i = self._base(world)
        ctx = ctxsvc.montar(world.sw, ORG, c, interacao=i, ferramentas_habilitadas=False)
        rest = {k: v for k, v in ctx.items() if k not in ("hash", "agora")}
        expected = hashlib.sha256(json.dumps(rest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        assert ctx["hash"] == expected

    def test_estado_reflects_the_contato(self, world):
        c, i = self._base(world)
        c = {**c, "slots": {"bairro": "Granja", "n": 3}, "operacao": "aluguel", "encerrado_at": "2026-10-15T00:00:00+00:00"}
        est = ctxsvc.montar(world.sw, ORG, c, interacao=i, ferramentas_habilitadas=False)["estado"]
        assert est == {"slots": {"bairro": "Granja", "n": "3"}, "operacao": "aluguel", "interacao_id": i["id"], "encerrado": True}

    def test_atualizacao_is_an_action_value_not_an_estado_value(self, world):
        c, i = self._base(world)
        est = ctxsvc.montar(world.sw, ORG, {**c, "operacao": "atualizacao"}, interacao=i, ferramentas_habilitadas=False)["estado"]
        assert est["operacao"] is None

    def test_ferramentas_follow_the_tools_token(self, world):
        c, i = self._base(world)
        on = ctxsvc.montar(world.sw, ORG, c, interacao=i, ferramentas_habilitadas=True)["ferramentas"]
        assert on == ["buscar_imoveis", "detalhes_imovel", "horarios_visita", "consultar_empreendimento"]

    def test_the_provider_registry_is_the_extension_point_and_replaces_in_place(self, world, monkeypatch):
        reg = list(ctxsvc.PROVIDERS)
        c, i = self._base(world)
        ctxsvc.registrar_provider("conhecimento", lambda ctx: {"conhecimento_md": f"# {ctx.org_id}"}, registro=reg)
        ctxsvc.registrar_provider("perguntas", lambda ctx: {"perguntas": [{"chave": f"q{n}"} for n in range(12)]}, registro=reg)
        ctxsvc.registrar_provider("estado_extra", lambda ctx: {"estado": {"extra": 1}}, registro=reg)
        ctx = ctxsvc.montar(world.sw, ORG, c, interacao=i, ferramentas_habilitadas=False, providers=reg)
        assert ctx["conhecimento_md"] == f"# {ORG}"
        assert len(ctx["perguntas"]) == 8  # capped at the contract's 0..8
        assert ctx["estado"]["extra"] == 1 and ctx["estado"]["interacao_id"] == i["id"]  # merged, not replaced
        assert [n for n, _ in reg][:2] == ["conhecimento", "perguntas"]  # position kept

    def test_a_provider_that_raises_is_contained_and_the_rest_still_render(self, world, monkeypatch, caplog):
        reg = list(ctxsvc.PROVIDERS)

        def boom(_ctx):
            raise RuntimeError("wave 1 is broken")

        ctxsvc.registrar_provider("conhecimento", boom, registro=reg)
        c, i = self._base(world)
        with caplog.at_level("ERROR"):
            ctx = ctxsvc.montar(world.sw, ORG, c, interacao=i, ferramentas_habilitadas=False, providers=reg)
        assert ctx["conhecimento_md"] == "" and ctx["estado"]["interacao_id"] == i["id"]
        assert "provider 'conhecimento' failed" in caplog.text

    def test_an_unknown_key_from_a_provider_is_refused_loudly(self, world, monkeypatch, caplog):
        reg = list(ctxsvc.PROVIDERS)
        ctxsvc.registrar_provider("rogue", lambda ctx: {"segredo": "x"}, registro=reg)
        c, i = self._base(world)
        with caplog.at_level("ERROR"):
            ctx = ctxsvc.montar(world.sw, ORG, c, interacao=i, ferramentas_habilitadas=False, providers=reg)
        assert "segredo" not in ctx and "unknown key" in caplog.text

    def test_oversized_knowledge_is_truncated_to_60000_and_the_whole_stays_under_80000(self, world, monkeypatch):
        import json

        reg = list(ctxsvc.PROVIDERS)
        ctxsvc.registrar_provider("conhecimento", lambda ctx: {"conhecimento_md": "x" * 90_000}, registro=reg)
        c, i = self._base(world)
        ctx = ctxsvc.montar(world.sw, ORG, c, interacao=i, ferramentas_habilitadas=False, providers=reg)
        assert len(ctx["conhecimento_md"]) == 60_000
        assert len(json.dumps(ctx, ensure_ascii=False)) <= ctxsvc.CONTEXTO_MAX

    def test_tools_token_detection_needs_an_active_agents_issued_lais_token(self, world):
        now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        label, scope = ctxsvc.TOOLS_TOKEN_LABEL, ctxsvc.TOOLS_TOKEN_SCOPE

        def seed(**row):
            world.sw.table("api_tokens").insert({
                "org_id": ORG, "label": label, "scopes": [scope], "issuer": "agents", "token_hash": "h" + str(len(world.rows("api_tokens"))),
                "token_prefix": "pk_x", "expires_at": (now + timedelta(days=30)).isoformat(), **row,
            }).execute()

        assert ctxsvc.org_tem_token_ferramentas(world.sw, ORG, agora=now) is False
        seed(revoked_at=now.isoformat())
        seed(expires_at=(now - timedelta(days=1)).isoformat())
        seed(issuer="outro")
        seed(scopes=["social-wiring:one-chat:read"])
        assert ctxsvc.org_tem_token_ferramentas(world.sw, ORG, agora=now) is False
        seed()
        assert ctxsvc.org_tem_token_ferramentas(world.sw, ORG, agora=now) is True
        assert ctxsvc.org_tem_token_ferramentas(world.sw, OTHER_ORG_ID, agora=now) is False


# ── actions ─────────────────────────────────────────────────────────────────
PERGUNTAS = [{"chave": "bairro"}, {"chave": "orcamento"}]


async def _apply(world, contato, *actions, lote="L1", agents=None, perguntas=PERGUNTAS, conv=CONV, handlers=None):
    return await acoes.aplicar(
        world.sw, org_id=ORG, contato=contato, result=_turn(*actions), lote_hash=lote,
        conversation_id=conv, agents_client=agents or world.agents, core_client=world.core, perguntas=perguntas,
        connection_id=CONNECTION_ID, chat_id="chat-1", handlers=handlers,
    )


@pytest.mark.asyncio
class TestAcoes:
    async def test_salvar_slots_merges_slots_and_routes_nome_email_to_their_columns(self, world):
        c = _mk_contato(world)
        contatos.abrir_interacao(world.sw, ORG, c)
        out = await _apply(world, c, LaisAction("salvar_slots", 1, {"slots": {
            "bairro": " Granja Viana ", "orcamento": "900 mil", "nome": "Ana Teste", "email": "ANA@Example.COM",
            "desconhecida": "x", "BAD KEY": "x",
        }}))
        assert out == [{"seq": 1, "tipo": "salvar_slots", "estado": "aplicada"}]
        row = world.rows("lais_contatos")[0]
        assert row["slots"] == {"bairro": "Granja Viana", "orcamento": "900 mil"}
        assert (row["nome"], row["email"]) == ("Ana Teste", "ana@example.com")
        assert world.rows("lais_interacoes")[0]["slots"] == row["slots"]
        ledger = world.rows("lais_acoes_aplicadas")[0]
        assert sorted(ledger["resultado"]["salvos"]) == ["bairro", "email", "nome", "orcamento"]
        assert sorted(ledger["resultado"]["ignorados"]) == ["BAD KEY", "desconhecida"]

    async def test_salvar_slots_caps_values_and_rejects_an_invalid_email(self, world):
        c = _mk_contato(world)
        await _apply(world, c, LaisAction("salvar_slots", 1, {"slots": {"bairro": "x" * 900, "email": "not-an-email"}}))
        row = world.rows("lais_contatos")[0]
        assert len(row["slots"]["bairro"]) == 500 and row["email"] is None

    async def test_salvar_slots_with_a_bad_shape_stores_nothing(self, world):
        c = _mk_contato(world)
        await _apply(world, c, LaisAction("salvar_slots", 1, {"slots": "bairro=Granja"}))
        assert world.rows("lais_contatos")[0]["slots"] == {}
        assert world.rows("lais_acoes_aplicadas")[0]["resultado"]["erro"] == "slots_invalido"

    async def test_definir_operacao_sets_contato_and_episode_and_refuses_unknown_values(self, world):
        c = _mk_contato(world)
        contatos.abrir_interacao(world.sw, ORG, c)
        await _apply(world, c, LaisAction("definir_operacao", 1, {"operacao": "aluguel"}), lote="L1")
        assert world.rows("lais_contatos")[0]["operacao"] == "aluguel"
        assert world.rows("lais_interacoes")[0]["operacao"] == "aluguel"
        await _apply(world, c, LaisAction("definir_operacao", 1, {"operacao": "troca"}), lote="L2")
        assert world.rows("lais_contatos")[0]["operacao"] == "aluguel"
        assert world.rows("lais_acoes_aplicadas", lote_hash="L2")[0]["resultado"] == {"erro": "operacao_invalida"}

    async def test_the_same_lote_applied_twice_applies_once(self, world):
        c = _mk_contato(world)
        acao = LaisAction("salvar_slots", 1, {"slots": {"bairro": "A"}})
        first = await _apply(world, c, acao)
        # someone changes the slot meanwhile; a REPLAY of the batch must not clobber it
        contatos.atualizar_contato(world.sw, c["id"], {"slots": {"bairro": "B"}})
        again = await _apply(world, c, acao)
        assert [o["estado"] for o in first] == ["aplicada"] and [o["estado"] for o in again] == ["repetida"]
        assert world.rows("lais_contatos")[0]["slots"] == {"bairro": "B"}
        assert len(world.rows("lais_acoes_aplicadas")) == 1

    async def test_a_new_lote_with_the_same_seq_is_a_new_application(self, world):
        c = _mk_contato(world)
        await _apply(world, c, LaisAction("salvar_slots", 1, {"slots": {"bairro": "A"}}), lote="L1")
        await _apply(world, c, LaisAction("salvar_slots", 1, {"slots": {"bairro": "C"}}), lote="L2")
        assert world.rows("lais_contatos")[0]["slots"] == {"bairro": "C"}
        assert len(world.rows("lais_acoes_aplicadas")) == 2

    async def test_actions_run_in_seq_order_not_arrival_order(self, world):
        c = _mk_contato(world)
        await _apply(world, c, LaisAction("salvar_slots", 2, {"slots": {"bairro": "depois"}}),
                     LaisAction("salvar_slots", 1, {"slots": {"bairro": "antes"}}))
        assert world.rows("lais_contatos")[0]["slots"] == {"bairro": "depois"}
        assert [r["seq"] for r in world.rows("lais_acoes_aplicadas")] == [1, 2]

    async def test_an_unknown_handler_emits_an_event_and_never_drops_the_rest(self, world):
        c = _mk_contato(world)
        out = await _apply(world, c, LaisAction("captacao", 1, {"codigo_imovel": "X1"}),
                           LaisAction("salvar_slots", 2, {"slots": {"bairro": "A"}}))
        assert [o["estado"] for o in out] == ["sem_handler", "aplicada"]
        ev = world.rows("lais_eventos")
        assert [(e["tipo"], e["payload"]) for e in ev] == [("acao_sem_handler", {"tipo": "captacao", "seq": 1})]
        assert world.rows("lais_acoes_aplicadas", seq=1)[0]["resultado"] == {"sem_handler": True}
        assert world.rows("lais_contatos")[0]["slots"] == {"bairro": "A"}

    async def test_a_registered_handler_receives_the_raw_payload_and_the_ledger_a_sanitised_one(self, world, monkeypatch):
        reg = dict(acoes.HANDLERS)
        seen = {}

        def handler(ctx, payload):
            seen.update(payload=payload, tipo=ctx.tipo, seq=ctx.seq, lote=ctx.lote_hash, chat=ctx.chat_id)
            return {"ok": True}

        acoes.registrar_handler("pedido_visita", handler, registro=reg)
        c = _mk_contato(world)
        await _apply(world, c, LaisAction("pedido_visita", 4, {"codigo_imovel": "X1", "cpf": "111.222.333-44"}), handlers=reg)
        assert seen["payload"]["cpf"] == "111.222.333-44" and (seen["tipo"], seen["seq"], seen["chat"]) == ("pedido_visita", 4, "chat-1")
        led = world.rows("lais_acoes_aplicadas")[0]
        assert "cpf" not in led["payload"] and led["payload"]["cpf_final"] == "344" and len(led["payload"]["cpf_hash"]) == 64
        assert led["resultado"] == {"ok": True}
        assert "111" not in str(led["payload"])

    async def test_an_async_handler_is_awaited(self, world, monkeypatch):
        reg = dict(acoes.HANDLERS)

        async def handler(ctx, payload):
            return {"async": True}

        acoes.registrar_handler("captacao", handler, registro=reg)
        c = _mk_contato(world)
        await _apply(world, c, LaisAction("captacao", 1, {"descricao": "casa"}), handlers=reg)
        assert world.rows("lais_acoes_aplicadas")[0]["resultado"] == {"async": True}

    async def test_a_handler_that_raises_is_contained_logged_and_reported_as_an_event(self, world, monkeypatch, caplog):
        reg = dict(acoes.HANDLERS)

        def handler(ctx, payload):
            raise RuntimeError("wave 3 bug")

        acoes.registrar_handler("qualificar_lead", handler, registro=reg)
        c = _mk_contato(world)
        with caplog.at_level("ERROR"):
            out = await _apply(world, c, LaisAction("qualificar_lead", 1, {"motivo": "m"}),
                               LaisAction("salvar_slots", 2, {"slots": {"bairro": "A"}}), handlers=reg)
        assert [o["estado"] for o in out] == ["falhou", "aplicada"]
        assert world.rows("lais_eventos")[0]["tipo"] == "acao_falhou"
        assert world.rows("lais_acoes_aplicadas", seq=1)[0]["resultado"] == {"erro": "RuntimeError"}
        assert "handler for qualificar_lead" in caplog.text

    async def test_encerrar_closes_the_episode_with_the_summary_bumps_gen_and_marks_the_contato(self, world):
        c = _mk_contato(world)
        i = contatos.abrir_interacao(world.sw, ORG, c)
        world.agents = FakeAgentsClient(resumo_script=[ResumoResult(
            resumo="Quer comprar.", slots={"bairro": "Granja"}, operacao="compra", intencoes=("visita",),
            desfecho="qualificado", custo_usd=0.02)])
        out = await _apply(world, c, LaisAction("encerrar", 1, {"motivo": "sem_interesse"}), agents=world.agents)
        assert out[0]["estado"] == "aplicada"
        contato = world.rows("lais_contatos")[0]
        assert contato["gen"] == 1 and contato["encerrado_at"]
        inter = world.rows("lais_interacoes")[0]
        assert inter["id"] == i["id"] and inter["encerrada_at"]
        assert (inter["resumo"], inter["slots"], inter["intencoes"], inter["desfecho"], inter["operacao"]) == (
            "Quer comprar.", {"bairro": "Granja"}, ["visita"], "qualificado", "compra")
        conv, req = world.agents.resumos[0]
        assert conv == CONV and [p["chave"] for p in req.perguntas] == ["bairro", "orcamento"]
        assert req.desde is not None
        assert contatos.interacao_aberta(world.sw, c["id"]) is None
        assert world.rows("lais_acoes_aplicadas")[0]["resultado"]["motivo"] == "sem_interesse"

    async def test_encerrar_invalidates_queued_jobs(self, world):
        c = _mk_contato(world)
        contatos.abrir_interacao(world.sw, ORG, c)
        job = contatos.payload_job(world.rows("lais_contatos")[0], "lead:k")
        await _apply(world, c, LaisAction("encerrar", 1, {"motivo": "outro"}))
        assert contatos.job_obsoleto(world.sw, ORG, c["id"], job["gen"]) is True

    async def test_a_failed_resumo_still_closes_the_episode_and_reports_it(self, world):
        c = _mk_contato(world)
        contatos.abrir_interacao(world.sw, ORG, c)
        agents = FakeAgentsClient(resumo_script=[AgentsUpstreamError(code="llm_upstream")])
        await _apply(world, c, LaisAction("encerrar", 1, {"motivo": "outro"}), agents=agents)
        inter = world.rows("lais_interacoes")[0]
        assert inter["encerrada_at"] and inter["resumo"] is None
        ev = world.rows("lais_eventos")
        assert [e["tipo"] for e in ev] == ["resumo_falhou"] and ev[0]["payload"]["codigo"] == "llm_upstream"

    async def test_encerrar_with_an_unknown_motivo_is_recorded_as_outro(self, world):
        c = _mk_contato(world)
        await _apply(world, c, LaisAction("encerrar", 1, {"motivo": "porque_sim"}))
        assert world.rows("lais_acoes_aplicadas")[0]["resultado"]["motivo"] == "outro"

    async def test_closing_twice_is_a_noop(self, world):
        c = _mk_contato(world)
        i = contatos.abrir_interacao(world.sw, ORG, c)
        agents = FakeAgentsClient()
        done = await acoes.fechar_interacao(world.sw, org_id=ORG, contato=c, interacao=i, agents_client=agents, conversation_id=CONV)
        again = await acoes.fechar_interacao(world.sw, org_id=ORG, contato=c, interacao=done, agents_client=agents, conversation_id=CONV)
        assert len(agents.resumos) == 1 and again["encerrada_at"] == done["encerrada_at"]

    async def test_closing_without_a_conversation_or_client_skips_the_summary_but_closes(self, world):
        c = _mk_contato(world)
        i = contatos.abrir_interacao(world.sw, ORG, c)
        await acoes.fechar_interacao(world.sw, org_id=ORG, contato=c, interacao=i, agents_client=None, conversation_id=None)
        assert world.rows("lais_interacoes")[0]["encerrada_at"] and world.rows("lais_eventos") == []

    async def test_a_ledger_failure_never_raises_into_the_caller(self, world, caplog):
        c = _mk_contato(world)

        class Boom:
            def table(self, _):
                raise RuntimeError("db down")

        with caplog.at_level("ERROR"):
            out = await acoes.aplicar(
                Boom(), org_id=ORG, contato=c, result=_turn(LaisAction("salvar_slots", 1, {"slots": {}})),
                lote_hash="L1", agents_client=None,
            )
        assert out == [{"seq": 1, "tipo": "salvar_slots", "estado": "falhou"}]

    def test_lote_hash_is_deterministic_and_batch_specific(self):
        assert acoes.lote_hash_de(CONV, ["a", "b"]) == acoes.lote_hash_de(CONV, ["a", "b"])
        assert acoes.lote_hash_de(CONV, ["a", "b"]) != acoes.lote_hash_de(CONV, ["a", "c"])
        assert acoes.lote_hash_de(CONV, ["a"]) != acoes.lote_hash_de("other", ["a"])


# ── through the lead worker ─────────────────────────────────────────────────
async def _run(world: World, key: str, **over):
    await process_lead_batch(key, world.buffer.memory_for(key), deps=world.deps(**over))


@pytest.mark.asyncio
class TestWorkerIntegration:
    async def test_the_turn_carries_the_contexto_and_the_contato_and_episode_exist(self, world):
        world.agents = FakeAgentsClient()
        await _run(world, buffer_lead(world, LEAD_CHAT, ["Oi"]))
        req = world.agents.turns[0]
        assert req.contexto is not None and len(req.contexto["hash"]) == 64
        contato = world.contato()
        assert contato["gen"] == 1 and contato["ultimo_inbound_at"] and contato["ultimo_outbound_at"]
        assert contato["org_id"] == ORG and contato["telefone_e164"] == "+5511988887777" and contato["nome"] == "Ana"
        inter = world.rows("lais_interacoes", contato_id=contato["id"])
        assert len(inter) == 1 and inter[0]["encerrada_at"] is None
        assert req.contexto["estado"]["interacao_id"] == inter[0]["id"]
        assert req.contexto["estado"]["encerrado"] is False

    async def test_every_inbound_batch_bumps_gen_and_keeps_one_episode(self, world):
        world.agents = FakeAgentsClient()
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        buffer_lead(world, LEAD_CHAT, ["quero alugar"], ids=["m2"])
        await _run(world, k)
        assert world.contato()["gen"] == 2
        assert len(world.rows("lais_interacoes")) == 1 and len(world.rows("lais_contatos")) == 1

    async def test_actions_are_applied_after_the_reply_went_out(self, world):
        class Recorder(FakeAgentsClient):
            pass

        order: list[str] = []
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=("Anotado!",), status="respondido",
            actions=(LaisAction("salvar_slots", 1, {"slots": {"nome": "Ana Teste"}}),
                     LaisAction("definir_operacao", 2, {"operacao": "compra"})),
        )])
        # the action ledger must not exist yet when the bubble is sent: capture it at send time
        original = world.waha.send_text

        async def send_text(*a, **kw):
            order.append(f"send:{len(world.rows('lais_acoes_aplicadas'))}")
            return await original(*a, **kw)

        world.waha.send_text = send_text
        await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]))
        assert order and all(o == "send:0" for o in order)  # disclosure + reply both precede the ledger
        c = world.contato()
        assert (c["nome"], c["operacao"]) == ("Ana Teste", "compra")
        assert len(world.rows("lais_acoes_aplicadas")) == 2

    async def test_a_replayed_batch_does_not_apply_its_actions_twice(self, world):
        acao = LaisAction("salvar_slots", 1, {"slots": {"nome": "Ana Teste"}})
        r = TurnResult(conversation_id=CONV, partes=("ok",), status="respondido", actions=(acao,))
        world.agents = FakeAgentsClient([r, r])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        # same provider ids come back (agents replays) -> same lote_hash -> ledger refuses a second apply
        from app.services import lais_acoes_service

        before = world.rows("lais_acoes_aplicadas")
        out = await lais_acoes_service.aplicar(
            world.sw, org_id=ORG, contato=world.contato(), result=r,
            lote_hash=lais_acoes_service.lote_hash_de(CONV, ["m1"]), conversation_id=CONV,
        )
        assert [o["estado"] for o in out] == ["repetida"] and world.rows("lais_acoes_aplicadas") == before

    async def test_a_silent_turn_with_actions_still_applies_them(self, world):
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=(), status="silencio",
            actions=(LaisAction("salvar_slots", 1, {"slots": {"nome": "Ana Teste"}}),))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["..."]))
        assert world.sent_texts() == [] and world.contato()["nome"] == "Ana Teste"

    async def test_an_action_without_a_handler_never_drops_the_reply(self, world):
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=("Vou agendar!",), status="respondido",
            actions=(LaisAction("captacao", 1, {"codigo_imovel": "X1"}),))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero visitar"]))
        assert world.sent_texts()[-1] == "Vou agendar!"
        assert [e["tipo"] for e in world.rows("lais_eventos")] == ["acao_sem_handler"]

    async def test_an_encerrar_turn_closes_the_episode_and_the_next_inbound_opens_a_new_one(self, world):
        world.agents = FakeAgentsClient([
            TurnResult(conversation_id=CONV, partes=("Até logo!",), status="encerrado",
                       actions=(LaisAction("encerrar", 1, {"motivo": "lead_encerrou"}),)),
            TurnResult(conversation_id=CONV, partes=("De volta!",), status="respondido"),
        ])
        k = buffer_lead(world, LEAD_CHAT, ["tchau"], ids=["m1"])
        await _run(world, k)
        assert world.contato()["encerrado_at"] and len(world.agents.resumos) == 1
        assert world.rows("lais_interacoes")[0]["encerrada_at"]
        buffer_lead(world, LEAD_CHAT, ["voltei"], ids=["m2"])
        await _run(world, k)
        inter = world.rows("lais_interacoes")
        assert len(inter) == 2 and sum(1 for i in inter if i["encerrada_at"] is None) == 1
        assert world.contato()["encerrado_at"] is None
        assert world.agents.turns[1].contexto["estado"]["encerrado"] is False
        assert world.agents.turns[1].contexto["estado"]["interacao_id"] != world.agents.turns[0].contexto["estado"]["interacao_id"]

    async def test_an_inbound_after_24h_of_silence_closes_the_old_episode_with_a_summary_and_opens_a_new_one(self, world):
        world.agents = FakeAgentsClient()
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        contatos.atualizar_contato(world.sw, world.contato()["id"], {"ultimo_inbound_at": old, "ultimo_outbound_at": old})
        world.chat_row()  # the conversation id is stored after the first reply
        buffer_lead(world, LEAD_CHAT, ["oi de novo"], ids=["m2"])
        await _run(world, k)
        inter = sorted(world.rows("lais_interacoes"), key=lambda r: r["iniciada_at"])
        assert len(inter) == 2 and inter[0]["encerrada_at"] and inter[1]["encerrada_at"] is None
        assert len(world.agents.resumos) == 1 and world.agents.resumos[0][0] == world.chat_row()["agente_conversation_id"]
        assert world.agents.turns[1].contexto["estado"]["interacao_id"] == inter[1]["id"]

    async def test_a_foundation_failure_runs_the_turn_with_page_0_behaviour(self, world, caplog):
        world.agents = FakeAgentsClient()

        class Boom:
            def table(self, _):
                raise RuntimeError("db down")

        with caplog.at_level("ERROR"):
            await _run(world, buffer_lead(world, LEAD_CHAT, ["oi"]), scoped=_Split(world, Boom()))
        assert world.agents.turns[0].contexto is None and world.sent_texts()
        assert "foundation prep failed" in caplog.text

    async def test_handoff_bumps_gen_so_queued_jobs_go_stale(self, world):
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=("Já chamo alguém",), status="handoff", actions=(HandoffAction("quer humano"),))])
        await _run(world, buffer_lead(world, LEAD_CHAT, ["quero falar com gente"]))
        assert world.contato()["gen"] == 2  # +1 inbound, +1 handoff

    async def test_a_paused_chat_gets_no_turn_but_the_inbound_still_counts(self, world):
        world.agents = FakeAgentsClient()
        world.sw.table("whatsapp_chats").update({"agente_pausado": True}).eq("connection_id", CONNECTION_ID).execute()
        await _run(world, buffer_lead(world, LEAD_CHAT, ["alguém aí?"]))
        assert world.agents.turns == []
        c = world.contato()
        assert c["gen"] == 1 and c["ultimo_inbound_at"] and world.rows("lais_interacoes") == []

    async def test_deletion_on_request_removes_the_lais_rows_of_the_chat_only(self, world):
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id=CONV, partes=("oi",), status="respondido",
            actions=(LaisAction("pedido_visita", 1, {}),))])
        k = buffer_lead(world, LEAD_CHAT, ["oi"], ids=["m1"])
        await _run(world, k)
        other = _mk_contato(world, "outra-pessoa@c.us")
        contatos.abrir_interacao(world.sw, ORG, other)
        mine = world.contato()["id"]
        assert world.rows("lais_interacoes", contato_id=mine) and world.rows("lais_acoes_aplicadas", contato_id=mine)
        buffer_lead(world, LEAD_CHAT, ["apagar meus dados"], ids=["m2"])
        await _run(world, k)
        assert world.contato() is None
        for t in ("lais_interacoes", "lais_acoes_aplicadas", "lais_eventos"):
            assert [r for r in world.rows(t) if r["contato_id"] == mine] == []
        assert [r["id"] for r in world.rows("lais_contatos")] == [other["id"]]
        assert world.rows("lais_interacoes")[0]["contato_id"] == other["id"]


class _Split:
    """A scoped client whose lais tables fail but everything else works (the foundation must
    degrade, the page-0 path must not)."""

    def __init__(self, world, boom):
        self._w, self._boom = world, boom

    def table(self, name):
        if name.startswith("lais_contatos") or name.startswith("lais_interacoes"):
            return self._boom.table(name)
        return self._w.sw.table(name)

    def __getattr__(self, item):
        return getattr(self._w.sw, item)
