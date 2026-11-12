"""Response schema of ``GET /api/studio/agents/{key}/prontidao`` (``app.studio.prontidao``): an explicit allowlist."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class ProntidaoItemOut(BaseModel):
    codigo: str
    grupo: str
    severidade: Literal["bloqueante", "aviso", "ok"]
    mensagem: str
    acao_sugerida: str | None = None
    #: A BLOCKING item names the 409 ``code`` publish answers with (``conteudo_incompleto`` | ``compile_blocked`` |
    #: ``mecanismo_reprovado`` | ``eval_required`` | ``qualificacao_indisponivel`` | ``numero_fallback_ausente`` | ``catalogo_ausente`` | ``base_nao_validada``); ``null`` otherwise.
    recusa_publicacao: str | None = None
    detalhe: dict[str, Any] | None = None


class ProntidaoOut(BaseModel):
    agent_key: str
    version_id: UUID
    #: Hash of the draft compiled NOW (what an evaluation must have judged for publish to open).
    hash: str
    #: True iff ``POST .../draft/publish`` would not refuse this draft (the human override of the judge suite aside).
    pronto_para_publicar: bool
    bloqueantes: int
    avisos: int
    itens: list[ProntidaoItemOut]
