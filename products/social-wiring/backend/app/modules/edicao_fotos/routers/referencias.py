"""`/api/edicao-fotos/referencias` — the global reference pool (contract §5).

| Method | Path | Who |
|---|---|---|
| GET    | `/referencias` | platform admin ∨ photo curator |
| POST   | `/referencias` | same — multipart `antes` + `depois` (+ `comodo`, `tipos_edicao`, `nota`) |
| DELETE | `/referencias/{id}` | same — ARCHIVES (kept for history, no longer counted) |

Platform scope: pairs carry no `org_id`, so there is no cross-org case — the
guard is the whole boundary (`deps.require_pool_manager`).

The size limit is counted in PAIRS (`fotos_platform_settings.
limite_pares_referencia`, set via `PUT /configuracoes/plataforma`); null/0 =
unlimited; a full pool refuses uploads with 409 `pool_cheio`. Every change
schedules the debounced style-guide rebuild (a DRAFT — activation stays
manual, `routers/guias.py`).

One upload route → the `/api/edicao-fotos/referencias` entry in
`app.main._MAX_BODY_PATH_OVERRIDES` (52 MB = 2 × 25 MB + multipart overhead).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from noctusai_lib.domain.photo_editing import (
    Actor,
    EditType,
    PhotoEditingPorts,
    ReferencePair,
    Room,
    add_reference_pair,
    archive_reference_pair,
    pool_status,
)
from noctusai_lib.domain.photo_editing.types import MAX_BYTES_PER_PHOTO

from app.modules.edicao_fotos.deps import get_edicao_ports, require_pool_manager
from app.modules.edicao_fotos.errors import ENGINE_ERRORS, api_error, engine_error
from app.modules.edicao_fotos.presenters import page_out, referencia_out
from app.modules.edicao_fotos.schemas import EditTypeLiteral, RoomLiteral
from app.modules.edicao_fotos.services.review import signed_url_in

router = APIRouter(prefix="/api/edicao-fotos/referencias", tags=["edicao-fotos"])

#: Bytes per side of a pair — the batch photo limit (plan §1: 25 MB/file).
MAX_BYTES_PER_SIDE = MAX_BYTES_PER_PHOTO
#: The body ceiling this route relies on (`_MAX_BODY_PATH_OVERRIDES`).
UPLOAD_ROUTE_MAX_BODY_BYTES = 52 * 1024 * 1024
NOTA_MAX_CHARS = 2000


async def _out(ports: PhotoEditingPorts, pair: ReferencePair) -> dict:
    storage = ports.reference_storage
    if storage is None:
        raise api_error(
            503, "armazenamento_referencias_indisponivel", "Armazenamento de referências indisponível."
        )
    return referencia_out(
        pair,
        antes_url=await signed_url_in(storage, pair.antes_url),
        depois_url=await signed_url_in(storage, pair.depois_url),
    )


async def _read_side(upload: UploadFile, side: str) -> bytes:
    data = await upload.read(MAX_BYTES_PER_SIDE + 1)
    if len(data) > MAX_BYTES_PER_SIDE:
        raise api_error(
            413,
            "arquivo_grande_demais",
            f"Imagem '{side}' acima de {MAX_BYTES_PER_SIDE // (1024 * 1024)} MB.",
        )
    if not data:
        raise api_error(422, "arquivo_vazio", f"Imagem '{side}' vazia.")
    return data


@router.get("")
async def list_referencias_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    incluir_arquivadas: bool = Query(False),
    _actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    pairs, total = await ports.repo.list_references(
        include_archived=incluir_arquivadas, limit=page_size, offset=(page - 1) * page_size
    )
    status = await pool_status(ports)
    return {
        **page_out(
            [await _out(ports, p) for p in pairs], page=page, page_size=page_size, total=total
        ),
        "pool": {
            "pares_ativos": status.pares_ativos,
            "limite_pares": status.limite_pares,
            "cheio": status.cheio,
        },
        # The fixed vocabularies the upload form offers (plan §1).
        "opcoes": {
            "comodos": [r.value for r in Room],
            "tipos_edicao": [t.value for t in EditType],
        },
    }


@router.post("", status_code=201)
async def create_referencia_route(
    antes: UploadFile = File(...),
    depois: UploadFile = File(...),
    comodo: RoomLiteral = Form(...),
    tipos_edicao: list[EditTypeLiteral] = Form([]),
    nota: Optional[str] = Form(default=None, max_length=NOTA_MAX_CHARS),
    actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    antes_bytes = await _read_side(antes, "antes")
    depois_bytes = await _read_side(depois, "depois")
    try:
        pair = await add_reference_pair(
            ports,
            antes=antes_bytes,
            depois=depois_bytes,
            comodo=comodo,
            tipos_edicao=tipos_edicao,
            nota=nota,
            criado_por=actor.user_id,
            max_bytes=MAX_BYTES_PER_SIDE,
        )
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return await _out(ports, pair)


@router.delete("/{referencia_id}")
async def archive_referencia_route(
    referencia_id: UUID,
    _actor: Actor = Depends(require_pool_manager),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    try:
        pair = await archive_reference_pair(ports, str(referencia_id))
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return await _out(ports, pair)
