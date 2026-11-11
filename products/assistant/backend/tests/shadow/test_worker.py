"""The classification worker: outcome per path, idempotency (no double write, no double pay), replay never touching
the intake row, the fail-closed start gate, and the poll budget (calls per idle tick)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from noctusai_lib.domain.jobs import DeadLetterError, FakeJobRepository
from noctusai_lib.domain.jobs.entity import Job, JobStatus
from noctusai_lib.integrations.llm.exceptions import LLMAPIError
from noctusai_lib.integrations.llm.spend_guard import InMemorySpendWindowReader, SurfaceLimit, configure_spend_guard
from noctusai_lib.integrations.prompt_registry import RegistroIAIndisponivel

from app.shadow import classificador as clf
from app.shadow import worker as w
from tests.shadow.conftest import ORG, resposta


def _job(intake_id, tipo=w.JOB_CLASSIFICAR, retry=0, **extra):
    now = datetime.now(timezone.utc)
    return Job(id="j", type=tipo, payload={"intake_id": intake_id, **extra}, status=JobStatus.RUNNING,
               retry_count=retry, max_retries=3, last_error=None, created_at=now, updated_at=now)


def _run(coro):
    return asyncio.run(coro)


def _sut(db, registro):
    return w.Classificador(db, registry=registro)


# ── first pass ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_pending_row_is_classified_once_and_moves_to_classified(seam, registro, db):
    fake = seam([resposta(True, "pede_horario")])
    i = db.add("Você tem horário quinta?")
    _run(_sut(db, registro).classificar_intake(_job(i)))
    assert db.rows[i]["outcome"] == "classified"
    assert [r["inserted"] for r in db.registros] == [True]
    (out,) = db.outputs.values()
    assert out["label"] == "agendamento" and out["metadata"]["origem"] == "primeira"
    assert len(fake.calls) == 1


def test_rerun_of_the_same_job_neither_writes_nor_pays_again(seam, registro, db):
    fake = seam([resposta(True), resposta(True)])
    i = db.add("Pode ser quinta?")
    sut = _sut(db, registro)
    _run(sut.classificar_intake(_job(i)))
    _run(sut.classificar_intake(_job(i)))
    assert len(db.registros) == 1 and len(db.outputs) == 1
    assert len(fake.calls) == 1


def test_identifiers_on_the_row_never_reach_the_provider(seam, registro, db):
    fake = seam([resposta(False)])
    i = db.add("Viu o jogo ontem?")
    _run(_sut(db, registro).classificar_intake(_job(i)))
    enviado = repr(fake.calls)
    row = db.rows[i]
    for segredo in (row["chat_ref"], row["waha_message_id"], row["phone"], i):
        assert segredo not in enviado
    assert fake.calls[0]["messages"][-1] == {"role": "user", "content": "Viu o jogo ontem?"}


@pytest.mark.parametrize("falha", ["exceeded", "unverifiable"])
def test_budget_refusal_is_skipped_budget_and_nothing_is_recorded(seam, registro, db, falha):
    fake = seam([resposta(True)])
    reader = InMemorySpendWindowReader()
    if falha == "exceeded":
        reader.totals[(ORG, "assistant", None)] = 9.0
    else:
        reader.fail_with = RuntimeError("ledger down")
    configure_spend_guard(reader=reader, limits={"assistant": SurfaceLimit("assistant", 1.0, "enforce")})
    i = db.add("Pode ser quinta?")
    _run(_sut(db, registro).classificar_intake(_job(i)))
    assert db.rows[i]["outcome"] == "skipped_budget"
    assert db.rows[i]["body"] == "Pode ser quinta?"  # a budget outage never destroys the text
    assert db.desfechos[-1][2].startswith("spend_ceiling_")
    assert db.registros == [] and fake.calls == []


def test_invalid_model_output_is_failed_with_a_code(seam, registro, db):
    seam(["SIM, é agendamento!"])
    i = db.add("Pode ser quinta?")
    _run(_sut(db, registro).classificar_intake(_job(i)))
    assert db.desfechos == [(i, "failed", "saida_invalida:nao_e_objeto_json")]
    assert db.registros == []


def test_provider_error_retries_then_records_failed_on_the_last_attempt(registro, db):
    async def quebra(*a, **k):
        raise LLMAPIError("anthropic", 500, "boom")

    i = db.add("Pode ser quinta?")
    sut = w.Classificador(db, registry=registro, chat=quebra)
    with pytest.raises(LLMAPIError):
        _run(sut.classificar_intake(_job(i, retry=0)))
    assert db.rows[i]["outcome"] == "pending"
    _run(sut.classificar_intake(_job(i, retry=3)))
    assert db.desfechos == [(i, "failed", "erro_provedor:llmapi_error")]


def test_missing_registry_row_keeps_the_row_pending_and_retries(db):
    from noctusai_lib.integrations.prompt_registry import FakePromptRegistry

    i = db.add("Pode ser quinta?")
    with pytest.raises(RegistroIAIndisponivel):
        _run(w.Classificador(db, registry=FakePromptRegistry([])).classificar_intake(_job(i, retry=3)))
    assert db.rows[i]["outcome"] == "pending" and db.desfechos == []


def test_row_without_text_is_failed_without_a_call(seam, registro, db):
    fake = seam([resposta(True)])
    i = db.add("   ")
    _run(_sut(db, registro).classificar_intake(_job(i)))
    assert db.desfechos == [(i, "failed", "sem_texto")] and fake.calls == []


# ── replay ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_replay_under_a_new_prompt_writes_a_new_output_and_never_touches_the_row(seam, registro, db):
    fake = seam([resposta(False), resposta(True)])
    i = db.add("Pode ser quinta?")
    sut = _sut(db, registro)
    _run(sut.classificar_intake(_job(i)))
    registro.atualizar(clf.CHAVE, prompt="PROMPT v2")
    versao, modelo = clf.versao_atual(registry=registro)
    desfechos_antes = list(db.desfechos)
    _run(sut.reclassificar_intake(_job(i, w.JOB_RECLASSIFICAR, prompt_version=versao, modelo=modelo)))
    assert len(db.outputs) == 2 and db.registros[-1] == {"intake_id": i, "inserted": True, "primeira": False}
    assert db.rows[i]["outcome"] == "classified" and db.desfechos == desfechos_antes
    # the replay again: already classified under this (version, model) -> no call, no write
    _run(sut.reclassificar_intake(_job(i, w.JOB_RECLASSIFICAR, prompt_version=versao, modelo=modelo)))
    assert len(fake.calls) == 2 and len(db.registros) == 2


def test_replay_classifies_a_skipped_budget_row_whose_text_was_kept(seam, registro, db):
    seam([resposta(True)])
    i = db.add("Pode ser quinta às 15h?", outcome="skipped_budget")
    versao, modelo = clf.versao_atual(registry=registro)
    _run(_sut(db, registro).reclassificar_intake(_job(i, w.JOB_RECLASSIFICAR, prompt_version=versao, modelo=modelo)))
    assert db.rows[i]["outcome"] == "classified" and len(db.outputs) == 1


def test_replay_for_a_version_the_registry_no_longer_serves_is_dead_lettered(seam, registro, db):
    fake = seam([resposta(True)])
    i = db.add("Pode ser quinta?", outcome="classified")
    with pytest.raises(DeadLetterError):
        _run(_sut(db, registro).reclassificar_intake(
            _job(i, w.JOB_RECLASSIFICAR, prompt_version="assistant.classificador_agendamento@000", modelo="x")))
    assert fake.calls == []


def test_enqueue_replay_dedupes_on_row_version_model(registro):
    repo = FakeJobRepository()

    class _Client:
        def table(self, _):
            return self

        def __getattr__(self, name):
            return lambda *a, **k: self

        @property
        def not_(self):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "a"}, {"id": "b"}])

    ids = ["00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"]
    r1 = _run(w.enfileirar_replay(repo, _Client, org_id=ORG, intake_ids=ids, registry=registro))
    r2 = _run(w.enfileirar_replay(repo, _Client, org_id=ORG, intake_ids=ids, registry=registro))
    assert r1["enfileirados"] == 2 and r2["enfileirados"] == 2
    assert len(repo._jobs) == 2  # the second request hit the dedupe keys


# ── fail-closed start + poll budget ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,esperado", [
    (None, None),
    ('{"assistant": {"usd": 5, "mode": "observe"}}', None),
    ('{"*": {"usd": 50, "mode": "enforce"}}', "*"),
    ('{"assistant": {"usd": 5, "mode": "enforce"}}', "assistant"),
    ('{"assistant": {"usd": 5, "mode": "observe"}, "*": {"usd": 50, "mode": "enforce"}}', None),
    ('{"assistant:plataforma.assistant.classificador_agendamento": {"usd": 1, "mode": "enforce"}}',
     "assistant:plataforma.assistant.classificador_agendamento"),
])
def test_the_worker_needs_an_enforced_spend_limit(raw, esperado):
    assert w.limite_de_gasto_aplicado(raw or "") == esperado


def test_start_refuses_without_an_enforced_limit(monkeypatch):
    monkeypatch.setenv("NOCTUS_SCHEDULERS_ENABLED", "1")
    monkeypatch.delenv("LLM_SPEND_LIMITS", raising=False)
    cfg = SimpleNamespace(assistant_classifier_enabled=True, assistant_classifier_max_chars=4000)
    assert _run(w.start_worker(cfg)) is False and not w.is_running()


def test_idle_worker_makes_one_claim_per_tick_and_backs_off():
    calls = {"claim": 0}

    class _Repo(FakeJobRepository):
        async def claim_next(self, **kw):
            calls["claim"] += 1
            return None

    sleeps: list[float] = []
    stop = asyncio.Event()

    async def _sleep(delay, _stop):
        sleeps.append(delay)
        if len(sleeps) >= 10:
            stop.set()

    worker = w.build_worker(_Repo(), w.Classificador(None), idle_sleep=_sleep)
    _run(worker.run_forever(stop_event=stop))
    assert calls["claim"] == 10  # one call per idle tick, nothing else on the wire
    assert sleeps[:6] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0] and max(sleeps) == 30.0


def test_replay_enqueue_accepts_skipped_budget_rows(registro):
    filtros: list[tuple] = []

    class _Client:
        def table(self, _):
            return self

        def __getattr__(self, name):
            def _f(*a, **k):
                filtros.append((name, a))
                return self
            return _f

        @property
        def not_(self):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    _run(w.enfileirar_replay(FakeJobRepository(), _Client, org_id=ORG,
                             intake_ids=["00000000-0000-0000-0000-00000000000a"], registry=registro))
    (_, (coluna, valores)), = [f for f in filtros if f[0] == "in_" and f[1][0] == "outcome"]
    assert set(valores) == {"classified", "failed", "skipped_budget"}
