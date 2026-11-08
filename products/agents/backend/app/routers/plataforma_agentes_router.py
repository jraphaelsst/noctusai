"""Platform AI-call registry API (migration 069): what the platform's own vendor calls are told, and with which model.

``GET /api/studio/plataforma/agentes`` (list), ``GET|PATCH /api/studio/plataforma/agentes/{chave}`` (read / edit the
whole prompt and the model), ``GET /api/studio/plataforma/modelos?vendor=`` (the allowed models). Platform admin only
(``require_platform_admin``: 401 unauthenticated, 403 ``platform_admin_required`` otherwise). ``modelo`` is validated
against the seed model catalog (``app.plataforma_ia.modelos_permitidos``) for the row's own vendor; an unknown model
is a 422. Seam: ``get_prompt_registry_dep``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field, model_validator

from app.dependencies import require_platform_admin
from app.routers.studio_agents_router import actor_id, http_error
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.integrations.prompt_registry import (
    ChaveNaoEncontrada,
    PromptEntry,
    invalidar_cache,
    make_prompt_registry,
    modelos_permitidos,
)

router = APIRouter(tags=["plataforma-agentes"], include_in_schema=False)

_CHAVE = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"
PROMPT_MAX = 100_000


def get_prompt_registry_dep():
    """DI seam over the platform prompt registry (seed ``prompt_registry``, Real over core's service-role client)."""
    from app.database import get_core_client

    return make_prompt_registry(get_core_client)


class PlataformaAgenteResumo(BaseModel):
    chave: str
    capacidade: str = "chat"
    nome: str
    descricao: str
    vendor: str
    modelo: str
    atualizado_em: datetime | None = None
    atualizado_por: UUID | None = None


class EstatisticaOut(BaseModel):
    vendor: str
    modelo: str
    n: int
    p50_latencia_ms: int
    custo_medio_usd: float | None = None
    taxa_erro: float


class PlataformaAgenteOut(PlataformaAgenteResumo):
    prompt: str
    estatisticas: list[EstatisticaOut] = []


class PlataformaAgentePatch(StrictHttpModel):
    vendor: Literal["anthropic", "openai"] | None = None
    prompt: str | None = Field(default=None, min_length=1, max_length=PROMPT_MAX)
    modelo: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def _algo(self):
        if self.prompt is None and self.modelo is None and self.vendor is None:
            raise ValueError("send prompt, modelo and/or vendor")
        return self


class ModeloOut(BaseModel):
    id: str
    label: str
    vendor: str
    descricao: str = ""
    custo_input_1m: float | None = None
    custo_output_1m: float | None = None


def _resumo(r: PromptEntry) -> dict:
    return {
        "chave": r.chave, "capacidade": r.capacidade, "nome": r.nome, "descricao": r.descricao, "vendor": r.vendor, "modelo": r.modelo,
        "atualizado_em": r.atualizado_em, "atualizado_por": r.atualizado_por,
    }


def _nao_encontrado():
    return http_error(404, "plataforma_agente_not_found", "Chamada de IA da plataforma nao encontrada.")


@router.get("/api/studio/plataforma/agentes", response_model=list[PlataformaAgenteResumo])
def listar_plataforma_agentes(
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_prompt_registry_dep),
) -> list[dict]:
    return [_resumo(r) for r in store.listar()]


@router.get("/api/studio/plataforma/agentes/{chave}", response_model=PlataformaAgenteOut)
def obter_plataforma_agente(
    chave: Annotated[str, Path(pattern=_CHAVE, max_length=64)],
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_prompt_registry_dep),
) -> dict:
    try:
        r = store.obter(chave)
    except ChaveNaoEncontrada as exc:
        raise _nao_encontrado() from exc
    return {**_resumo(r), "prompt": r.prompt, "estatisticas": store.estatisticas(chave)}


@router.patch("/api/studio/plataforma/agentes/{chave}", response_model=PlataformaAgenteOut)
def editar_plataforma_agente(
    chave: Annotated[str, Path(pattern=_CHAVE, max_length=64)],
    payload: PlataformaAgentePatch,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_prompt_registry_dep),
) -> dict:
    try:
        atual = store.obter(chave)
        vendor = payload.vendor or atual.vendor
        modelo = payload.modelo or atual.modelo
        if (payload.modelo is not None or payload.vendor is not None) and modelo not in {
            m["id"] for m in modelos_permitidos(vendor, atual.capacidade)
        }:
            raise http_error(
                422, "modelo_invalido",
                f"Modelo {modelo!r} nao pertence ao catalogo de {vendor} para {atual.capacidade}; escolha um modelo de {vendor}.",
            )
        r = store.atualizar(
            chave, prompt=payload.prompt, modelo=payload.modelo, vendor=payload.vendor, actor=actor_id(ctx))
    except ChaveNaoEncontrada as exc:
        raise _nao_encontrado() from exc
    invalidar_cache(chave)
    return {**_resumo(r), "prompt": r.prompt, "estatisticas": store.estatisticas(chave)}


@router.get("/api/studio/plataforma/modelos", response_model=list[ModeloOut])
def listar_modelos(
    vendor: Literal["anthropic", "openai"] | None = Query(default=None),
    capacidade: Literal["chat", "vision", "transcription"] = Query(default="chat"),
    ctx: AuthContext = Depends(require_platform_admin),
) -> list[dict]:
    vendors = (vendor,) if vendor else ("anthropic", "openai")
    return [m for v in vendors for m in modelos_permitidos(v, capacidade)]
