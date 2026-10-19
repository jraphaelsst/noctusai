"""Lais wave 13 -- Analise de credito flow (contract 15 / 17): the consent gate, the seam, the job.

THE invariant under test: the provider is NEVER called without a stored consent aceito=true. Seams: mock DB,
`FakeCreditoProvider` injected through `registrar_provider_factory`, `FakeJobRepository` through `registrar_repo`
-- nothing of ours is patched. Fixtures carry no personal data."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from noctusai_lib.domain.jobs import FakeJobRepository

from app.clients.agents import LaisAction, TurnResult
from app.routers import lais_credito_router  # noqa: F401  (import binds the handler / hook / contexto extras)
from app.services import lais_acoes_service as acoes
from app.services import lais_contatos_service as contatos
from app.services import lais_contexto_service as contexto
from app.services import lais_credito_provider as prov
from app.services import lais_credito_service as svc
from app.services import lais_eventos_service as eventos

from tests.routers.test_lais_visitas import _mundo, _pedir, _primeiro_slot
from tests.support.lais_world import ORG_ID


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake():
    p = prov.FakeCreditoProvider()
    svc.registrar_provider_factory(lambda org, cfg: p)
    yield p
    svc.registrar_provider_factory(None)


@pytest.fixture
def repo():
    r = FakeJobRepository()
    svc.registrar_repo(r)
    yield r
    svc.registrar_repo(None)


def _mundo_credito(*, ativo=True, provider="fake", operacao="aluguel", apenas_aluguel=True):
    w, contato = _mundo()
    for t in (svc.T_CONFIG, svc.T_CONSENT, svc.T_ANALISES):
        w.sw.set_table_data(t, [])
    if ativo is not None:
        w.sw.set_table_data(svc.T_CONFIG, [{"org_id": ORG_ID, "ativo": ativo, "provider": provider, "apenas_aluguel": apenas_aluguel}])
    contatos.atualizar_contato(w.sw, contato["id"], {"operacao": operacao})
    return w, w.contato()


def _acao(w, contato, tipo, payload, *, seq=1, lote="l-credito"):
    res = TurnResult(conversation_id=str(uuid4()), partes=(), status="respondido", actions=(LaisAction(tipo, seq, payload),))
    return _run(acoes.aplicar(w.sw, org_id=ORG_ID, contato=contato, result=res, lote_hash=lote))


def _consentir(w, contato, aceito, *, lote="l-consent"):
    return _acao(w, contato, "consentimento_credito", {"aceito": aceito}, lote=lote)


def _pedir_visita(w, contato, *, lote="l-visita"):
    return _pedir(w, contato, {"inicio": _primeiro_slot(w)["inicio"], "codigo": "AL1"}, lote=lote)


def _jobs(repo):
    return [j for j in repo._jobs.values() if j.type == svc.JOB_ANALISE]


def _analises(w):
    return w.rows(svc.T_ANALISES)


class TestWiring:
    def test_handler_hook_and_contexto_extras_are_bound(self):
        assert acoes.HANDLERS["consentimento_credito"] is svc._h_consentimento
        assert svc._pos_pedido_visita in acoes.POS_ACAO["pedido_visita"]
        assert svc._acoes_extra in contexto.ACOES_EXTRAS and svc._estado_extra in contexto.ESTADO_EXTRAS
        assert acoes.HANDLERS["pedido_visita"] is not None  # wave 5's handler is composed, not replaced

    def test_event_type_is_known(self):
        assert "credito_analisado" in eventos.TIPOS


class TestConsentGate:
    def test_visit_without_consent_never_calls_the_provider(self, fake, repo):
        w, c = _mundo_credito()
        (r,) = _pedir_visita(w, c)
        assert r["estado"] == "aplicada" and w.rows("lais_visitas")
        assert fake.chamadas == [] and _analises(w) == [] and _jobs(repo) == []

    def test_refused_consent_is_stored_and_nothing_runs(self, fake, repo):
        w, c = _mundo_credito()
        _pedir_visita(w, c)
        (r,) = _consentir(w, c, False)
        assert r["estado"] == "aplicada"
        (linha,) = w.rows(svc.T_CONSENT)
        assert linha["aceito"] is False and linha["texto_versao"] == svc.TEXTO_VERSAO
        assert fake.chamadas == [] and _analises(w) == []
        # a later visit still does not run it
        _pedir_visita(w, c, lote="l-v2")
        assert fake.chamadas == [] and _analises(w) == []

    def test_consent_without_a_visit_waits_for_the_visit(self, fake, repo):
        w, c = _mundo_credito()
        _consentir(w, c, True)
        assert fake.chamadas == [] and _analises(w) == []
        _pedir_visita(w, c)
        (a,) = _analises(w)
        assert a["status"] == "pendente" and len(_jobs(repo)) == 1  # queued on the worker repo, not run inline
        assert fake.chamadas == []

    def test_consent_after_the_visit_starts_it(self, fake, repo):
        w, c = _mundo_credito()
        _pedir_visita(w, c)
        _consentir(w, c, True)
        assert len(_analises(w)) == 1 and fake.chamadas == []

    def test_aluguel_only(self, fake, repo):
        w, c = _mundo_credito(operacao="compra")
        _pedir_visita(w, c)
        (r,) = _consentir(w, c, True)
        assert r["estado"] == "aplicada"
        assert w.rows(svc.T_CONSENT) == [] and _analises(w) == [] and fake.chamadas == []

    def test_org_can_lift_the_aluguel_limit(self, fake, repo):
        w, c = _mundo_credito(operacao="compra", apenas_aluguel=False)
        _pedir_visita(w, c)
        _consentir(w, c, True)
        assert len(_analises(w)) == 1

    @pytest.mark.parametrize("cfg", [dict(ativo=False), dict(ativo=None)])
    def test_inactive_or_unconfigured_org_does_nothing(self, fake, repo, cfg):
        w, c = _mundo_credito(**cfg)
        _pedir_visita(w, c)
        _consentir(w, c, True)
        assert w.rows(svc.T_CONSENT) == [] and _analises(w) == [] and fake.chamadas == []

    def test_non_boolean_aceito_is_refused(self, fake, repo):
        w, c = _mundo_credito()
        _consentir(w, c, "sim")
        assert w.rows(svc.T_CONSENT) == [] and fake.chamadas == []

    def test_one_analysis_per_consent_even_when_replayed(self, fake, repo):
        w, c = _mundo_credito()
        _consentir(w, c, True)
        _pedir_visita(w, c)
        _pedir_visita(w, c, lote="l-v2")
        assert len(_analises(w)) == 1


class TestJob:
    def _preparar(self, repo, fake_=None, **kw):
        w, c = _mundo_credito(**kw)
        _consentir(w, c, True)
        _pedir_visita(w, c)
        (a,) = _analises(w)
        return w, c, a

    def test_approve_path_stores_status_resumo_and_emits_the_event(self, fake, repo):
        w, c, a = self._preparar(repo)
        assert _run(svc.executar_analise(w.sw, ORG_ID, a["id"])) == "aprovado"
        (linha,) = _analises(w)
        assert linha["status"] == "aprovado" and linha["resumo"] == "Análise aprovado (fake)."
        assert len(fake.chamadas) == 1 and fake.chamadas[0].codigo_imovel == "AL1"
        (ev,) = [e for e in w.rows("lais_eventos") if e["tipo"] == "credito_analisado"]
        assert ev["payload"] == {"analise_id": a["id"], "status": "aprovado"}

    def test_reject_path(self, fake, repo):
        fake.resultado = "reprovado"
        w, c, a = self._preparar(repo)
        assert _run(svc.executar_analise(w.sw, ORG_ID, a["id"])) == "reprovado"
        assert _analises(w)[0]["status"] == "reprovado"

    def test_pending_result_stays_pendente(self, fake, repo):
        fake.resultado = "pendente"
        w, c, a = self._preparar(repo)
        assert _run(svc.executar_analise(w.sw, ORG_ID, a["id"])) == "pendente"

    def test_resumo_is_clamped(self, fake, repo):
        fake.resumo = "x " * 400
        w, c, a = self._preparar(repo)
        _run(svc.executar_analise(w.sw, ORG_ID, a["id"]))
        assert len(_analises(w)[0]["resumo"]) <= prov.RESUMO_MAX

    def test_second_run_of_the_same_job_is_a_noop(self, fake, repo):
        w, c, a = self._preparar(repo)
        _run(svc.executar_analise(w.sw, ORG_ID, a["id"]))
        assert _run(svc.executar_analise(w.sw, ORG_ID, a["id"])) == "ja_processada"
        assert len(fake.chamadas) == 1

    def test_consent_revoked_before_the_job_fires_is_stale(self, fake, repo):
        w, c, a = self._preparar(repo)
        _consentir(w, c, False, lote="l-revoga")
        assert _run(svc.executar_analise(w.sw, ORG_ID, a["id"])) == "obsoleto"
        assert fake.chamadas == [] and _analises(w)[0]["status"] == "pendente"

    def test_org_switched_off_before_the_job_fires(self, fake, repo):
        w, c, a = self._preparar(repo)
        w.sw.set_table_data(svc.T_CONFIG, [{"org_id": ORG_ID, "ativo": False, "provider": "fake", "apenas_aluguel": True}])
        assert _run(svc.executar_analise(w.sw, ORG_ID, a["id"])) == "politica_desligada"
        assert fake.chamadas == []

    def test_provider_failure_is_an_erro_row_not_an_exception(self, fake, repo):
        fake.erro = prov.CreditoProviderErro("boom: detalhes internos")
        w, c, a = self._preparar(repo)
        assert _run(svc.executar_analise(w.sw, ORG_ID, a["id"])) == "erro"
        linha = _analises(w)[0]
        assert linha["status"] == "erro" and "boom" not in (linha["resumo"] or "")

    def test_the_worker_handler_runs_the_queued_job(self, fake, repo):
        w, c, a = self._preparar(repo)
        (job,) = _jobs(repo)
        handler = svc.handlers(client_provider=lambda: w.sw)[svc.JOB_ANALISE]
        _run(handler(job))
        assert _analises(w)[0]["status"] == "aprovado"


class TestRealStubAndFactory:
    def test_the_real_stub_refuses_with_provedor_nao_configurado(self):
        svc.registrar_provider_factory(None)
        w, c = _mundo_credito(provider="credaluga")
        _consentir(w, c, True)
        _pedir_visita(w, c)  # no repo: runs inline
        (a,) = _analises(w)
        assert a["status"] == "erro" and a["resumo"].startswith(prov.NAO_CONFIGURADO)

    @pytest.mark.parametrize("nome,cred,allow", [
        (None, None, True), ("desconhecido", None, True), ("fake", None, False),
    ])
    def test_factory_refuses_instead_of_defaulting(self, nome, cred, allow):
        with pytest.raises(prov.CreditoNaoConfigurado):
            prov.make_credito_provider(nome, credencial=cred, allow_fake=allow)

    def test_factory_builds_the_fake_in_dev_and_the_stub_always(self):
        assert isinstance(prov.make_credito_provider("fake", allow_fake=True), prov.FakeCreditoProvider)
        stub = prov.make_credito_provider("credaluga", credencial="tok")
        with pytest.raises(prov.CreditoNaoConfigurado):
            _run(stub.analisar(prov.ConsultaCredito("o", "c", None, None, "aluguel")))

    def test_config_validation(self):
        w, c = _mundo_credito(ativo=None)
        with pytest.raises(Exception) as e1:
            svc.salvar_config(w.sw, ORG_ID, ativo=True, provider=None, apenas_aluguel=True)
        assert e1.value.code == "provider_obrigatorio"
        with pytest.raises(Exception) as e2:
            svc.salvar_config(w.sw, ORG_ID, ativo=False, provider="nada", apenas_aluguel=True)
        assert e2.value.code == "provider_invalido"
        assert svc.salvar_config(w.sw, ORG_ID, ativo=True, provider="credaluga", apenas_aluguel=True)["ativo"] is True


class TestContexto:
    def _montar(self, w, c):
        return contexto.montar(w.sw, ORG_ID, c, ferramentas_habilitadas=False)

    def test_ask_state_exposes_the_tool_and_estado(self):
        w, c = _mundo_credito()
        out = self._montar(w, c)
        assert out["estado"]["credito"] == {"ativo": True, "consentimento": None}
        assert "consentimento_credito" in out["acoes"]

    @pytest.mark.parametrize("aceito,expect_tool", [(True, False), (False, True)])
    def test_after_the_answer(self, aceito, expect_tool):
        w, c = _mundo_credito()
        _consentir(w, c, aceito)
        out = self._montar(w, c)
        assert out["estado"]["credito"]["consentimento"] is aceito
        assert ("consentimento_credito" in out["acoes"]) is expect_tool

    @pytest.mark.parametrize("cfg", [dict(ativo=False), dict(operacao="compra"), dict(operacao=None)])
    def test_absent_when_it_does_not_apply(self, cfg):
        w, c = _mundo_credito(**cfg)
        out = self._montar(w, c)
        assert "credito" not in out["estado"] and "consentimento_credito" not in out["acoes"]

    def test_extras_never_remove_what_the_acoes_provider_returned(self):
        w, c = _mundo_credito()
        out = self._montar(w, c)
        assert set(contexto.ACOES_LAIS) - {"qualificar_lead"} <= set(out["acoes"])
