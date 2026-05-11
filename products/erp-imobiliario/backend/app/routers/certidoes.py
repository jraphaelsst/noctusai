"""
Certidões Negativas Router — Automated issuance and AI analysis of
negative certificates for real estate due diligence.

-- CREATE TABLE certidao_consultas (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   created_by uuid NOT NULL,
--   tipo_documento text NOT NULL CHECK (tipo_documento IN ('cpf', 'cnpj')),
--   documento text NOT NULL,
--   nome text NOT NULL,
--   data_nascimento text,
--   genero text,
--   rg text,
--   nome_mae text,
--   nome_pai text,
--   status text NOT NULL DEFAULT 'pendente',
--   total_certidoes int NOT NULL DEFAULT 0,
--   concluidas int NOT NULL DEFAULT 0,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
--
-- CREATE TABLE certidao_resultados (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   consulta_id uuid NOT NULL REFERENCES certidao_consultas(id) ON DELETE CASCADE,
--   org_id uuid NOT NULL,
--   tipo text NOT NULL,
--   nome_display text NOT NULL,
--   ordem int NOT NULL DEFAULT 0,
--   status text NOT NULL DEFAULT 'pendente',
--   analise_ia text,
--   arquivo_url text,
--   arquivo_nome text,
--   api_response jsonb,
--   erro_mensagem text,
--   api_requested_at timestamptz,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import asyncio
import io
import logging
import time
import zipfile
from typing import Optional, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Header, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, get_admin_client, get_org_id, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.certidoes_service import (
    CERTIDOES_CONFIG,
    TJSP_COOLDOWN_SECONDS,
    TJSP_TIPO,
    get_certidoes_tipos,
    processar_consulta,
    process_manual_upload,
    check_required_credentials,
    schedule_tjsp_for_org,
    recover_stale_processando,
    cancelar_processamento,
    _get_tjsp_last_request_at,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/certidoes", tags=["Certidões"])

# Throttle staleness recovery — run at most once per 60 seconds
_last_stale_check: float = 0.0
_STALE_CHECK_INTERVAL = 60.0


# --------------- Schemas ---------------

class ConsultaCreate(BaseModel):
    tipo_documento: Literal["cpf", "cnpj"]
    documento: str = Field(..., min_length=11, max_length=18)
    nome: str = Field(..., min_length=2, max_length=200)
    data_nascimento: Optional[str] = None
    genero: Optional[Literal["M", "F"]] = None
    rg: Optional[str] = None
    nome_mae: Optional[str] = None
    nome_pai: Optional[str] = None


# --------------- Endpoints ---------------

@router.get("/tipos")
async def listar_tipos_certidoes(_ = Depends(get_current_user)):
    """List available certificate types."""
    return success_response(get_certidoes_tipos())


@router.get("/consultas")
async def listar_consultas(
    busca: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth = Depends(get_current_user)):
    """List certificate consultation requests."""
    user, token = auth
    db = get_user_client(token)

    # Auto-recover resultados stuck in "processando" for too long (e.g. server
    # restart killed the background task). Throttled to once per 60s to avoid
    # adding a DB query on every 3s poll cycle.
    global _last_stale_check
    now = time.monotonic()
    if now - _last_stale_check >= _STALE_CHECK_INTERVAL:
        _last_stale_check = now
        recover_stale_processando(get_admin_client())

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count
    count_query = db.table("certidao_consultas").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if busca:
        count_query = count_query.or_(
            f"nome.ilike.%{busca}%,documento.ilike.%{busca}%"
        )
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data
    query = db.table("certidao_consultas").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if busca:
        query = query.or_(
            f"nome.ilike.%{busca}%,documento.ilike.%{busca}%"
        )
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    consultas = result.data or []

    # Compute success/error counts per consulta from resultados (single query)
    if consultas:
        consulta_ids = [c["id"] for c in consultas]
        status_result = db.table("certidao_resultados").select(
            "consulta_id, status"
        ).in_("consulta_id", consulta_ids).in_(
            "status", ["sucesso", "erro"]
        ).execute()
        success_counts: dict[str, int] = {}
        erro_counts: dict[str, int] = {}
        for r in (status_result.data or []):
            cid = r["consulta_id"]
            if r["status"] == "sucesso":
                success_counts[cid] = success_counts.get(cid, 0) + 1
            else:
                erro_counts[cid] = erro_counts.get(cid, 0) + 1
        for c in consultas:
            c["concluidas"] = success_counts.get(c["id"], 0)
            c["erros"] = erro_counts.get(c["id"], 0)

    return paginated_response(consultas, total, validated_page, validated_page_size)


@router.post("/consultas")
async def criar_consulta(
    body: ConsultaCreate,
    background_tasks: BackgroundTasks,
    auth = Depends(get_current_user)):
    """Create a new certificate consultation and start processing in background."""
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user)

    # Validate required credentials before creating anything
    missing = check_required_credentials(org_id)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=" ".join(missing)
            + " Acesse Configurações > Chaves de API para configurar.",
        )

    # Insert consulta
    consulta_data = {
        **body.model_dump(exclude_none=True),
        "created_by": user.id,
        "status": "pendente",
        "total_certidoes": len(CERTIDOES_CONFIG),
        "concluidas": 0,
    }
    if org_id:
        consulta_data["org_id"] = org_id

    consulta_result = db.table("certidao_consultas").insert(consulta_data).execute()
    if not consulta_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar consulta")
    consulta = consulta_result.data[0]

    # Insert one resultado per certificate type
    resultados_data = [
        {
            "consulta_id": consulta["id"],
            **({"org_id": org_id} if org_id else {}),
            "tipo": config["tipo"],
            "nome_display": config["nome"],
            "ordem": config["ordem"],
            "status": "pendente",
        }
        for config in CERTIDOES_CONFIG
    ]
    db.table("certidao_resultados").insert(resultados_data).execute()

    log_action(
        user.id, "criar", "certidao_consulta", consulta["id"],
        f"Solicitou certidões para {body.nome} ({body.tipo_documento.upper()}: {body.documento})"
    )

    # Start background processing with admin client (service role for updates).
    # Passed as async coroutine so it runs in the main event loop — required for
    # TJSP on-demand scheduling (asyncio.create_task needs the main loop).
    admin_db = get_admin_client()
    background_tasks.add_task(processar_consulta, consulta["id"], admin_db)

    # Return consulta with resultados
    resultados = db.table("certidao_resultados").select("*").eq(
        "consulta_id", consulta["id"]
    ).order("ordem").execute()

    consulta["resultados"] = resultados.data or []
    return success_response(consulta)


@router.get("/consultas/{consulta_id}")
async def obter_consulta(consulta_id: str, auth = Depends(get_current_user)):
    """Get a consultation with all its certificate results."""
    user, token = auth
    db = get_user_client(token)

    consulta = db.table("certidao_consultas").select("*").eq(
        "id", consulta_id
    ).single().execute()
    if not consulta.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    resultados = db.table("certidao_resultados").select("*").eq(
        "consulta_id", consulta_id
    ).order("ordem").execute()

    data = consulta.data
    res_list = resultados.data or []
    data["resultados"] = res_list
    data["concluidas"] = sum(1 for r in res_list if r.get("status") == "sucesso")
    data["erros"] = sum(1 for r in res_list if r.get("status") == "erro")
    return success_response(data)


@router.post("/consultas/{consulta_id}/reprocessar")
async def reprocessar_consulta(
    consulta_id: str,
    background_tasks: BackgroundTasks,
    auth = Depends(get_current_user)):
    """Retry failed certificates in a consultation."""
    user, token = auth
    db = get_user_client(token)

    consulta = db.table("certidao_consultas").select("*").eq(
        "id", consulta_id
    ).single().execute()
    if not consulta.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    # Reset failed non-TJSP resultados to pendente (will process in parallel)
    db.table("certidao_resultados").update({
        "status": "pendente",
        "erro_mensagem": None,
    }).eq("consulta_id", consulta_id).eq("status", "erro").neq("tipo", TJSP_TIPO).execute()

    # Reset failed TJSP resultados directly to na_fila (respects cooldown queue)
    db.table("certidao_resultados").update({
        "status": "na_fila",
        "erro_mensagem": None,
    }).eq("consulta_id", consulta_id).eq("status", "erro").eq("tipo", TJSP_TIPO).execute()

    # Reset consulta status
    db.table("certidao_consultas").update({
        "status": "processando",
    }).eq("id", consulta_id).execute()

    log_action(
        user.id, "editar", "certidao_consulta", consulta_id,
        "Reprocessou certidões com erro"
    )

    admin_db = get_admin_client()
    background_tasks.add_task(processar_consulta, consulta_id, admin_db)

    # Schedule TJSP items (processar_consulta only picks up "pendente" items,
    # so "na_fila" TJSP items need to be scheduled separately)
    org_id = get_org_id(user)
    if org_id:
        schedule_tjsp_for_org(org_id, admin_db)

    return ok_response("Reprocessamento iniciado")


@router.post("/consultas/{consulta_id}/cancelar")
async def cancelar_consulta_processamento(
    consulta_id: str,
    auth = Depends(get_current_user)):
    """Cancel in-progress certificate processing for a specific consulta."""
    user, token = auth
    db = get_user_client(token)

    check = db.table("certidao_consultas").select("id").eq("id", consulta_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    admin_db = get_admin_client()
    result = cancelar_processamento(consulta_id, admin_db)

    if result["cancelados"] > 0:
        log_action(
            user.id, "editar", "certidao_consulta", consulta_id,
            f"Cancelou processamento de {result['cancelados']} certidões"
        )

    return success_response(result)


@router.delete("/consultas/{consulta_id}")
async def excluir_consulta(consulta_id: str, auth = Depends(get_current_user)):
    """Delete a consultation, its results, and associated storage files."""
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user)

    check = db.table("certidao_consultas").select("id").eq("id", consulta_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    # Delete storage files before removing DB rows (requires admin/service-role
    # client — user client fails list_buckets() and StorageService falls to dry-run)
    if org_id:
        resultados = db.table("certidao_resultados").select(
            "arquivo_url"
        ).eq("consulta_id", consulta_id).execute()
        admin_db = get_admin_client()
        _delete_storage_files(resultados.data or [], org_id, admin_db)

    # CASCADE will delete resultados
    db.table("certidao_consultas").delete().eq("id", consulta_id).execute()

    log_action(
        user.id, "excluir", "certidao_consulta", consulta_id,
        f"Excluiu consulta de certidões {consulta_id}"
    )
    return ok_response("Consulta excluída com sucesso")


@router.get("/download")
async def download_certidao(
    url: str = Query(..., description="URL do arquivo para download"),
    filename: str = Query("certidao.pdf", description="Nome do arquivo"),
    _ = Depends(get_current_user)):
    """Proxy download — fetches the file server-side to bypass CORS restrictions."""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=60.0, follow_redirects=True)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Não foi possível baixar o arquivo")

            content_type = resp.headers.get("content-type", "application/octet-stream")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
    except httpx.HTTPError as e:
        logger.error("Download proxy failed: %s", e)
        raise HTTPException(status_code=502, detail="Erro ao baixar arquivo")


@router.get("/consultas/{consulta_id}/download-zip")
async def download_consulta_zip(
    consulta_id: str,
    auth = Depends(get_current_user)):
    """Download all successful certificates from a consultation as a ZIP file."""
    user, token = auth
    db = get_user_client(token)

    consulta = db.table("certidao_consultas").select(
        "id, nome, documento"
    ).eq("id", consulta_id).single().execute()
    if not consulta.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    resultados = db.table("certidao_resultados").select(
        "arquivo_url, arquivo_nome, nome_display"
    ).eq("consulta_id", consulta_id).eq(
        "status", "sucesso"
    ).order("ordem").execute()
    items = resultados.data or []

    if not items:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma certidão disponível para download",
        )

    # Download all files concurrently
    async def _fetch(client: httpx.AsyncClient, item: dict) -> Optional[tuple]:
        url = item.get("arquivo_url")
        if not url:
            return None
        try:
            resp = await client.get(url, timeout=60.0, follow_redirects=True)
            if resp.status_code != 200:
                return None
            filename = item.get("arquivo_nome") or f"{item['nome_display']}.pdf"
            return (filename, resp.content)
        except httpx.HTTPError as exc:
            logger.warning("certidoes: download failed for %s (%s); skipping in batch ZIP", url, exc)
            return None

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch(client, it) for it in items])

    files = [r for r in results if r is not None]
    if not files:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível baixar os arquivos das certidões",
        )

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        seen: dict[str, int] = {}
        for filename, content in files:
            # Deduplicate filenames
            if filename in seen:
                seen[filename] += 1
                name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
                filename = f"{name} ({seen[filename]}).{ext}" if ext else f"{name} ({seen[filename]})"
            else:
                seen[filename] = 0
            zf.writestr(filename, content)
    buf.seek(0)

    nome_safe = consulta.data["nome"].replace(" ", "_")[:50]
    doc = consulta.data["documento"]
    zip_filename = f"certidoes_{nome_safe}_{doc}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@router.post("/resultados/{resultado_id}/upload")
async def upload_certidao_manual(
    resultado_id: str,
    file: UploadFile = File(...),
    auth = Depends(get_current_user)):
    """Upload a certificate PDF manually for a resultado that failed automation.

    Delegates to the service layer which replicates the exact same post-download
    pipeline as the automated flow: storage upload → PDF text extraction →
    AI analysis → update resultado → recalculate consulta status.
    """
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user)

    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=422,
            detail="Apenas arquivos PDF são aceitos.",
        )

    # Fetch resultado and its parent consulta
    resultado = db.table("certidao_resultados").select(
        "id, consulta_id, tipo, nome_display"
    ).eq("id", resultado_id).single().execute()
    if not resultado.data:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")

    consulta_id = resultado.data["consulta_id"]
    consulta = db.table("certidao_consultas").select("*").eq(
        "id", consulta_id
    ).single().execute()
    if not consulta.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")

    # Delegate to service — same pipeline as automated flow
    admin_db = get_admin_client()
    update_data = await process_manual_upload(
        pdf_bytes=pdf_bytes,
        resultado_id=resultado_id,
        consulta=consulta.data,
        tipo=resultado.data["tipo"],
        nome_display=resultado.data["nome_display"],
        org_id=org_id,
        db=admin_db,
    )

    log_action(
        user.id, "editar", "certidao_resultado", resultado_id,
        f"Upload manual de certidão {resultado.data['nome_display']}"
    )

    return success_response({
        **resultado.data,
        **update_data,
    })


@router.get("/fila-tjsp")
async def status_fila_tjsp(auth = Depends(get_current_user)):
    """Get TJSP queue status — queued items, cooldown info."""
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user)

    # Fetch queued TJSP items for this org
    queued = db.table("certidao_resultados").select(
        "id, consulta_id, created_at"
    ).eq("tipo", TJSP_TIPO).eq("status", "na_fila").order("created_at").execute()
    queued_items = queued.data or []

    # Enrich with consulta info in a single batch query
    items = []
    consulta_cache: dict = {}
    if queued_items:
        unique_cids = list({item["consulta_id"] for item in queued_items})
        consultas_result = db.table("certidao_consultas").select(
            "id, nome, documento, tipo_documento"
        ).in_("id", unique_cids).execute()
        consulta_cache = {c["id"]: c for c in (consultas_result.data or [])}

    for i, item in enumerate(queued_items):
        consulta_info = consulta_cache.get(item["consulta_id"], {})
        items.append({
            "id": item["id"],
            "consulta_id": item["consulta_id"],
            "posicao": i + 1,
            "nome": consulta_info.get("nome", ""),
            "documento": consulta_info.get("documento", ""),
            "tipo_documento": consulta_info.get("tipo_documento", ""),
            "created_at": item["created_at"],
        })

    # Cooldown info
    from datetime import datetime, timezone
    cooldown_info: dict = {"ativo": False}
    if org_id:
        last_at = _get_tjsp_last_request_at(org_id, db)
        if last_at:
            now = datetime.now(timezone.utc)
            elapsed = (now - last_at).total_seconds()
            remaining = max(0, TJSP_COOLDOWN_SECONDS - elapsed)
            cooldown_info = {
                "ativo": remaining > 0,
                "ultimo_request_at": last_at.isoformat(),
                "segundos_restantes": int(remaining),
            }

    return success_response({
        "items": items,
        "total_na_fila": len(items),
        "cooldown": cooldown_info,
    })


def _delete_storage_files(resultados: list, org_id: str, db) -> None:
    """Delete storage files for a list of resultados before deleting the consulta.

    Uses the Supabase storage API directly (not StorageService) to avoid the
    dry-run fallback that silently skips real deletions.
    """
    bucket = "erp-certidoes"
    bucket_base = f"/object/public/{bucket}/"

    paths_to_delete: list[str] = []
    for r in resultados:
        url = r.get("arquivo_url")
        if not url or bucket_base not in url:
            logger.debug("Skipping non-storage URL: %s", url)
            continue
        path = url.split(bucket_base, 1)[1]
        # Strip trailing query string — get_public_url appends "?" to URLs
        path = path.split("?", 1)[0]
        paths_to_delete.append(path)

    if not paths_to_delete:
        logger.info("No storage files to delete for this consulta")
        return

    logger.info("Deleting %d storage files from bucket %s: %s", len(paths_to_delete), bucket, paths_to_delete)
    try:
        db.storage.from_(bucket).remove(paths_to_delete)
        logger.info("Successfully deleted %d storage files", len(paths_to_delete))
    except Exception as e:
        logger.error("Failed to delete storage files: %s", e)


