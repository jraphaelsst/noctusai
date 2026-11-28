"""The Diretor de Edição production graph end to end on the seed runner, with ONLY Fakes: the stages, their order and
dependencies, the ledger rows (measured / nao_medido, never an estimate), the synthetic-output refusal, the coded failures
and the outcome enum. No DB, no vendor, no renderer: the seams are the Fakes of :mod:`direcao.fakes`."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from noctusai_lib.domain.jobs import FakeJobRepository, RetryPolicy, Worker
from noctusai_lib.domain.media_production import FakeLedger, FakeMover, FakeProgress, FakeQuota, MediaGraphRunner
from noctusai_lib.domain.media_production.types import CONCLUIDO, FALHOU

from app.modules.media_creation.direcao import passos as ps
from app.modules.media_creation.direcao.entrada import congelar_entrada
from app.modules.media_creation.direcao.fakes import (
    FakeGeradorDeMidia,
    FakeMontador,
    FakePlanejadorDeCenas,
    FakeResolvedorDeEstilo,
    adaptadores_fake,
)
from app.modules.media_creation.direcao.handlers import DirecaoDeps, build_handlers_direcao
from app.modules.media_creation.direcao.tipos import CenaPlanejada, PlanoDeCenas

ORG, POST, MARCA = "org-1", "post-1", "marca-1"
ROTEIRO = """**Gancho**

Você já sentiu que o dia passa e nada muda? Hoje eu vou te mostrar um jeito simples de virar essa chave.

# Desenvolvimento

Primeiro, escolha uma única coisa para fazer antes do almoço. Só uma.

=== ESTRUTURAS_USADAS ===
#12: gancho
"""


def run(coro):
    return asyncio.run(coro)


def entrada(rodada: int = 1):
    return congelar_entrada(
        org_id=ORG, post_id=POST, marca_id=MARCA, rodada=rodada, headline_id="h1", headline="Um jeito simples de mudar o dia",
        roteiro_id="r1", roteiro_versao=2, roteiro=ROTEIRO,
    )


class Rig:
    def __init__(self, *, adaptadores=None, permitir_sintetico=True, registrar_asset=None, quota=None) -> None:
        self.repo = FakeJobRepository()
        self.ledger, self.progress, self.mover = FakeLedger(), FakeProgress(), FakeMover()
        self.assets: list[dict] = []
        deps = DirecaoDeps(
            adaptadores=adaptadores or adaptadores_fake(), permitir_sintetico=permitir_sintetico,
            registrar_asset=registrar_asset or self._registrar,
        )
        self.runner = MediaGraphRunner(
            jobs=self.repo, ledger=self.ledger, progress=self.progress, quota=quota or FakeQuota(), mover=self.mover,
            registry=build_handlers_direcao(deps), max_retries=0,
        )
        self.worker = Worker(
            self.repo, worker_id="w", handlers=self.runner.handlers, retry_policy=RetryPolicy(max_retries=0, backoff_seconds=0)
        )

    def _registrar(self, org_id, post_id, chave, medicoes):
        self.assets.append({"org": org_id, "post": post_id, "chave": chave})
        return {"id": f"asset-{len(self.assets)}"}

    async def rodar(self, e=None, **kw):
        await self.runner.enqueue_graph(ps.montar_grafo(e or entrada(), **kw))
        while await self.worker.run_once():
            pass
        return await self.ledger.carregar(ORG, POST)


def linhas(rows):
    return {r.passo: r for r in rows}


def test_the_graph_is_the_declared_stages_in_dependency_order_and_each_stage_is_data():
    g = ps.montar_grafo(entrada())
    assert tuple(s.passo for s in g.passos) == ps.PASSOS_DIRECAO
    dep = {s.passo: set(s.depende_de) for s in g.passos}
    assert dep[ps.PASSO_RECEPCAO] == set()
    assert dep[ps.PASSO_PLANO] == {ps.PASSO_RECEPCAO, ps.PASSO_ESTILO}
    assert dep[ps.PASSO_MONTAGEM] == {ps.PASSO_RECEPCAO, ps.PASSO_PLANO, ps.PASSO_MIDIA}
    assert set(ps.ESTAGIOS) == set(ps.PASSOS_DIRECAO)
    assert all(ps.ESTAGIOS[n].rotulo and ps.ESTAGIOS[n].peso > 0 for n in ps.PASSOS_DIRECAO)


def test_a_full_run_on_fakes_concludes_every_stage_and_delivers_for_review():
    rig = Rig()
    rows = run(rig.rodar())
    por = linhas(rows)
    assert set(por) == set(ps.PASSOS_DIRECAO) and all(r.status == CONCLUIDO for r in rows)
    assert ps.resultado_da_rodada(rows, 1) == ps.ENTREGUE_PARA_REVISAO
    pacote = por[ps.PASSO_PACOTE].resultado["pacote"]
    assert pacote["sintetico"] is True and pacote["estilo"]["id"] == "estilo-fake" and pacote["asset_id"] == "asset-1"
    assert rig.assets == [{"org": ORG, "post": POST, "chave": pacote["arquivo_chave"]}]
    assert ("post-1", "criacao_concluida") in rig.mover.movimentos


def test_the_ledger_carries_what_was_measured_and_names_what_was_not():
    rows = linhas(run(Rig().rodar()))
    plano = rows[ps.PASSO_PLANO]
    assert plano.medicoes["planejador"] == "fake" and plano.medicoes["n_cenas"] >= 1
    assert plano.medicoes["palavras_sem_cena"] == 0
    assert rows[ps.PASSO_MIDIA].vendor == "fake"
    assert rows[ps.PASSO_MIDIA].custo_usd == Decimal("0")  # a Fake charged nothing: a measured fact, not an estimate
    assert rows[ps.PASSO_MONTAGEM].medicoes["lufs"] is not None


def test_a_generator_that_does_not_measure_its_cost_leaves_it_unmeasured_never_zero():
    class SemCusto(FakeGeradorDeMidia):
        def gerar(self, entrada, plano):
            m = super().gerar(entrada, plano)
            return type(m)(m.gerador, m.versao, m.itens, m.sintetico, m.request_id, {}, None)

    rows = linhas(run(Rig(adaptadores=adaptadores_fake(gerador=SemCusto())).rodar()))
    assert rows[ps.PASSO_MIDIA].custo_usd is None and "custo_usd" in rows[ps.PASSO_MIDIA].nao_medido


def test_synthetic_output_never_reaches_the_review_queue_unless_explicitly_allowed():
    rows = run(Rig(permitir_sintetico=False).rodar())
    por = linhas(rows)
    assert por[ps.PASSO_CHECAGENS].status == FALHOU and por[ps.PASSO_CHECAGENS].erro_codigo == "saida_sintetica"
    assert ps.PASSO_PACOTE not in por or por[ps.PASSO_PACOTE].status != CONCLUIDO
    assert ps.resultado_da_rodada(rows, 1) == ps.FALHOU


def test_a_plan_that_adds_text_fails_the_plan_stage_with_a_code_and_spends_nothing_downstream():
    class Mentiroso(FakePlanejadorDeCenas):
        def planejar(self, entrada, estilo):
            return PlanoDeCenas("mentiroso", "1", estilo, (CenaPlanejada("c1", "w0", "w3", ("Compre agora",)),))

    rig = Rig(adaptadores=adaptadores_fake(planejador=Mentiroso()))
    por = linhas(run(rig.rodar()))
    assert por[ps.PASSO_PLANO].status == FALHOU and por[ps.PASSO_PLANO].erro_codigo == "plano_invalido"
    assert ps.PASSO_MIDIA not in por or por[ps.PASSO_MIDIA].status != CONCLUIDO
    assert rig.assets == []


def test_a_measurement_outside_the_target_fails_the_checks_stage_not_the_assembly():
    class Alto(FakeMontador):
        def montar(self, entrada, plano, midia):
            m = super().montar(entrada, plano, midia)
            return type(m)(m.montador, m.versao, m.arquivo_chave, m.sintetico, {**m.medicoes, "lufs": -9.0})

    por = linhas(run(Rig(adaptadores=adaptadores_fake(montador=Alto())).rodar()))
    assert por[ps.PASSO_MONTAGEM].status == CONCLUIDO
    assert por[ps.PASSO_CHECAGENS].status == FALHOU and por[ps.PASSO_CHECAGENS].erro_codigo == "checagem_reprovada"


def test_the_quota_estimate_is_checked_before_the_generator_runs():
    class Caro(FakeGeradorDeMidia):
        def estimar_usd(self, plano):
            return Decimal("99")

    rig = Rig(adaptadores=adaptadores_fake(gerador=Caro()))
    rows = run(rig.rodar(estimativas={ps.PASSO_MIDIA: Decimal("99")}))
    por = linhas(rows)
    assert por[ps.PASSO_MIDIA].status == FALHOU and por[ps.PASSO_MIDIA].erro_codigo == "cota"
    assert por[ps.PASSO_MONTAGEM].status != CONCLUIDO


def test_the_estilo_stage_records_which_style_and_planner_versions_produced_the_run():
    por = linhas(run(Rig().rodar()))
    assert por[ps.PASSO_ESTILO].medicoes["estilo_id"] == "estilo-fake"
    assert por[ps.PASSO_PLANO].medicoes["versao"] == por[ps.PASSO_PLANO].resultado["plano"]["versao"]


def test_the_outcome_enum_is_closed_and_derived_from_the_ledger():
    assert set(ps.RESULTADOS) == {ps.ENTREGUE_PARA_REVISAO, ps.FALHOU, ps.CANCELADO, ps.EM_ANDAMENTO}
    assert ps.resultado_da_rodada([], 1) == ps.EM_ANDAMENTO


def test_a_frozen_entry_is_tokenised_once_with_stable_word_ids_and_hashes():
    e = entrada()
    assert e.ids() == [f"w{i}" for i in range(len(e.palavras))]
    assert e.palavras[0].texto == "Você" and "ESTRUTURAS_USADAS" not in " ".join(p.texto for p in e.palavras)
    assert len(e.roteiro_sha256) == 64 and e.roteiro_sha256 != e.headline_sha256
    assert e == type(e).de_dict(e.para_dict())


def test_an_empty_speech_cannot_be_frozen():
    with pytest.raises(Exception) as exc:
        congelar_entrada(
            org_id=ORG, post_id=POST, marca_id=MARCA, rodada=1, headline_id="h", headline="x", roteiro_id="r",
            roteiro_versao=1, roteiro="**Gancho**\n\n# So titulo",
        )
    assert getattr(exc.value, "codigo", "") == "roteiro_sem_fala"
