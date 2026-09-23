"""Automações v1 — the rules the engine runs (roadmap R11, contract §E2).

  GET    /api/automacoes?pipeline=&stage_id=     list the org's rules
  POST   /api/automacoes                         create (org admins)
  PATCH  /api/automacoes/{id}                    edit / toggle `ativo` (org admins)
  DELETE /api/automacoes/{id}                    remove (org admins) → 204
  GET    /api/automacoes/execucoes?limit=&automacao_id=   the execution log

Writes are admin-only for the same reason the stage editors are: a rule acts
on every card of the board, for the whole agency. The engine itself is
`app/services/automacoes.py`; this router only stores what it runs, and
refuses (422) a rule that could never run — a stage of the other board, a
card-hub action on the Esteira, a responsável that does not exist.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from noctusai_lib.domain.pipeline import get_stage
from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import exigir_admin_da_org, garantir_etapas_padrao, get_db
from app.schemas.automacoes import AutomacaoCreate, AutomacaoUpdate, automacao_out
from app.services import quadro_comum as qc
from app.services.automacoes import PIPELINES, listar_execucoes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automacoes", tags=["automacoes"])

#: Actions that write to the negócio CARD HUB — meaningless on the Esteira.
_SO_COMERCIAL = {"criar_checklist"}


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _recusar(code: str, mensagem: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"detail": mensagem, "code": code})


def _validar(db: Any, org_id: str, pipeline: str, stage_id: str, acao: dict) -> None:
    cfg = PIPELINES[pipeline]
    garantir_etapas_padrao(db, cfg, org_id)
    try:
        etapa = get_stage(db, cfg, stage_id, org_id=org_id)
    except NotFoundError:
        raise _recusar("etapa_invalida", "Esta etapa não existe neste quadro.")
    if not etapa.get("ativo", True):
        raise _recusar("etapa_invalida", "Esta etapa está desativada.")
    tipo, params = acao["tipo"], acao.get("params") or {}
    if tipo in _SO_COMERCIAL and pipeline != "comercial":
        raise _recusar(
            "acao_incompativel",
            "Checklists automáticos existem só no funil comercial (card do negócio).",
        )
    for chave in ("profissional_id", "responsavel_id"):
        if params.get(chave):
            try:
                qc.carregar(db, "profissional", org_id, params[chave], select="id",
                            rotulo="profissional")
            except NotFoundError:
                raise _recusar("profissional_invalido", "O profissional informado não existe.")


@router.get("")
async def listar_automacoes(
    pipeline: str | None = None,
    stage_id: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    consulta = db.table("automacao").select("*").eq("org_id", _org(auth))
    if pipeline:
        consulta = consulta.eq("pipeline", pipeline)
    if stage_id:
        consulta = consulta.eq("etapa_id", stage_id)
    linhas = list(consulta.execute().data or [])
    linhas.sort(key=lambda r: (str(r.get("pipeline")), str(r.get("created_at") or "")))
    return success_response([automacao_out(r) for r in linhas])


@router.get("/execucoes")
async def listar_execucoes_automacoes(
    limit: int = Query(default=50, ge=1, le=200),
    automacao_id: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    """Newest first: what ran, on which card, and — for `erro` — why."""
    return success_response(listar_execucoes(db, _org(auth), limit=limit, automacao_id=automacao_id))


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(exigir_admin_da_org)])
async def criar_automacao(
    payload: AutomacaoCreate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    org_id = _org(auth)
    acao = payload.acao.model_dump()
    _validar(db, org_id, payload.pipeline, payload.stage_id, acao)
    criado = (
        db.table("automacao").insert(
            {
                "org_id": org_id,
                "pipeline": payload.pipeline,
                "etapa_id": payload.stage_id,
                "gatilho": payload.gatilho,
                "sla_horas": payload.sla_horas,
                "acao": acao,
                "ativo": payload.ativo,
            }
        ).execute().data or []
    )
    if not criado:
        raise RuntimeError("insert de automacao não retornou a linha criada")
    logger.info("automação criada org=%s id=%s tipo=%s", org_id, criado[0]["id"], acao["tipo"])
    return success_response(automacao_out(criado[0]))


@router.patch("/{automacao_id}", dependencies=[Depends(exigir_admin_da_org)])
async def atualizar_automacao(
    automacao_id: str,
    payload: AutomacaoUpdate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    org_id = _org(auth)
    atual = qc.carregar(db, "automacao", org_id, automacao_id, rotulo="automação")
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar.")

    # Validate the rule as it will be AFTER the patch, not the patch alone.
    gatilho = dados.get("gatilho", atual.get("gatilho"))
    sla_horas = dados.get("sla_horas", atual.get("sla_horas"))
    if gatilho == "sla" and not sla_horas:
        raise _recusar("sla_sem_horas", "Uma automação de SLA precisa de `sla_horas`.")
    stage_id = dados.get("stage_id", atual.get("etapa_id"))
    acao = dados["acao"] if "acao" in dados else (atual.get("acao") or {})
    _validar(db, org_id, str(atual["pipeline"]), str(stage_id), acao)

    valores: dict[str, Any] = {}
    if "stage_id" in dados:
        valores["etapa_id"] = dados["stage_id"]
    if "gatilho" in dados:
        valores["gatilho"] = dados["gatilho"]
    if "sla_horas" in dados or gatilho == "entrada_etapa":
        valores["sla_horas"] = None if gatilho == "entrada_etapa" else sla_horas
    if "acao" in dados:
        valores["acao"] = dados["acao"]
    if "ativo" in dados:
        valores["ativo"] = dados["ativo"]
    linhas = (
        db.table("automacao").update(valores).eq("id", automacao_id).eq("org_id", org_id)
        .execute().data or []
    )
    if not linhas:
        raise HTTPException(status_code=404, detail="Automação não encontrada")
    return success_response(automacao_out(linhas[0]))


@router.delete(
    "/{automacao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def remover_automacao(
    automacao_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> Response:
    """Hard delete; its execuções go with it (ON DELETE CASCADE). To stop a
    rule while keeping its history, PATCH `ativo: false` instead."""
    org_id = _org(auth)
    qc.carregar(db, "automacao", org_id, automacao_id, rotulo="automação")
    db.table("automacao").delete().eq("id", automacao_id).eq("org_id", org_id).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
