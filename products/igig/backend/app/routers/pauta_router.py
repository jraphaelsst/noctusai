"""Calendário editorial e copywriting — Módulo 3.

  GET   /api/pautas/calendario?inicio=&fim=   the month/week window
  CRUD  /api/pautas …                          create, edit copy, reschedule
  POST  /api/pautas/{id}/pecas                 upload a peça (closes the
                                               Módulo 4 portal's side-by-side gap)

Scheduling is a PATCH of `data_publicacao` rather than a bespoke "mover"
endpoint: the calendar's drag-and-drop and the detail form are the same edit,
and giving them one code path means they cannot diverge.

`caracteres_copy` is computed here, not in the browser. The spec asks for a
live character counter; deriving it server-side means "what counts as a
character" has ONE definition instead of one per screen, and the calendar's
list view can flag an over-long legenda without re-implementing the rule.
"""
# NOTE: no `from __future__ import annotations` — this module has an upload
# route and may grow a rate limiter; see esteira_router.py for the slowapi/PEP
# 563 interaction that makes eager annotations the safe default here.
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from noctusai_lib.integrations.persistence import RecordNotFound

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.schemas.pauta import (
    CalendarioResponse,
    PautaCreate,
    PautaOut,
    PautaUpdate,
    PecaOut,
)
from app.storage import chave_da_peca, get_storage
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pautas", tags=["pautas"])

#: Peças are images and video. An allowlist, not a denylist — the same
#: reasoning as the logo upload in marca_router.
_PECA_MIMES = {
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "video/mp4", "video/quicktime",
}
_PECA_MAX_BYTES = 50 * 1024 * 1024


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _out(row: dict) -> PautaOut:
    """Project a pauta, deriving the copy character count."""
    return PautaOut(**row, caracteres_copy=len(row.get("copy_texto") or ""))


@router.get("/calendario", response_model=CalendarioResponse)
async def calendario(
    inicio: str = Query(..., description="ISO-8601 inclusive"),
    fim: str = Query(..., description="ISO-8601 inclusive"),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> CalendarioResponse:
    """Pautas scheduled inside a window, ordered by publication date.

    Unscheduled pautas (`data_publicacao` NULL) are deliberately EXCLUDED —
    they have no place on a date grid. `GET /api/pautas` returns them.
    """
    if fim < inicio:
        raise HTTPException(status_code=422, detail="Período inválido: fim anterior ao início")
    org_id = _org(auth)
    itens = repos.pauta.no_periodo(org_id, inicio, fim)
    return CalendarioResponse(inicio=inicio, fim=fim, itens=[_out(p) for p in itens])


@router.get("", response_model=list[PautaOut])
async def listar_pautas(
    cliente_id: str | None = None,
    funil: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[PautaOut]:
    org_id = _org(auth)
    if cliente_id:
        itens = repos.pauta.do_cliente(org_id, cliente_id)
    elif funil:
        itens = repos.pauta.por_funil(org_id, funil)
    else:
        itens = repos.pauta.listar(org_id)
    return [_out(p) for p in itens]


@router.post("", response_model=PautaOut, status_code=status.HTTP_201_CREATED)
async def criar_pauta(
    payload: PautaCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PautaOut:
    org_id = _org(auth)
    try:
        repos.cliente.buscar(org_id, payload.cliente_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return _out(repos.pauta.criar(org_id, payload.model_dump(exclude_none=True)))


@router.get("/{pauta_id}", response_model=PautaOut)
async def obter_pauta(
    pauta_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PautaOut:
    try:
        return _out(repos.pauta.buscar(_org(auth), pauta_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Pauta não encontrada")


@router.patch("/{pauta_id}", response_model=PautaOut)
async def atualizar_pauta(
    pauta_id: str,
    payload: PautaUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PautaOut:
    """Edit copy, direção de vídeo, funil, or RESCHEDULE.

    `exclude_unset` rather than `exclude_none`: clearing a field (sending
    explicit null to unschedule a pauta) must be distinguishable from not
    mentioning it. `exclude_none` would silently make unscheduling impossible.
    """
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        return _out(repos.pauta.atualizar(_org(auth), pauta_id, dados))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Pauta não encontrada")


@router.delete("/{pauta_id}", status_code=status.HTTP_200_OK)
async def remover_pauta(
    pauta_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    """Delete a pauta. Cascades to its tarefas, apontamentos and peças."""
    if not repos.pauta.remover(_org(auth), pauta_id):
        raise HTTPException(status_code=404, detail="Pauta não encontrada")
    return {"ok": True}


# ── Peças (closes the Módulo 4 portal gap) ──────────────────────────
@router.get("/{pauta_id}/pecas", response_model=list[PecaOut])
async def listar_pecas(
    pauta_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[PecaOut]:
    return [PecaOut(**p) for p in repos.peca.da_pauta(_org(auth), pauta_id)]


@router.post("/{pauta_id}/pecas", response_model=PecaOut, status_code=status.HTTP_201_CREATED)
async def enviar_peca(
    pauta_id: str,
    arquivo: UploadFile = File(...),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> PecaOut:
    """Upload the visual asset the client reviews beside the legenda."""
    org_id = _org(auth)
    try:
        repos.pauta.buscar(org_id, pauta_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Pauta não encontrada")

    if arquivo.content_type not in _PECA_MIMES:
        raise HTTPException(
            status_code=422,
            detail=f"Formato não suportado: {arquivo.content_type}",
        )
    conteudo = await arquivo.read()
    if len(conteudo) > _PECA_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Peça excede 50 MB")

    chave = chave_da_peca(org_id, pauta_id, arquivo.filename or "peca")
    await get_storage().put(
        bucket=settings.igig_storage_bucket,
        key=chave,
        data=conteudo,
        content_type=arquivo.content_type,
    )
    registro = repos.peca.anexar(
        org_id, pauta_id,
        storage_key=chave,
        nome_arquivo=arquivo.filename,
        mime_type=arquivo.content_type,
        tamanho_bytes=len(conteudo),
    )
    logger.info("peça enviada org=%s pauta=%s key=%s", org_id, pauta_id, chave)
    return PecaOut(**registro)
