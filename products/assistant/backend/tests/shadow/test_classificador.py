"""The classifier call itself: the provider receives the message TEXT only, the text is cut at 4000 characters, the
answer is parsed strictly (off-contract => SaidaInvalida => `failed`), and the money gate refusing or being unable to
verify is `skipped_budget` with the text KEPT. All through the real seed seam over a Fake provider; no live model."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.jobs.entity import Job, JobStatus
from noctusai_lib.integrations.llm.exceptions import SpendCeilingExceeded, SpendCeilingUnverifiable
from noctusai_lib.integrations.llm.spend_guard import InMemorySpendWindowReader, SurfaceLimit, configure_spend_guard
from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, RegistroIAIndisponivel

from app.shadow import classificador as clf
from app.shadow import worker as w
from tests.shadow.conftest import MODELO, ORG, PROMPT, resposta


def _run(coro):
    return asyncio.run(coro)


def _job(intake_id):
    now = datetime.now(timezone.utc)
    return Job(id="j", type=w.JOB_CLASSIFICAR, payload={"intake_id": intake_id}, status=JobStatus.RUNNING,
               retry_count=0, max_retries=3, last_error=None, created_at=now, updated_at=now)


def _limite(falha: str) -> None:
    reader = InMemorySpendWindowReader()
    if falha == "exceeded":
        reader.totals[(ORG, "assistant", None)] = 9.0
    else:
        reader.fail_with = RuntimeError("ledger down")
    configure_spend_guard(reader=reader, limits={"assistant": SurfaceLimit("assistant", 1.0, "enforce")})


# ── text only ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_provider_receives_only_the_registry_prompt_and_the_message_text(seam, registro):
    fake = seam([resposta(True)])
    r = _run(clf.classificar("Pode ser quinta às 15h?", org_id=ORG, registry=registro))
    (chamada,) = fake.calls
    assert chamada["messages"] == [
        {"role": "system", "content": PROMPT}, {"role": "user", "content": "Pode ser quinta às 15h?"},
    ]
    assert ORG not in json.dumps(chamada["messages"], ensure_ascii=False)
    assert r.modelo == MODELO and r.prompt_version == clf.versao_do_prompt(PROMPT)


def test_the_worker_forwards_the_body_and_nothing_else_from_the_row(seam, registro, db):
    fake = seam([resposta(False)])
    i = db.add("Viu o jogo ontem?")
    _run(w.Classificador(db, registry=registro).classificar_intake(_job(i)))
    enviado = json.dumps(fake.calls, default=str, ensure_ascii=False)
    for identificador in (i, db.rows[i]["chat_ref"], db.rows[i]["waha_message_id"], db.rows[i]["phone"]):
        assert identificador not in enviado
    assert fake.calls[0]["messages"][1:] == [{"role": "user", "content": "Viu o jogo ontem?"}]


# ── truncation ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_text_longer_than_4000_chars_is_cut_and_the_cut_is_recorded(seam, registro):
    assert clf.MAX_CHARS_PADRAO == 4000
    fake = seam([resposta(False), resposta(False)])
    longo = "a" * 4500
    r = _run(clf.classificar(longo, org_id=ORG, registry=registro))
    assert fake.calls[0]["messages"][-1]["content"] == "a" * 4000
    assert r.truncado is True and r.metadata("primeira")["truncado"] is True
    r2 = _run(clf.classificar("a" * 4000, org_id=ORG, registry=registro))
    assert fake.calls[1]["messages"][-1]["content"] == "a" * 4000 and r2.truncado is False


# ── strict parse ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("saida,motivo", [
    ("SIM", "nao_e_objeto_json"),
    ("Claro! {\"is_scheduling\": true}", "nao_e_objeto_json"),
    ("{is_scheduling: true}", "json_invalido"),
    ('{"is_scheduling": true, "confidence": 0.9}', "fora_do_contrato"),
    ('{"is_scheduling": true, "confidence": 0.9, "reason_code": "propoe_horario", "extra": 1}', "fora_do_contrato"),
    ('{"is_scheduling": "true", "confidence": 0.9, "reason_code": "propoe_horario"}', "fora_do_contrato"),
    ('{"is_scheduling": true, "confidence": 1.5, "reason_code": "propoe_horario"}', "fora_do_contrato"),
    ('{"is_scheduling": true, "confidence": true, "reason_code": "propoe_horario"}', "fora_do_contrato"),
    ('{"is_scheduling": true, "confidence": 0.9, "reason_code": "talvez"}', "fora_do_contrato"),
    ('{"is_scheduling": true, "confidence": 0.9, "reason_code": "sem_agendamento"}', "motivo_incoerente"),
    ('{"is_scheduling": false, "confidence": 0.9, "reason_code": "cancela"}', "motivo_incoerente"),
])
def test_off_contract_output_is_refused_with_a_code(saida, motivo):
    with pytest.raises(clf.SaidaInvalida) as exc:
        clf.interpretar(saida)
    assert exc.value.motivo == motivo


def test_the_contract_and_a_json_fence_are_accepted():
    assert clf.interpretar(resposta(True, "remarca")).reason_code == "remarca"
    cercado = "```json\n" + resposta(False, "insuficiente", 1) + "\n```"
    c = clf.interpretar(cercado)
    assert c.is_scheduling is False and c.confidence == 1.0


def test_off_contract_output_from_the_model_makes_the_row_failed(seam, registro, db):
    seam(['{"is_scheduling": true, "confidence": 0.9, "reason_code": "sem_agendamento"}'])
    i = db.add("Pode ser quinta?")
    _run(w.Classificador(db, registry=registro).classificar_intake(_job(i)))
    assert db.rows[i]["outcome"] == "failed"
    assert db.desfechos == [(i, "failed", "saida_invalida:motivo_incoerente")] and db.outputs == {}


# ── money gate ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("falha,erro", [("exceeded", SpendCeilingExceeded), ("unverifiable", SpendCeilingUnverifiable)])
def test_spend_refusal_or_unverifiable_raises_before_the_provider_is_called(seam, registro, falha, erro):
    fake = seam([resposta(True)])
    _limite(falha)
    with pytest.raises(erro):
        _run(clf.classificar("Pode ser quinta?", org_id=ORG, registry=registro))
    assert fake.calls == []


@pytest.mark.parametrize("falha", ["exceeded", "unverifiable"])
def test_spend_refusal_or_unverifiable_is_skipped_budget_with_the_body_kept(seam, registro, db, falha):
    fake = seam([resposta(True)])
    _limite(falha)
    i = db.add("Pode ser quinta?")
    _run(w.Classificador(db, registry=registro).classificar_intake(_job(i)))
    assert db.rows[i]["outcome"] == "skipped_budget"
    assert db.rows[i]["body"] == "Pode ser quinta?"
    assert fake.calls == [] and db.outputs == {}


# ── registry ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_missing_registry_row_refuses_instead_of_guessing(seam):
    fake = seam([resposta(True)])
    with pytest.raises(RegistroIAIndisponivel):
        _run(clf.classificar("Pode ser quinta?", org_id=ORG, registry=FakePromptRegistry([])))
    assert fake.calls == []


def test_editing_the_prompt_moves_prompt_version(registro):
    antes = clf.versao_atual(registry=registro)
    registro.atualizar(clf.CHAVE, prompt="PROMPT v2")
    depois = clf.versao_atual(registry=registro)
    assert antes[0] != depois[0] and antes[1] == depois[1]
    assert depois[0] == clf.versao_do_prompt("PROMPT v2") and depois[0].startswith(clf.CHAVE + "@")
