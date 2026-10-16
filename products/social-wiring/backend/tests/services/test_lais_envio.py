"""Lais wave 3 -- Envio ao SW (contract 5): the idempotent send, the rule table, the policies, the cold timer's
stale guard, and the foundation registries it binds. Seams are the Fakes the seed/product ship (mock DB,
`FakeJobRepository`); the one DB double that misbehaves on purpose (`FaultyClient`) is a thin delegating wrapper,
nothing of ours is patched. The mock has no triggers, so the funil card the real `spawn_funil_card` trigger creates
is asserted through its cause: exactly ONE `leads` INSERT per phone (one lead = one card). No personal data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import LaisAction, TurnResult
from app.services import lais_acoes_service as acoes
from app.services import lais_contatos_service as contatos
from app.services import lais_contexto_service as contexto
from app.services import lais_envio_criterios as crit
from app.services import lais_envio_service as envio
from app.services import lais_perguntas_service as perguntas

from tests.support.lais_world import CONNECTION_ID, LEAD_CHAT, ORG_ID as ORG, World

SP = envio.FUSO
MANHA = datetime(2026, 10, 15, 10, 0, tzinfo=SP).astimezone(timezone.utc)
FONE = "+5511988887777"
CONV = "00000000-0000-4000-8000-0000000000c0"
GRUPO_BASE = [{"campo": "comportamento", "operador": "=", "valor": "qualificado"}]
REGRA_BASE = [GRUPO_BASE]


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    for t in (envio.T_REGRAS, envio.T_POLITICAS, envio.T_ENTREGAS, "leads", "lead_sources", "lead_source_aliases",
              "cliente_notas", "clientes", "cliente_touches", "atendimentos"):
        w.sw.set_table_data(t, [])
    w.sw.set_table_data("lais_perguntas_catalogo", [
        {"chave": k, "label": k, "categoria": "lead", "ordem": i, "sensivel": None, "operacao": None}
        for i, k in enumerate(("objetivo", "orcamento", "quartos", "renda_familiar", "cpf", "codigo_imovel"))
    ])
    return w


@pytest.fixture
def client_provider(world):
    envio.registrar_client_provider(lambda: world.sw)
    yield
    envio.registrar_client_provider(None)


@pytest.fixture
def repo():
    r = FakeJobRepository()
    envio.registrar_repo(r)
    yield r
    envio.registrar_repo(None)


def _contato(world: World, chat: str = LEAD_CHAT, fone: str | None = FONE, **over) -> dict:
    c = contatos.obter_ou_criar_contato(world.sw, org_id=ORG, connection_id=CONNECTION_ID, chat_id=chat,
                                        telefone_e164=fone, nome="Ana Exemplo")
    if over:
        contatos.atualizar_contato(world.sw, c["id"], over)
    return world.contato(chat)


def _regras(world: World, grupos=None, *, diferenciar=False) -> dict:
    grupos = grupos or REGRA_BASE
    regras = ([{"operacao": "compra", "grupos": grupos}, {"operacao": "aluguel", "grupos": grupos}]
              if diferenciar else [{"operacao": "ambas", "grupos": grupos}])
    return envio.substituir_regras(world.sw, ORG, diferenciar, regras)


class FaultyClient:
    """The schema client, except `leads` refuses writes while `quebrado` -- a DB outage on one table."""

    def __init__(self, inner: Any) -> None:
        self._inner, self.quebrado = inner, True

    def table(self, nome: str):
        if self.quebrado and nome == "leads":
            raise RuntimeError("leads table unavailable")
        return self._inner.table(nome)

    def __getattr__(self, item):
        return getattr(self._inner, item)


# ── idempotency: one lead (= one card) per phone per org ────────────────────
class TestIdempotencia:
    def test_two_triggers_for_one_contato_are_one_lead_one_note_one_ledger_row(self, world):
        c = _contato(world, operacao="compra", slots={"orcamento": "500000"})
        a = envio.enviar(world.sw, ORG, c, "qualificado")
        b = envio.enviar(world.sw, ORG, c, "visita")
        assert (a["criado"], a["ja_enviado"], a["status_envio"]) == (True, False, "enviado")
        assert (b["ja_enviado"], b["lead_id"]) == (True, a["lead_id"])
        assert len(world.rows("leads")) == 1
        assert len(world.rows("cliente_notas")) == 1
        assert [e["status"] for e in world.rows(envio.T_ENTREGAS)] == ["ok"]
        assert [e["tipo"] for e in world.rows("lais_eventos")] == ["novo_lead"]
        assert world.contato()["lead_id"] == a["lead_id"]

    def test_the_lead_carries_the_julia_source_phone_and_the_slots_as_its_first_note(self, world):
        c = _contato(world, operacao="compra", slots={"orcamento": "500000", "cpf": "sha256:x|final:123", "codigo_imovel": "AP0042"})
        envio.enviar(world.sw, ORG, c, "qualificado")
        lead = world.rows("leads")[0]
        src = world.rows("lead_sources", slug="julia")
        assert len(src) == 1 and lead["origem_id"] == src[0]["id"]
        assert (lead["contato_norm"], lead["cliente_nome"], lead["codigo_imovel"]) == (FONE, "Ana Exemplo", "AP0042")
        nota = world.rows("cliente_notas")[0]["corpo"]
        assert "orcamento: 500000" in nota and "operação: compra" in nota
        assert "sha256" not in nota and "cpf" not in nota  # sensitive slots never leave the contato

    def test_the_julia_source_row_is_created_once_per_org(self, world):
        envio.enviar(world.sw, ORG, _contato(world), "manual")
        envio.enviar(world.sw, ORG, _contato(world, chat="5511977776666@c.us", fone="+5511977776666"), "manual")
        assert len(world.rows("lead_sources", slug="julia")) == 1 and len(world.rows("leads")) == 2

    def test_an_existing_sw_lead_with_the_same_phone_is_attached_never_duplicated(self, world):
        world.sw.table("leads").insert({
            "id": "00000000-0000-4000-8000-000000000a01", "org_id": ORG, "data_entrada": "2026-10-01", "tipo_lead": "novo",
            "needs_review": False, "cliente_nome": None, "contato": "(11) 98888-7777", "contato_norm": FONE,
            "contato_tipo": "telefone", "observacoes": "nota antiga", "created_at": "2026-10-01T00:00:00+00:00",
        }).execute()
        c = _contato(world, slots={"codigo_imovel": "AP0042"})
        r = envio.enviar(world.sw, ORG, c, "qualificado")
        assert (r["criado"], r["lead_id"]) == (False, "00000000-0000-4000-8000-000000000a01")
        lead = world.rows("leads")
        assert len(lead) == 1
        assert lead[0]["cliente_nome"] == "Ana Exemplo" and lead[0]["codigo_imovel"] == "AP0042"  # filled, not overwritten
        assert lead[0]["observacoes"].startswith("nota antiga") and "Lead enviado pela Julia" in lead[0]["observacoes"]
        assert world.contato()["lead_id"] == r["lead_id"]

    def test_a_contato_already_linked_to_a_lead_keeps_that_lead(self, world):
        lead = "00000000-0000-4000-8000-000000000a09"
        c = _contato(world, lead_id=lead)
        r = envio.enviar(world.sw, ORG, c, "visita")
        assert (r["lead_id"], r["criado"], r["ja_enviado"]) == (lead, False, False)
        assert world.rows("leads") == [] and world.contato()["status_envio"] == "enviado_auto"

    def test_two_chats_of_the_same_phone_share_one_lead(self, world):
        a = envio.enviar(world.sw, ORG, _contato(world), "manual")
        b = envio.enviar(world.sw, ORG, _contato(world, chat="outro@c.us", fone="55 11 98888-7777"), "manual")
        assert (a["criado"], b["criado"]) == (True, False) and a["lead_id"] == b["lead_id"]
        assert len(world.rows("leads")) == 1

    def test_the_phone_falls_back_to_the_c_us_chat_id(self, world):
        c = _contato(world, fone=None)
        assert envio.telefone_do_contato(c) == FONE
        assert envio.enviar(world.sw, ORG, c, "manual")["criado"] is True

    def test_a_contato_without_a_phone_is_422_status_erro_and_a_ledger_row(self, world):
        c = _contato(world, chat="sem-telefone@lid", fone=None)
        with pytest.raises(AppException) as e:
            envio.enviar(world.sw, ORG, c, "manual")
        assert (e.value.code, e.value.status_code) == ("contato_sem_telefone", 422)
        assert world.contato("sem-telefone@lid")["status_envio"] == "erro"
        assert [(x["status"], x["erro"]) for x in world.rows(envio.T_ENTREGAS)] == [("erro", "contato_sem_telefone")]
        assert world.rows("leads") == []

    def test_a_failed_create_is_502_status_erro_and_the_retry_succeeds(self, world):
        faulty = FaultyClient(world.sw)
        c = _contato(world)
        with pytest.raises(AppException) as e:
            envio.enviar(faulty, ORG, c, "manual")
        assert (e.value.code, e.value.status_code) == ("envio_falhou", 502)
        row = world.contato()
        assert row["status_envio"] == "erro" and row.get("lead_id") is None
        assert world.rows(envio.T_ENTREGAS)[0]["erro"].startswith("envio_falhou: RuntimeError")
        faulty.quebrado = False
        ok = envio.enviar(faulty, ORG, world.contato(), "manual")
        assert ok["criado"] and world.contato()["status_envio"] == "enviado" and len(world.rows("leads")) == 1

    def test_status_depends_on_the_trigger(self, world):
        assert envio.enviar(world.sw, ORG, _contato(world), "frio")["status_envio"] == "enviado_auto"
        assert envio.enviar(world.sw, ORG, _contato(world, chat="b@c.us", fone="+5511911112222"), "qualificado")["status_envio"] == "enviado"

    def test_another_orgs_contato_is_not_found(self, world):
        c = _contato(world)
        with pytest.raises(AppException) as e:
            envio.enviar(world.sw, "00000000-0000-4000-8000-0000000000f1", c, "manual")
        assert e.value.status_code == 404


# ── the criteria vocabulary ─────────────────────────────────────────────────
def _ctt(**kw):
    return {"operacao": kw.pop("operacao", None), "nome": kw.pop("nome", "Ana"), "email": kw.pop("email", None), "slots": kw}


def _c(campo, operador, valor=None):
    return {"campo": campo, "operador": operador, "valor": valor}


AVALIACAO = [
    # (case id, grupos, contato, qualificado, visita, esperado)
    ("base_qualificado", [GRUPO_BASE], _ctt(), True, False, True),
    ("base_nao_qualificado", [GRUPO_BASE], _ctt(), False, False, False),
    ("e_dentro_do_grupo", [[*GRUPO_BASE, _c("orcamento", ">=", 300000)]], _ctt(orcamento="500000"), True, False, True),
    ("e_falha_um", [[*GRUPO_BASE, _c("orcamento", ">=", 300000)]], _ctt(orcamento="100000"), True, False, False),
    ("ou_entre_grupos", [[*GRUPO_BASE, _c("orcamento", ">=", 900000)], [_c("visita_solicitada", "=", True)]], _ctt(orcamento="1"), False, True, True),
    ("ou_nenhum", [[*GRUPO_BASE, _c("orcamento", ">=", 900000)], [_c("visita_solicitada", "=", True)]], _ctt(orcamento="1"), True, False, False),
    ("preenchido_sim", [[_c("quartos", "preenchido")]], _ctt(quartos="3"), False, False, True),
    ("preenchido_vazio", [[_c("quartos", "preenchido")]], _ctt(quartos="  "), False, False, False),
    ("preenchido_ausente", [[_c("quartos", "preenchido")]], _ctt(), False, False, False),
    ("preenchido_nome_coluna", [[_c("nome", "preenchido")]], _ctt(nome="Ana"), False, False, True),
    ("preenchido_email_ausente", [[_c("email", "preenchido")]], _ctt(), False, False, False),
    ("maior_igual_borda", [[_c("orcamento", ">=", 500000)]], _ctt(orcamento="500000"), False, False, True),
    ("maior_igual_abaixo", [[_c("orcamento", ">=", 500000)]], _ctt(orcamento="499999"), False, False, False),
    ("menor_igual_borda", [[_c("orcamento", "<=", 500000)]], _ctt(orcamento="500000"), False, False, True),
    ("menor_igual_acima", [[_c("orcamento", "<=", 500000)]], _ctt(orcamento="500001"), False, False, False),
    ("entre_dentro", [[_c("orcamento", "entre", [300000, 600000])]], _ctt(orcamento="450000"), False, False, True),
    ("entre_bordas", [[_c("orcamento", "entre", [300000, 600000])]], _ctt(orcamento="600000"), False, False, True),
    ("entre_fora", [[_c("orcamento", "entre", [300000, 600000])]], _ctt(orcamento="600001"), False, False, False),
    ("numero_pt_br", [[_c("orcamento", ">=", 1500)]], _ctt(orcamento="R$ 1.500,00"), False, False, True),
    ("numero_mil", [[_c("orcamento", ">=", 900000)]], _ctt(orcamento="900 mil"), False, False, True),
    ("numerico_nao_numero", [[_c("orcamento", ">=", 1)]], _ctt(orcamento="depende"), False, False, False),
    ("numerico_ausente", [[_c("orcamento", "<=", 1)]], _ctt(), False, False, False),
    ("visita_sim", [[_c("visita_solicitada", "=", True)]], _ctt(), False, True, True),
    ("visita_nao", [[_c("visita_solicitada", "=", True)]], _ctt(), True, False, False),
    ("operacao_igual", [[_c("operacao", "=", "compra")]], _ctt(operacao="compra"), False, False, True),
    ("operacao_diferente", [[_c("operacao", "=", "compra")]], _ctt(operacao="aluguel"), False, False, False),
    ("sem_grupos", [], _ctt(), True, True, False),
    ("grupo_vazio", [[]], _ctt(), True, True, False),
]


class TestAvaliacao:
    @pytest.mark.parametrize("grupos,contato,qual,visita,esperado", [a[1:] for a in AVALIACAO], ids=[a[0] for a in AVALIACAO])
    def test_rule_table(self, grupos, contato, qual, visita, esperado):
        assert crit.avaliar(grupos, contato, qualificado=qual, visita=visita) is esperado

    def test_a_malformed_stored_rule_never_matches(self):
        assert crit.avaliar("x", _ctt(), qualificado=True) is False
        assert crit.avaliar([["x"]], _ctt(), qualificado=True) is False


CHAVES = {"objetivo", "orcamento", "quartos", "renda_familiar", "cpf"}


class TestValidacao:
    def test_a_valid_rule_is_normalised(self):
        out = crit.validar_grupos([[*GRUPO_BASE, _c("orcamento", "entre", ["300000", "R$ 600.000,00"])], [_c("quartos", "preenchido", "lixo")]], CHAVES)
        assert out[0][1] == {"campo": "orcamento", "operador": "entre", "valor": [300000.0, 600000.0]}
        assert out[1] == [{"campo": "quartos", "operador": "preenchido", "valor": None}]

    @pytest.mark.parametrize("grupos,code", [
        ("x", "grupos_invalidos"), ([], "grupos_invalidos"), ([[]], "grupos_invalidos"), ([[GRUPO_BASE[0]]] * 11, "grupos_invalidos"),
        ([[_c("orcamento", "preenchido")]], "base_obrigatoria"),
        ([[*GRUPO_BASE, _c("inventado", "preenchido")]], "campo_desconhecido"),
        ([[*GRUPO_BASE, _c("orcamento", "!=", 1)]], "operador_invalido"),
        ([[*GRUPO_BASE, _c("orcamento", ">=", "muito")]], "valor_invalido"),
        ([[*GRUPO_BASE, _c("orcamento", "entre", [5, 1])]], "valor_invalido"),
        ([[*GRUPO_BASE, _c("orcamento", "entre", [1])]], "valor_invalido"),
        ([[*GRUPO_BASE, _c("cpf", ">=", 1)]], "campo_sensivel"),
        ([[*GRUPO_BASE, _c("renda_familiar", "entre", [1, 2])]], "campo_sensivel"),
        ([[*GRUPO_BASE, _c("nome", ">=", 1)]], "campo_sensivel"),
        ([[{"campo": "comportamento", "operador": "=", "valor": "frio"}]], "criterio_invalido"),
        ([[*GRUPO_BASE, _c("visita_solicitada", "=", False)]], "criterio_invalido"),
        ([[*GRUPO_BASE, _c("operacao", "=", "venda")]], "criterio_invalido"),
        ([[*GRUPO_BASE, {"campo": "orcamento", "operador": ">=", "valor": 1, "extra": 1}]], "criterio_invalido"),
    ])
    def test_typed_422(self, grupos, code):
        with pytest.raises(AppException) as e:
            crit.validar_grupos(grupos, CHAVES)
        assert (e.value.code, e.value.status_code) == (code, 422)

    def test_chaves_usadas_ignores_the_fixed_fields(self):
        g = [[*GRUPO_BASE, _c("orcamento", ">=", 1)], [_c("visita_solicitada", "=", True), _c("operacao", "=", "compra"), _c("quartos", "preenchido")]]
        assert crit.chaves_usadas(g) == {"orcamento", "quartos"} and crit.usa_visita(g) and not crit.usa_visita(REGRA_BASE)


# ── rules CRUD ──────────────────────────────────────────────────────────────
class TestRegras:
    def test_empty_org_has_no_rule(self, world):
        assert envio.montar_regras(world.sw, ORG) == {"diferenciar": False, "regras": []}
        assert envio.org_tem_regra(world.sw, ORG) is False

    def test_one_shared_rule_then_split_replaces_ambas(self, world):
        assert _regras(world)["regras"] == [{"operacao": "ambas", "grupos": REGRA_BASE, "versao": 1}]
        out = _regras(world, [[*GRUPO_BASE, _c("orcamento", ">=", 1)]], diferenciar=True)
        assert out["diferenciar"] is True and sorted(r["operacao"] for r in out["regras"]) == ["aluguel", "compra"]
        assert len(world.rows(envio.T_REGRAS)) == 2

    def test_version_bumps_only_when_the_groups_change(self, world):
        _regras(world)
        assert _regras(world)["regras"][0]["versao"] == 1
        assert _regras(world, [[*GRUPO_BASE, _c("quartos", "preenchido")]])["regras"][0]["versao"] == 2

    @pytest.mark.parametrize("diferenciar,regras", [
        (True, [{"operacao": "compra", "grupos": REGRA_BASE}]),
        (True, [{"operacao": "ambas", "grupos": REGRA_BASE}]),
        (False, [{"operacao": "compra", "grupos": REGRA_BASE}]),
        (False, [{"operacao": "ambas", "grupos": REGRA_BASE}, {"operacao": "ambas", "grupos": REGRA_BASE}]),
    ])
    def test_the_operation_set_must_match_the_checkbox(self, world, diferenciar, regras):
        with pytest.raises(AppException) as e:
            envio.substituir_regras(world.sw, ORG, diferenciar, regras)
        assert e.value.code == "operacoes_invalidas" and world.rows(envio.T_REGRAS) == []

    def test_an_invalid_rule_leaves_the_stored_one_untouched(self, world):
        _regras(world)
        with pytest.raises(AppException):
            envio.substituir_regras(world.sw, ORG, False, [{"operacao": "ambas", "grupos": [[_c("orcamento", "preenchido")]]}])
        assert envio.montar_regras(world.sw, ORG)["regras"][0]["grupos"] == REGRA_BASE

    def test_rule_lookup_prefers_the_operations_own_row_then_ambas(self, world):
        _regras(world, diferenciar=True)
        rows = envio.listar_regras(world.sw, ORG)
        assert envio.regra_do_contato(rows, "compra")["operacao"] == "compra"
        assert envio.regra_do_contato(rows, "administracao") is None and envio.regra_do_contato(rows, None) is None
        world.sw.set_table_data(envio.T_REGRAS, [])
        _regras(world)
        assert envio.regra_do_contato(envio.listar_regras(world.sw, ORG), "administracao")["operacao"] == "ambas"

    def test_perguntas_is_told_which_slot_keys_the_rules_use_and_locks_them(self, world):
        _regras(world, [[*GRUPO_BASE, _c("orcamento", ">=", 1)]])
        assert envio.criterios_que_usam(world.sw, ORG) == {"orcamento": ["Compra e aluguel · grupo 1"]}
        world.sw.set_table_data("lais_perguntas_org", [
            {"org_id": ORG, "chave": "objetivo", "ativa": True, "qualificatoria": True},
            {"org_id": ORG, "chave": "orcamento", "ativa": True, "qualificatoria": True},
        ])
        perguntas.registrar_criterios(envio.criterios_que_usam)
        try:
            with pytest.raises(AppException) as e:
                perguntas.substituir_selecao(world.sw, ORG, [{"chave": "objetivo", "qualificatoria": True}])
            assert (e.value.code, e.value.status_code) == ("usada_em_criterio", 409)
            assert e.value.details["chaves"] == ["orcamento"]
        finally:
            perguntas.registrar_criterios(perguntas._sem_criterios)


# ── policies ────────────────────────────────────────────────────────────────
class TestPoliticas:
    def test_defaults(self, world):
        assert envio.ler_politicas(world.sw, ORG) == {
            "frios": {"ativo": False, "modo": "intervalo", "minutos": 60},
            "captacoes": "notificar", "whatsapp_invalido": False, "pesquisa": False}

    def test_a_partial_put_keeps_the_rest(self, world):
        envio.salvar_politicas(world.sw, ORG, {"captacoes": "enviar", "pesquisa": True})
        out = envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True, "minutos": 90}})
        assert out["captacoes"] == "enviar" and out["pesquisa"] is True
        assert out["frios"] == {"ativo": True, "modo": "intervalo", "minutos": 90}
        assert len(world.rows(envio.T_POLITICAS)) == 1

    @pytest.mark.parametrize("patch", [
        {"frios": {"minutos": 45}}, {"frios": {"minutos": 630}}, {"frios": {"minutos": 0}},
        {"frios": {"modo": "amanha"}}, {"captacoes": "talvez"},
    ])
    def test_typed_422(self, world, patch):
        with pytest.raises(AppException) as e:
            envio.salvar_politicas(world.sw, ORG, patch)
        assert (e.value.code, e.value.status_code) == ("politica_invalida", 422) and world.rows(envio.T_POLITICAS) == []

    def test_every_half_hour_from_30_minutes_to_10_hours_is_valid(self, world):
        for m in (30, 60, 300, 600):
            assert envio.salvar_politicas(world.sw, ORG, {"frios": {"minutos": m}})["frios"]["minutos"] == m


# ── triggers through the foundation registries ──────────────────────────────
def _turno(*acts) -> TurnResult:
    return TurnResult(conversation_id=CONV, partes=("ok",), status="respondido", actions=tuple(acts))


def _handlers() -> dict:
    h = dict(acoes.HANDLERS)
    acoes.registrar_handler("qualificar_lead", envio._h_qualificar_lead, registro=h)
    acoes.registrar_handler("captacao", envio._h_captacao, registro=h)
    return h


async def _aplicar(world, contato, *acts, lote="L1", handlers=None):
    return await acoes.aplicar(
        world.sw, org_id=ORG, contato=contato, result=_turno(*acts), lote_hash=lote, conversation_id=CONV,
        agents_client=world.agents, core_client=world.core, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT,
        handlers=handlers or _handlers(),
    )


@pytest.mark.asyncio
class TestGatilhos:
    async def test_qualificar_lead_sends_when_the_rule_matches(self, world):
        _regras(world, [[*GRUPO_BASE, _c("orcamento", ">=", 300000)]])
        c = _contato(world, operacao="compra", slots={"orcamento": "500000"})
        out = await _aplicar(world, c, LaisAction("qualificar_lead", 1, {}))
        assert out == [{"seq": 1, "tipo": "qualificar_lead", "estado": "aplicada"}]
        assert world.contato()["status_envio"] == "enviado" and len(world.rows("leads")) == 1
        assert world.rows("lais_acoes_aplicadas")[0]["resultado"]["enviado"] is True

    async def test_no_match_stays_nao_pronto(self, world):
        _regras(world, [[*GRUPO_BASE, _c("orcamento", ">=", 900000)]])
        c = _contato(world, operacao="compra", slots={"orcamento": "500000"})
        await _aplicar(world, c, LaisAction("qualificar_lead", 1, {}))
        assert world.contato()["status_envio"] == "nao_pronto" and world.rows("leads") == []
        assert world.rows("lais_acoes_aplicadas")[0]["resultado"] == {"enviado": False, "motivo": "criterios_nao_atendidos"}

    async def test_no_rule_at_all_never_sends(self, world):
        await _aplicar(world, _contato(world), LaisAction("qualificar_lead", 1, {}))
        assert world.rows("leads") == []

    async def test_the_split_rule_of_the_contatos_operation_is_the_one_applied(self, world):
        envio.substituir_regras(world.sw, ORG, True, [
            {"operacao": "compra", "grupos": [[*GRUPO_BASE, _c("orcamento", ">=", 900000)]]},
            {"operacao": "aluguel", "grupos": REGRA_BASE},
        ])
        await _aplicar(world, _contato(world, operacao="compra", slots={"orcamento": "1"}), LaisAction("qualificar_lead", 1, {}))
        assert world.rows("leads") == []
        await _aplicar(world, _contato(world, operacao="aluguel"), LaisAction("qualificar_lead", 1, {}), lote="L2")
        assert len(world.rows("leads")) == 1

    async def test_a_replayed_batch_does_not_send_twice(self, world):
        _regras(world)
        c = _contato(world, operacao="compra")
        await _aplicar(world, c, LaisAction("qualificar_lead", 1, {}))
        again = await _aplicar(world, c, LaisAction("qualificar_lead", 1, {}))
        assert again[0]["estado"] == "repetida" and len(world.rows("leads")) == 1

    async def test_qualification_then_visit_hook_is_still_one_lead(self, world, client_provider):
        _regras(world, [GRUPO_BASE, [{"campo": "visita_solicitada", "operador": "=", "valor": True}]])
        c = _contato(world, operacao="compra")
        await _aplicar(world, c, LaisAction("qualificar_lead", 1, {}))
        envio._hook_on_visita(ORG, world.contato(), {"id": "v1"})
        envio._hook_forcar_envio(ORG, world.contato(), {"id": "v1"})
        assert len(world.rows("leads")) == 1 and len(world.rows("cliente_notas")) == 1
        assert [e["gatilho"] for e in world.rows(envio.T_ENTREGAS)] == ["qualificado"]

    async def test_the_visit_hook_sends_only_when_a_rule_has_the_visit_criterion(self, world, client_provider):
        _regras(world)  # base only
        envio._hook_on_visita(ORG, _contato(world, operacao="compra"), {"id": "v1"})
        assert world.rows("leads") == []
        _regras(world, [GRUPO_BASE, [{"campo": "visita_solicitada", "operador": "=", "valor": True}]])
        envio._hook_on_visita(ORG, world.contato(), {"id": "v1"})
        assert len(world.rows("leads")) == 1 and world.rows(envio.T_ENTREGAS)[0]["gatilho"] == "visita"

    async def test_a_visit_rule_with_extra_criteria_needs_them_too(self, world, client_provider):
        _regras(world, [GRUPO_BASE, [{"campo": "visita_solicitada", "operador": "=", "valor": True}, _c("quartos", "preenchido")]])
        envio._hook_on_visita(ORG, _contato(world, operacao="compra"), {"id": "v1"})
        assert world.rows("leads") == []

    async def test_forcar_envio_sends_regardless_of_the_rules(self, world, client_provider):
        envio._hook_forcar_envio(ORG, _contato(world), {"id": "v1"})
        assert len(world.rows("leads")) == 1 and world.contato()["status_envio"] == "enviado_auto"

    async def test_captacao_notify_policy_records_the_event_only(self, world):
        out = await _aplicar(world, _contato(world), LaisAction("captacao", 1, {}))
        assert out[0]["estado"] == "aplicada" and world.rows("leads") == []
        assert [e["tipo"] for e in world.rows("lais_eventos")] == ["captacao"]

    async def test_captacao_send_policy_sends(self, world):
        envio.salvar_politicas(world.sw, ORG, {"captacoes": "enviar"})
        await _aplicar(world, _contato(world), LaisAction("captacao", 1, {}))
        assert len(world.rows("leads")) == 1 and world.rows(envio.T_ENTREGAS)[0]["gatilho"] == "captacao"
        assert {e["tipo"] for e in world.rows("lais_eventos")} == {"captacao", "novo_lead"}

    @pytest.mark.parametrize("policy,motivo,enviado", [(True, "invalido", True), (False, "invalido", False), (True, "sem_interesse", False)])
    async def test_encerrar_invalido_follows_the_whatsapp_invalido_policy(self, world, policy, motivo, enviado):
        envio.salvar_politicas(world.sw, ORG, {"whatsapp_invalido": policy})
        acoes.registrar_pos_encerrar(envio._pos_encerrar)
        try:
            await _aplicar(world, _contato(world), LaisAction("encerrar", 1, {"motivo": motivo}))
        finally:
            acoes.POS_ENCERRAR.remove(envio._pos_encerrar)
        assert bool(world.rows("leads")) is enviado
        if enviado:
            assert world.rows(envio.T_ENTREGAS)[0]["gatilho"] == "invalido"

    async def test_a_failing_pos_encerrar_hook_never_undoes_the_close(self, world):
        def boom(ctx, motivo):
            raise RuntimeError("policy exploded")

        acoes.registrar_pos_encerrar(boom)
        try:
            out = await _aplicar(world, _contato(world), LaisAction("encerrar", 1, {"motivo": "invalido"}))
        finally:
            acoes.POS_ENCERRAR.remove(boom)
        assert out[0]["estado"] == "aplicada" and world.contato()["encerrado_at"]


class TestContextoAcoes:
    def _ctx(self, world):
        return contexto.ContextoCtx(client=world.sw, org_id=ORG, contato=_contato(world))

    def test_qualificar_lead_is_dropped_when_the_org_has_no_rule(self, world):
        acoes_ = envio._prov_acoes(self._ctx(world))["acoes"]
        assert "qualificar_lead" not in acoes_
        assert acoes_ == [a for a in contexto.ACOES_LAIS if a != "qualificar_lead"]

    def test_it_is_back_once_a_rule_exists(self, world):
        _regras(world)
        assert envio._prov_acoes(self._ctx(world))["acoes"] == list(contexto.ACOES_LAIS)

    def test_registered_provider_replaces_only_the_acoes_slot(self, world):
        registro = list(contexto.PROVIDERS)
        contexto.registrar_provider("acoes", envio._prov_acoes, registro=registro)
        assert [n for n, _ in registro] == [n for n, _ in contexto.PROVIDERS]
        assert dict(registro)["acoes"] is envio._prov_acoes and dict(registro)["perguntas"] is dict(contexto.PROVIDERS)["perguntas"]


# ── cold leads ──────────────────────────────────────────────────────────────
def _jobs(repo, tipo=envio.JOB_FRIO):
    return [j for j in repo._jobs.values() if j.type == tipo]


@pytest.mark.asyncio
class TestFrios:
    async def test_policy_off_arms_nothing(self, world, repo):
        assert await envio.lead_frio(world.sw, ORG, _contato(world), agora=MANHA) is None and _jobs(repo) == []

    async def test_interval_mode_fires_after_the_configured_minutes_with_the_current_gen(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True, "minutos": 90}})
        c = _contato(world)
        c, _ = contatos.registrar_inbound(world.sw, c)
        await envio.lead_frio(world.sw, ORG, c, agora=MANHA)
        (job,) = _jobs(repo)
        assert job.scheduled_for == MANHA + timedelta(minutes=90)
        assert job.payload["gen"] == c["gen"] == 1 and job.payload["org_id"] == ORG
        assert job.payload["chat_key"] == f"lead:{CONNECTION_ID}:{LEAD_CHAT}"

    async def test_next_morning_mode_lands_between_05_and_06_sao_paulo_the_day_after(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True, "modo": "manha_seguinte"}})
        await envio.lead_frio(world.sw, ORG, _contato(world), agora=MANHA)
        quando = _jobs(repo)[0].scheduled_for.astimezone(SP)
        assert quando.date() == datetime(2026, 10, 16).date() and quando.hour == 5 and 0 <= quando.minute < 60

    async def test_late_night_still_means_the_next_calendar_morning(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True, "modo": "manha_seguinte"}})
        noite = datetime(2026, 10, 15, 23, 50, tzinfo=SP)
        quando = envio.instante_frio({"modo": "manha_seguinte"}, "c1", noite).astimezone(SP)
        assert (quando.day, quando.hour) == (16, 5)

    async def test_the_same_gen_is_armed_once(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        c = _contato(world)
        await envio.lead_frio(world.sw, ORG, c, agora=MANHA)
        await envio.lead_frio(world.sw, ORG, c, agora=MANHA)
        assert len(_jobs(repo)) == 1

    async def test_an_already_sent_contato_is_not_armed(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        assert await envio.lead_frio(world.sw, ORG, _contato(world, status_envio="enviado"), agora=MANHA) is None

    async def test_without_a_repository_the_hook_says_so(self, world):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        with pytest.raises(RuntimeError, match="job repository"):
            await envio.lead_frio(world.sw, ORG, _contato(world), agora=MANHA)

    async def test_the_fired_job_sends_with_gatilho_frio(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        await envio.lead_frio(world.sw, ORG, _contato(world), agora=MANHA)
        assert envio.executar_frio(_jobs(repo)[0], client=world.sw) == "enviado"
        assert world.rows(envio.T_ENTREGAS)[0]["gatilho"] == "frio" and world.contato()["status_envio"] == "enviado_auto"
        assert envio.executar_frio(_jobs(repo)[0], client=world.sw) == "ja_enviado" and len(world.rows("leads")) == 1

    async def test_stale_guard_an_inbound_after_arming_makes_the_job_obsolete(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        c = _contato(world)
        await envio.lead_frio(world.sw, ORG, c, agora=MANHA)
        contatos.registrar_inbound(world.sw, world.contato())  # the lead answered: gen + 1
        assert envio.executar_frio(_jobs(repo)[0], client=world.sw) == "obsoleto"
        assert world.rows("leads") == [] and world.rows(envio.T_ENTREGAS) == []

    async def test_stale_guard_encerrar_makes_the_job_obsolete(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        c = _contato(world)
        await envio.lead_frio(world.sw, ORG, c, agora=MANHA)
        contatos.bump_gen(world.sw, c["id"], encerrado_at=MANHA.isoformat())
        assert envio.executar_frio(_jobs(repo)[0], client=world.sw) == "obsoleto"

    async def test_policy_switched_off_before_it_fires(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        await envio.lead_frio(world.sw, ORG, _contato(world), agora=MANHA)
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": False}})
        assert envio.executar_frio(_jobs(repo)[0], client=world.sw) == "politica_desligada" and world.rows("leads") == []

    async def test_a_contato_without_phone_reports_the_error_outcome(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        c = _contato(world, chat="x@lid", fone=None)
        await envio.lead_frio(world.sw, ORG, c, agora=MANHA)
        assert envio.executar_frio(_jobs(repo)[0], client=world.sw) == "erro:contato_sem_telefone"

    async def test_payload_without_ids_is_invalid(self, world):
        from types import SimpleNamespace

        job = SimpleNamespace(id="j1", type=envio.JOB_FRIO, payload={"org_id": ORG})
        assert envio.executar_frio(job, client=world.sw) == "payload_invalido"

    async def test_the_registered_job_handler_builds_its_client_at_fire_time(self, world, repo):
        envio.salvar_politicas(world.sw, ORG, {"frios": {"ativo": True}})
        await envio.lead_frio(world.sw, ORG, _contato(world), agora=MANHA)
        h = envio.handlers(client_provider=lambda: world.sw)
        assert set(h) == {envio.JOB_FRIO}
        await h[envio.JOB_FRIO](_jobs(repo)[0])
        assert len(world.rows("leads")) == 1


class TestCanais:
    def test_union_of_sw_sources_lais_origins_and_stored_channels(self, world):
        from app.services import lais_leads_service as leads

        world.sw.table("lead_sources").insert({"id": "00000000-0000-4000-8000-0000000000b1", "org_id": ORG, "slug": "indicacao",
                                               "label": "Indicação", "categoria": "direto", "ativo": True, "ordem": 0}).execute()
        _contato(world, canal="ProprioNovoLais")
        out = {c["slug"]: c["label"] for c in leads.canais(world.sw, ORG)}
        assert out["indicacao"] == "Indicação" and out["GrupoZapLais"] == "Grupo Zap" and out["ProprioNovoLais"] == "Proprio Novo"
        assert all(set(c) == {"slug", "label"} for c in leads.canais(world.sw, ORG))
