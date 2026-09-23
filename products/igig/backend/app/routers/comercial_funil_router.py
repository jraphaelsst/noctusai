"""Comercial funnel board — roadmap R2/R3/R4.

  GET/POST/PATCH/DELETE /api/comercial/pipeline/stages …  stage editor (seed
                                                          router; writes = org
                                                          admins; `fechado` is
                                                          protected)
  GET   /api/comercial/board                              the funnel columns
  POST  /api/comercial/negocios                           put a lead on the funnel
  PATCH /api/comercial/negocios/{id}                      edit titulo/valor/responsável
  POST  /api/comercial/negocios/{id}/mover-etapa          drag (Fechado REQUIRES
                                                          `orcamento_id`)
  POST  /api/comercial/negocios/{id}/perder               archive with a reason

The negócio CARD surface (notas, tags, membros, checklists, documentos,
timeline, `/card`) is the seed card hub under the same prefix
(`app/card_hub.py`); its collection router is mounted BEFORE this one.

Rules live in `app/services/comercial_funil.py`; this router maps HTTP to them.
Board + move responses use the seed `{"data": ...}` envelope the seed
`createPipelineHooks` consumes.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.domain.pipeline import pipeline_stages_router
from noctusai_lib.primitives.responses import success_response

from app.automacoes_deps import get_portas_automacao
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import (
    PIPELINE_COMERCIAL,
    exigir_admin_da_org,
    get_db,
    get_pipeline_auth,
    pipeline_context,
)
from app.schemas.pipeline import MoverNegocioIn, NegocioCreate, NegocioUpdate, PerderNegocioIn
from app.services import automacoes, comercial_funil
from app.services import quadro_comum as qc
from app.services.regras import RegraViolada, http_de

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comercial", tags=["comercial-funil"])

stages_router = pipeline_stages_router(
    PIPELINE_COMERCIAL,
    auth_dependency=get_pipeline_auth,
    resolve_context=lambda pa: pipeline_context(pa, PIPELINE_COMERCIAL),
    success_response=success_response,
    prefix="/api/comercial/pipeline/stages",
    tags=["comercial-etapas"],
    require_stage_admin=exigir_admin_da_org,
)


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _usuario(auth: tuple) -> str:
    return str(auth[0].id)


@router.get("/board")
async def obter_board(
    limite_por_etapa: int | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    """Open + won negócios, one column per active stage (empty ones included)."""
    return success_response(
        comercial_funil.quadro(db, _org(auth), limite_por_etapa=limite_por_etapa)
    )


@router.get("/negocios")
async def listar_negocios(
    status_filtro: str | None = Query(default=None, alias="status"),
    q: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    """Every negócio, ANY status — the `perdido` archive + search, unlike
    `GET /board` (open + ganho only). `status`: aberto|ganho|perdido."""
    return success_response(comercial_funil.listar_negocios(db, _org(auth), status=status_filtro, q=q))


@router.get("/negocios/{negocio_id}")
async def obter_negocio(
    negocio_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    """One negócio card, ANY status — so a `perdido` deal or a deep link from
    an orçamento can open, not only board members."""
    return success_response(comercial_funil.buscar_negocio(db, _org(auth), negocio_id))


@router.post("/negocios", status_code=status.HTTP_201_CREATED)
async def criar_negocio(
    payload: NegocioCreate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    portas: automacoes.PortasAutomacao = Depends(get_portas_automacao),
) -> dict:
    """Put a lead on the funnel — an existing `lead_id`, or a new `lead`
    typed in by the agency (`origem='manual'`). Lands in the entry stage, on top."""
    org_id = _org(auth)
    lead_id = payload.lead_id
    if payload.lead is not None:
        criado = (
            db.table("lead").insert(
                {"org_id": org_id, "origem": "manual", **payload.lead.model_dump(exclude_none=True)}
            ).execute().data or []
        )
        if not criado:
            raise RuntimeError("insert de lead não retornou a linha criada")
        lead_id = str(criado[0]["id"])
    try:
        negocio = comercial_funil.abrir_negocio(
            db, org_id,
            lead_id=lead_id,
            titulo=payload.titulo,
            valor_estimado=payload.valor_estimado,
            responsavel_id=payload.responsavel_id,
            user_id=_usuario(auth),
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    await automacoes.ao_entrar_etapa(portas, org_id, pipeline="comercial", card_id=negocio["id"], user_id=_usuario(auth))
    return success_response(negocio)


@router.patch("/negocios/{negocio_id}")
async def atualizar_negocio(
    negocio_id: str,
    payload: NegocioUpdate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    org_id = _org(auth)
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar.")
    if dados.get("responsavel_id"):
        qc.carregar(db, "profissional", org_id, dados["responsavel_id"], select="id",
                    rotulo="profissional")
    qc.carregar(db, "negocio", org_id, negocio_id, select="id", rotulo="negócio")
    linhas = (
        db.table("negocio").update(dados).eq("id", negocio_id).eq("org_id", org_id)
        .execute().data or []
    )
    if not linhas:
        raise HTTPException(status_code=404, detail="Negócio não encontrado")
    return success_response(linhas[0])


@router.post("/negocios/{negocio_id}/mover-etapa")
async def mover_etapa(
    negocio_id: str,
    payload: MoverNegocioIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    portas: automacoes.PortasAutomacao = Depends(get_portas_automacao),
) -> dict:
    """Drag a negócio. Dropping on the `fechado` stage needs `orcamento_id`
    (409 `orcamento_obrigatorio`): the orçamento is accepted, the deal marked
    ganho and the Cliente created from the lead. See the service for every
    409 code."""
    try:
        linha = comercial_funil.mover_negocio(
            db, _org(auth),
            negocio_id=negocio_id,
            para_etapa_id=payload.para_etapa_id,
            user_id=_usuario(auth),
            novo_indice=payload.novo_indice,
            motivo=payload.motivo,
            orcamento_id=payload.orcamento_id,
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    await automacoes.ao_entrar_etapa(portas, _org(auth), pipeline="comercial", card_id=negocio_id, user_id=_usuario(auth))
    return success_response(linha)


@router.post("/negocios/{negocio_id}/perder")
async def perder_negocio(
    negocio_id: str,
    payload: PerderNegocioIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    """Archive an open deal with its reason (leaves the board; kept for stats)."""
    try:
        linha = comercial_funil.perder_negocio(
            db, _org(auth), negocio_id=negocio_id, motivo=payload.motivo
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return success_response(linha)
