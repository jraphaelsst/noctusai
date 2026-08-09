"""Pydantic contracts for Módulo 4 — esteira, timesheet and approval portal."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

from app.repositories import ETAPAS

__all__ = [
    "Etapa",
    "TarefaCreate",
    "TarefaOut",
    "MoverTarefa",
    "QuadroResponse",
    "ApontamentoOut",
    "IniciarTimer",
    "LinkAprovacaoOut",
    "AprovacaoPublicaOut",
    "DecisaoIn",
    "DecisaoOut",
]

#: Derived from the repository constant so the wire contract, the DB CHECK
#: and the kanban can never disagree about the 8 steps.
Etapa = Literal[ETAPAS]  # type: ignore[valid-type]


class TarefaCreate(StrictHttpModel):
    pauta_id: str
    titulo: str = Field(min_length=1, max_length=200)
    responsavel_id: str | None = None
    prazo: str | None = None


class TarefaOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    pauta_id: str
    titulo: str
    etapa: str
    responsavel_id: str | None = None
    prazo: str | None = None
    refacoes: int = 0
    observacao_cliente: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MoverTarefa(StrictHttpModel):
    etapa: str


class QuadroResponse(BaseModel):
    """The kanban: ordered column keys plus the tasks in each.

    `etapas` is sent explicitly rather than letting the client hardcode the
    order — the sequence is a business rule (the rigid esteira), and a client
    that invents its own ordering would drift from the backend's.
    """

    etapas: list[str]
    colunas: dict[str, list[TarefaOut]]


class ApontamentoOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    tarefa_id: str
    usuario_id: str
    iniciado_em: str
    encerrado_em: str | None = None
    minutos: int = 0


class IniciarTimer(StrictHttpModel):
    usuario_id: str


class LinkAprovacaoOut(BaseModel):
    """What the agency gets back after minting a client link."""

    model_config = ConfigDict(extra="ignore")

    id: str
    tarefa_id: str
    token: str
    expira_em: str | None = None
    decidido_em: str | None = None
    decisao: str | None = None


class AprovacaoPublicaOut(BaseModel):
    """What the CLIENT sees on the public portal.

    Deliberately narrow: the tarefa's title, the copy and the brand context —
    and nothing that would leak the agency's internals (no org_id, no
    responsavel, no refação counter, no ids the client could probe with).
    """

    titulo: str
    copy_texto: str | None = None
    direcao_video: str | None = None
    formato: str | None = None
    cliente_nome: str | None = None
    ja_decidida: bool = False


class DecisaoIn(StrictHttpModel):
    decisao: Literal["aprovado", "ajuste"]
    observacao: str = Field(default="", max_length=2000)


class DecisaoOut(BaseModel):
    ok: bool
    decisao: str
