"""Stage gates — a card may not ENTER a role-bearing stage while a check refuses.

The API is the only place this can live: the drag is not the only way a card
moves (the board, the card dialog and any automation reach the same endpoint),
so a gate enforced in the UI is a courtesy and nothing more.

Gates are keyed by the stage's `papel`, never its name or id, so an operator
renaming or reordering the column cannot dodge (or break) the rule.
"""
from __future__ import annotations

from typing import Any, Mapping

from .config import FunnelConfig, FunnelContext, FunnelGate, Pendencia
from .errors import FunnelError


class GateRefused(FunnelError):
    """409 `gate_refused` — `details = {gate, pendencias:[{codigo, mensagem}]}`."""

    def __init__(self, gate: str, pendencias: list[Pendencia]):
        super().__init__(
            "gate_refused",
            pendencias[0].mensagem if pendencias else "Movimento recusado.",
            409,
            {"gate": gate, "pendencias": [p.as_dict() for p in pendencias]},
        )
        self.gate = gate
        self.pendencias = pendencias


def gate_for(cfg: FunnelConfig, stage: Mapping[str, Any]) -> FunnelGate | None:
    papel = stage.get("papel")
    return cfg.gates.get(papel) if papel else None


def run_gate(cfg: FunnelConfig, ctx: FunnelContext, card: dict, stage: Mapping[str, Any]) -> None:
    """Raise `GateRefused` when the gate for `stage`'s role has pendencies.

    Only the `extra` keys the gate DECLARED in `inputs` reach it: the body is
    client-controlled, and a check should not be able to be steered by a key it
    never asked for.
    """
    gate = gate_for(cfg, stage)
    if gate is None:
        return
    scoped = FunnelContext(
        db=ctx.db,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
        extra={k: v for k, v in ctx.extra.items() if k in gate.inputs},
        to_stage=stage,
    )
    pendencias = gate.check(ctx.db, scoped, card)
    if pendencias:
        raise GateRefused(gate.code, list(pendencias))


__all__ = ["GateRefused", "gate_for", "run_gate"]
