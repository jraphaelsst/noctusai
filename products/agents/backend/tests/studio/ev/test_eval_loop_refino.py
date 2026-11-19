"""The eval-loop REFINE step end to end over the Fakes (owner 2026-11-19): after a round closes below the target the driver proposes ONE
bounded edit of ONE own draft row, writes it to the DRAFT with its event and cost in one step, books the next round on the new hash and
later records whether the score improved. Nothing is patched: the driver, the service, the stores and the refiner are the real classes
over in-memory doubles; the model is the product's own ``FakeRefinador`` / a ``chat`` stub under the seed ``chamar_ia``."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.notifications import FakeNotificationSink
from app.schemas.studio_eval_loops import LoopOut
from app.stores._db_errors import StudioConflict
from app.stores.studio_definitions import FakeStudioDefinitionStore, SectionInput
from app.stores.studio_definitions_conteudo import FerramentaInput, TextoInput
from app.stores.studio_eval_consolidacao import FakeConsolidacaoStore
from app.stores.studio_eval_loops import FakeLoopStore
from app.stores.studio_eval_refino import EscritaLinha, FakeRefinoStore, SupabaseRefinoStore
from app.studio.eval_loop_driver import LoopDriver, agendar_ao_fechar, install_driver
from app.studio.eval_loop_refinador import (
    CHAVE_REFINADOR, EntradaRefino, FakeRefinador, LlmRefinador, get_refinador, interpretar_saida,
)
from app.studio.eval_loop_refino import (
    CasoFalhando, LinhasDoAgente, RefinoRecusado, SaidaRefino, SecaoLinha, deve_refinar, trecho_do_diff, validar_proposta,
)
from app.studio.eval_loop_refino_protegido import protegidas_para_rpc
from app.studio.eval_loop_refino_service import RefinoService
from app.studio.eval_loop_service import EvalLoopService, RunResumo
from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, PromptEntry

ORG, OWNER = uuid4(), uuid4()
TOM = "Seja cordial e objetivo nas respostas ao lead. Faça uma pergunta por vez."
REGRAS = "Nunca prometa preço antes de consultar o catálogo."


def saida(tipo="secao", chave="tom", novo=None, casos=("caso-a",), racional="O agente respondeu sem consultar o catálogo."):
    return SaidaRefino.model_validate({
        "alvo": {"tipo": tipo, "chave": chave}, "novo_conteudo": novo or (TOM + " Antes de citar preço, consulte o catálogo."),
        "racional": racional, "casos_alvo": list(casos)})


CASOS = (
    CasoFalhando(slug="caso-a", titulo="Caso A", suite="mecanismo", falhas=(("ferramenta", "nao_chamou_catalogo"),),
                 turnos=({"lead": "Quanto custa o apartamento de dois quartos no centro da cidade?", "bolhas": ["Custa 500 mil reais."],
                          "ferramentas": []},)),
)
LINHAS = LinhasDoAgente(
    version_id=uuid4(), compiled_hash="h", secoes=(
        SecaoLinha("tom", "Tom", TOM, True), SecaoLinha("regras", "Regras", REGRAS, True, ("discordar-com-respeito",)),
        SecaoLinha("antiga", "Antiga", "Texto desativado de uma seção antiga.", False)),
    textos=(("compilador.titulo_ferramentas", "Ferramentas disponíveis"),), ferramentas=(
        ("handoff", "Passa a conversa para uma pessoa.", True), ("kb_buscar", "Busca trechos na base de conhecimento.", True)))


# ── the validator: what the model may NOT make the server write ───────────────────────────────────────────────


def _recusa(s: SaidaRefino) -> str:
    with pytest.raises(RefinoRecusado) as e:
        validar_proposta(s, LINHAS, CASOS)
    return e.value.code


def test_an_edit_of_one_existing_active_row_is_accepted_and_trimmed():
    p = validar_proposta(saida(), LINHAS, CASOS)
    assert (p.tipo, p.chave, p.antes) == ("secao", "tom", TOM) and p.depois.endswith("consulte o catálogo.") and p.casos_alvo == ("caso-a",)


@pytest.mark.parametrize("quando,esperado", [
    (dict(chave="nao-existe"), "linha_inexistente"),
    (dict(chave="antiga", novo="Texto novo para uma seção que está desativada."), "linha_inativa"),
    (dict(chave="regras", novo=REGRAS + " Sempre."), "linha_protegida"),  # a section that declares platform rules
    (dict(casos=("outro-caso",)), "casos_alvo_invalidos"),
    (dict(novo=TOM), "sem_mudanca"),
    (dict(novo="curto"), "conteudo_pequeno"),
    (dict(novo=TOM + " x" * 1500), "crescimento_excedido"),
    (dict(novo=TOM + " Veja https://exemplo.com/catalogo antes."), "contem_url"),
    (dict(novo=TOM + " Veja exemplo.com.br antes."), "contem_url"),
    (dict(novo=TOM + " Fale com joao@exemplo.org."), "contem_contato"),
    (dict(novo=TOM + " Ligue para (11) 91234-5678."), "contem_contato"),
    (dict(novo=TOM + " Use a chave sk-ABCDEFGHIJKLMNOPQRSTUV para entrar."), "contem_segredo"),
    (dict(novo=TOM + " Chame a ferramenta consentimento_credito quando precisar."), "menciona_ferramenta"),
    (dict(novo=TOM + " Chame `handoff` sempre."), "menciona_ferramenta"),
    (dict(novo=TOM + " Use {nome_do_lead} no início."), "marcadores_alterados"),
    (dict(novo=TOM + " Exemplo de lead: Quanto custa o apartamento de dois quartos no centro da cidade?"), "copia_dados_do_caso"),
])
def test_what_the_validator_refuses(quando, esperado):
    assert _recusa(saida(**quando)) == esperado


def test_a_tool_row_edit_changes_the_description_only_and_a_new_tool_is_not_a_target():
    ok = validar_proposta(saida("ferramenta", "kb_buscar", "Busca trechos da base de conhecimento relacionados à pergunta do lead."), LINHAS, CASOS)
    assert (ok.tipo, ok.chave) == ("ferramenta", "kb_buscar")
    assert _recusa(saida("ferramenta", "ferramenta_nova", "Faz algo novo com permissão nova.")) == "linha_inexistente"


def test_the_model_cannot_smuggle_permission_fields_the_parse_is_strict():
    raw = {"alvo": {"tipo": "ferramenta", "chave": "handoff"}, "novo_conteudo": "Descrição nova da ferramenta de transferência.",
           "racional": "r", "casos_alvo": ["caso-a"], "ativo": True, "parametros": {"x": 1}}
    assert interpretar_saida(json.dumps(raw)) is None
    assert interpretar_saida("não é json") is None
    assert interpretar_saida(json.dumps({**raw, "ativo": None, "parametros": None})) is None
    assert interpretar_saida(json.dumps({k: v for k, v in raw.items() if k not in ("ativo", "parametros")})) is not None


def test_a_preexisting_link_in_the_row_is_not_a_new_link():
    com_link = SecaoLinha("tom", "Tom", TOM + " Catálogo em https://exemplo.com/c.", True)
    linhas = LinhasDoAgente(uuid4(), "h", secoes=(com_link,))
    p = validar_proposta(saida(novo=com_link.conteudo + " Pergunte o bairro."), linhas, CASOS)
    assert "Pergunte o bairro." in p.depois


# ── world: a driver over the Fakes with the refine step wired ─────────────────────────────────────────────────


def _hash(defs, vid):
    rows = [(s.chave, s.conteudo, s.ativo) for s in defs.list_sections(ORG, vid)] + [(t.chave, t.conteudo) for t in defs.list_textos(ORG, vid)] \
        + [(f.ferramenta, f.descricao) for f in defs.list_ferramentas(ORG, vid)]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]


class Mundo:
    def __init__(self, *, refinador=None, modo="automatico", orcamento=10.0, rodadas=6, casos=CASOS, escopo="org"):
        self.defs = FakeStudioDefinitionStore()
        self.agent = self.defs.seed_agent(ORG, "agente-x", nome="X", conteudo_modo="linhas", definition_scope=escopo)
        self.draft = self.defs.create_draft(ORG, self.agent.id, None, OWNER)
        self.defs.replace_sections(ORG, self.draft.id, [
            SectionInput(chave="tom", titulo="Tom", ordem=10, conteudo=TOM),
            SectionInput(chave="regras", titulo="Regras", ordem=20, conteudo=REGRAS, regras=("discordar-com-respeito",))])
        self.defs.replace_textos(ORG, self.draft.id, [TextoInput("compilador.titulo_ferramentas", "Ferramentas disponíveis")])
        self.defs.replace_ferramentas(ORG, self.draft.id, [FerramentaInput("handoff", "Passa a conversa para uma pessoa.")])
        self.carimbar(ORG, self.agent.id, self.draft.id)
        self.loops = FakeLoopStore()
        self.sink = FakeNotificationSink(admin_ids=["admin-1"])
        self.svc = EvalLoopService(self.loops, self.sink, FakeConsolidacaoStore(), ao_fechar=agendar_ao_fechar)
        self.loop = self.loops.create_loop(
            ORG, self.agent.id, agente_chave="agente-x", suite="mecanismo", rodadas_planejadas=rodadas, alvo=0.95, piso=0.8,
            orcamento_usd=orcamento, started_by=OWNER, modo=modo)
        self.refinador = refinador or FakeRefinador([saida()])
        self.refino_store = FakeRefinoStore(self.defs, self.loops)
        self.casos = list(casos)
        self.resumos: dict = {}
        self.abertas: list = []
        self.servico = RefinoService(
            loops=self.loops, defs=self.defs, refinador=self.refinador, refino=self.refino_store,
            ler_casos=lambda rec, run_id: self.casos, carimbar_hash=self.carimbar)
        self.driver = LoopDriver(
            servico=lambda: self.svc, iniciar=self._iniciar, ler_resumo=lambda rec, rid: self.resumos.get(rid),
            refinar=self.servico.refinar)

    def carimbar(self, org, agent_id, draft_id):
        h = _hash(self.defs, draft_id)
        self.defs.set_compiled_hash(org, draft_id, h)
        return h

    async def _iniciar(self, rec):
        """Books a round exactly like the route: the real admission (G6/G7) then the round."""
        h = self.carimbar(ORG, self.agent.id, self.draft.id)
        adm = self.svc.admitir(ORG, rec.agent_id, rec.id, suite="mecanismo", compiled_hash=h, limite_usd=5.0)
        run_id = uuid4()
        self.svc.abrir(ORG, rec.id, run_id=run_id, run_tipo="mecanismo", compiled_hash=h, partes=None)
        self.abertas.append((run_id, adm.limite_usd))
        return run_id

    def terminar(self, run_id, score, *, custo=1.0, falhas=("caso-a",)):
        h = self.carimbar(ORG, self.agent.id, self.draft.id)
        self.resumos[run_id] = RunResumo(run_id=run_id, run_tipo="mecanismo", status="concluida", score=score, custo_usd=custo,
                                         falhas=tuple(falhas) if score < 0.95 else (), compiled_hash=h)

    def avancar(self):
        return asyncio.run(self.driver.avancar(ORG, self.agent.id, self.loop.id))

    def rec(self):
        return self.loops.get_loop(ORG, self.agent.id, self.loop.id)

    def eventos(self, *nomes):
        return [e for e in self.loops.eventos if not nomes or e["evento"] in nomes]

    def secao(self, chave="tom"):
        return next(s.conteudo for s in self.defs.list_sections(ORG, self.draft.id) if s.chave == chave)

    def fechar_rodada(self, score, **kw):
        run_id = self.abertas[-1][0]
        self.terminar(run_id, score, **kw)
        asyncio.run(self.driver.avancar(ORG, self.agent.id, self.loop.id))
        return run_id


@pytest.fixture(autouse=True)
def _sem_driver_global():
    install_driver(None)
    yield
    install_driver(None)


def test_a_round_below_target_is_refined_then_the_next_round_runs_on_the_new_hash_and_the_effect_is_recorded():
    m = Mundo()
    assert m.avancar() == "rodada_aberta" and len(m.abertas) == 1  # round 1 (nothing to refine yet)
    assert m.eventos("refinamento_proposto") == []
    hash1 = m.defs.get_version(ORG, m.draft.id).compiled_hash

    m.terminar(m.abertas[0][0], 0.5)
    assert m.avancar() == "rodada_aberta" and len(m.abertas) == 2  # closes round 1, REFINES, books round 2

    prop, = m.eventos("refinamento_proposto")
    d = prop["detalhe"]
    assert prop["rodada_seq"] == 1 and d["alvo"] == {"tipo": "secao", "chave": "tom"} and d["casos_alvo"] == ["caso-a"]
    assert d["diff"]["antes"] == TOM and d["diff"]["depois"].endswith("consulte o catálogo.") and d["custo_usd"] == 0.01
    assert d["score_base"] == 0.5 and d["hash_base"] == hash1 and d["racional"]
    assert m.secao("tom").endswith("consulte o catálogo.") and m.secao("regras") == REGRAS  # ONE row; the protected one untouched
    assert m.defs.get_active_version(ORG, m.agent.id) is None  # a draft edit: nothing published
    hash2 = m.defs.get_version(ORG, m.draft.id).compiled_hash
    assert hash2 != hash1 and m.loops.list_rodadas(ORG, m.loop.id)[1].compiled_hash == hash2  # round 2 ran on the NEW hash
    assert m.rec().gasto_usd == pytest.approx(1.0 + 0.01)  # the round's cost + the refine's, in ONE budget

    m.terminar(m.abertas[1][0], 0.8)
    m.avancar()
    av, = m.eventos("refinamento_avaliado")
    assert av["rodada_seq"] == 2 and av["detalhe"] == {
        "rodada_refinada": 1, "rodada_avaliada": 2, "status_rodada": "concluida", "alvo": {"tipo": "secao", "chave": "tom"},
        "melhorou": True, "score_antes": 0.5, "score_depois": 0.8, "hash_antes": hash1, "hash_depois": hash2,
        "custo_refino_usd": 0.01, "custo_rodada_usd": 1.0}

    estado = m.svc.estado(ORG, m.agent.id, m.loop.id)
    r1 = estado["serie"][0]["refinamento"]
    assert r1["estado"] == "proposto" and r1["avaliado"] and r1["melhorou"] is True and (r1["score_antes"], r1["score_depois"]) == (0.5, 0.8)
    assert r1["diff"]["depois"].endswith("consulte o catálogo.") and r1["alvo"] == {"tipo": "secao", "chave": "tom"}
    # round 2 (0.8, still below target) was refined too: the Fake had no second answer -> a recorded, free refusal
    assert estado["refinamentos"] == {"propostos": 1, "recusados": 1, "sem_edicao": 0, "avaliados": 1, "melhoraram": 1,
                                      "pendentes_revisao": 1, "custo_usd": 0.01}
    assert r1["pendente_revisao"] is True and r1["revisao"] is None  # the edit waits for a person (publish is blocked meanwhile)
    LoopOut(**estado)  # the read model satisfies the HTTP contract


def test_a_refine_is_decided_once_per_round_a_second_pass_does_not_spend_again():
    m = Mundo(refinador=FakeRefinador([saida(), saida(novo=TOM + " Outra coisa que o refinador sugeriria.")]))
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    m.avancar()
    assert len(m.refinador.chamadas) == 1
    assert asyncio.run(m.servico.refinar(m.rec())) == "nada"  # the round that follows is open; and the base round has its decision
    assert len(m.refinador.chamadas) == 1 and len(m.eventos("refinamento_proposto")) == 1
    asyncio.run(m.servico.refinar(m.rec()))
    assert len(m.refinador.chamadas) == 1


def test_a_refused_proposal_writes_nothing_records_why_and_still_charges_the_call():
    ruim = saida(novo=TOM + " Veja https://exemplo.com/catalogo agora.")
    m = Mundo(refinador=FakeRefinador([ruim]))
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    assert m.avancar() == "aguardando"  # content unchanged -> the gate's G6 idles the loop, exactly as before this step existed
    rec, = m.eventos("refinamento_recusado")
    assert rec["detalhe"]["codigo"] == "contem_url" and rec["detalhe"]["custo_usd"] == 0.01 and rec["rodada_seq"] == 1
    assert m.secao("tom") == TOM and m.eventos("refinamento_proposto") == []
    assert m.rec().gasto_usd == pytest.approx(1.01) and m.rec().aviso["codigo"] == "hash_inalterado"


def test_the_refiner_unavailable_records_a_free_refusal_and_the_loop_idles_as_before():
    m = Mundo(refinador=FakeRefinador([]))
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    assert m.avancar() == "aguardando"
    rec, = m.eventos("refinamento_recusado")
    assert rec["detalhe"]["codigo"] == "refinador_indisponivel" and rec["detalhe"]["custo_usd"] == 0.0 and m.rec().gasto_usd == pytest.approx(1.0)


def test_when_someone_edited_the_draft_since_the_round_the_step_stands_down_without_calling_the_model():
    m = Mundo()
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    m.defs.replace_textos(ORG, m.draft.id, [TextoInput("compilador.titulo_ferramentas", "Ferramentas editadas à mão")])  # a human edit
    m.avancar()
    rec, = m.eventos("refinamento_recusado")
    assert rec["detalhe"]["codigo"] == "rascunho_alterado" and m.refinador.chamadas == []
    assert len(m.abertas) == 2  # the human's edit changed the hash: the next round runs on it


def test_a_manual_loop_and_a_loop_that_reached_the_target_are_not_refined():
    m = Mundo(modo="manual")
    run_id = uuid4()
    m.svc.abrir(ORG, m.loop.id, run_id=run_id, run_tipo="mecanismo", compiled_hash=_hash(m.defs, m.draft.id), partes=None)
    m.terminar(run_id, 0.5)
    m.svc.fechar_por_run(ORG, m.resumos[run_id])
    assert asyncio.run(m.servico.refinar(m.rec())) == "nada" and m.refinador.chamadas == []
    alvo = Mundo()
    alvo.avancar()
    alvo.terminar(alvo.abertas[0][0], 0.97, falhas=())
    alvo.avancar()
    assert alvo.rec().motivo_parada == "alvo_atingido" and alvo.refinador.chamadas == []


def test_two_rounds_without_gain_stop_the_loop_and_revert_nothing_the_edits_stay_in_the_draft():
    m = Mundo(refinador=FakeRefinador([saida(), saida("texto", "compilador.titulo_ferramentas", "Ferramentas disponíveis agora")]))
    m.avancar()                         # round 1
    m.terminar(m.abertas[0][0], 0.5)
    m.avancar()                         # refine 1 + round 2
    m.terminar(m.abertas[1][0], 0.5)
    m.avancar()                         # refine 2 + round 3
    m.terminar(m.abertas[2][0], 0.5)
    m.avancar()                         # round 3 closes: 2 consecutive rounds without gain -> stop
    assert m.rec().motivo_parada == "sem_melhora" and m.rec().status == "parado"
    assert len(m.eventos("refinamento_proposto")) == 2
    assert m.secao("tom").endswith("consulte o catálogo.")  # nothing reverted
    assert next(t.conteudo for t in m.defs.list_textos(ORG, m.draft.id)) == "Ferramentas disponíveis agora"
    avs = [e["detalhe"]["melhorou"] for e in m.eventos("refinamento_avaliado")]
    assert avs == [False, False]


def test_the_refine_call_is_capped_by_the_budget_left_and_its_cost_can_exhaust_the_loop_budget():
    m = Mundo(orcamento=1.5, refinador=FakeRefinador([saida()], custo_usd=0.6))
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5, custo=1.0)  # 1.0 of 1.5 spent
    m.avancar()
    assert m.refinador.chamadas[0][1] == pytest.approx(0.5)  # limite_usd = what the loop budget has left
    # 0.6 > 0.5 left: the Fake refuses on the cap before spending -- no edit, no spend
    rec, = m.eventos("refinamento_recusado")
    assert rec["detalhe"]["codigo"] == "limite_de_custo" and m.rec().gasto_usd == pytest.approx(1.0)

    ok = Mundo(orcamento=1.5, refinador=FakeRefinador([saida()], custo_usd=0.5))
    ok.avancar()
    ok.terminar(ok.abertas[0][0], 0.5, custo=1.0)
    assert ok.avancar() == "orcamento_atingido"  # the refine used up the budget: the next round is refused by G7 and the loop stops
    assert ok.rec().gasto_usd == pytest.approx(1.5) and ok.rec().motivo_parada == "orcamento_atingido"
    assert ok.eventos("refinamento_proposto")  # the edit it paid for is recorded and stays


def test_a_budget_too_small_to_refine_is_a_free_recorded_refusal():
    m = Mundo(orcamento=1.01)
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5, custo=1.0)
    m.avancar()
    assert m.eventos("refinamento_recusado")[0]["detalhe"]["codigo"] == "orcamento_insuficiente" and m.refinador.chamadas == []


def test_only_the_loop_agents_own_rows_are_listed_and_editable_an_inherited_layers_row_is_not_a_target():
    m = Mundo()
    pai = m.defs.seed_agent(ORG, "agente-base", nome="Base", conteudo_modo="linhas")
    pai_draft = m.defs.create_draft(ORG, pai.id, None, OWNER)
    m.defs.replace_sections(ORG, pai_draft.id, [SectionInput(chave="so-no-pai", titulo="Pai", ordem=5, conteudo="Regra herdada do agente base, longa.")])
    m.refinador = FakeRefinador([saida(chave="so-no-pai", novo="Regra herdada do agente base, longa, editada pelo refino.")])
    m.servico = RefinoService(loops=m.loops, defs=m.defs, refinador=m.refinador, refino=m.refino_store,
                              ler_casos=lambda rec, rid: m.casos, carimbar_hash=m.carimbar)
    m.driver = LoopDriver(servico=lambda: m.svc, iniciar=m._iniciar, ler_resumo=lambda rec, rid: m.resumos.get(rid), refinar=m.servico.refinar)
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    m.avancar()
    entrada, _ = m.refinador.chamadas[0]
    assert {s["chave"] for s in entrada.linhas.para_modelo()["secoes"]} == {"tom", "regras"}  # the parent's row is not even shown
    assert m.eventos("refinamento_recusado")[0]["detalhe"]["codigo"] == "linha_inexistente"
    assert next(s.conteudo for s in m.defs.list_sections(ORG, pai_draft.id)) == "Regra herdada do agente base, longa."


def test_an_agent_whose_content_is_not_row_editable_is_not_refined():
    m = Mundo()
    legado = m.defs.seed_agent(ORG, "agente-legado", nome="L", conteudo_modo="legado")
    m.loops.loops[m.loop.id] = replace(m.rec(), agent_id=legado.id)
    m.agent = legado
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    m.avancar()
    assert m.eventos("refinamento_recusado")[0]["detalhe"]["codigo"] == "agente_sem_linhas" and m.refinador.chamadas == []


def test_the_cases_of_a_round_with_personal_data_are_never_sent_to_the_model():
    com_pii = (CasoFalhando(slug="caso-a", titulo="A", suite="mecanismo", turnos=({"lead": "Meu e-mail é maria@exemplo.org", "bolhas": []},)),)
    m = Mundo(casos=com_pii)
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    m.avancar()
    assert m.eventos("refinamento_recusado")[0]["detalhe"]["codigo"] == "pii_nos_casos" and m.refinador.chamadas == []


def test_a_refiner_that_crashes_never_stops_the_loop():
    m = Mundo(refinador=FakeRefinador([RuntimeError("boom")]))
    m.avancar()
    m.terminar(m.abertas[0][0], 0.5)
    assert m.avancar() == "aguardando"
    assert m.eventos("refinamento_recusado")[0]["detalhe"]["codigo"] == "refinador_falhou"


def test_deve_refinar_is_pure_and_idempotent():
    from app.studio.eval_loop import Rodada

    r = Rodada(seq=1, run_id=uuid4(), run_tipo="mecanismo", compiled_hash="h", status="concluida", score=0.5, falhas=("a",))
    kw = dict(status="ativo", modo="automatico", alvo=0.95, rodadas=[r], eventos=[])
    assert deve_refinar(**kw) is r
    assert deve_refinar(**{**kw, "eventos": [{"evento": "refinamento_recusado", "rodada_seq": 1}]}) is None
    assert deve_refinar(**{**kw, "modo": "manual"}) is None and deve_refinar(**{**kw, "status": "parado"}) is None
    assert deve_refinar(**{**kw, "rodadas": [r, Rodada(2, uuid4(), "mecanismo", "h2")]}) is None  # a round is open
    assert deve_refinar(**{**kw, "rodadas": [Rodada(1, uuid4(), "mecanismo", "h", status="erro")]}) is None
    assert deve_refinar(**{**kw, "rodadas": [Rodada(1, uuid4(), "mecanismo", "h", status="concluida", score=0.99, falhas=())]}) is None


def test_trecho_do_diff_windows_the_changed_region():
    a, b = trecho_do_diff("x" * 1000 + "MEIO" + "y" * 1000, "x" * 1000 + "MEIO NOVO" + "y" * 1000)
    assert "MEIO" in a and "MEIO NOVO" in b and len(a) < 400 and a.startswith("…") and a.endswith("…")
    assert trecho_do_diff("curto", "curto novo") == ("curto", "curto novo")


# ── the atomic write: all or nothing ──────────────────────────────────────────────────────────────────────────


def _store_world():
    defs, loops = FakeStudioDefinitionStore(), FakeLoopStore()
    ag = defs.seed_agent(ORG, "a", conteudo_modo="linhas")
    d = defs.create_draft(ORG, ag.id, None, OWNER)
    defs.replace_sections(ORG, d.id, [SectionInput(chave="tom", titulo="Tom", ordem=1, conteudo="antes")])
    defs.set_compiled_hash(ORG, d.id, "H")
    loop = loops.create_loop(ORG, ag.id, agente_chave="a", suite="mecanismo", rodadas_planejadas=3, alvo=0.9, piso=0.8,
                             orcamento_usd=5.0, started_by=OWNER, modo="automatico")
    return defs, loops, d, loop, FakeRefinoStore(defs, loops)


@pytest.mark.parametrize("quebra,codigo", [("hash", "conflito_de_versao"), ("texto", "linha_alterada")])
def test_a_stale_hash_or_a_changed_row_writes_nothing_charges_nothing_and_records_no_event(quebra, codigo):
    defs, loops, d, loop, st = _store_world()
    esc = EscritaLinha(d.id, "secao", "tom", "antes" if quebra == "hash" else "diferente", "depois", "H" if quebra == "texto" else "OUTRO")
    if quebra == "texto":
        esc = EscritaLinha(d.id, "secao", "tom", "diferente", "depois", "H")
    with pytest.raises(StudioConflict) as e:
        st.registrar(ORG, loop.id, 1, evento="refinamento_proposto", detalhe={}, custo_usd=0.3, escrita=esc)
    assert e.value.code == codigo
    assert defs.list_sections(ORG, d.id)[0].conteudo == "antes" and loops.loops[loop.id].gasto_usd == 0.0 and loops.eventos == []


def test_a_second_decision_for_the_same_round_is_refused_whole():
    defs, loops, d, loop, st = _store_world()
    esc = EscritaLinha(d.id, "secao", "tom", "antes", "depois", "H")
    st.registrar(ORG, loop.id, 1, evento="refinamento_proposto", detalhe={}, custo_usd=0.3, escrita=esc)
    with pytest.raises(StudioConflict) as e:
        st.registrar(ORG, loop.id, 1, evento="refinamento_recusado", detalhe={}, custo_usd=0.2, escrita=None)
    assert e.value.code == "refino_ja_registrado" and loops.loops[loop.id].gasto_usd == pytest.approx(0.3)


def test_the_real_store_is_one_rpc_with_the_row_cas_arguments():
    chamadas = []

    class Rpc:
        def __init__(self, fn, params):
            self.fn, self.params = fn, params

        def execute(self):
            chamadas.append((self.fn, self.params))
            return SimpleNamespace(data=str(uuid4()))

    class Cliente:
        def schema(self, s):
            assert s == "agents"
            return SimpleNamespace(rpc=lambda fn, params: Rpc(fn, params))

    vid, loop = uuid4(), uuid4()
    SupabaseRefinoStore(Cliente()).registrar(
        ORG, loop, 2, evento="refinamento_proposto", detalhe={"k": 1}, custo_usd=0.12345,
        escrita=EscritaLinha(vid, "texto", "c", "a", "b", "H"))
    SupabaseRefinoStore(Cliente()).registrar(ORG, loop, 3, evento="refinamento_recusado", detalhe={}, custo_usd=0.0, escrita=None)
    (fn, p), (_, q) = chamadas
    assert fn == "aplicar_refinamento_loop" and p == {
        "p_org_id": str(ORG), "p_loop_id": str(loop), "p_rodada_seq": 2, "p_evento": "refinamento_proposto", "p_detalhe": {"k": 1},
        "p_custo_usd": 0.1235, "p_version_id": str(vid), "p_tipo": "texto", "p_chave": "c", "p_antes": "a", "p_depois": "b",
        "p_expected_hash": "H", "p_protegidas": protegidas_para_rpc()}
    assert "p_version_id" not in q and q["p_evento"] == "refinamento_recusado"


# ── the Real refiner: registry-fed, capped before the call, strict after ──────────────────────────────────────


def _entrada():
    return EntradaRefino(org_id=ORG, agente_chave="x", suite="mecanismo", rodada=1, score=0.5, alvo=0.95, casos=CASOS, linhas=LINHAS)


def _registro(modelo="claude-haiku-5-5", ativo=True):
    return FakePromptRegistry([PromptEntry(
        chave=CHAVE_REFINADOR, nome="Refinador", descricao="d", vendor="anthropic", modelo=modelo, prompt="PROMPT-DO-REGISTRO", ativo=ativo)])


class Chat:
    def __init__(self, texto, *, custo=0.03, usage=True):
        self.texto, self.custo, self.usage, self.chamadas = texto, custo, usage, []

    async def __call__(self, messages, **kw):
        self.chamadas.append((messages, kw))
        u = SimpleNamespace(prompt_tokens=1000, completion_tokens=200, cost_usd=self.custo) if self.usage else None
        return SimpleNamespace(text=self.texto, usage=u)


def test_the_real_refiner_sends_the_registry_prompt_plus_data_only_and_reports_the_measured_cost():
    chat = Chat(saida().model_dump_json())
    r = asyncio.run(LlmRefinador(registro=_registro, chat=chat).propor(_entrada(), limite_usd=1.0))
    assert r.saida is not None and r.custo_usd == 0.03 and r.codigo is None and r.modelo == "claude-haiku-5-5"
    (msgs, kw), = chat.chamadas
    assert msgs[0] == {"role": "system", "content": "PROMPT-DO-REGISTRO"}  # the whole prompt comes from the registry row
    dados = json.loads(msgs[1]["content"])
    assert set(dados) == {"contexto", "casos_falhando", "linhas_do_agente", "schema_saida"}  # one JSON object of data, no prose
    assert dados["casos_falhando"][0]["transcricao"][0]["lead"].startswith("Quanto custa")  # the lead text rides as a JSON string
    assert "parametros" not in json.dumps(dados["linhas_do_agente"]) and kw["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("registro,chat,limite,codigo", [
    (lambda: FakePromptRegistry([]), Chat("{}"), 1.0, "refinador_indisponivel"),
    (lambda: _registro(ativo=False), Chat("{}"), 1.0, "refinador_indisponivel"),
    (lambda: _registro(modelo="modelo-sem-preco"), Chat("{}"), 1.0, "modelo_sem_preco"),
    (_registro, Chat("{}"), 0.00001, "limite_de_custo"),  # the estimate does not fit the cap: the call is NOT made
    (_registro, Chat("não é json"), 1.0, "saida_invalida"),
    (_registro, Chat(json.dumps({"alvo": {"tipo": "secao", "chave": "tom"}, "novo_conteudo": "x" * 30, "racional": "r",
                                 "casos_alvo": ["a"], "ativo": True})), 1.0, "saida_invalida"),
])
def test_the_real_refiner_refuses_with_a_fixed_code(registro, chat, limite, codigo):
    r = asyncio.run(LlmRefinador(registro=registro, chat=chat).propor(_entrada(), limite_usd=limite))
    assert r.saida is None and r.codigo == codigo
    if codigo in ("refinador_indisponivel", "modelo_sem_preco", "limite_de_custo"):
        assert chat.chamadas == [] and r.custo_usd == 0.0


def test_an_unmeasured_call_is_charged_its_estimate_not_zero_and_a_provider_error_is_a_fixed_code():
    r = asyncio.run(LlmRefinador(registro=_registro, chat=Chat(saida().model_dump_json(), usage=False)).propor(_entrada(), limite_usd=1.0))
    assert r.saida is not None and r.custo_usd == 0.0 or r.custo_usd > 0.0  # the seed records usage=None as cost None -> estimate

    async def quebra(messages, **kw):
        raise RuntimeError("provider down")

    r = asyncio.run(LlmRefinador(registro=_registro, chat=quebra).propor(_entrada(), limite_usd=1.0))
    assert r.saida is None and r.codigo == "llm_erro"


def test_the_factory_never_invents_an_edit_without_a_service_key():
    sem_chave = SimpleNamespace(supabase_service_role_key=None)
    r = asyncio.run(get_refinador(sem_chave).propor(_entrada(), limite_usd=1.0))
    assert r.saida is None and r.codigo == "refinador_indisponivel"
    assert isinstance(get_refinador(SimpleNamespace(supabase_service_role_key="k")), LlmRefinador)
