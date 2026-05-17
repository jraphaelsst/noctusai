"""Pydantic schemas for WhatsApp inbound webhook.

WAHA delivers webhooks in a standard shape; these schemas parse the
inbound message payload so the router + intake service can operate on
typed data instead of raw dicts.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WAHAMedia(BaseModel):
    """Media descriptor on WAHA message payloads."""

    model_config = ConfigDict(extra="allow")

    url: str | None = None
    mimetype: str | None = None
    filename: str | None = None


class WAHAReplyTo(BaseModel):
    """Reply metadata. WAHA shape varies slightly by engine/version."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    body: str | None = None
    participant: str | None = None


class WAHAMe(BaseModel):
    """Authenticated account identity returned by session endpoints/events."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    pushName: str | None = None


class WAHAEngine(BaseModel):
    """Session engine descriptor. Docs show {"engine":"WEBJS|NOWEB|..."}."""

    model_config = ConfigDict(extra="allow")

    engine: str | None = None


class WAHAWebhookConfig(BaseModel):
    """Webhook config inside session info."""

    model_config = ConfigDict(extra="allow")

    url: str | None = None
    events: list[str] = Field(default_factory=list)
    hmac: str | None = None
    retries: Any = None
    customHeaders: Any = None


class WAHASessionConfig(BaseModel):
    """Known subset of WAHA session config."""

    model_config = ConfigDict(extra="allow")

    webhooks: list[WAHAWebhookConfig] = Field(default_factory=list)
    debug: bool | None = None


class WAHASessionInfo(BaseModel):
    """Response from GET /api/sessions/{name} and list item from /api/sessions."""

    model_config = ConfigDict(extra="allow")

    name: str
    status: str | None = None
    config: WAHASessionConfig | dict[str, Any] | None = None
    me: WAHAMe | dict[str, Any] | None = None
    engine: WAHAEngine | dict[str, Any] | None = None


class WAHASessionStatusHistoryItem(BaseModel):
    """Item in session.status payload.statuses."""

    model_config = ConfigDict(extra="allow")

    status: str
    timestamp: int | float | None = None


class WAHASessionStatusPayload(BaseModel):
    """Payload for the session.status event."""

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    statuses: list[WAHASessionStatusHistoryItem] = Field(default_factory=list)


class WAHAMessagePayload(BaseModel):
    """Subset of the WAHA webhook payload we care about.

    WAHA sends many event types (message, ack, state-change, etc.); we
    only process ``message`` events with a text body. The router
    short-circuits on anything else.
    """

    model_config = ConfigDict(extra="allow")

    event: str = ""
    session: str = ""
    payload: WAHAMessage | WAHASessionStatusPayload | dict[str, Any] | None = None
    me: WAHAMe | dict[str, Any] | None = None
    engine: str | dict[str, Any] | None = None
    environment: dict[str, Any] | None = None


class WAHAMessage(BaseModel):
    """The inner ``payload`` object of a WAHA message webhook."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = ""
    timestamp: int | float = 0
    from_: str = Field(default="", alias="from")
    to: str = ""
    chat_id: str = Field(default="", alias="chatId")
    body: str = ""
    from_me: bool = Field(default=False, alias="fromMe")
    participant: str | None = None
    reply_to: WAHAReplyTo | dict[str, Any] | None = Field(default=None, alias="replyTo")
    has_media: bool = Field(default=False, alias="hasMedia")
    media: WAHAMedia | dict[str, Any] | None = None
    ack: int | str | None = None
    # WAHA puts the chat ID in ``from`` for incoming messages
    # and in ``to`` for outgoing. We normalise in the router.


class WAHASendTextResponse(BaseModel):
    """Known variants from POST /api/sendText.

    WAHA engines may return a top-level ``id``, a WhatsApp Web-style
    ``key.id``, or nested internal ``_data.id``. Keep extra fields so
    logs can retain provider detail without schema churn.
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    key: dict[str, Any] | None = None
    message: dict[str, Any] | None = None
    data: dict[str, Any] | None = Field(default=None, alias="_data")


def extract_waha_message_id(payload: dict[str, Any]) -> str | None:
    """Best-effort id extractor for WAHA send responses."""
    if not isinstance(payload, dict):
        return None
    direct = payload.get("id")
    if direct:
        return str(direct)
    key = payload.get("key")
    if isinstance(key, dict) and key.get("id"):
        return str(key["id"])
    data = payload.get("_data")
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    nested_id = payload.get("message", {}).get("id") if isinstance(payload.get("message"), dict) else None
    return str(nested_id) if nested_id else None


class UploadCommand(BaseModel):
    """Parsed result of a valid inbound upload command.

    Extracted from the message body by the intake service's parser.
    """

    product_code: str
    drive_url: str


class VideoCandidateSnapshot(BaseModel):
    """Snapshot of a single video candidate persisted in ``PendingUpload``.

    Mirrors ``gdrive_service.VideoCandidate`` but with serializable types
    (path → str) so the whole ``PendingUpload`` can JSON-roundtrip
    through Redis.
    """

    local_path: str
    file_name: str
    file_size_bytes: int
    format: str
    duration_seconds: float | None = None


class PendingUpload(BaseModel):
    """State stored in Redis while awaiting user confirmation.

    Serialized as JSON; key: ``whatsapp:conv:{session_id}`` where
    ``session_id`` is the WhatsApp phone for the WAHA path or a
    platform-issued web session id for the in-app chat.

    One of ``drive_url`` or ``file_id`` is populated, depending on
    whether the upload was requested via a Drive link or a file the
    user attached in the chat UI.
    """

    product_code: str
    drive_url: str | None = None
    file_id: str | None = None
    video_filename: str | None = None
    video_size_bytes: int | None = None
    video_format: str | None = None  # "youtube" | "reels" | "unknown"
    crm_title: str | None = None
    crm_description: str | None = None
    privacy_status: str = "private"
    # Populated when ``list_youtube_candidates`` returned N≥2 horizontal
    # videos from the Drive folder. The intake state machine transitions
    # to ``awaiting_video_choice`` and the user replies with the index
    # (1-based) of the candidate they want to upload. Cleared once the
    # selection resolves.
    candidate_videos: list[VideoCandidateSnapshot] = Field(default_factory=list)
    # When the intake pre-downloads a Drive folder to disambiguate the
    # video (multi-candidate flow), the resolved local path is stored
    # here. ``_run_upload`` honors this and skips the upload-service's
    # re-download step via ``queue_browser_upload``.
    local_video_path: str | None = None
    local_video_filename: str | None = None
    local_video_size_bytes: int | None = None
    state: Literal[
        "idle",
        "awaiting_confirmation",
        "awaiting_manual_title",
        "awaiting_video_choice",
        "processing",
    ] = "idle"


class IntakeConversationDTO(BaseModel):
    """One row in the intake/flow monitor — a conversation's live state.

    Derived from the Redis ``whatsapp:conv:{session_id}`` PendingUpload
    snapshot plus the active-upload counter. Read-only projection; no
    PendingUpload internals (local paths, candidate blobs) leak.
    """

    session_id: str
    state: str
    product_code: str | None = None
    drive_url: str | None = None
    video_filename: str | None = None
    video_format: str | None = None
    candidate_count: int = 0
    active_uploads: int = 0


class IntakeMessageDTO(BaseModel):
    """One inbound/outbound line in a conversation's recent history."""

    direction: str
    body: str
    created_at: str | None = None
    provider_message_id: str | None = None


class IntakeConversationDetailDTO(BaseModel):
    """Conversation state + its recent message history."""

    conversation: IntakeConversationDTO
    messages: list[IntakeMessageDTO] = Field(default_factory=list)


class IntakeCancelResult(BaseModel):
    """Outcome of clearing a stuck conversation's pending state."""

    session_id: str
    cleared: bool
