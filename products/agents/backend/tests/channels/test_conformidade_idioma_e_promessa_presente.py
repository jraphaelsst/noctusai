"""Julia's `mecanismo` run d6cf6ad5 (2026-11-27): ``transferencia_sem_handoff`` missed a first-person PRESENT promise ("então eu passo a sua preferência ... para ele"): the lead
   was told the visit request was handed over and nothing was handed over.
"""
from __future__ import annotations

import pytest

from app.channels import conformidade as c

class TestPromessaDeContatoNoPresente:
    @pytest.mark.parametrize("resposta", [
        "Quem combina a visita e o horário é o corretor, então eu passo a sua preferência de sábado de manhã para ele.",
        "Passo seu pedido para o corretor agora.",
        "Encaminho a sua preferência pra equipe.",
        "Eu repasso isso para ela.",
        "Passo seu pedido pro corretor agora.", "Passo a sua preferência aos corretores.", "Eu repasso isso pras atendentes.",
        "Repasso isso pros corretores.",
    ])
    def test_the_present_tense_handover_is_a_promise_when_nothing_backs_it(self, resposta):
        assert c.transferencia_sem_handoff(resposta, transferiu_no_turno=False)

    @pytest.mark.parametrize("resposta", [
        "Quem combina a visita e o horário é o corretor, então eu passo a sua preferência de sábado de manhã para ele.",
        "Passo seu pedido para o corretor agora.",
    ])
    def test_it_is_true_after_a_handoff_or_a_registered_visit(self, resposta):
        assert c.transferencia_sem_handoff(resposta, transferiu_no_turno=True) is None
        assert c.transferencia_sem_handoff(resposta, transferiu_no_turno=False, contato_garantido_no_turno=True) is None

    @pytest.mark.parametrize("resposta", [
        "Te explico passo a passo para ele entender.",
        "Se quiser, eu passo para o corretor.",
        "Não passo seu pedido para o corretor sem você confirmar.",
        "Posso te passar o link para você ver.",
        "O passo seguinte é escolher o bairro. Qual você prefere?",
        "O passo seguinte é escolher o bairro para a visita.", "Um passo importante para ele é decidir o orçamento.",
        "Esse passo para o corretor confirmar vem depois.", "O próximo passo para o time é a visita.",
        "Cada passo para o corretor leva um dia.", "Passo: enviar documento para o corretor.",
        "O primeiro passo para ela é escolher.", "Este passo pro corretor leva um dia.", "O último passo aos corretores é a visita.",
        "Encaminho seu contato para o corretor?", "Passo seu pedido para ele?",
    ])
    def test_idioms_offers_and_negations_are_no_promise(self, resposta):
        assert c.transferencia_sem_handoff(resposta, transferiu_no_turno=False) is None
