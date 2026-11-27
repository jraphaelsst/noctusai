"""Owner decision 2026-11-27: Julia answers in Portuguese only, but a stop request is honoured in ANY language (consent
withdrawal). The deterministic floor (exact message) and the stop-sentence guard (no complaint alert on a stop) speak
English and Spanish too."""
from __future__ import annotations

import pytest

from app.channels import conformidade as c


@pytest.mark.parametrize("mensagem", [
    "STOP", "Stop!", "unsubscribe", "Stop messaging me", "stop texting me.", "Don't message me", "do not contact me", "remove me",
    "alto", "Basta", "basta!", "No me escribas", "no me escribas más", "No me escriban", "detente", "darse de baja", "opt out",
    "PARAR", "sai",
])
def test_the_exact_stop_message_ends_the_conversation_in_any_language(mensagem):
    assert c.palavra_de_parar([mensagem], None) is not None, mensagem


@pytest.mark.parametrize("mensagem", [
    "I want to stop by the apartment on Saturday", "Hi, I would like to see the flat", "no me gusta el barrio", "alto padrão, por favor",
])
def test_ordinary_messages_are_no_stop(mensagem):
    assert c.palavra_de_parar([mensagem], None) is None


@pytest.mark.parametrize("mensagem", [
    "This service is terrible, stop messaging me", "Please don't contact me again", "Unsubscribe me from this list",
    "No me escribas más, qué atención horrible", "Dejen de escribirme por favor",
])
def test_a_stop_sentence_in_another_language_is_never_alerted_as_a_complaint(mensagem):
    assert c.insatisfacao_sem_alerta(
        [mensagem], alertou_no_turno=False, padroes=[r"horrible|terrible"]) is None
