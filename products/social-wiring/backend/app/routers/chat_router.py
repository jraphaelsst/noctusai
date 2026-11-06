"""Platform-side chat surface for the tool-calling chatbot (Anthropic).

Mirrors the WhatsApp inbound flow but lives behind an HTTP API the
frontend can call directly. The same :class:`ChatbotService` and
:class:`WhatsAppIntakeService` back both surfaces — the only difference
is the session id shape:

- WhatsApp: ``5511974693365@c.us`` (the sender's phone JID)
- Platform: ``web:<uuid>`` issued by the frontend on first message

Access tier ``org`` (OWASP API1 BOLA / API2 broken authentication): every route sits
behind ``get_current_user_org``. The org comes from the authenticated session -- never a
"default org" -- and the Redis session key is namespaced by that org, so one org can
never read, reset or continue another org's conversation by guessing a ``session_id``.
(Until 2026-11 this surface was anonymous and acted for the first org with a YouTube
credential.)
"""
from __future__ import annotations

import logging
import uuid as _uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import redis
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.integrations.redis import make_redis_client
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.primitives.exceptions import AppException
from fastapi import Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.services.chatbot_service import ChatbotService, append_memory
from app.services.conversation_module import route_inbound
from app.services.credential_vault import CredentialStore, EncryptionNotConfigured
from app.services.account_credentials import build_youtube_service_for_org
from app.services import vista_credenciais
from app.services.media_service import make_media_service
from app.modules.youtube.services.upload import stage_browser_upload
from app.services.whatsapp_intake_service import WhatsAppIntakeService, web_reply_sink
from app.modules.youtube.services.youtube import YouTubeService, YouTubeServiceError

logger = logging.getLogger(__name__)

router = make_router(tier="org", guard=get_current_user_org, prefix="/api/chat", tags=["chat"])

_UPLOAD_DIR = Path("/tmp/uploads")
_WEB_SESSION_PREFIX = "web:"


# ─── Response shapes ───────────────────────────────────────────────────
class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatHistoryItem] = Field(default_factory=list)
    # The upload flow keeps talking after the HTTP reply (Drive download,
    # video choice, "publicado"); while this is set the UI keeps polling.
    pending: dict[str, Any] | None = None


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
    return make_redis_client(settings.redis_url, decode_responses=True)


def _build_intake(org_id: UUID) -> WhatsAppIntakeService:
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

    # ``org_id`` is the AUTHENTICATED caller's org (``get_current_user_org``).
    # That org's own Vista credential; none -> manual titles (never an env key).
    crm = vista_credenciais.adapter_ou_none(org_id)

    return WhatsAppIntakeService(
        redis_client=redis_client,
        authorized_numbers=[],  # platform chat skips the WhatsApp whitelist
        crm_service=crm,
        admin_supabase=admin_supabase,
        youtube_service=youtube,
        upload_dir=_UPLOAD_DIR,
        org_id=org_id,
    )


def _ensure_web_session(session_id: str | None) -> str:
    """Normalize to a ``web:<uuid>`` session id. Generates one if blank."""
    if not session_id:
        return f"{_WEB_SESSION_PREFIX}{_uuid.uuid4().hex}"
    if not session_id.startswith(_WEB_SESSION_PREFIX):
        return f"{_WEB_SESSION_PREFIX}{session_id}"
    return session_id


def _org_session(external_session: str, org_id: UUID) -> str:
    """Org-namespaced Redis session key: ``web:<uuid>|<org_id>``. The client only ever sees
    (and sends) the external ``web:<uuid>``; another org's id never maps to this key."""
    return f"{external_session}|{org_id}"


def _caller_org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


# ─── POST /api/chat/upload-file — stage-only ───────────────────────────
@router.post("/upload-file", response_model=FileStaged)
def stage_chat_file(
    file: UploadFile = File(...),
    session_id: str = Form(""),
    auth: tuple = Depends(get_current_user_org),
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

    org_id = _caller_org(auth)
    intake = _build_intake(org_id)

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
    auth: tuple = Depends(get_current_user_org),
) -> ChatReply:
    """One chat turn for the platform UI — code first, model last.

    Routed by :func:`route_inbound`, the same order WhatsApp uses: upload
    answers (sim/não, título, escolha de vídeo), typed commands, code +
    attached video, code + Drive link all run without a model; only the
    rest reaches the Claude tool loop. Every reply the turn produced is
    collected and returned as ``reply``.

    Multipart so the same call can carry an optional file attachment. A
    video is staged and registered under a ``file_id`` (used directly when
    the text has a property code; otherwise passed to the model as
    context). Other attachments are resolved to text for the model.
    """
    org_id = _caller_org(auth)
    external_session = _ensure_web_session(session_id)
    normalized_session = _org_session(external_session, org_id)
    intake = await run_blocking(_build_intake, org_id)
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
                        media_service = make_media_service(org_id=intake.org_id)
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

    # The user's turn goes to the conversation memory first, so every path
    # below (deterministic or model) answers into the same history.
    inbound_label = text or ""
    if file is not None and getattr(file, "filename", None):
        inbound_label = f"{inbound_label} 📎 {file.filename}".strip()
    await run_blocking(
        append_memory,
        intake.redis_client,
        session_id=normalized_session,
        direction="inbound",
        text=inbound_label,
    )

    async def _llm(message: str) -> None:
        chatbot = ChatbotService(
            redis_client=intake.redis_client,
            intake_service=intake,
            session_id=normalized_session,
            model=settings.chatbot_llm_model,
            extra_context=extra_context,
        )
        answer = await chatbot.reply(message, append_inbound=False, append_outbound=False)
        await intake.send_reply(normalized_session, answer)

    collected: list[str] = []
    token = web_reply_sink.set(collected)
    try:
        await route_inbound(
            intake=intake,
            session_id=normalized_session,
            text=text or "",
            llm_fallback=_llm,
            commands=intake.youtube_chat_commands(),
            attached_file_id=file_id,
        )
    except AppException:
        # Typed failures (e.g. `ProviderQuotaExhausted`) already carry their
        # status + PT-BR message; the framework handler renders them.
        logger.exception("chat routing failed for session=%s", normalized_session)
        raise
    except Exception as exc:
        logger.exception("chat routing failed for session=%s", normalized_session)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"chatbot failure: {exc}",
        ) from exc
    finally:
        web_reply_sink.reset(token)

    reply = "\n\n".join(m for m in collected if m)
    if not reply:
        logger.warning("chat turn produced no reply for session=%s", normalized_session)
        reply = "Recebi sua mensagem, mas não tenho uma resposta para ela agora."

    pending = await intake.get_pending_upload(normalized_session)
    return ChatReply(
        session_id=external_session,
        reply=reply,
        file_id=file_id,
        pending=pending if pending.get("found") else None,
    )


# ─── GET /api/chat/history/{session_id} ────────────────────────────────
@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def chat_history(session_id: str, auth: tuple = Depends(get_current_user_org)) -> ChatHistoryResponse:
    """Return the recent conversation memory for the platform UI to
    render after a refresh. Caps at MAX_MEMORY_ITEMS items (12)."""
    org_id = _caller_org(auth)
    external = _ensure_web_session(session_id)
    normalized = _org_session(external, org_id)
    intake = await run_blocking(_build_intake, org_id)
    chatbot = ChatbotService(
        redis_client=intake.redis_client,
        intake_service=intake,
        session_id=normalized,
        model=settings.chatbot_llm_model,
    )
    pending = await intake.get_pending_upload(normalized)
    return ChatHistoryResponse(
        session_id=external,
        messages=[ChatHistoryItem(**m) for m in chatbot.load_history()],
        pending=pending if pending.get("found") else None,
    )


# ─── POST /api/chat/reset/{session_id} ─────────────────────────────────
@router.post("/reset/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def chat_reset(session_id: str, auth: tuple = Depends(get_current_user_org)) -> None:
    org_id = _caller_org(auth)
    normalized = _org_session(_ensure_web_session(session_id), org_id)
    intake = await run_blocking(_build_intake, org_id)
    chatbot = ChatbotService(
        redis_client=intake.redis_client,
        intake_service=intake,
        session_id=normalized,
        model=settings.chatbot_llm_model,
    )
    await run_blocking(chatbot.reset_history)
    await intake.cancel_pending_upload(normalized)


__all__ = ["router"]
