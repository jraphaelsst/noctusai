"""THE outbound gate for every automatic agent WhatsApp send -- one chokepoint, gate 0 + two gates.

Every message Julia sends on her own (a reply turn, the re-engagement tiers, a regua attempt, the Meta
lead-form first contact, the Google review ask) passes `exigir` BEFORE it reaches a transport:

  gate 0  only for a send on behalf of a block OTHER than `sdr` (`exigir(..., bloco=...)`, maya-blocks): that
          block's `atendimento_blocos` row is `ativo` AND names an `agent_key` (absent row = the code default =
          off, so in v1 -- no agent allowed outside `sdr` -- every such send is refused: `bloco_inativo` /
          `bloco_sem_agente` / `bloco_desconhecido`). `bloco='sdr'` (the default) skips it: Julia's own on/off is
          gate 1, exactly as before -- the block's `ativo` means "Maya supervises it", never "Julia may talk";

  gate 1  the line has Julia on: `whatsapp_connections.agente_leads_ativo` (DB default false), re-read from the
          DB at send time -- never a record object loaded earlier, so switching Julia off stops a queued job;
  gate 2  the org opted in to THIS flow (every default is off / NULL, nothing is seeded):
            resposta              -- none beyond gate 1: the lead wrote first (also covers the recesso notice,
                                     the privacy disclosure and the deletion confirmation of that turn)
            reengajamento_minutos -- `lais_reengajamento_config.minutos_ativo`   (default false)
            reengajamento_horas   -- `lais_reengajamento_config.horas_ativo`     (default false)
            regua                 -- the `lais_reguas` row is `ativa`            (default false)
            primeiro_contato      -- an APPROVED `primeiro_contato` modelo exists (none until the org submits one
                                     and Meta approves it)
            avaliacao             -- `lais_avaliacao_config.google_review_url` is set (default NULL)

Refuse-not-null: a blocked send raises `EnvioBloqueado` after logging the reason and emitting the
`envio_bloqueado` Lais event (`{fluxo, motivo, connection_id}`, plus `bloco` for a non-`sdr` block) -- never a
silent skip. Callers turn it into
their own outcome label.

`exigir` returns a `Liberacao`; a send helper that does not call `exigir` itself takes the `Liberacao` and calls
`conferir` on it; a `Liberacao` is sealed (only `exigir` can build one). Keeper:
`tests/services/test_lais_envio_gate_keeper.py` fails when a WhatsApp send in a Lais module -- or in any module that
imports one -- sits in a function that does not CALL `exigir` / `conferir` (operator-initiated sends are listed there
one by one with their reason).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from app.services import lais_eventos_service

logger = logging.getLogger(__name__)

T_CONEXOES = "whatsapp_connections"
T_REENGAJAMENTO_CONFIG = "lais_reengajamento_config"
T_REGUAS = "lais_reguas"
T_MODELOS = "lais_modelos"
T_AVALIACOES_CONFIG = "lais_avaliacao_config"
EVENTO_BLOQUEADO = "envio_bloqueado"


class Fluxo(str, Enum):
    RESPOSTA = "resposta"
    REENGAJAMENTO_MINUTOS = "reengajamento_minutos"
    REENGAJAMENTO_HORAS = "reengajamento_horas"
    REGUA = "regua"
    PRIMEIRO_CONTATO = "primeiro_contato"
    AVALIACAO = "avaliacao"


#: `run_reengajamento_turn`'s `estado_extra["reengajamento"]` -> the flow it is.
FLUXO_DO_TIER: dict[str, Fluxo] = {
    "minutos": Fluxo.REENGAJAMENTO_MINUTOS, "horas": Fluxo.REENGAJAMENTO_HORAS, "regua": Fluxo.REGUA,
}


#: Module-private seal: only `exigir` can build a `Liberacao` (a hand-built one raises), so a pass cannot be forged.
_SELO = object()


@dataclass(frozen=True)
class Liberacao:
    """Proof that `exigir` passed for this org + line + flow. Only `exigir` builds one (sealed)."""

    org_id: str
    connection_id: str
    fluxo: Fluxo
    selo: object = field(default=None, repr=False, compare=False)
    #: The block the send is made for (maya-blocks); `sdr` = Julia.
    bloco: str = "sdr"

    def __post_init__(self) -> None:
        if self.selo is not _SELO:
            raise TypeError("Liberacao is issued only by lais_envio_gate.exigir")


class EnvioBloqueado(Exception):
    """A gate refused the send; `motivo` is the first failing check."""

    def __init__(self, fluxo: Fluxo, motivo: str):
        super().__init__(f"envio {fluxo.value} bloqueado: {motivo}")
        self.fluxo = fluxo
        self.motivo = motivo


def _uma(db: Any, tabela: str, org_id: str, **filtros: Any) -> Optional[dict[str, Any]]:
    q = db.table(tabela).select("*").eq("org_id", org_id)
    for coluna, valor in filtros.items():
        q = q.eq(coluna, valor)
    rows = q.limit(1).execute().data or []
    return rows[0] if rows else None


BLOCO_SDR = "sdr"


def _motivo_do_bloco(db: Any, org: str, bloco: str) -> Optional[str]:
    """Gate 0 (a block other than `sdr`): its row is `ativo` and names an agent. Absent row = default = off."""
    from app.modules.atendimento_blocos import repository as blocos_repo
    from app.modules.atendimento_blocos.blocos import BLOCO_POR_NOME

    if bloco not in BLOCO_POR_NOME:
        return "bloco_desconhecido"
    config = blocos_repo.config_do_bloco(db, org, bloco)
    if not config.ativo:
        return "bloco_inativo"
    if not config.agent_key:
        return "bloco_sem_agente"
    return None


def motivo_do_bloqueio(
    db: Any, org_id: UUID | str, connection_id: UUID | str | None, fluxo: Fluxo, *, regua_id: UUID | str | None = None,
    bloco: str = BLOCO_SDR,
) -> Optional[str]:
    """None when every gate passes; otherwise the first failing check. Pure read -- `exigir` acts on it."""
    org = str(org_id)
    if bloco != BLOCO_SDR:
        motivo_bloco = _motivo_do_bloco(db, org, bloco)
        if motivo_bloco is not None:
            return motivo_bloco
    if not connection_id:
        return "sem_conexao"
    conexao = _uma(db, T_CONEXOES, org, id=str(connection_id))
    if conexao is None:
        return "sem_conexao"
    if conexao.get("agente_leads_ativo") is not True:
        return "julia_desligada"
    if fluxo is Fluxo.RESPOSTA:
        return None
    if fluxo in (Fluxo.REENGAJAMENTO_MINUTOS, Fluxo.REENGAJAMENTO_HORAS):
        cfg = _uma(db, T_REENGAJAMENTO_CONFIG, org) or {}
        chave = "minutos_ativo" if fluxo is Fluxo.REENGAJAMENTO_MINUTOS else "horas_ativo"
        return None if cfg.get(chave) is True else "reengajamento_desativado"
    if fluxo is Fluxo.REGUA:
        regua = _uma(db, T_REGUAS, org, id=str(regua_id)) if regua_id else None
        return None if regua and regua.get("ativa") is True else "regua_inativa"
    if fluxo is Fluxo.PRIMEIRO_CONTATO:
        modelo = _uma(db, T_MODELOS, org, categoria="primeiro_contato", status="aprovado")
        return None if modelo else "modelo_nao_aprovado"
    if fluxo is Fluxo.AVALIACAO:
        cfg = _uma(db, T_AVALIACOES_CONFIG, org) or {}
        return None if cfg.get("google_review_url") else "sem_link"
    return "fluxo_desconhecido"


def exigir(
    db: Any, org_id: UUID | str, connection_id: UUID | str | None, fluxo: Fluxo, *,
    contato_id: UUID | str | None = None, regua_id: UUID | str | None = None, bloco: str = BLOCO_SDR,
) -> Liberacao:
    """Every gate, or `EnvioBloqueado` (logged + `envio_bloqueado` event). `db` is the social_wiring-scoped client."""
    fluxo = Fluxo(fluxo)
    motivo = motivo_do_bloqueio(db, org_id, connection_id, fluxo, regua_id=regua_id, bloco=bloco)
    if motivo is None:
        return Liberacao(org_id=str(org_id), connection_id=str(connection_id), fluxo=fluxo, selo=_SELO, bloco=bloco)
    logger.warning(
        "lais: envio %s BLOQUEADO (%s) org=%s conn=%s contato=%s bloco=%s", fluxo.value, motivo, org_id, connection_id, contato_id, bloco,
    )
    payload = {"fluxo": fluxo.value, "motivo": motivo, "connection_id": str(connection_id) if connection_id else None}
    if bloco != BLOCO_SDR:
        payload["bloco"] = bloco
    lais_eventos_service.emitir(db, org_id, EVENTO_BLOQUEADO, contato_id, payload)
    raise EnvioBloqueado(fluxo, motivo)


def conferir(liberacao: Any, connection_id: UUID | str) -> Liberacao:
    """A send helper's check that it was handed a real `Liberacao` for THIS line."""
    if not isinstance(liberacao, Liberacao):
        raise EnvioBloqueado(Fluxo.RESPOSTA, "sem_liberacao")
    if liberacao.connection_id != str(connection_id):
        raise EnvioBloqueado(liberacao.fluxo, "liberacao_de_outra_conexao")
    return liberacao


__all__ = [
    "BLOCO_SDR", "EVENTO_BLOQUEADO", "EnvioBloqueado", "FLUXO_DO_TIER", "Fluxo", "Liberacao", "conferir", "exigir",
    "motivo_do_bloqueio",
]
