"""Upload pipeline HTTP surface.

Endpoints:
    POST   /api/videos/upload                  multipart file + metadata fields
    POST   /api/videos/upload-from-drive       JSON body { drive_url, metadata }
    GET    /api/videos/upload/{job_id}/status  polled by the UI's progress bar
    GET    /api/videos/upload/history          recent jobs for the Upload page table

The two POST endpoints both return 202 + a job_id; actual upload work
runs in a FastAPI BackgroundTask. Polling /status (every ~2s) is the UI
contract — no WebSocket dependency in Phase 2 (re-evaluate when we hit
N≥2 products that want server-push progress).

Auth pattern: ``Depends(get_current_user_org)`` returning
``(user, token, raw_org_id)``. The dep is a closure-bound factory output
from ``noctusai_lib.api.auth.make_get_current_user_org`` — see
``KB § PATTERNS/backend.md § Auth — canonical pattern`` for why this
chains correctly through FastAPI when ``Depends(get_org_id)`` does not.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import ValidationError

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_user_client,
)
from app.modules.youtube.schemas.upload import (
    BatchChildOut,
    BatchStatusCounts,
    BatchStatusOut,
    BatchUploadCreated,
    GdriveFolderUploadRequest,
    GdriveUploadRequest,
    UploadJobCreated,
    UploadJobOut,
    UploadMetadata,
)
from app.services.credential_vault import (
    CredentialStore, EncryptionNotConfigured, build_credential_store)
from app.services.notification_service import NotificationService
from app.modules.youtube.services.upload import (
    UploadService,
    UploadServiceError,
    rename_for_job,
    stage_browser_upload,
)
from app.modules.youtube.services.youtube import YouTubeService, YouTubeServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/videos/upload", tags=["upload"])

# Where browser-uploaded multipart bodies and Drive downloads are staged.
# Mounted as a docker volume in compose so files survive container
# restarts mid-upload (rare, but the data loss would be irrecoverable).
_UPLOAD_DIR = Path("/tmp/uploads")


# ─── Service construction helper ───────────────────────────────────────
def _build_upload_service(token: str) -> UploadService:
    """Wire the upload service together. Mirrors the settings_router
    helper's 503-on-config-gap shape so the operator gets an actionable
    error instead of a 500."""
    user_supabase = get_user_client(token)
    admin_supabase = get_admin_client()

    try:
        store = build_credential_store(admin_supabase)
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        youtube = YouTubeService(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            redirect_uri=settings.youtube_redirect_uri,
            credential_store=store,
        )
    except YouTubeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    notification = NotificationService(
        admin_supabase=admin_supabase,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        waha_base_url=settings.waha_base_url,
        waha_api_key=settings.waha_api_key,
        waha_session=settings.waha_session,
    )

    # Best-effort Redis client so this path queues uniformly with the
    # WhatsApp-triggered uploads. A Redis outage degrades to bypassing
    # the queue (the service interprets ``redis_client=None`` as
    # "queue disabled") rather than blocking the request.
    redis_client = None
    try:
        import redis as _redis

        redis_client = _redis.from_url(settings.redis_url, decode_responses=True)
        redis_client.ping()
    except Exception:
        # Logged at warn so the gap is visible without spamming.
        import logging

        logging.getLogger(__name__).warning(
            "upload_router: Redis unreachable at %s — uploads will bypass the queue.",
            settings.redis_url,
        )
        redis_client = None

    return UploadService(
        user_supabase=user_supabase,
        admin_supabase=admin_supabase,
        upload_dir=_UPLOAD_DIR,
        youtube_service=youtube,
        notification_service=notification,
        redis_client=redis_client,
    )


def _row_to_out(row: dict[str, Any]) -> UploadJobOut:
    """Database row → UploadJobOut. Centralised so the shape stays
    consistent across single-job + history endpoints."""
    notify_recipients = row.get("notify_recipients") or []
    raw_batch_id = row.get("batch_id")
    return UploadJobOut(
        id=UUID(row["id"]),
        status=row["status"],
        progress_percent=row.get("progress_percent", 0),
        title=row["title"],
        file_name=row["file_name"],
        file_size_bytes=row.get("file_size_bytes"),
        source_type=row["source_type"],
        source_url=row.get("source_url"),
        youtube_video_id=row.get("youtube_video_id"),
        error_message=row.get("error_message"),
        privacy_status=row.get("privacy_status", "private"),
        notify_recipient_count=len(notify_recipients),
        product_code=row.get("product_code"),
        target_format=row.get("target_format"),
        batch_id=UUID(raw_batch_id) if raw_batch_id else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _resolve_metadata_from_product_code(
    *,
    product_code: str,
    privacy_status: str,
) -> UploadMetadata:
    """Vista CRM lookup → UploadMetadata. Mirrors the chatbot intake's
    enrichment path (``whatsapp_intake_service.prepare_upload_request``)
    so a curl/dashboard caller gets the same title/description shape
    the WhatsApp flow produces.

    HTTP error map (raised as `HTTPException`, not return values):
      - 422: invalid product code format.
      - 503: CRM not configured (`crm_base_url`/`crm_api_key` empty).
      - 404: code valid + CRM up, but no property found.
      - 502: CRM returned an unexpected error.
    """
    from app.services.crm_service import (
        CRMNotConfigured,
        CRMService,
        CRMServiceError,
        build_youtube_metadata,
        validate_product_code,
    )

    code = (product_code or "").strip().upper()
    if not validate_product_code(code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid product_code format: {code!r}",
        )

    try:
        crm = CRMService(
            base_url=settings.crm_base_url,
            api_key=settings.crm_api_key,
        )
    except CRMNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        prop = await crm.get_property(code)
    except CRMServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CRM lookup failed: {exc}",
        ) from exc

    if prop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no property found for product_code={code}",
        )

    yt_meta = build_youtube_metadata(prop, code)
    return UploadMetadata(
        title=yt_meta["title"],
        description=yt_meta["description"],
        tags=yt_meta["tags"],
        privacy_status=privacy_status,
        category_id="22",
        notify_recipients=[],
        product_code=code,
    )


def _user_id(user) -> UUID | None:
    """Pull the auth.users.id off whatever shape the dependency returned."""
    if user is None:
        return None
    raw = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None


# ─── POST /upload — browser file upload ────────────────────────────────
@router.post(
    "",
    response_model=UploadJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_video(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    metadata_json: str = Form(
        ...,
        alias="metadata",
        description='JSON-encoded UploadMetadata: {"title":"...","description":"...","tags":[...],"privacy_status":"private","category_id":"22","notify_recipients":[]}',
    ),
    auth: tuple = Depends(get_current_user_org),
) -> UploadJobCreated:
    """Browser drag-and-drop upload. Multipart body carries the file +
    a single JSON-encoded ``metadata`` field — JSON-in-form rather than
    one form field per metadata key so nested types (tags[], notify_recipients[])
    don't have to be reconstructed by the FastAPI machinery."""
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    try:
        metadata = UploadMetadata(**json.loads(metadata_json))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid metadata payload: {exc}",
        ) from exc

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="upload missing filename",
        )

    service = _build_upload_service(token)

    # Stage the multipart body to disk BEFORE inserting the job row, so
    # if the disk write fails we don't leave a queued-but-unrunnable row.
    try:
        with stage_browser_upload(
            upload_dir=_UPLOAD_DIR,
            file_name=file.filename,
            upload_stream=file.file,
        ) as staging_path:
            file_size = staging_path.stat().st_size

            try:
                queued = service.queue_browser_upload(
                    org_id=org_id,
                    created_by=_user_id(user),
                    metadata=metadata,
                    file_name=file.filename,
                    file_size_bytes=file_size,
                    local_path=staging_path,
                )
            except UploadServiceError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc

            # Now that the job_id exists, rename the staging file so the
            # background worker can find it deterministically.
            rename_for_job(staging_path, queued.job_id, file.filename)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"failed to write upload to disk: {exc}",
        ) from exc

    background.add_task(service.run_upload_job, job_id=queued.job_id)
    return UploadJobCreated(job_id=queued.job_id, status=queued.status)


# ─── POST /upload-from-drive — Google Drive link ───────────────────────
@router.post(
    "-from-drive",
    response_model=UploadJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_from_drive(
    payload: GdriveUploadRequest,
    background: BackgroundTasks,
    auth: tuple = Depends(get_current_user_org),
) -> UploadJobCreated:
    """Queue a Drive-sourced upload. Download happens in the background
    (it can take minutes for big files) — the response is immediate."""
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_upload_service(token)

    try:
        queued = service.queue_drive_upload(
            org_id=org_id,
            created_by=_user_id(user),
            metadata=payload.metadata,
            drive_url=str(payload.drive_url),
        )
    except UploadServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    background.add_task(service.run_upload_job, job_id=queued.job_id)
    return UploadJobCreated(job_id=queued.job_id, status=queued.status)


# ─── POST /drive-folder — multi-video fan-out (youtube-drive-folder-fanout)
@router.post(
    "/drive-folder",
    response_model=BatchUploadCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_from_drive_folder(
    payload: GdriveFolderUploadRequest,
    background: BackgroundTasks,
    auth: tuple = Depends(get_current_user_org),
) -> BatchUploadCreated:
    """Queue a Drive **folder** as a batch of independent upload jobs.

    Every video in the folder (recursing one level into subfolders)
    becomes its own ``upload_jobs`` row sharing one ``batch_id``. The
    worker classifies each video at run time — vertical files get the
    Shorts treatment automatically (no separate endpoint needed).

    Two input modes (validated by the schema):
      - ``metadata`` set → manual mode; title/description/tags travel
        with the request.
      - ``product_code`` set → Vista CRM lookup mode; server fetches
        property data + builds the same metadata shape used by the
        chatbot intake (``build_youtube_metadata(prop, code)``).

    Returns 202 + the batch_id + the list of child jobs.

    HTTP error map:
      - 400: invalid folder URL / parse failure / `UploadServiceError`
        wrapping a bad operator-side input.
      - 404: ``product_code`` mode but Vista returned no property for
        the code.
      - 422: well-formed URL but Drive returned no acceptable videos
        (empty folder, only non-videos, sharing-permission gap, …).
      - 503: credential-store config gap OR Vista not configured when
        ``product_code`` mode was requested.
    """
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_upload_service(token)

    # Resolve metadata: either explicit (manual mode) or Vista lookup.
    if payload.metadata is not None:
        resolved_metadata = payload.metadata
    else:
        resolved_metadata = await _resolve_metadata_from_product_code(
            product_code=payload.product_code or "",
            privacy_status=payload.privacy_status,
        )

    try:
        batch = service.queue_drive_folder_upload(
            org_id=org_id,
            created_by=_user_id(user),
            metadata=resolved_metadata,
            drive_folder_url=str(payload.drive_folder_url),
        )
    except UploadServiceError as exc:
        msg = str(exc)
        # Distinguish "no videos found / Drive permission" (caller fixable
        # at the folder level) from "URL malformed" (caller fixable at the
        # input level). The phrase fingerprints below come from
        # `iter_drive_folder_videos` + `parse_folder_id`.
        no_videos = any(
            tok in msg for tok in (
                "No accepted video",
                "no files",
                "fanout failed",
            )
        )
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
                if no_videos
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=msg,
        ) from exc

    for child in batch.children:
        background.add_task(service.run_upload_job, job_id=child.job_id)

    return BatchUploadCreated(
        batch_id=batch.batch_id,
        jobs=[
            BatchChildOut(
                job_id=child.job_id,
                file_name=child.file_name,
                parent_subfolder=child.parent_subfolder,
            )
            for child in batch.children
        ],
    )


# ─── GET /{id}/status ──────────────────────────────────────────────────
@router.get("/{job_id}/status", response_model=UploadJobOut)
async def get_upload_status(
    job_id: UUID,
    auth: tuple = Depends(get_current_user_org),
) -> UploadJobOut:
    """UI polls this every ~2s while a job is in flight. RLS-bounded so
    a caller can't peek at another org's jobs by guessing UUIDs."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_upload_service(token)
    row = service.get_job(job_id=job_id, org_id=org_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="upload job not found",
        )
    return _row_to_out(row)


# ─── POST /{id}/retry — re-queue a failed job ──────────────────────────
@router.post(
    "/{job_id}/retry",
    response_model=UploadJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_upload(
    job_id: UUID,
    background: BackgroundTasks,
    auth: tuple = Depends(get_current_user_org),
) -> UploadJobOut:
    """Re-queue a previously-failed upload job.

    Only fires on jobs in ``failed`` state — otherwise returns 409 so
    the dashboard's retry button is clear about which rows are
    re-runnable. The actual upload runs in the background task; the
    response is the updated job row (status flipped to ``queued``).

    Note: this does NOT re-download from Drive. If the source folder is
    no longer accessible, the re-run will fail with a fresh Drive error
    — the operator can see the failure on the same job row and decide
    whether to re-issue the original WhatsApp command.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_upload_service(token)

    try:
        refreshed = service.retry_failed_job(job_id=job_id, org_id=org_id)
    except UploadServiceError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            ) from exc
        # "retry only works on failed jobs" or similar
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=msg,
        ) from exc

    background.add_task(service.run_upload_job, job_id=job_id)
    return _row_to_out(refreshed)


# ─── GET /batch/{batch_id} — aggregate status of a fan-out batch ──────
@router.get("/batch/{batch_id}", response_model=BatchStatusOut)
async def get_batch_status(
    batch_id: UUID,
    auth: tuple = Depends(get_current_user_org),
) -> BatchStatusOut:
    """Aggregate state of one Drive-folder fan-out batch.

    Returns 404 when no rows match the batch_id within the caller's
    org — RLS-bounded so a guess can't leak another org's batch."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_upload_service(token)

    snapshot = service.get_batch_status(org_id=org_id, batch_id=batch_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no batch with id={batch_id} in this org",
        )

    return BatchStatusOut(
        batch_id=snapshot["batch_id"],
        total=snapshot["total"],
        counts=BatchStatusCounts(**snapshot["counts"]),
        jobs=[_row_to_out(r) for r in snapshot["jobs"]],
    )


# ─── GET /history ──────────────────────────────────────────────────────
@router.get("/history", response_model=list[UploadJobOut])
async def list_upload_history(
    limit: int = 25,
    auth: tuple = Depends(get_current_user_org),
) -> list[UploadJobOut]:
    """Most-recent jobs for the Upload page's history table."""
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 100",
        )
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    service = _build_upload_service(token)
    rows = service.list_history(org_id=org_id, limit=limit)
    return [_row_to_out(row) for row in rows]


__all__ = ["router"]
