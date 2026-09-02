"""Certidões Negativas — HTTP surface.

    GET    /api/certidoes/tipos                          the catalogue
    GET    /api/certidoes/consultas                      list + per-consulta counts
    POST   /api/certidoes/consultas                      create + fan out + process
    GET    /api/certidoes/consultas/{id}                 detail + resultados
    POST   /api/certidoes/consultas/{id}/reprocessar     retry the failed ones
    POST   /api/certidoes/consultas/{id}/cancelar        stop what is in flight
    DELETE /api/certidoes/consultas/{id}                 + storage cleanup
    GET    /api/certidoes/download                       one file, proxied
    GET    /api/certidoes/consultas/{id}/download-zip    all of them, zipped
    POST   /api/certidoes/resultados/{id}/upload         manual PDF, same pipeline
    GET    /api/certidoes/fila-tjsp                      queue + live cooldown

Same paths as the ERP router this is ported from, because a live user's
frontend calls them.

Auth: `Depends(get_current_user_org)` → `(user, token, org_id)`, per
`KB § PATTERNS/backend/backend.md § Auth — canonical pattern`. The org is the
access boundary: migration 091 scopes reads to `current_org_id()` and routes
writes through service-role, so **every** query below carries an explicit
`.eq("org_id", ...)`. A consulta belonging to another org is a 404, not a 403 —
its existence is not this caller's business.

🔴 THE `arquivo_url` CONTRACT — read this before building against it
--------------------------------------------------------------------
`resultados[].arquivo_url` is an OPAQUE HANDLE, not a fetchable URL. It holds
EITHER a key in this product's private document bucket (the normal case, when
we persisted the file) OR an `https://` URL at the source system (the fallback,
when we could not). It diverges from the ERP, whose column held a permanent
PUBLIC url — this product's bucket is private with short-TTL signed URLs, so a
stored URL would be a dead link minutes after issuance (`service._persist_pdf`
has the full reasoning).

For a frontend that means:

- **Never `fetch()` / `<a href>` / `<img src>` an `arquivo_url` directly.** A
  bucket key is not a URL and will not resolve.
- **Treat it as truthy-or-not**: non-null ⇒ a file exists for this resultado
  ⇒ show the download control. That check is unchanged from the ERP.
- **Download through `GET /api/certidoes/download?url=<arquivo_url>`**, which
  resolves either kind server-side and streams the PDF back. It also
  authorizes the handle against the caller's org, so passing anything this API
  did not hand you is a 404 by design.
- The whole-consulta `GET /api/certidoes/consultas/{id}/download-zip` needs no
  handle at all.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
import unicodedata
import zipfile
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response, StreamingResponse
from noctusai_lib.integrations.storage import StorageBackend

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.certidoes import service
from app.modules.certidoes.deps import get_certidoes_client, get_storage_backend
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    TJSP_TIPO,
    get_certidoes_tipos,
)
from app.modules.certidoes.schemas import ConsultaCreate
from app.responses import (
    calculate_pagination,
    ok_response,
    paginated_response,
    success_response,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/certidoes", tags=["Certidões"])

CONSULTAS = service.CONSULTAS
RESULTADOS = service.RESULTADOS

#: PostgREST-safe ceiling for `page_size`. This product's settings carry no
#: `max_page_size`, so the bound is declared here rather than borrowed from a
#: field that does not exist.
MAX_PAGE_SIZE = 200

# Throttle the stranded-work recovery — at most once per 60 seconds, so the
# frontend's 3-second poll does not add a DB round-trip per tick.
_last_stale_check: float = 0.0
_STALE_CHECK_INTERVAL = 60.0


def _maybe_recover(db, storage: StorageBackend, org_id: UUID) -> None:
    """Throttled recovery of work stranded by a dead process.

    Two legs, both on the same throttle:

    - `recover_stale_processando` — the ERP behaviour: a resultado stuck in
      `processando` for over 15 minutes goes to `erro` so the spinner stops and
      the user gets a reprocess button instead of an infinite wait.
    - `schedule_tjsp_for_org` — NOT in the ERP, which resumed the TJSP queue
      only from its lifespan hook. `app/lifespan.py` is not this slice's to
      edit, and the seed scheduler refuses to run at all without
      `NOCTUS_SCHEDULERS_ENABLED` (deployed containers only). Re-arming here
      means the queue resumes the moment a human opens the page — which is both
      the environment-independent path and the moment it matters. Idempotent:
      it returns immediately when a task is already in flight for this org.
    """
    global _last_stale_check
    now = time.monotonic()
    if now - _last_stale_check < _STALE_CHECK_INTERVAL:
        return
    _last_stale_check = now
    service.recover_stale_processando(db)
    service.schedule_tjsp_for_org(str(org_id), db, storage)


def _content_disposition(filename: str) -> str:
    """An attachment header that survives an accented filename.

    🔴 NOT COSMETIC, AND NOT HYPOTHETICAL. HTTP header values are latin-1 on
    the wire, so returning `filename="certidoes_João_da_Silva_...zip"` raises
    inside Starlette and the whole response 500s. The download therefore failed
    for anyone whose name carries an accent — which in a Brazilian real-estate
    product is most people. The ERP original built the header the same way and
    had the same latent defect; it is fixed here rather than ported.

    RFC 6266: an ASCII-folded `filename=` that any client understands, PLUS a
    percent-encoded UTF-8 `filename*=` that every current browser prefers — so
    the accented name is what the user actually sees, and nothing breaks if it
    is not understood.
    """
    folded = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace('"', "")
        .strip()
    )
    # An all-non-ASCII name folds to "" — a header with an empty filename is
    # worse than a generic one, because some clients save it as the URL path.
    ascii_name = folded or "download"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _get_consulta_or_404(db, consulta_id: str, org_id: UUID, select: str = "*") -> dict:
    """One consulta belonging to this org, or a 404.

    `.execute()` on a filtered select rather than `.single()`: `single()` raises
    on zero rows, and the raised shape differs across supabase-py versions —
    this returns the honest 404 the same way regardless.
    """
    rows = (
        db.table(CONSULTAS)
        .select(select)
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")
    return rows[0]


# --------------- Endpoints ---------------


@router.get("/tipos")
async def listar_tipos_certidoes(_auth=Depends(get_current_user_org)):
    """List available certificate types."""
    return success_response(get_certidoes_tipos())


@router.get("/consultas")
async def listar_consultas(
    busca: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """List certificate consultation requests, newest first."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    _maybe_recover(db, storage, org_id)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, MAX_PAGE_SIZE
    )

    def _scoped(query):
        query = query.eq("org_id", str(org_id))
        if status:
            query = query.eq("status", status)
        if busca:
            query = query.or_(f"nome.ilike.%{busca}%,documento.ilike.%{busca}%")
        return query

    count_result = _scoped(
        db.table(CONSULTAS).select("id", count="exact")
    ).execute()
    total = count_result.count if count_result.count is not None else 0

    result = (
        _scoped(db.table(CONSULTAS).select("*"))
        .order("created_at", desc=True)
        .range(offset, offset + validated_page_size - 1)
        .execute()
    )
    consultas = result.data or []

    # Success/error counts per consulta. Both the URL-length and the row-cap
    # hazards live on this read — see `service.status_counts_por_consulta`,
    # which owns both.
    if consultas:
        success_counts, erro_counts = service.status_counts_por_consulta(
            [c["id"] for c in consultas], org_id, db
        )
        for c in consultas:
            c["concluidas"] = success_counts.get(c["id"], 0)
            c["erros"] = erro_counts.get(c["id"], 0)

    return paginated_response(consultas, total, validated_page, validated_page_size)


@router.post("/consultas")
async def criar_consulta(
    body: ConsultaCreate,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """Create a consultation, fan out one resultado per type, start processing."""
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Pre-flight the credentials BEFORE writing anything. Without this the
    # consulta is created, ten resultados fan out, and every one of them fails
    # a minute later with the same message — a row the user now has to delete
    # to learn something we knew before we started.
    missing = service.check_required_credentials(str(org_id))
    if missing:
        # Wording is VERBATIM the sentence `matriculas/router.py` and
        # `settings_router.py` already use — the Settings page it names is one
        # page, so three workflows telling the operator to visit it in three
        # different phrasings reads as three different places.
        raise HTTPException(
            status_code=422,
            detail=" ".join(missing)
            + " Configure em Configurações → Chaves de API.",
        )

    consulta_data = {
        **body.model_dump(exclude_none=True),
        "org_id": str(org_id),
        "created_by": str(user.id),
        "status": "pendente",
        "total_certidoes": len(CERTIDOES_CONFIG),
        "concluidas": 0,
    }

    consulta_result = db.table(CONSULTAS).insert(consulta_data).execute()
    if not consulta_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar consulta")
    consulta = consulta_result.data[0]

    resultados_data = [
        {
            "consulta_id": consulta["id"],
            "org_id": str(org_id),
            "tipo": config["tipo"],
            "nome_display": config["nome"],
            "ordem": config["ordem"],
            "status": "pendente",
        }
        for config in CERTIDOES_CONFIG
    ]
    db.table(RESULTADOS).insert(resultados_data).execute()

    # Background processing. Passed as an async coroutine function so it runs
    # in the MAIN event loop — required for the TJSP on-demand scheduling,
    # which needs a running loop to create its task on.
    background_tasks.add_task(service.processar_consulta, consulta["id"], db, storage)

    # One resultado per registry type per consulta: the fan-out in
    # `criar_consulta` inserts exactly `len(CERTIDOES_CONFIG)` of them and the
    # FK cascades with the consulta.
    # postgrest-unbounded-ok: bounded at 10 rows by that fan-out, not 1 000.
    resultados = (
        db.table(RESULTADOS)
        .select("*")
        .eq("consulta_id", consulta["id"])
        .eq("org_id", str(org_id))
        .order("ordem")
        .execute()
    )
    consulta["resultados"] = resultados.data or []
    return success_response(consulta)


@router.get("/consultas/{consulta_id}")
async def obter_consulta(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """Get a consultation with all its certificate results.

    THE endpoint the certidão detail screen polls. Each `resultados[]` entry's
    `arquivo_url` is an opaque handle to be round-tripped through
    `GET /api/certidoes/download`, never fetched directly — see this module's
    docstring for the contract.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    data = _get_consulta_or_404(db, consulta_id, org_id)

    # One resultado per registry type per consulta: the fan-out in
    # `criar_consulta` inserts exactly `len(CERTIDOES_CONFIG)` of them and the
    # FK cascades with the consulta.
    # postgrest-unbounded-ok: bounded at 10 rows by that fan-out, not 1 000.
    resultados = (
        db.table(RESULTADOS)
        .select("*")
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .order("ordem")
        .execute()
    )
    res_list = resultados.data or []
    data["resultados"] = res_list
    data["concluidas"] = sum(1 for r in res_list if r.get("status") == "sucesso")
    data["erros"] = sum(1 for r in res_list if r.get("status") == "erro")
    return success_response(data)


@router.post("/consultas/{consulta_id}/reprocessar")
async def reprocessar_consulta(
    consulta_id: str,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """Retry the failed certificates in a consultation."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    # Failed non-TJSP resultados → pendente (they run in parallel immediately).
    db.table(RESULTADOS).update({
        "status": "pendente",
        "erro_mensagem": None,
    }).eq("consulta_id", consulta_id).eq("org_id", str(org_id)).eq(
        "status", "erro"
    ).neq("tipo", TJSP_TIPO).execute()

    # Failed TJSP resultados → na_fila directly, NOT pendente. `pendente` would
    # make `processar_consulta` fire the request now, and a premature TJSP call
    # RESETS their 30-minute counter — the retry would push the real attempt
    # further away rather than closer.
    db.table(RESULTADOS).update({
        "status": "na_fila",
        "erro_mensagem": None,
    }).eq("consulta_id", consulta_id).eq("org_id", str(org_id)).eq(
        "status", "erro"
    ).eq("tipo", TJSP_TIPO).execute()

    db.table(CONSULTAS).update({
        "status": "processando",
    }).eq("id", consulta_id).eq("org_id", str(org_id)).execute()

    background_tasks.add_task(service.processar_consulta, consulta_id, db, storage)

    # `processar_consulta` only picks up "pendente" rows, so the TJSP items we
    # just moved to "na_fila" need their own scheduling pass.
    service.schedule_tjsp_for_org(str(org_id), db, storage)

    return ok_response("Reprocessamento iniciado")


@router.post("/consultas/{consulta_id}/cancelar")
async def cancelar_consulta_processamento(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """Cancel in-progress certificate processing for one consulta."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    result = service.cancelar_processamento(consulta_id, str(org_id), db)
    return success_response(result)


@router.delete("/consultas/{consulta_id}")
async def excluir_consulta(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """Delete a consultation, its results, and the files behind them."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Verify existence up front so the 404 path performs no storage cleanup.
    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    # One resultado per registry type per consulta: the fan-out in
    # `criar_consulta` inserts exactly `len(CERTIDOES_CONFIG)` of them and the
    # FK cascades with the consulta.
    # postgrest-unbounded-ok: bounded at 10 rows by that fan-out, not 1 000.
    resultados = (
        db.table(RESULTADOS)
        .select("arquivo_url")
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    )
    # Blobs BEFORE rows: a row we delete first is a key we can no longer find,
    # i.e. an orphan in the bucket nobody will ever look for again.
    await service.delete_storage_files(resultados.data or [], storage)

    # CASCADE removes the resultados (migration 091's FK).
    db.table(CONSULTAS).delete().eq("id", consulta_id).eq(
        "org_id", str(org_id)
    ).execute()

    return ok_response("Consulta excluída com sucesso")


@router.get("/download")
async def download_certidao(
    url: str = Query(..., description="URL ou chave do arquivo para download"),
    filename: str = Query("certidao.pdf", description="Nome do arquivo"),
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """Download one certificate — from our bucket, or proxied from the source.

    🔴 `url` IS AUTHORIZED BEFORE IT IS FETCHED. The ERP original fetched
    whatever it was handed, which is both an SSRF vector (the server will GET
    any host a caller names) and a cross-org read (any bucket key, any org).
    Requiring the value to actually appear as an `arquivo_url` on a resultado in
    THIS caller's org closes both with one indexed lookup, and costs a legitimate
    caller nothing — the frontend only ever passes back a value this API gave it.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    owned = (
        db.table(RESULTADOS)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("arquivo_url", url)
        .limit(1)
        .execute()
    ).data or []
    if not owned:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    async with httpx.AsyncClient() as client:
        content = await service.read_certidao_bytes(url, storage, client)

    if content is None:
        raise HTTPException(
            status_code=502, detail="Não foi possível baixar o arquivo"
        )

    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/consultas/{consulta_id}/download-zip")
async def download_consulta_zip(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """Download every successful certificate of a consultation as one ZIP."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    consulta = _get_consulta_or_404(
        db, consulta_id, org_id, select="id, nome, documento"
    )

    # One resultado per registry type per consulta: the fan-out in
    # `criar_consulta` inserts exactly `len(CERTIDOES_CONFIG)` of them and the
    # FK cascades with the consulta.
    # postgrest-unbounded-ok: bounded at 10 rows by that fan-out, not 1 000.
    resultados = (
        db.table(RESULTADOS)
        .select("arquivo_url, arquivo_nome, nome_display")
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .eq("status", "sucesso")
        .order("ordem")
        .execute()
    )
    items = [r for r in (resultados.data or []) if r.get("arquivo_url")]

    if not items:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma certidão disponível para download",
        )

    async def _fetch(client: httpx.AsyncClient, item: dict) -> Optional[tuple]:
        content = await service.read_certidao_bytes(
            item["arquivo_url"], storage, client
        )
        if content is None:
            # Named, not swallowed: one unreachable file must not sink the ZIP
            # of the nine that ARE there, but it does get a log line.
            logger.warning(
                "certidoes: %s unavailable for consulta %s; omitted from the ZIP",
                item.get("nome_display"), consulta_id,
            )
            return None
        filename = item.get("arquivo_nome") or f"{item['nome_display']}.pdf"
        return (filename, content)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch(client, it) for it in items])

    files = [r for r in results if r is not None]
    if not files:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível baixar os arquivos das certidões",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        seen: dict[str, int] = {}
        for filename, content in files:
            # Deduplicate filenames — a zip with two identical entries opens to
            # one file in most extractors, silently losing the other.
            if filename in seen:
                seen[filename] += 1
                name, ext = (
                    filename.rsplit(".", 1) if "." in filename else (filename, "")
                )
                filename = (
                    f"{name} ({seen[filename]}).{ext}"
                    if ext
                    else f"{name} ({seen[filename]})"
                )
            else:
                seen[filename] = 0
            zf.writestr(filename, content)
    buf.seek(0)

    nome_safe = consulta["nome"].replace(" ", "_")[:50]
    doc = consulta["documento"]
    zip_filename = f"certidoes_{nome_safe}_{doc}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(zip_filename)},
    )


@router.post("/resultados/{resultado_id}/upload")
async def upload_certidao_manual(
    resultado_id: str,
    file: UploadFile = File(...),
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """Upload a certificate PDF by hand for a resultado the automation failed.

    Delegates to the service layer, which replicates the exact post-download
    pipeline of the automated flow: storage → PDF text extraction → AI analysis
    → update resultado → recalculate consulta status. The operator's manual
    certidão ends up indistinguishable from an automated one, which is the
    point: the next person reading the file cannot tell, and should not need to.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=422,
            detail="Apenas arquivos PDF são aceitos.",
        )

    resultado_rows = (
        db.table(RESULTADOS)
        .select("id, consulta_id, tipo, nome_display")
        .eq("id", resultado_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not resultado_rows:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    resultado = resultado_rows[0]

    consulta = _get_consulta_or_404(db, resultado["consulta_id"], org_id)

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")

    update_data = await service.process_manual_upload(
        pdf_bytes=pdf_bytes,
        resultado_id=resultado_id,
        consulta=consulta,
        tipo=resultado["tipo"],
        nome_display=resultado["nome_display"],
        org_id=str(org_id),
        db=db,
        storage=storage,
    )

    return success_response({**resultado, **update_data})


@router.get("/fila-tjsp")
async def status_fila_tjsp(
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """The TJSP queue for this org — who is waiting, and for how much longer."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    queued_items = service.queued_tjsp_for_org(org_id, db)

    # Enrich with consulta info in batched queries (URL-length safety on
    # `.in_()`), so the queue reads as names rather than as ids.
    items = []
    consulta_cache: dict = {}
    if queued_items:
        unique_cids = list({item["consulta_id"] for item in queued_items})
        for batch in service.in_batches(unique_cids):
            # `id` is the primary key, so this returns exactly one row per
            # id, and `in_batches` already caps a batch at 200 ids.
            # postgrest-unbounded-ok: at most 200 rows, well under the cap.
            consultas_result = (
                db.table(CONSULTAS)
                .select("id, nome, documento, tipo_documento")
                .eq("org_id", str(org_id))
                .in_("id", batch)
                .execute()
            )
            for c in (consultas_result.data or []):
                consulta_cache[c["id"]] = c

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

    return success_response({
        "items": items,
        "total_na_fila": len(items),
        "cooldown": service.tjsp_cooldown_status(org_id, db),
    })


__all__ = ["router"]
