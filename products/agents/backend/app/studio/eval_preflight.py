"""Preflight of an eval run or loop round: compile the agent's turn ONCE and refuse, with the reason, before anything is booked
or spent (owner 2026-11-17: 46 cases burned a round because the turn refused to start for a layer with no qualification standard,
and the loop counted a 0.0). The check is the SAME call the turn makes (``turno.preparar`` over the eval world), so it can never
disagree with what the cases will hit."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# The reason shown to the owner is chosen HERE by the refusal's stable code -- never copied out of the exception.
_MOTIVOS: dict[str, str] = {
    "qualificacao_indisponivel": "O agente não tem um padrão de qualificação publicado.",
    "no_active_version": "O agente não tem versão publicada.",
    "no_draft": "O agente não tem rascunho para avaliar.",
    "conteudo_incompleto": "O conteúdo do agente está incompleto.",
    "prompt_too_large": "O prompt compilado passa do limite de tamanho.",
    "agente_nao_informado": "A avaliação não indica qual agente executar.",
    "agente_nao_encontrado": "O agente da avaliação não existe.",
    "capacidade": "Capacidade esgotada.",
}
_MOTIVO_GENERICO = "O turno do agente não pode começar."

__all__ = ["checar_turno", "preflight_comportamento", "preflight_mecanismo"]


def checar_turno(driver: Any, agent: Any, *, suite: str) -> None:
    """Raise 409 ``{code, detail}`` (the turn's own refusal) when the agent's turn cannot start; a no-op for a driver without a
    preflight (a scripted Fake) and, in the behaviour suite, for an agent that does not run on the channel turn path."""
    if driver is None or not hasattr(driver, "preflight"):
        return
    if suite == "comportamento" and not (
        getattr(agent, "modelo", False) or (getattr(agent, "usa_canais", False) and getattr(agent, "runtime", "") == "llm")
    ):
        return
    from app.channels.turno import TurnoRecusado

    if hasattr(driver, "definir_agente"):
        driver.definir_agente(agent.key)
    try:
        driver.preflight()
    except TurnoRecusado as exc:
        logger.warning("eval preflight refused agent=%s code=%s detalhe=%s", agent.key, exc.codigo, exc.detalhe)
        codigo = str(exc.codigo)
        motivo = _MOTIVOS.get(codigo, _MOTIVO_GENERICO)
        if codigo == "conteudo_incompleto" and getattr(exc, "interno", ""):
            motivo = f"{motivo.rstrip('.')}. {exc.interno}"  # registry keys from our own compile: names the missing system texts
        raise HTTPException(409, detail={
            "detail": "O agente não pode ser avaliado agora: " + motivo, "code": codigo, "preflight": True}) from exc


def preflight_comportamento(agent: Any) -> None:
    from app.studio.eval_driver import get_eval_turn_driver

    checar_turno(get_eval_turn_driver(), agent, suite="comportamento")


def preflight_mecanismo(agent: Any, driver: Any) -> None:
    checar_turno(driver, agent, suite="mecanismo")
