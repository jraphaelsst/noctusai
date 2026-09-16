"""`/api/edicao-fotos/lotes` — contract §3.

| Method | Path | Who |
|---|---|---|
| GET  | `/lotes` | member — own batches for a corretor, org-wide for an agency/platform admin |
| POST | `/lotes` | member — blocked until the org has an editor model + edit types |
| GET  | `/lotes/{id}` | member who can see the batch |
| POST | `/lotes/{id}/fotos` | same — multipart, ≤ `MAX_FILES_PER_REQUEST` files per call |
| POST | `/lotes/{id}/vista` | same — pulls the imóvel's Vista gallery |
| POST | `/lotes/{id}/submeter` | same |
| POST | `/lotes/{id}/fotos/{foto_id}/retentar` | same |
| GET  | `/lotes/{id}/zip` | same — 409 until every photo is decided |

Every call goes through the engine's route entry points
(`noctusai_lib.domain.photo_editing`); nothing here re-implements a pipeline
rule. Batch visibility is enforced by `deps.load_visible_batch`.
"""
from __future__ import annotations

from pathlib import PurePath
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from noctusai_lib.domain.photo_editing import (
    Actor,
    OrgSettings,
    PhotoEditingPorts,
    Speed,
    add_photo_bytes,
    build_batch_zip,
    retry_photo,
    submit_batch,
    zip_file_name,
)

from app.modules.edicao_fotos.deps import (
    get_edicao_ports,
    get_vista_photo_source,
    load_visible_batch,
    require_member,
)
from app.modules.edicao_fotos.errors import ENGINE_ERRORS, api_error, engine_error
from app.modules.edicao_fotos.presenters import batch_out, page_out, photo_out
from app.modules.edicao_fotos.schemas import LoteCreateBody, VistaIngestBody
from app.modules.edicao_fotos.services.vista_fotos import VistaPhotoSource, ingest_vista_gallery

router = APIRouter(prefix="/api/edicao-fotos/lotes", tags=["edicao-fotos"])

#: Files per upload request. The batch limit (100) is enforced by the engine;
#: this bounds ONE request so its body stays under the route's
#: `_MAX_BODY_PATH_OVERRIDES` ceiling (10 × 25 MB + multipart overhead).
MAX_FILES_PER_REQUEST = 10
UPLOAD_ROUTE_MAX_BODY_BYTES = 256 * 1024 * 1024


async def _settings(ports: PhotoEditingPorts, org_id: str) -> OrgSettings:
    return await ports.repo.get_org_settings(org_id) or OrgSettings(org_id=org_id)


@router.get("")
async def list_lotes_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    own_only = not (actor.is_platform_admin or actor.is_agency_admin)
    batches, total = await ports.repo.list_batches(
        org_id=actor.org_id,
        criado_por=actor.user_id if own_only else None,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return page_out([batch_out(b) for b in batches], page=page, page_size=page_size, total=total)


@router.post("", status_code=201)
async def create_lote_route(
    body: LoteCreateBody,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    settings = await _settings(ports, actor.org_id)
    if not settings.modelo_editor_id:
        raise api_error(
            422, "modelo_nao_configurado", "Nenhum modelo de edição configurado para a organização."
        )
    if not settings.tipos_edicao_ativos:
        raise api_error(422, "sem_tipos_edicao", "Nenhum tipo de edição ativo.")
    platform = await ports.repo.get_platform_settings()
    speed = Speed(settings.velocidade_override or platform.velocidade_default)
    if speed is Speed.ECONOMICO:
        raise api_error(422, "economico_indisponivel", "Modo Econômico indisponível.")
    if body.imovel is not None and str(body.imovel.org_id) != actor.org_id:
        raise api_error(
            422, "imovel_outra_organizacao", "O imóvel precisa pertencer à sua organização."
        )
    batch = await ports.repo.create_batch(
        org_id=actor.org_id,
        nome=body.nome.strip(),
        criado_por=actor.user_id,
        # The imóvel link is what enables a Vista pull; each photo also
        # records its own provenance in `vista_codigo`.
        origem="vista" if body.imovel is not None else "upload",
        velocidade=speed,
        imovel_org_id=str(body.imovel.org_id) if body.imovel else None,
        imovel_codigo=body.imovel.codigo.strip() if body.imovel else None,
    )
    return batch_out(batch, [])


@router.get("/{lote_id}")
async def get_lote_route(
    lote_id: UUID,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    photos = await ports.repo.list_photos(batch.id)
    return {**batch_out(batch, photos), "fotos": [photo_out(p) for p in photos]}


@router.post("/{lote_id}/fotos", status_code=201)
async def upload_fotos_route(
    lote_id: UUID,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    files: list[UploadFile] = File(...),
) -> dict:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    if not files:
        raise api_error(422, "sem_arquivos", "Nenhum arquivo enviado.")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise api_error(
            422, "muitos_arquivos", f"Envie no máximo {MAX_FILES_PER_REQUEST} fotos por requisição."
        )
    settings = await _settings(ports, batch.org_id)
    existing = await ports.repo.list_photos(batch.id)
    if len(existing) + len(files) > settings.limite_fotos_por_lote:
        raise api_error(
            409, "lote_cheio", f"Limite de {settings.limite_fotos_por_lote} fotos por lote."
        )
    # Validate EVERY file before storing any, so a bad file never leaves a
    # half-uploaded request behind.
    staged: list[tuple[bytes, str]] = []
    for upload in files:
        name = upload.filename or ""
        ext = PurePath(name).suffix.lstrip(".").lower()
        if not ext:
            raise api_error(415, "formato_nao_suportado", f"Arquivo sem extensão: {name!r}.")
        data = await upload.read(settings.limite_bytes_por_foto + 1)
        if len(data) > settings.limite_bytes_por_foto:
            raise api_error(
                413,
                "arquivo_grande_demais",
                f"{name}: acima de {settings.limite_bytes_por_foto // (1024 * 1024)} MB.",
            )
        staged.append((data, ext))
    try:
        stored = [
            await add_photo_bytes(ports, lote_id=batch.id, data=data, extension=ext)
            for data, ext in staged
        ]
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return {"fotos": [photo_out(p) for p in stored]}


@router.post("/{lote_id}/vista")
async def vista_ingest_route(
    lote_id: UUID,
    body: VistaIngestBody,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    source: VistaPhotoSource = Depends(get_vista_photo_source),
) -> dict:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    if batch.status.value != "rascunho":
        raise api_error(409, "lote_ja_submetido", "O lote já foi submetido.")
    try:
        result = await ingest_vista_gallery(
            ports, source, lote_id=batch.id, codigo=body.codigo.strip()
        )
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    if result.encontradas == 0:
        raise api_error(404, "imovel_sem_fotos", f"Nenhuma foto encontrada no Vista para {body.codigo}.")
    return result.as_dict()


@router.post("/{lote_id}/submeter")
async def submit_lote_route(
    lote_id: UUID,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    try:
        submitted = await submit_batch(ports, batch.id, submitted_by=actor.user_id)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return batch_out(submitted, await ports.repo.list_photos(batch.id))


@router.post("/{lote_id}/fotos/{foto_id}/retentar")
async def retry_foto_route(
    lote_id: UUID,
    foto_id: UUID,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    photo = await ports.repo.get_photo(str(foto_id))
    if photo is None or str(photo.lote_id) != str(batch.id):
        raise api_error(404, "foto_nao_encontrada", "Foto não encontrada neste lote.")
    try:
        moved = await retry_photo(ports, photo.id, requested_by=actor.user_id)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    return photo_out(moved)


@router.get("/{lote_id}/zip")
async def zip_lote_route(
    lote_id: UUID,
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> Response:
    batch = await load_visible_batch(ports, actor, str(lote_id))
    # Built on every fetch from the CURRENT decisions — a changed decision is
    # reflected on the next download with no cache to invalidate. The archive
    # is byte-deterministic, so unchanged batches produce identical files.
    try:
        data = await build_batch_zip(ports, batch.id)
    except ENGINE_ERRORS as exc:
        raise engine_error(exc) from exc
    filename = zip_file_name(batch.nome)
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
            ),
            "Cache-Control": "no-store",
        },
    )
