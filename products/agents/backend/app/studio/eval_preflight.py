"""Preflight of an eval run or loop round: compile the agent's turn ONCE and refuse, with the reason, before anything is booked
or spent (owner 2026-11-17: 46 cases burned a round because the turn refused to start for a layer with no qualification standard,
and the loop counted a 0.0). The check is the SAME call the turn makes (``turno.preparar`` over the eval world), so it can never
disagree with what the cases will hit."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

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
        # detail-safe: TurnoRecusado.detalhe is a fixed pt-BR domain message authored in turno.py, never an exception's own text
        raise HTTPException(409, detail={
            "detail": f"O agente não pode ser avaliado agora: {exc.detalhe}", "code": exc.codigo, "preflight": True}) from exc


def preflight_comportamento(agent: Any) -> None:
    from app.studio.eval_driver import get_eval_turn_driver

    checar_turno(get_eval_turn_driver(), agent, suite="comportamento")


def preflight_mecanismo(agent: Any, driver: Any) -> None:
    checar_turno(driver, agent, suite="mecanismo")
