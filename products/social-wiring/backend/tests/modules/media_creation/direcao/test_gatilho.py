"""The approval -> production trigger: headline AND roteiro approved => ONE idempotent production request.

Real: the trigger, the approvals organ (its own Fake ledger, same refusals as the ``apr_record`` RPC), the route data. Fake: the
DB client (``FakeDb``), the event writer (in-memory twin of migration 373's RPC, whose own behaviour is pinned on PGlite by
``test_migration_cs_direcao``), the enqueue (records the call) and the ledger read."""
from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any, Optional

from noctusai_lib.domain.approvals import ApprovalService, build_approvals_store

from app.modules.media_creation.criacao_rotas import ROTAS, resolver_rota
from app.modules.media_creation.direcao import gatilho as g
from app.modules.media_creation.services.criacao_service import CriacaoError
from app.modules.media_creation.services.roteiro_aprovacao import CFG
from tests.modules.media_creation.criacao_fakes import FakeDb

ORG, MARCA = str(uuid.uuid4()), str(uuid.uuid4())


def run(coro):
    return asyncio.run(coro)


class Eventos:
    """In-memory twin of ``cs_direcao_evento``: one solicitada per (post, chave); recusadas always."""

    def __init__(self) -> None:
        self.linhas: list[dict[str, Any]] = []
        self._trava = threading.Lock()  # the real writer is atomic (a UNIQUE index); the twin must be too

    def solicitar(self, org_id, post_id, chave, dados) -> bool:
        with self._trava:
            return self._solicitar(org_id, post_id, chave, dados)

    def _solicitar(self, org_id, post_id, chave, dados) -> bool:
        if any(l["tipo"] == "direcao_solicitada" and l["post"] == post_id and l["chave"] == chave for l in self.linhas):
            return False
        self.linhas.append({"tipo": "direcao_solicitada", "org": org_id, "post": post_id, "chave": chave, "dados": dados})
        return True

    def recusar(self, org_id, post_id, chave, codigo, dados) -> None:
        self.linhas.append({"tipo": "direcao_recusada", "org": org_id, "post": post_id, "chave": chave, "codigo": codigo})

    def de(self, tipo: str) -> list[dict]:
        return [l for l in self.linhas if l["tipo"] == tipo]


class Rig:
    def __init__(self, *, rota: Optional[str] = "reel_dirigido", ligado: bool = True) -> None:
        self.db = FakeDb()
        self.approvals = ApprovalService(build_approvals_store(CFG, use_fake=True), CFG)
        self.eventos = Eventos()
        self.enfileiradas: list[tuple] = []
        self.falha: Optional[BaseException] = None
        self.grafos: set[tuple[str, str]] = set()
        self.ligado = ligado
        self.headline, self.roteiro, self.post = (str(uuid.uuid4()) for _ in range(3))
        self.db.tables["cs_headlines"] = [{"id": self.headline, "org_id": ORG, "texto": "h"}]
        self.db.tables["cs_roteiros"] = [{"id": self.roteiro, "org_id": ORG, "status": "completo", "versao": 1}]
        self.db.tables["cs_posts"] = [{
            "id": self.post, "org_id": ORG, "marca_id": MARCA, "formato": "reel", "criacao_rota": rota,
            "criacao_estado": None, "headline_id": self.headline, "roteiro_id": self.roteiro,
        }]
        self.gatilho = g.GatilhoDirecao(
            self.db, habilitado=lambda _org: self.ligado, solicitacoes=self.eventos, enfileirar=self._enfileirar,
            grafo_existente=self._grafo, approvals=self.approvals,
        )

    async def _enfileirar(self, post_id, org_id, ator_id):
        if self.falha:
            raise self.falha
        self.enfileiradas.append((post_id, org_id, ator_id))
        self.grafos.add((org_id, post_id))
        return {"post_id": post_id, "rota": "reel_dirigido", "rodada": 1}

    async def _grafo(self, org_id, post_id) -> bool:
        return (org_id, post_id) in self.grafos

    def aprovar(self, headline=True, roteiro=True, versao=1):
        if headline:
            self.approvals.submit(ORG, "headline", self.headline, 1)
            self.approvals.approve(ORG, "headline", self.headline, 1, actor_id="u")
        if roteiro:
            self.approvals.submit(ORG, "roteiro", self.roteiro, versao)
            self.approvals.approve(ORG, "roteiro", self.roteiro, versao, actor_id="u")

    def avaliar(self, **kw):
        return run(self.gatilho.avaliar_post(ORG, self.post, **kw))


def test_the_route_data_says_which_routes_start_by_themselves():
    assert ROTAS["reel_dirigido"].gatilho_automatico is True
    assert all(not r.gatilho_automatico for k, r in ROTAS.items() if k != "reel_dirigido")
    # ... and the new route is never picked by (formato, modo): only an explicit criacao_rota selects it
    assert resolver_rota("reel").chave == "reel_narrado"


def test_both_approvals_queue_exactly_one_run_and_record_the_intent_event():
    r = Rig()
    r.aprovar()
    out = r.avaliar(ator_id="u1")
    assert out.resultado == g.DISPARADO and out.chave.startswith(f"direcao:{r.post}:h{r.headline}:r{r.roteiro}:v1")
    assert r.enfileiradas == [(r.post, ORG, "u1")]
    assert [e["chave"] for e in r.eventos.de("direcao_solicitada")] == [out.chave]
    assert r.eventos.de("direcao_solicitada")[0]["dados"]["rota"] == "reel_dirigido"


def test_only_one_of_the_two_approvals_does_not_trigger():
    r = Rig()
    r.aprovar(roteiro=False)
    assert r.avaliar().resultado == g.APROVACOES_PENDENTES
    r.aprovar(headline=False)
    assert r.avaliar().resultado == g.DISPARADO
    assert len(r.enfileiradas) == 1


def test_a_repeated_trigger_is_idempotent_it_neither_records_nor_queues_again():
    r = Rig()
    r.aprovar()
    assert r.avaliar().resultado == g.DISPARADO
    assert r.avaliar().resultado == g.JA_SOLICITADO
    assert r.avaliar().resultado == g.JA_SOLICITADO
    assert len(r.enfileiradas) == 1 and len(r.eventos.de("direcao_solicitada")) == 1


def test_concurrent_triggers_queue_once():
    r = Rig()
    r.aprovar()

    async def go():
        return await asyncio.gather(*(r.gatilho.avaliar_post(ORG, r.post) for _ in range(5)))

    out = run(go())
    assert [o.resultado for o in out].count(g.DISPARADO) == 1
    assert len(r.enfileiradas) == 1


def test_a_crash_between_the_event_and_the_enqueue_is_healed_by_the_next_trigger():
    r = Rig()
    r.aprovar()
    r.falha = RuntimeError("boom")
    assert r.avaliar().resultado == g.RECUSADO
    assert r.enfileiradas == [] and len(r.eventos.de("direcao_solicitada")) == 1
    r.falha = None
    assert r.avaliar().resultado == g.DISPARADO  # event existed, no graph: the enqueue is repeated, the event is not
    assert len(r.enfileiradas) == 1 and len(r.eventos.de("direcao_solicitada")) == 1


def test_an_edited_and_reapproved_roteiro_is_a_new_request():
    r = Rig()
    r.aprovar()
    first = r.avaliar()
    r.db.tables["cs_roteiros"][0]["versao"] = 2
    r.grafos.clear()
    r.aprovar(headline=False, versao=2)
    second = r.avaliar()
    assert (first.resultado, second.resultado) == (g.DISPARADO, g.DISPARADO) and first.chave != second.chave
    assert len(r.eventos.de("direcao_solicitada")) == 2


def test_an_edit_without_reapproval_does_not_trigger():
    r = Rig()
    r.aprovar()
    r.db.tables["cs_roteiros"][0]["versao"] = 2  # the approval of versao 1 no longer counts
    assert r.avaliar().resultado == g.APROVACOES_PENDENTES


def test_the_switch_off_is_a_no_op_and_the_route_without_a_trigger_is_never_touched():
    off = Rig(ligado=False)
    off.aprovar()
    assert off.avaliar().resultado == g.DESLIGADO and off.eventos.linhas == [] and off.enfileiradas == []
    narrado = Rig(rota="reel_narrado")
    narrado.aprovar()
    assert narrado.avaliar().resultado == g.SEM_GATILHO_NA_ROTA and narrado.enfileiradas == []
    sem_rota = Rig(rota=None)
    sem_rota.aprovar()
    assert sem_rota.avaliar().resultado == g.SEM_GATILHO_NA_ROTA


def test_a_coded_refusal_is_recorded_with_its_code_and_never_raised_into_the_approval():
    r = Rig()
    r.aprovar()
    r.falha = CriacaoError(409, "rota_nao_implementada", "A rota ainda não está disponível")
    out = r.avaliar()
    assert (out.resultado, out.codigo) == (g.RECUSADO, "rota_nao_implementada")
    assert [e["codigo"] for e in r.eventos.de("direcao_recusada")] == ["rota_nao_implementada"]


def test_an_already_running_graph_is_reported_not_doubled():
    r = Rig()
    r.aprovar()

    async def ja(*_a):
        return {"ja_em_andamento": True}

    r.gatilho = g.GatilhoDirecao(
        r.db, habilitado=lambda _o: True, solicitacoes=r.eventos, enfileirar=ja, grafo_existente=r._grafo, approvals=r.approvals,
    )
    assert r.avaliar().resultado == g.JA_SOLICITADO


def test_the_unknown_post_is_a_value():
    r = Rig()
    assert run(r.gatilho.avaliar_post(ORG, str(uuid.uuid4()))).resultado == g.POST_NAO_ENCONTRADO


def test_the_approval_endpoints_can_trigger_by_the_approved_subject():
    r = Rig()
    r.aprovar()
    out = run(r.gatilho.avaliar_por(ORG, "headline_id", r.headline))
    assert [o.resultado for o in out] == [g.DISPARADO]
    assert run(r.gatilho.avaliar_por(ORG, "roteiro_id", r.roteiro))[0].resultado == g.JA_SOLICITADO


def test_the_reconcile_sweep_catches_a_missed_approval_path_and_skips_what_is_queued():
    r = Rig()
    r.aprovar()  # approved through a path that never called the trigger
    assert [o.resultado for o in run(r.gatilho.reconciliar(ORG))] == [g.DISPARADO]
    r.db.tables["cs_posts"][0]["criacao_estado"] = "na_fila"
    assert run(r.gatilho.reconciliar(ORG)) == []


def test_acionar_apos_aprovacao_is_a_no_op_with_the_switch_off_and_never_raises():
    r = Rig()
    r.aprovar()
    reads = len(r.db.calls)
    assert run(g.acionar_apos_aprovacao(r.db, ORG, post_id=r.post, ligado=False)) == []
    assert len(r.db.calls) == reads  # not even a read on the approval path

    class Quebrado:
        async def avaliar_post(self, *a, **k):
            raise RuntimeError("falha")

    assert run(g.acionar_apos_aprovacao(r.db, ORG, post_id=r.post, gatilho=Quebrado(), ligado=True)) == []  # logged, not raised
    ok = run(g.acionar_apos_aprovacao(r.db, ORG, headline_id=r.headline, gatilho=r.gatilho, ligado=True))
    assert [o.resultado for o in ok] == [g.DISPARADO]


def test_the_supabase_writer_calls_the_373_rpc_with_the_agreed_arguments():
    class Db:
        def __init__(self):
            self.chamadas = []

        def rpc(self, nome, params):
            self.chamadas.append((nome, params))
            from types import SimpleNamespace

            return SimpleNamespace(execute=lambda: SimpleNamespace(data=len(self.chamadas) == 1))

    db = Db()
    s = g.SupabaseSolicitacoes(db)
    assert s.solicitar(ORG, "p", "k", {"rota": "reel_dirigido"}) is True
    assert s.solicitar(ORG, "p", "k", {}) is False
    s.recusar(ORG, "p", "k", "cota", {})
    assert [c[0] for c in db.chamadas] == ["cs_direcao_evento"] * 3
    assert db.chamadas[0][1]["p_tipo"] == "direcao_solicitada" and db.chamadas[2][1]["p_dados"]["codigo"] == "cota"
