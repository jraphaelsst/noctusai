"""Pydantic contracts for Módulo 4 — esteira, timesheet and approval portal."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "TarefaOut",
    "TarefaUpdate",
    "ApontamentoOut",
    "LinkAprovacaoOut",
    "AprovacaoPublicaOut",
    "PecaPublica",
    "DecisaoIn",
    "DecisaoOut",
    "PapelEtapaIn",
]

class TarefaOut(BaseModel):
    """A tarefa row. Its stage is `etapa_id` (a user-editable stage ROW since
    migration 017); the board endpoint serves the stage objects themselves."""

    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    pauta_id: str
    cliente_id: str | None = None
    titulo: str
    etapa_id: str
    #: Fractional board position — PostgREST serves `numeric` as a string.
    kanban_pos: float | str | None = None
    responsavel_id: str | None = None
    prazo: str | None = None
    refacoes: int = 0
    observacao_cliente: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TarefaUpdate(StrictHttpModel):
    """PATCH `/api/esteira/tarefas/{id}` — título, responsável, prazo, pauta.

    Deliberately does NOT accept `etapa_id`: moving a tarefa between stages
    is `mover-etapa`'s job (the one-step-forward / motivo-to-go-back rules,
    the refação count, the automations) — a second path that could write
    `etapa_id` directly would bypass every one of those. Before this schema
    existed there was no edit at all: fixing a typo in `titulo`, or a wrong
    `responsavel_id`, meant deleting the tarefa and losing its apontamentos.
    """

    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    responsavel_id: str | None = None
    prazo: str | None = None
    pauta_id: str | None = None


class ApontamentoOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    tarefa_id: str
    usuario_id: str
    profissional_id: str | None = None
    iniciado_em: str
    encerrado_em: str | None = None
    minutos: int = 0


class LinkAprovacaoOut(BaseModel):
    """What the agency gets back after minting a client link."""

    model_config = ConfigDict(extra="ignore")

    id: str
    tarefa_id: str
    token: str
    expira_em: str | None = None
    decidido_em: str | None = None
    decisao: str | None = None


class PecaPublica(BaseModel):
    """A peça as the CLIENT sees it: a fetchable URL and nothing else.

    No storage key, no id — those are the agency's internals and would let a
    caller probe the bucket.
    """

    url: str | None = None
    mime_type: str | None = None


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
    #: The spec's "peça em paralelo com o texto da legenda". Empty when the
    #: pauta has no asset yet — the portal degrades to copy-only rather than
    #: showing a broken frame.
    pecas: list[PecaPublica] = Field(default_factory=list)
    ja_decidida: bool = False
    #: False once the agency pulled the tarefa out of the approval stage — the
    #: portal then shows the content read-only (a decision would be a 409).
    aguardando_aprovacao: bool = True


class DecisaoIn(StrictHttpModel):
    decisao: Literal["aprovado", "ajuste"]
    observacao: str = Field(default="", max_length=2000)


class DecisaoOut(BaseModel):
    ok: bool
    decisao: str
    #: Whether the agency was ACTUALLY notified (an in-app row was written for
    #: at least one recipient). The portal's "Sua agência já foi notificada"
    #: copy used to be shown unconditionally — including when the notify call
    #: raised, or had zero recipients — which is a promise the backend cannot
    #: keep. Defaults to `False` so a caller that forgets to set it never
    #: overstates what happened.
    notificado: bool = False


class PapelEtapaIn(StrictHttpModel):
    """`PATCH /api/esteira/stages/{id}/papel` — reassign a system role.

    `papel: None` CLEARS the role from this stage. Sent through a dedicated
    endpoint (not the generic stage PATCH) because reassigning a role — never
    leaving zero stages carrying it — needs to read AND write more than one
    stage atomically; see `esteira_router.atribuir_papel_etapa`.
    """

    papel: str | None = None
