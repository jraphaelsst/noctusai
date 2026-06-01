"""Platform-side chat surface for the OpenAI tool-calling chatbot.

Mirrors the WhatsApp inbound flow but lives behind an HTTP API the
frontend can call directly. The same :class:`ChatbotService` and
:class:`WhatsAppIntakeService` back both surfaces — the only difference
is the session id shape:

- WhatsApp: ``5511974693365@c.us`` (the sender's phone JID)
- Platform: ``web:<uuid>`` issued by the frontend on first message

The endpoint is unauthenticated for now per the user's direction (the
frontend route itself is auth-gated). When a real auth model lands we
swap the ``session_id`` parameter for an org-scoped key derived from
the JWT.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import redis
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import get_admin_client
from app.services.chatbot_service import ChatbotService
from app.services.credential_vault import CredentialStore, EncryptionNotConfigured
from app.services.account_credentials import build_youtube_service_for_org
from noctusai_lib.integrations.vista import (
    VistaNotConfigured as CRMNotConfigured,
    VistaRESTAdapter as CRMService,
)
from app.services.media_service import make_media_service
from app.modules.youtube.services.upload import stage_browser_upload
from app.services.whatsapp_intake_service import WhatsAppIntakeService
from app.modules.youtube.services.youtube import YouTubeService, YouTubeServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

_UPLOAD_DIR = Path("/tmp/uploads")
_WEB_SESSION_PREFIX = "web:"


# ─── Response shapes ───────────────────────────────────────────────────
class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatHistoryItem] = Field(default_factory=list)


class ChatReply(BaseModel):
    session_id: str
    reply: str
    file_id: str | None = None
    pending: dict[str, Any] | None = None


class FileStaged(BaseModel):
    file_id: str
    file_name: str
    file_size_bytes: int


# ─── Wiring helpers ────────────────────────────────────────────────────
def _make_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _build_intake() -> WhatsAppIntakeService:
    """Mirror of the WhatsApp router's wiring. Returns the same
    intake-service shape; raises HTTPException(503) on misconfig so the
    frontend gets actionable feedback instead of a silent failure."""
    admin_supabase = get_admin_client()

    try:
        redis_client = _make_redis()
        redis_client.ping()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"redis unavailable: {exc}",
        ) from exc

    youtube: YouTubeService | None = None
    try:
        youtube = build_youtube_service_for_org(admin_supabase, settings)
    except (EncryptionNotConfigured, YouTubeServiceError) as exc:
        logger.warning("YouTube service unavailable for chat: %s", exc)

    crm: CRMService | None = None
    try:
        crm = CRMService(
            base_url=settings.crm_base_url,
            api_key=settings.crm_api_key,
        )
    except CRMNotConfigured:
        logger.info("CRM not configured — platform chat will use manual titles")

    # No JWT context, so the chat surface uses the seed default org
    # (the local-dev org in SQLite mode; the first connected YouTube
    # org in Supabase mode — same shape as the WhatsApp router).
    org_id = _resolve_default_org(admin_supabase) or UUID(settings.local_dev_org_id)

    return WhatsAppIntakeService(
        waha_base_url=settings.waha_base_url,
        waha_api_key=settings.waha_api_key,
        waha_session=settings.waha_session,
        redis_client=redis_client,
        authorized_numbers=[],  # platform chat skips the WhatsApp whitelist
        crm_service=crm,
        admin_supabase=admin_supabase,
        youtube_service=youtube,
        upload_dir=_UPLOAD_DIR,
        org_id=org_id,
    )


def _resolve_default_org(admin_supabase) -> UUID | None:
    try:
        response = (
            admin_supabase
            .schema("social_wiring")
            .table("credentials")
            .select("org_id")
            .eq("provider", "youtube")
            .limit(1)
            .execute()
        )
        if response.data:
            return UUID(response.data[0]["org_id"])
    except Exception as exc:
        logger.error("failed to resolve default org for chat: %s", exc)
    return None


def _ensure_web_session(session_id: str | None) -> str:
    """Normalize to a ``web:<uuid>`` session id. Generates one if blank."""
    if not session_id:
        return f"{_WEB_SESSION_PREFIX}{_uuid.uuid4().hex}"
    if not session_id.startswith(_WEB_SESSION_PREFIX):
        return f"{_WEB_SESSION_PREFIX}{session_id}"
    return session_id


# ─── POST /api/chat/upload-file — stage-only ───────────────────────────
@router.post("/upload-file", response_model=FileStaged)
async def stage_chat_file(
    file: UploadFile = File(...),
    session_id: str = Form(""),
) -> FileStaged:
    """Stream a video file to disk and register it under a file_id.

    The chatbot's ``prepare_upload_from_file`` tool resolves the file_id
    against the intake's file registry. The file is kept on disk for up
    to 4 hours (Redis TTL); if the user never confirms, the file is
    leaked — pre-commit hygiene sweep cleans the upload_dir.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="upload missing filename",
        )

    normalized_session = _ensure_web_session(session_id)
    intake = _build_intake()

    try:
        with stage_browser_upload(
            upload_dir=_UPLOAD_DIR,
            file_name=file.filename,
            upload_stream=file.file,
        ) as staging_path:
            file_size = staging_path.stat().st_size
            file_id = f"stg-{_uuid.uuid4().hex}"
            intake.register_uploaded_file(
                file_id=file_id,
                local_path=str(staging_path),
                file_name=file.filename,
                file_size_bytes=file_size,
            )
            # NOTE: we deliberately do NOT auto-cleanup; the file lives
            # until confirm_pending_upload renames it to the job path
            # or the TTL expires. The pending-upload flow owns disk
            # cleanup from here on.
            return FileStaged(
                file_id=file_id,
                file_name=file.filename,
                file_size_bytes=file_size,
            )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"failed to stage file: {exc}",
        ) from exc


# ─── POST /api/chat/message — multipart text + optional file ───────────
@router.post("/message", response_model=ChatReply)
async def chat_message(
    text: str = Form(""),
    session_id: str = Form(""),
    file: UploadFile | None = File(None),
) -> ChatReply:
    """Drive the OpenAI tool-calling loop for the platform UI.

    Multipart so the same call can carry an optional file attachment.
    When ``file`` is present, the backend stages it first, then injects
    a system-style hint into the chatbot's extra_context so the model
    knows it can call ``prepare_upload_from_file`` with the issued
    file_id without the user having to copy/paste it.
    """
    normalized_session = _ensure_web_session(session_id)
    intake = _build_intake()
    file_id: str | None = None
    extra_context: str | None = None

    if file is not None and getattr(file, "filename", None):
        mt = (file.content_type or "").lower()
        is_video_for_upload = mt.startswith("video/")
        try:
            with stage_browser_upload(
                upload_dir=_UPLOAD_DIR,
                file_name=file.filename,
                upload_stream=file.file,
            ) as staging_path:
                file_size = staging_path.stat().st_size
                if is_video_for_upload:
                    # Video → register for the YouTube upload pipeline; the
                    # chatbot's prepare_upload_from_file tool resolves the
                    # file_id and queues the publish.
                    file_id = f"stg-{_uuid.uuid4().hex}"
                    intake.register_uploaded_file(
                        file_id=file_id,
                        local_path=str(staging_path),
                        file_name=file.filename,
                        file_size_bytes=file_size,
                    )
                    extra_context = (
                        "Contexto: usuario anexou um arquivo de video na "
                        f"mensagem atual. file_id={file_id} "
                        f"filename={file.filename} size_bytes={file_size}. "
                        "Use prepare_upload_from_file com este file_id quando "
                        "decidir preparar o upload."
                    )
                else:
                    # Image / audio / document → resolve via the media
                    # service so the chatbot sees the transcript or
                    # description, not just "[arquivo anexado]". File
                    # gets cleaned up after resolution (we don't keep
                    # non-video attachments).
                    try:
                        media_service = make_media_service()
                        resolved = await media_service.resolve_inbound(
                            url=None,  # bytes-in-hand path below overrides
                            mimetype=mt,
                            filename=file.filename,
                            fallback_text="",
                        )
                        # The URL-less path returns an error mode; switch
                        # to the bytes-in-hand resolvers directly.
                        media_bytes = staging_path.read_bytes()
                        if mt.startswith("audio/"):
                            transcript = await media_service.transcribe_audio(
                                media_bytes, filename=file.filename or "audio.ogg"
                            )
                            enriched = (
                                f"[Audio transcrito] {transcript}"
                                if transcript
                                else "[Audio recebido — transcricao indisponivel]"
                            )
                        elif mt.startswith("image/"):
                            description = await media_service.describe_image(
                                media_bytes, mimetype=mt
                            )
                            enriched = (
                                f"[Imagem] {description}"
                                if description
                                else "[Imagem recebida — descricao indisponivel]"
                            )
                        else:
                            enriched = (
                                f"[Anexo recebido: {file.filename} ({mt or 'desconhecido'})]"
                            )
                        extra_context = (
                            "Contexto: o usuario anexou um arquivo na mensagem "
                            f"atual. Tipo: {mt or 'desconhecido'}. Resolucao: "
                            f"{enriched}. Use isso para responder com base no "
                            "conteudo, nao apenas no fato de que um anexo chegou."
                        )
                    except Exception:
                        logger.exception("media resolution failed in chat router")
                    finally:
                        # Non-video attachments are transient — drop the
                        # staged file once we have the resolved text.
                        try:
                            staging_path.unlink(missing_ok=True)
                        except Exception:
                            pass
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                detail=f"failed to stage file: {exc}",
            ) from exc

    chatbot = ChatbotService(
        redis_client=intake.redis_client,
        intake_service=intake,
        session_id=normalized_session,
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
        extra_context=extra_context,
    )

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    try:
        reply = await chatbot.reply(text or "")
    except Exception as exc:
        logger.exception("chatbot reply failed for session=%s", normalized_session)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"chatbot failure: {exc}",
        ) from exc

    pending = await intake.get_pending_upload(normalized_session)
    return ChatReply(
        session_id=normalized_session,
        reply=reply,
        file_id=file_id,
        pending=pending if pending.get("found") else None,
    )


# ─── GET /api/chat/history/{session_id} ────────────────────────────────
@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def chat_history(session_id: str) -> ChatHistoryResponse:
    """Return the recent conversation memory for the platform UI to
    render after a refresh. Caps at MAX_MEMORY_ITEMS items (12)."""
    normalized = _ensure_web_session(session_id)
    intake = _build_intake()
    chatbot = ChatbotService(
        redis_client=intake.redis_client,
        intake_service=intake,
        session_id=normalized,
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key or "noop",
    )
    return ChatHistoryResponse(
        session_id=normalized,
        messages=[ChatHistoryItem(**m) for m in chatbot.load_history()],
    )


# ─── POST /api/chat/reset/{session_id} ─────────────────────────────────
@router.post("/reset/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def chat_reset(session_id: str) -> None:
    normalized = _ensure_web_session(session_id)
    intake = _build_intake()
    chatbot = ChatbotService(
        redis_client=intake.redis_client,
        intake_service=intake,
        session_id=normalized,
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key or "noop",
    )
    chatbot.reset_history()
    await intake.cancel_pending_upload(normalized)


__all__ = ["router"]
