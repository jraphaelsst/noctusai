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
from noctusai_lib.integrations.storage import StorageBackend

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
from app.services.regras import RegraViolada, http_de, mensagem_horas_perdidas
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
    cliente_id: str | None = Query(default=None, description="Só as pautas deste cliente"),
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
    itens = repos.pauta.no_periodo(org_id, inicio, fim, cliente_id=cliente_id)
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
    confirmar_perda_horas: bool = False,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    """Delete a pauta. Cascades to its tarefas, apontamentos and peças.

    409 `horas_serao_perdidas` when any of its tarefas carries logged
    apontamentos and `confirmar_perda_horas` was not sent — the confirm
    dialog used to warn about nothing (achado 4: deleting a pauta silently
    took every hour logged on its tarefas with it).

    Every peça's STORAGE OBJECT is deleted too, the same as `remover_peca`
    does one at a time — the DB row cascades via `ON DELETE CASCADE`, but
    nothing ever told the bucket, so a pauta deleted whole (not peça by
    peça) leaked its files forever (tech-lead addendum, 2026-09).
    """
    org_id = _org(auth)
    try:
        repos.pauta.buscar(org_id, pauta_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Pauta não encontrada")

    if not confirmar_perda_horas:
        tarefas = repos.tarefa.do_pauta(org_id, pauta_id)
        apontamentos = [
            a for t in tarefas for a in repos.apontamento.da_tarefa(org_id, str(t["id"]))
        ]
        if apontamentos:
            minutos = sum(int(a.get("minutos") or 0) for a in apontamentos)
            raise http_de(RegraViolada(
                409, "horas_serao_perdidas",
                mensagem_horas_perdidas(minutos, len(apontamentos)),
            ))

    # Read the peças BEFORE the cascading delete removes their rows.
    pecas = repos.peca.da_pauta(org_id, pauta_id)

    if not repos.pauta.remover(org_id, pauta_id):
        raise HTTPException(status_code=404, detail="Pauta não encontrada")

    for peca in pecas:
        try:
            await storage.delete(bucket=settings.igig_storage_bucket, key=str(peca["storage_key"]))
        except Exception:  # noqa: BLE001 — the row delete already succeeded
            logger.exception(
                "falha ao remover peça do armazenamento org=%s pauta=%s key=%s",
                org_id, pauta_id, peca.get("storage_key"),
            )
    return {"ok": True}


# ── Peças (closes the Módulo 4 portal gap) ──────────────────────────
async def _peca_out(p: dict, *, storage: StorageBackend) -> PecaOut:
    """A peça row plus a freshly-signed `url` — minted per response, same
    "key is durable, URL is a per-read credential" rule as the marca logo. A
    signing failure must not take the whole list down (achado 16: there was
    no way to VIEW a peça at all before this)."""
    url = None
    try:
        url = await storage.signed_url(bucket=settings.igig_storage_bucket, key=str(p["storage_key"]))
    except Exception:  # noqa: BLE001 — a broken link is better than a 500 list
        logger.warning("peça sem URL assinada: %s", p.get("storage_key"))
    return PecaOut(**p, url=url)


@router.get("/{pauta_id}/pecas", response_model=list[PecaOut])
async def listar_pecas(
    pauta_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    storage: StorageBackend = Depends(get_storage),
) -> list[PecaOut]:
    return [
        await _peca_out(p, storage=storage) for p in repos.peca.da_pauta(_org(auth), pauta_id)
    ]


@router.post("/{pauta_id}/pecas", response_model=PecaOut, status_code=status.HTTP_201_CREATED)
async def enviar_peca(
    pauta_id: str,
    arquivo: UploadFile = File(...),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    storage: StorageBackend = Depends(get_storage),
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
            detail=f"Formato não suportado: {arquivo.content_type}. "
                   "Envie PNG, JPEG, WebP, GIF, MP4 ou MOV.",
        )
    conteudo = await arquivo.read()
    if len(conteudo) > _PECA_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Peça excede 50 MB")

    chave = chave_da_peca(org_id, pauta_id, arquivo.filename or "peca")
    await storage.put(
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
    return await _peca_out(registro, storage=storage)


@router.delete("/{pauta_id}/pecas/{peca_id}", status_code=status.HTTP_200_OK)
async def remover_peca(
    pauta_id: str,
    peca_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    """Remove one peça — there was no way to do this at all before (achado
    16). 404 when the peça exists but belongs to a DIFFERENT pauta, same
    posture as an org mismatch: the URL's two ids must agree."""
    org_id = _org(auth)
    try:
        peca = repos.peca.buscar(org_id, peca_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if str(peca.get("pauta_id")) != pauta_id:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    repos.peca.remover(org_id, peca_id)
    try:
        await storage.delete(bucket=settings.igig_storage_bucket, key=str(peca["storage_key"]))
    except Exception:  # noqa: BLE001 — the row delete already succeeded
        logger.exception(
            "falha ao remover peça do armazenamento org=%s peca=%s key=%s",
            org_id, peca_id, peca.get("storage_key"),
        )
    return {"ok": True}
