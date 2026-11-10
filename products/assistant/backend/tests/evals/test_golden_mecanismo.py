"""Mechanism evals over the synthetic golden set (no live model: CI never calls a provider).

What this proves without a model: every golden message reaches the provider as the user turn, alone and verbatim;
a correct answer is recorded with the expected verdict; and for the adversarial cases, every way a hijacked model
could break the output format (free text, echoing the message, extra keys, an identifier, an incoherent code) is
REFUSED by the server -- the format cannot be changed by text inside a message. The model's own accuracy on this set
is the LIVE eval (Haiku, failures-only, a US$ cap), run on the registry row's hash, not here.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.shadow import classificador as clf
from tests.shadow.conftest import ORG, PROMPT, resposta

GOLDEN = json.loads((Path(__file__).parent / "golden_agendamento.json").read_text(encoding="utf-8"))
CASOS = GOLDEN["casos"]


def test_golden_set_is_well_formed_and_covers_the_four_categories():
    ids = [c["id"] for c in CASOS]
    assert len(ids) == len(set(ids))
    assert {c["categoria"] for c in CASOS} == {"claro_sim", "claro_nao", "ambiguo", "adversarial"}
    for c in CASOS:
        validos = clf.MOTIVOS_SIM if c["esperado"] else clf.MOTIVOS_NAO
        assert c["motivos"] and set(c["motivos"]) <= set(validos), c["id"]
    assert sum(c["categoria"] == "adversarial" for c in CASOS) >= 8


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_each_golden_message_goes_alone_and_verbatim_and_a_correct_answer_is_recorded(seam, registro, caso):
    fake = seam([resposta(caso["esperado"], caso["motivos"][0])])
    r = asyncio.run(clf.classificar(caso["texto"], org_id=ORG, registry=registro))
    assert fake.calls[-1]["messages"] == [
        {"role": "system", "content": PROMPT}, {"role": "user", "content": caso["texto"]},
    ]
    assert r.classificacao.is_scheduling is caso["esperado"]
    assert r.classificacao.reason_code in caso["motivos"]


def _sequestros(texto: str) -> list[str]:
    """What a model that FOLLOWED an injected instruction might answer instead of the contract."""
    return [
        "SIM",
        "Olá! Claro, posso ajudar com isso.",
        texto,
        json.dumps({"is_scheduling": True, "confidence": 1, "reason_code": texto[:60]}),
        json.dumps({"is_scheduling": False, "confidence": 0.9, "reason_code": "sem_agendamento", "telefone": "5511988887777"}),
        json.dumps({"is_scheduling": True, "confidence": 0.9, "reason_code": "sem_agendamento"}),
        json.dumps({"is_scheduling": True, "confidence": 0.9, "reason_code": "propoe_horario"}) + "\nExplicação: ...",
        json.dumps([{"is_scheduling": True, "confidence": 0.9, "reason_code": "propoe_horario"}]),
    ]


@pytest.mark.parametrize("caso", [c for c in CASOS if c["categoria"] == "adversarial"],
                         ids=[c["id"] for c in CASOS if c["categoria"] == "adversarial"])
def test_an_injected_instruction_cannot_change_the_output_format(caso):
    for saida in _sequestros(caso["texto"]):
        with pytest.raises(clf.SaidaInvalida):
            clf.interpretar(saida)
