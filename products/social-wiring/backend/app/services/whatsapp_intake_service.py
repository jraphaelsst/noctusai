"""WhatsApp inbound intake — parse commands, manage conversation state.

Handles the conversational flow for WhatsApp-triggered video uploads:
1. Receives a product code + Drive URL from the authorized user
2. Downloads video + fetches CRM data in parallel
3. Presents a confirmation summary
4. On "sim" → queues the upload job
5. On completion → sends the YouTube link back

Conversation state is stored in Redis with a 30-minute TTL so abandoned
flows don't leak memory. Only one conversation per phone number is
active at a time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from uuid import UUID

import httpx

from noctusai_lib.integrations.whatsapp import (
    get_whatsapp_client,
)

from app.config import settings
from app.schemas.whatsapp import (
    PendingUpload,
    UploadCommand,
    VideoCandidateSnapshot,
    extract_waha_message_id,
)
from app.services import gdrive_service
from app.services.chatbot_service import append_memory as _append_chat_memory
from noctusai_lib.domain.real_estate import (
    PropertyData,
    build_youtube_metadata,
    validate_product_code,
)
from noctusai_lib.integrations.vista import (
    VistaError as CRMServiceError,
    VistaNotConfigured as CRMNotConfigured,
    VistaRESTAdapter as CRMService,
)
from app.services.message_store import DuplicateMessage, MessageStore
from app.services.waha_response_registry import record_waha_sample

logger = logging.getLogger(__name__)

# Independent extractors — code and URL may appear in either order.
# Keep tolerance aligned with conversation_module._regex_extract so the
# fast-path gate and the state-machine handler agree on what counts as a
# valid upload command (silent drops from order-mismatch caused user-
# visible "no reply" incidents).
_PRODUCT_CODE_RE = re.compile(r"\bONE\d{3,6}\b", re.IGNORECASE)
_DRIVE_URL_RE = re.compile(
    r"https?://(?:drive\.google\.com|docs\.google\.com)\S+",
    re.IGNORECASE,
)

# Confirmation responses
_YES_RESPONSES = {"sim", "s", "confirmar", "confirma", "yes", "y", "ok"}
_NO_RESPONSES = {"não", "nao", "n", "cancelar", "cancela", "cancel", "no"}

_REDIS_KEY_PREFIX = "whatsapp:conv:"
_REDIS_TTL_SECONDS = 30 * 60  # 30 minutes
_ACTIVE_UPLOADS_PREFIX = "whatsapp:active_uploads:"
_ACTIVE_UPLOADS_TTL = 2 * 60 * 60  # 2h — far exceeds even slow uploads, auto-self-heals on stuck counters


def _meta_attachments_summary(attachments: list[dict[str, Any]] | None) -> list[str]:
    """Project the seed ``FacebookPost.attachments`` (raw Graph dicts) into
    the terse label list the chatbot JSON exposes.

    The seed value object carries the raw attachment dicts (it does not
    pre-summarize, unlike the retired product mapper). We reproduce the
    old projection here at the consumer: ``title → description → type``,
    dropping empties. Keeps the ``attachments_summary`` response key
    shape identical to the pre-seed-consume behavior.
    """
    labels: list[str] = []
    for att in attachments or []:
        if not isinstance(att, dict):
            continue
        label = att.get("title") or att.get("description") or att.get("type") or ""
        if label:
            labels.append(label)
    return labels


def _meta_insights_period(insights: Any) -> str:
    """Recover the insight rollup window from the seed ``PostInsights``.

    The seed flattens insights to ``{object_id, metrics, raw}`` and drops
    the dedicated ``period`` field the product mapper exposed. We read it
    back off the first raw row (Graph stamps every metric row with a
    ``period``), defaulting to ``"lifetime"`` — the value the retired
    mapper used and what engagement counts are reported over.
    """
    for row in getattr(insights, "raw", None) or []:
        if isinstance(row, dict) and row.get("period"):
            return row["period"]
    return "lifetime"


def _format_size(bytes_: int | None) -> str:
    """Render a byte count as human-readable size for choice menus.

    Returns ``"?"`` when ``bytes_`` is missing/zero. Output stays terse
    (one unit, one decimal) so it fits on a phone screen alongside the
    filename in a numbered choice list.
    """
    if not bytes_:
        return "?"
    units = ["B", "KB", "MB", "GB"]
    size = float(bytes_)
    for unit in units:
        if size < 1024 or unit == "GB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def _format_duration(seconds: float | None) -> str:
    """Render a duration as ``mm:ss`` for choice menus.

    Returns ``""`` when duration is unknown so callers can conditionally
    append (``" (4:32)"`` becomes ``""``). ffprobe being absent — the
    common case in slim containers — naturally lands here.
    """
    if not seconds or seconds <= 0:
        return ""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def _active_uploads_key(phone: str) -> str:
    """Redis key for the per-phone active-upload counter."""
    clean = (
        phone.replace("@c.us", "")
        .replace("@s.whatsapp.net", "")
        .replace("@lid", "")
    )
    return f"{_ACTIVE_UPLOADS_PREFIX}{clean}"

# Platform chat file registry — Redis-backed so the chat router and the
# upload pipeline see the same staged-file metadata after a restart.
_FILE_REGISTRY_PREFIX = "chat:file:"
_FILE_REGISTRY_TTL_SECONDS = 4 * 60 * 60  # 4 hours — generous for slow uploads


def _compute_content_stats(text: str, rendered_as: str) -> dict[str, Any]:
    """Deterministic aggregates the LLM can quote without counting.

    Composes the seed ``noctusai_lib.integrations.google_drive.compute_content_stats``
    (generic line/char/CSV-shape counts, single-sourced) + appends the
    real-estate-specific ONE-code regex extraction (the user's
    domain — stays per-product per the seed module's own note that
    "the real-estate-specific 'ONE-code' regex stays a per-product
    concern").

    `rendered_as` accepts BOTH seed-canonical (``"text/csv"`` /
    ``"text/plain"``) and the absorbed product's legacy shorthand
    (``"csv"`` / ``"text"``) — translated via
    :func:`translate_rendered_as` so existing tool-description prose
    that says ``"csv"`` keeps working alongside the seed-canonical
    surface.
    """
    import re

    from noctusai_lib.integrations.google_drive import (
        compute_content_stats as _seed_compute_content_stats,
        translate_rendered_as,
    )

    if not text:
        return {"total_chars": 0, "total_lines": 0}

    # Translate to canonical so the seed helper's CSV branch matches
    # regardless of which vocabulary the caller passes.
    canonical = translate_rendered_as(rendered_as, to="canonical")
    base = dict(_seed_compute_content_stats(text, rendered_as=canonical))

    # Real-estate-specific: count ONE codes (the user's domain — kept
    # per-product per the seed `content_stats.py` docstring).
    code_pattern = re.compile(r"\bONE\d{3,6}\b")
    matches = code_pattern.findall(text)
    if matches:
        unique = sorted(set(matches))
        base["one_code_count"] = len(matches)
        base["unique_one_codes"] = len(unique)
        base["one_codes_sample"] = unique[:20]

    return base


def _chat_id_for_sender(phone: str) -> str:
    """Return a WAHA chatId for either a raw E.164 number or WAHA JID."""
    clean = phone.strip()
    if clean.endswith(("@c.us", "@s.whatsapp.net", "@lid")):
        return clean
    return f"{clean.lstrip('+')}@c.us"


class WhatsAppIntakeService:
    """Per-request collaborator for the WhatsApp webhook router.

    Manages conversation state via Redis and orchestrates the
    command → confirm → upload flow.
    """

    def __init__(
        self,
        *,
        waha_base_url: str,
        waha_api_key: str,
        waha_session: str,
        redis_client,
        authorized_numbers: list[str],
        crm_service: CRMService | None,
        admin_supabase,
        youtube_service,
        upload_dir,
        org_id: UUID,
        connection_id: UUID | None = None,
    ):
        self._waha_base_url = waha_base_url
        self._waha_api_key = waha_api_key
        self._waha_session = waha_session
        self._redis = redis_client
        self._authorized = set(self._normalize_numbers(authorized_numbers))
        self._crm = crm_service
        self._admin = admin_supabase
        self._youtube = youtube_service
        self._upload_dir = upload_dir
        self._org_id = org_id
        # Per-connection tag (migration 014). When set, outbound messages
        # persisted via _reply() are tagged with this connection_id so the
        # chat inbox can show the full conversation thread.
        self._connection_id = connection_id

    @staticmethod
    def _normalize_numbers(numbers: list[str]) -> list[str]:
        """Strip whitespace and ensure +prefix."""
        result = []
        for n in numbers:
            n = n.strip()
            if n:
                result.append(n)
        return result

    def is_authorized(self, phone: str) -> bool:
        """Check if the sender is in the whitelist.

        WAHA may identify the sender three different ways:
        - ``5511974693365@c.us`` — standard chat id, phone is the prefix.
        - ``5511974693365@s.whatsapp.net`` — alt suffix from some engines.
        - ``33613018058989@lid`` — WhatsApp's Linked Identifier; the LID
          is OPAQUE and does NOT contain the phone number. The same user
          on different chats can have different LIDs.

        Resolution order:
        1. Direct whitelist hit (raw LID form `<digits>@lid` listed in
           env wins for LID inbound).
        2. Strip JID suffixes → phone form, check whitelist with the
           `+` prefix.
        3. Look up the LID→phone cache (populated by send-text responses)
           and recheck the phone whitelist.
        """
        raw = (phone or "").strip()
        if not raw:
            return False
        # 1) LID literal whitelist (raw form: "33613018058989@lid")
        if raw.lower().endswith("@lid") and raw in self._authorized:
            return True
        # 2) Phone form
        clean = (
            raw
            .replace("@c.us", "")
            .replace("@s.whatsapp.net", "")
        )
        if "@lid" not in clean.lower():
            phone_candidate = clean if clean.startswith("+") else f"+{clean}"
            if phone_candidate in self._authorized:
                return True
        # 3) LID→phone cache lookup (opportunistic capture from outbound)
        if raw.lower().endswith("@lid"):
            cached_phone = self._lid_to_phone(raw)
            if cached_phone and cached_phone in self._authorized:
                return True
        return False

    # ─── LID ↔ phone cache (Redis-backed, populated by outbound sends) ─
    @staticmethod
    def _lid_phone_key(lid: str) -> str:
        return f"whatsapp:lid_to_phone:{lid}"

    def _lid_to_phone(self, lid: str) -> str | None:
        try:
            return self._redis.get(self._lid_phone_key(lid))
        except Exception:
            return None

    def remember_lid_for_phone(self, lid: str, phone: str) -> None:
        """Persist a (lid → phone) mapping captured from a WAHA send
        response, and migrate any memory accumulated under the LID
        key over to the phone key.

        The migration matters for Case B (user contacts FIRST, before
        the bot has ever sent anything): the first inbound + first
        outbound land in the LID-keyed memory because the cache is empty.
        The cache only fills on the FIRST successful outbound. After
        this method runs, the next inbound's canonical_session_id
        returns the phone form — and without migration the agent's
        recall starts empty. So we COPY the LID list onto the phone
        list (preserving timestamps + direction).

        30-day TTL on the lid→phone mapping — LIDs are stable across
        WhatsApp sessions but users can rotate them.
        """
        if not lid or not phone:
            return
        try:
            from app.services.chatbot_service import (
                MAX_MEMORY_ITEMS,
                MEMORY_TTL_SECONDS,
                memory_key_for,
            )
            already_cached = self._redis.get(self._lid_phone_key(lid))
            self._redis.set(self._lid_phone_key(lid), phone, ex=30 * 24 * 3600)
            if already_cached:
                # Mapping already known; don't re-migrate (would dup entries).
                return
            lid_memory_key = memory_key_for(lid)
            phone_memory_key = memory_key_for(phone)
            lid_entries = self._redis.lrange(lid_memory_key, 0, -1) or []
            if not lid_entries:
                return
            # rpush each entry onto the phone key, then dedup-trim. We
            # don't atomic-pipeline this — a transient inconsistency
            # would only show as duplicated memory items, not data loss.
            for entry in lid_entries:
                self._redis.rpush(phone_memory_key, entry)
            self._redis.ltrim(phone_memory_key, -MAX_MEMORY_ITEMS, -1)
            self._redis.expire(phone_memory_key, MEMORY_TTL_SECONDS)
        except Exception:
            logger.exception("failed to persist/migrate lid→phone cache for %s", lid)

    def canonical_session_id(self, raw_sender: str) -> str:
        """Return the canonical session id for a WAHA-side sender.

        WhatsApp now hides phone numbers behind opaque LIDs by default.
        WAHA sends ``from: 33613018058989@lid`` (the inbound side) and
        the bot's own send responses carry ``_data.id.remote: <same lid>``
        (the outbound side, with phone-form chat_id on the request).

        Without normalization, the SAME conversation would split into
        two memory keys: one keyed by phone (from the outbound) and one
        keyed by LID (from the inbound). The agent's recall breaks.

        Resolution:
        1. If ``raw_sender`` is already a phone form (digits or +digits),
           pass-through (with + prefix).
        2. If ``raw_sender`` is an LID and we have a cached phone mapping,
           return the phone form.
        3. If ``raw_sender`` is an LID with no cached phone, return the
           LID as-is — the agent's memory will start fresh for this
           conversation, but subsequent outbounds will populate the
           cache via ``remember_lid_for_phone``, and from the SECOND
           reply onwards both directions share the same key.
        """
        raw = (raw_sender or "").strip()
        if not raw:
            return raw
        if raw.lower().endswith("@lid"):
            phone = self._lid_to_phone(raw)
            if phone:
                return phone
            return raw
        clean = raw.replace("@c.us", "").replace("@s.whatsapp.net", "")
        if clean and not clean.startswith("+") and clean.isdigit():
            return f"+{clean}"
        return clean or raw

    def _redis_key(self, phone: str) -> str:
        clean = phone.replace("@c.us", "").replace("@s.whatsapp.net", "")
        return f"{_REDIS_KEY_PREFIX}{clean}"

    @property
    def redis_client(self):
        """Redis client shared with the chatbot memory layer."""
        return self._redis

    async def _get_state(self, phone: str) -> PendingUpload | None:
        """Load conversation state from Redis."""
        key = self._redis_key(phone)
        raw = self._redis.get(key)
        if not raw:
            return None
        try:
            return PendingUpload(**json.loads(raw))
        except Exception:
            logger.warning("corrupt conversation state for %s — resetting", phone)
            self._redis.delete(key)
            return None

    async def _set_state(self, phone: str, state: PendingUpload) -> None:
        """Save conversation state to Redis with TTL."""
        key = self._redis_key(phone)
        self._redis.set(key, state.model_dump_json(), ex=_REDIS_TTL_SECONDS)

    async def _clear_state(self, phone: str) -> None:
        """Remove conversation state from Redis."""
        self._redis.delete(self._redis_key(phone))

    async def lookup_property(self, product_code: str) -> dict[str, Any]:
        """Tool-safe CRM lookup used by the OpenAI chatbot layer."""
        code = (product_code or "").strip().upper()
        if not validate_product_code(code):
            return {"ok": False, "error": "invalid_product_code", "product_code": code}
        if not self._crm:
            return {"ok": False, "error": "crm_not_configured", "product_code": code}
        try:
            data = await self._crm.get_property(code)
        except CRMServiceError as exc:
            logger.warning("CRM lookup failed for %s: %s", code, exc)
            return {"ok": False, "error": "crm_lookup_failed", "message": str(exc), "product_code": code}
        if not data:
            return {"ok": False, "error": "property_not_found", "product_code": code}
        metadata = build_youtube_metadata(data, code)
        return {
            "ok": True,
            "product_code": code,
            "title": data.title,
            "address": data.address,
            "price": data.price,
            "bedrooms": data.bedrooms,
            "area_sqm": data.area_sqm,
            "youtube_title": metadata["title"],
            "description_preview": (data.description or "")[:500],
        }

    # ─── File registry (used by the platform chat surface) ─────────────
    @staticmethod
    def _file_registry_key(file_id: str) -> str:
        return f"{_FILE_REGISTRY_PREFIX}{file_id}"

    def register_uploaded_file(
        self,
        *,
        file_id: str,
        local_path: str,
        file_name: str,
        file_size_bytes: int,
    ) -> None:
        """Record a staged file the chatbot tool can later resolve.

        The file lives on disk (under ``upload_dir``) while we wait for
        the user to confirm; ``confirm_pending_upload`` resolves the
        file_id through this registry to find the path."""
        payload = json.dumps(
            {
                "local_path": local_path,
                "file_name": file_name,
                "file_size_bytes": file_size_bytes,
            }
        )
        self._redis.set(
            self._file_registry_key(file_id),
            payload,
            ex=_FILE_REGISTRY_TTL_SECONDS,
        )

    def get_uploaded_file(self, file_id: str) -> dict[str, Any] | None:
        raw = self._redis.get(self._file_registry_key(file_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def forget_uploaded_file(self, file_id: str) -> None:
        self._redis.delete(self._file_registry_key(file_id))

    async def prepare_upload_request(
        self,
        phone: str,
        *,
        product_code: str,
        drive_url: str,
        manual_title: str | None = None,
        privacy_status: str = "private",
    ) -> dict[str, Any]:
        """Validate and persist a pending upload without sending a reply.

        This is the side-effect boundary for the chatbot's
        `prepare_upload_request` tool. It does not queue YouTube work; it
        only stores a confirmation-ready pending state.
        """
        code = (product_code or "").strip().upper()
        url = (drive_url or "").strip()
        if not validate_product_code(code):
            return {"ok": False, "error": "invalid_product_code", "product_code": code}
        if not re.match(r"https?://(?:drive\.google\.com|docs\.google\.com)\S+", url, re.IGNORECASE):
            return {"ok": False, "error": "invalid_drive_url", "drive_url": url[:120]}
        if privacy_status not in {"private", "unlisted", "public"}:
            privacy_status = "private"

        crm_title = None
        crm_description = None
        crm_data: PropertyData | None = None
        if self._crm:
            try:
                crm_data = await self._crm.get_property(code)
            except CRMServiceError as exc:
                logger.warning("CRM lookup failed for %s: %s", code, exc)
        if crm_data:
            crm_title = crm_data.title
            crm_description = crm_data.description
        elif manual_title:
            crm_title = manual_title.strip()[:100]

        next_state = "awaiting_confirmation" if crm_title else "awaiting_manual_title"
        pending = PendingUpload(
            product_code=code,
            drive_url=url,
            crm_title=crm_title,
            crm_description=crm_description,
            privacy_status=privacy_status,
            state=next_state,
        )
        await self._set_state(phone, pending)

        result: dict[str, Any] = {
            "ok": True,
            "state": pending.state,
            "product_code": code,
            "drive_url": url,
            "privacy_status": privacy_status,
            "has_crm_data": crm_data is not None,
            "title": crm_title,
        }
        if crm_data:
            meta = build_youtube_metadata(crm_data, code)
            result.update({
                "address": crm_data.address,
                "price": crm_data.price,
                "youtube_title": meta["title"],
                "description_preview": (crm_data.description or "")[:500],
            })
        elif not crm_title:
            result["warning"] = "crm_missing_and_no_manual_title"
        return result

    async def prepare_upload_from_file_request(
        self,
        phone: str,
        *,
        product_code: str,
        file_id: str,
        manual_title: str | None = None,
        privacy_status: str = "private",
    ) -> dict[str, Any]:
        """Validate and persist a pending upload that points to a
        pre-staged local file.

        ``file_id`` is issued by the chat router after streaming the
        multipart body to disk; this method resolves it against the
        Redis file registry and records the resolved file metadata on
        the pending state so ``confirm_pending_upload`` can dispatch
        the browser-file path without a second lookup.
        """
        code = (product_code or "").strip().upper()
        fid = (file_id or "").strip()
        if not validate_product_code(code):
            return {"ok": False, "error": "invalid_product_code", "product_code": code}
        if not fid:
            return {"ok": False, "error": "missing_file_id"}
        file_info = self.get_uploaded_file(fid)
        if not file_info:
            return {"ok": False, "error": "file_not_found", "file_id": fid}
        if privacy_status not in {"private", "unlisted", "public"}:
            privacy_status = "private"

        crm_title = None
        crm_description = None
        crm_data: PropertyData | None = None
        if self._crm:
            try:
                crm_data = await self._crm.get_property(code)
            except CRMServiceError as exc:
                logger.warning("CRM lookup failed for %s: %s", code, exc)
        if crm_data:
            crm_title = crm_data.title
            crm_description = crm_data.description
        elif manual_title:
            crm_title = manual_title.strip()[:100]

        next_state = "awaiting_confirmation" if crm_title else "awaiting_manual_title"
        pending = PendingUpload(
            product_code=code,
            file_id=fid,
            video_filename=file_info.get("file_name"),
            video_size_bytes=file_info.get("file_size_bytes"),
            crm_title=crm_title,
            crm_description=crm_description,
            privacy_status=privacy_status,
            state=next_state,
        )
        await self._set_state(phone, pending)

        result: dict[str, Any] = {
            "ok": True,
            "state": pending.state,
            "product_code": code,
            "file_id": fid,
            "file_name": file_info.get("file_name"),
            "file_size_bytes": file_info.get("file_size_bytes"),
            "privacy_status": privacy_status,
            "has_crm_data": crm_data is not None,
            "title": crm_title,
        }
        if crm_data:
            meta = build_youtube_metadata(crm_data, code)
            result.update(
                {
                    "address": crm_data.address,
                    "price": crm_data.price,
                    "youtube_title": meta["title"],
                    "description_preview": (crm_data.description or "")[:500],
                }
            )
        elif not crm_title:
            result["warning"] = "crm_missing_and_no_manual_title"
        return result

    async def get_pending_upload(self, phone: str) -> dict[str, Any]:
        pending = await self._get_state(phone)
        if not pending:
            return {"found": False}
        return {
            "found": True,
            "state": pending.state,
            "product_code": pending.product_code,
            "drive_url": pending.drive_url,
            "file_id": pending.file_id,
            "video_filename": pending.video_filename,
            "video_size_bytes": pending.video_size_bytes,
            "title": pending.crm_title,
            "privacy_status": pending.privacy_status,
        }

    async def cancel_pending_upload(self, phone: str) -> dict[str, Any]:
        """Cancel the conversation's pending upload + clean up downloads.

        Called by the LLM ``cancel_upload`` tool when the user expresses
        a cancel intent in natural language ("deixa pra lá", "para",
        "cancela isso aí"). The regex state-machine has a parallel
        cancel path via the ``cancelar`` keyword in
        ``_handle_video_choice`` / ``_handle_confirmation`` — both paths
        converge here to ensure local cleanup happens regardless of
        which intent surface fired.
        """
        from pathlib import Path as _Path

        pending = await self._get_state(phone)
        if not pending:
            return {"ok": False, "error": "no_pending_upload"}

        # Cleanup any pre-downloaded files the cancel orphans. Three
        # sources to walk: the chosen file (local_video_path) and the
        # full candidate list (when state == awaiting_video_choice and
        # the user changed their mind mid-menu).
        cleaned: list[str] = []
        if pending.local_video_path:
            try:
                gdrive_service.cleanup(_Path(pending.local_video_path))
                cleaned.append(pending.local_video_filename or pending.local_video_path)
            except Exception:
                logger.exception(
                    "cancel cleanup failed for local_video_path %s",
                    pending.local_video_path,
                )
        for cand in pending.candidate_videos:
            try:
                gdrive_service.cleanup(_Path(cand.local_path))
                cleaned.append(cand.file_name)
            except Exception:
                logger.exception(
                    "cancel cleanup failed for candidate %s", cand.local_path
                )

        await self._clear_state(phone)
        return {
            "ok": True,
            "cancelled": True,
            "product_code": pending.product_code,
            "files_cleaned": cleaned,
        }

    async def confirm_pending_upload(self, phone: str) -> dict[str, Any]:
        pending = await self._get_state(phone)
        if not pending:
            return {"ok": False, "error": "no_pending_upload"}
        if pending.state not in {"awaiting_confirmation", "awaiting_manual_title"}:
            return {"ok": False, "error": "invalid_state", "state": pending.state}
        if pending.state == "awaiting_manual_title" and not pending.crm_title:
            return {"ok": False, "error": "missing_manual_title"}
        if self._youtube is None:
            return {"ok": False, "error": "youtube_not_connected"}

        pending.state = "processing"
        await self._set_state(phone, pending)
        asyncio.create_task(self._run_upload(phone, pending))
        return {
            "ok": True,
            "queued": True,
            "product_code": pending.product_code,
            "title": pending.crm_title or f"Imóvel {pending.product_code}",
        }

    async def _reply(self, phone: str, text: str) -> None:
        """Send a WhatsApp text reply.

        Mirrors whatsapp-scheduling: every successful WAHA send appends
        an ``outbound`` entry to the conversation memory so the agent's
        recall reflects what it just said — not just what the user said.
        Send failures are NOT recorded (the message never reached the
        user, so the agent shouldn't claim it did).
        """
        client = get_whatsapp_client(
            base_url=self._waha_base_url,
            api_key=self._waha_api_key,
            session=self._waha_session,
        )
        chat_id = _chat_id_for_sender(phone)
        try:
            result = await client.send_text(chat_id, text)
            # Memory key must match the chatbot loop's key for recall to
            # work. The chatbot uses canonical_session_id(phone) so we
            # do the same here — keeps inbound + outbound on the SAME
            # conversation key regardless of which form (LID or phone)
            # the caller passed in.
            canonical = self.canonical_session_id(phone)
            _append_chat_memory(
                self._redis,
                session_id=canonical,
                direction="outbound",
                text=text,
            )
            # Durable persistence — best-effort, never blocks delivery.
            try:
                store = MessageStore(
                    admin_supabase=self._admin,
                    org_id=self._org_id,
                )
                outbound_message_id = (
                    extract_waha_message_id(result) if isinstance(result, dict) else None
                )
                store.record(
                    session_id=canonical,
                    raw_sender=phone,
                    direction="outbound",
                    body=text,
                    provider_message_id=outbound_message_id,
                    authorized=True,
                    connection_id=self._connection_id,
                )
            except DuplicateMessage:
                # Outbound dedup: shouldn't normally happen, but if WAHA
                # echoes the message_id of a prior send, drop silently.
                pass
            except Exception:
                logger.exception("conversation_messages outbound insert failed")
            # Opportunistic LID capture — `_data.id.remote` on the
            # send-text response is the recipient's LID. Only cache the
            # mapping when our `phone` arg is ACTUALLY a phone form
            # (digits + optional + prefix). When the webhook hands us
            # the sender's LID as `phone`, we have NO real phone to
            # cache — caching the LID-as-phone would corrupt the
            # `lid_to_phone` cache (a bug Codex shipped in v1 of this
            # method and the user surfaced in production: after one
            # round-trip the next inbound failed auth because the cache
            # value was the LID itself, not the authorized phone).
            captured_lid: str | None = None
            if isinstance(result, dict):
                data = result.get("_data") or {}
                id_obj = data.get("id") if isinstance(data, dict) else None
                if isinstance(id_obj, dict):
                    captured_lid = id_obj.get("remote")
            if captured_lid and captured_lid.lower().endswith("@lid"):
                phone_clean = (
                    phone.replace("@c.us", "").replace("@s.whatsapp.net", "")
                )
                looks_like_phone = (
                    "@lid" not in phone_clean.lower()
                    and bool(phone_clean.lstrip("+"))
                    and phone_clean.lstrip("+").isdigit()
                )
                if looks_like_phone:
                    if not phone_clean.startswith("+"):
                        phone_clean = f"+{phone_clean}"
                    self.remember_lid_for_phone(captured_lid, phone_clean)
                # Mirror outbound to the LID-keyed memory regardless of
                # whether we knew the phone — keeps recall coherent for
                # inbounds that arrive via the LID before the cache is
                # populated.
                _append_chat_memory(
                    self._redis,
                    session_id=captured_lid,
                    direction="outbound",
                    text=text,
                )
            record_waha_sample(
                source="POST /api/sendText",
                direction="app_to_waha_response",
                http_status=201,
                payload=result,
                handling_notes=(
                    "Treat any 2xx sendText response as success. Extract message id "
                    "best-effort from id, key.id, _data.id, or message.id; never "
                    "require one exact envelope."
                ),
            )
        except httpx.HTTPStatusError as exc:
            error_payload: Any = None
            try:
                error_payload = exc.response.json()
            except Exception:
                error_payload = {"text": exc.response.text[:1000]}
            record_waha_sample(
                source="POST /api/sendText",
                direction="app_to_waha_response",
                http_status=exc.response.status_code,
                payload=error_payload,
                handling_notes=(
                    "Treat non-2xx sendText responses as delivery failure. Log and "
                    "continue webhook handling so WAHA does not retry the inbound "
                    "message forever."
                ),
            )
            logger.exception("failed to send WhatsApp reply to %s", phone)
        except Exception:
            logger.exception("failed to send WhatsApp reply to %s", phone)

    async def send_reply(self, phone: str, text: str) -> None:
        """Public reply boundary for GPT-driven orchestration."""
        await self._reply(phone, text)

    async def handle_message(self, phone: str, body: str) -> None:
        """Main entry point — route inbound message through state machine."""
        current = await self._get_state(phone)
        state = current.state if current else "idle"

        if state == "processing":
            # Pluralize when multiple uploads are in flight on the same
            # phone (the "todos" flow can spawn N parallel jobs). Read
            # the active-counter from Redis; treat any error as 1.
            try:
                raw = self._redis.get(_active_uploads_key(phone))
                count = int(raw) if raw else 1
            except Exception:
                count = 1
            if count > 1:
                msg = (
                    f"⏳ {count} uploads em andamento. "
                    "Aguarde a conclusão antes de enviar outro comando."
                )
            else:
                msg = "⏳ Um upload já está em andamento. Aguarde a conclusão."
            await self._reply(phone, msg)
            return

        if state == "awaiting_confirmation":
            await self._handle_confirmation(phone, body, current)
            return

        if state == "awaiting_manual_title":
            await self._handle_manual_title(phone, body, current)
            return

        if state == "awaiting_video_choice":
            await self._handle_video_choice(phone, body, current)
            return

        # IDLE — expect a new command
        await self._handle_new_command(phone, body)

    async def _handle_new_command(self, phone: str, body: str) -> None:
        """Parse a new upload command from the message body."""
        code_match = _PRODUCT_CODE_RE.search(body)
        url_match = _DRIVE_URL_RE.search(body)
        if not (code_match and url_match):
            if code_match and not url_match:
                await self._reply(
                    phone,
                    "❌ Não encontrei um link do Google Drive na mensagem.\n\n"
                    "Envie no formato:\n"
                    "ONE0000 https://drive.google.com/..."
                )
                return
            if url_match and not code_match:
                await self._reply(
                    phone,
                    "❌ Código do imóvel não encontrado.\n\n"
                    "Envie no formato:\n"
                    "ONE0000 https://drive.google.com/..."
                )
                return
            # Totally unrelated message — ignore silently
            return

        product_code = code_match.group(0).upper()
        drive_url = url_match.group(0)

        if not validate_product_code(product_code):
            await self._reply(
                phone,
                f"❌ Código inválido: {product_code}\n"
                "Use o formato ONExxxx (ex: ONE5555)"
            )
            return

        # Acknowledge receipt
        await self._reply(
            phone,
            f"📋 Recebi o pedido de upload:\n"
            f"🏠 Código: {product_code}\n"
            f"📁 Link: {drive_url[:80]}{'...' if len(drive_url) > 80 else ''}\n\n"
            f"Buscando dados do imóvel no CRM...\n"
            f"⏳ Aguarde."
        )

        # Fetch CRM data (best-effort)
        crm_title = None
        crm_description = None
        crm_data: PropertyData | None = None

        if self._crm:
            try:
                crm_data = await self._crm.get_property(product_code)
                if crm_data:
                    crm_title = crm_data.title
                    crm_description = crm_data.description
            except CRMServiceError as exc:
                logger.warning("CRM lookup failed for %s: %s", product_code, exc)

        # Auto-confirmation toggle (settings.youtube_auto_confirmation_message)
        # ------------------------------------------------------------------
        # True (default) → show the "Confirma upload? (sim/não)" prompt and
        #   wait for the user's reply before queueing the upload.
        # False → on a CRM hit, skip the prompt and queue the upload
        #   immediately. We send a short "🚀 Iniciando…" instead so the
        #   operator sees the bot acknowledged + acted.
        # The CRM-MISS branch always takes the prompt path even when
        # auto-confirm is off, because we genuinely need the user's title
        # to proceed — there's nothing to auto-confirm.
        auto_proceed = not settings.youtube_auto_confirmation_message

        if crm_data and auto_proceed:
            # Skip awaiting_confirmation; go straight to processing.
            pending = PendingUpload(
                product_code=product_code,
                drive_url=drive_url,
                crm_title=crm_title,
                crm_description=crm_description,
                state="processing",
            )
            await self._set_state(phone, pending)
            yt_meta = build_youtube_metadata(crm_data, product_code)
            await self._reply(
                phone,
                f"🚀 Iniciando upload — {product_code} ({yt_meta['title']}).\n"
                f"Auto-confirmação ATIVADA. Te aviso ao concluir."
            )
            asyncio.create_task(self._run_upload(phone, pending))
            return

        # Build pending state — confirmation path (default).
        pending = PendingUpload(
            product_code=product_code,
            drive_url=drive_url,
            crm_title=crm_title,
            crm_description=crm_description,
            state="awaiting_confirmation",
        )
        await self._set_state(phone, pending)

        # Build confirmation message
        if crm_data:
            yt_meta = build_youtube_metadata(crm_data, product_code)
            confirm_msg = (
                f"✅ Dados encontrados:\n"
                f"🏠 {product_code} — {crm_data.title}\n"
            )
            if crm_data.address:
                confirm_msg += f"📍 {crm_data.address}\n"
            if crm_data.price:
                confirm_msg += f"💰 {crm_data.price}\n"
            desc_preview = (crm_data.description or "")[:200]
            if desc_preview:
                confirm_msg += f"📝 {desc_preview}{'...' if len(crm_data.description or '') > 200 else ''}\n"
            confirm_msg += f"🔒 Privacidade: Privado\n"
            confirm_msg += (
                f"\n📺 Título no YouTube: {yt_meta['title']}\n\n"
                f"Confirma o upload? Responda *SIM* para prosseguir ou *NÃO* para cancelar."
            )
        else:
            confirm_msg = (
                f"⚠️ Não consegui buscar os dados de {product_code} no CRM.\n\n"
                f"Deseja prosseguir com título manual?\n"
                f"Envie o título desejado ou *CANCELAR*."
            )
            pending.state = "awaiting_manual_title"
            await self._set_state(phone, pending)

        await self._reply(phone, confirm_msg)

    async def _handle_confirmation(
        self, phone: str, body: str, pending: PendingUpload
    ) -> None:
        """Handle sim/não response."""
        normalized = body.strip().lower()

        if normalized in _NO_RESPONSES:
            await self._clear_state(phone)
            await self._reply(phone, "❎ Upload cancelado.")
            return

        if normalized not in _YES_RESPONSES:
            await self._reply(
                phone,
                "Responda *SIM* para confirmar ou *NÃO* para cancelar."
            )
            return

        # User confirmed — queue the upload
        pending.state = "processing"
        await self._set_state(phone, pending)

        await self._reply(
            phone,
            "🚀 Upload iniciado! Você será notificado quando estiver pronto."
        )

        # Queue the upload job in background
        asyncio.create_task(
            self._run_upload(phone, pending)
        )

    async def _handle_manual_title(
        self, phone: str, body: str, pending: PendingUpload
    ) -> None:
        """Handle manual title input when CRM lookup failed."""
        normalized = body.strip().lower()

        if normalized in _NO_RESPONSES:
            await self._clear_state(phone)
            await self._reply(phone, "❎ Upload cancelado.")
            return

        # Use the message body as the title
        manual_title = body.strip()[:100]
        if len(manual_title) < 3:
            await self._reply(
                phone,
                "O título precisa ter pelo menos 3 caracteres.\n"
                "Envie o título ou *CANCELAR*."
            )
            return

        pending.crm_title = manual_title
        pending.state = "awaiting_confirmation"
        await self._set_state(phone, pending)

        await self._reply(
            phone,
            f"📺 Título: {manual_title}\n"
            f"🏠 Código: {pending.product_code}\n"
            f"🔒 Privacidade: Privado\n\n"
            f"Confirma o upload? Responda *SIM* para prosseguir ou *NÃO* para cancelar."
        )

    async def _handle_video_choice(
        self, phone: str, body: str, pending: PendingUpload
    ) -> None:
        """Resolve which candidate video the user picked from the menu.

        Expected reply: a 1-based index (``"1"``, ``"2"``, ...) matching
        ``pending.candidate_videos``. Also handles ``cancelar`` to abort.
        Any other input → repeat the menu prompt with a hint.

        On a valid pick:
          - unchosen candidates are deleted from disk (saves /tmp space).
          - ``pending.local_video_path`` is set to the chosen file.
          - state → ``processing``.
          - ``_run_upload`` is re-spawned and skips the candidate scan
            because ``local_video_path`` is already set.
        """
        from pathlib import Path as _Path
        from app.services import gdrive_service

        normalized = body.strip().lower()
        if normalized in _NO_RESPONSES:
            # Clean up every downloaded candidate before clearing state.
            for cand in pending.candidate_videos:
                try:
                    gdrive_service.cleanup(_Path(cand.local_path))
                except Exception:
                    logger.exception(
                        "cleanup failed for candidate %s", cand.local_path
                    )
            await self._clear_state(phone)
            await self._reply(phone, "❎ Upload cancelado. Arquivos descartados.")
            return

        # "todos" / "all" — spawn one upload per candidate, with
        # auto-disambiguated " · Parte N/M" titles. Each job goes through
        # the global queue independently; the bot delivers per-job
        # progress + completion pings.
        if normalized in {"todos", "all", "a", "todas"}:
            candidates = list(pending.candidate_videos)
            n = len(candidates)
            await self._reply(
                phone,
                f"🚀 Subindo *TODOS* os {n} vídeos como uploads separados.\n"
                f"Cada um vai pra fila; você recebe o progresso de cada um.",
            )
            pending.state = "processing"
            pending.candidate_videos = []
            await self._set_state(phone, pending)

            base_title = pending.crm_title or f"Imóvel {pending.product_code}"
            for idx, cand in enumerate(candidates, start=1):
                sub_pending = pending.model_copy(deep=True)
                sub_pending.local_video_path = cand.local_path
                sub_pending.local_video_filename = cand.file_name
                sub_pending.local_video_size_bytes = cand.file_size_bytes
                sub_pending.video_format = cand.format
                sub_pending.crm_title = f"{base_title} · Parte {idx}/{n}"
                sub_pending.candidate_videos = []
                sub_pending.state = "processing"
                asyncio.create_task(self._run_upload(phone, sub_pending))
            return

        # Parse a 1-based index.
        try:
            idx = int(normalized) - 1
        except ValueError:
            await self._reply(
                phone,
                "Responda com o número do vídeo (ex: *1*), *TODOS* ou *CANCELAR*."
            )
            return

        if not (0 <= idx < len(pending.candidate_videos)):
            await self._reply(
                phone,
                f"Opção inválida — responda entre *1* e *{len(pending.candidate_videos)}*, "
                "ou *CANCELAR*."
            )
            return

        chosen = pending.candidate_videos[idx]

        # Delete the unchosen candidates from disk.
        for i, cand in enumerate(pending.candidate_videos):
            if i == idx:
                continue
            try:
                gdrive_service.cleanup(_Path(cand.local_path))
            except Exception:
                logger.exception(
                    "cleanup failed for unchosen candidate %s", cand.local_path
                )

        pending.local_video_path = chosen.local_path
        pending.local_video_filename = chosen.file_name
        pending.local_video_size_bytes = chosen.file_size_bytes
        pending.video_format = chosen.format
        pending.candidate_videos = []
        pending.state = "processing"
        await self._set_state(phone, pending)

        await self._reply(
            phone,
            f"✅ Selecionado: *{chosen.file_name}* ({_format_size(chosen.file_size_bytes)})\n"
            f"🚀 Iniciando upload…"
        )

        asyncio.create_task(self._run_upload(phone, pending))

    # ─── Google Calendar tool handlers ─────────────────────────────────
    async def schedule_calendar_event(
        self,
        *,
        summary: str,
        start_at_iso: str,
        end_at_iso: str,
        description: str | None = None,
        location: str | None = None,
        attendee_emails: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a Google Calendar event.

        Wraps the calendar adapter factory + the EventInput shape. Runs
        the blocking google-api-client call inside ``asyncio.to_thread``
        so the event loop stays responsive. Failure modes return a
        structured ``{"ok": False, "error": ...}`` payload — the chatbot
        loop relays them as user-facing prose.
        """
        from datetime import datetime
        from app.services.calendar import (
            EventAttendee,
            EventInput,
            get_calendar_adapter,
        )
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)

        if not summary or not start_at_iso or not end_at_iso:
            return {
                "ok": False,
                "error": "missing_required_field",
                "detail": "summary, start_at, end_at sao obrigatorios",
            }
        try:
            start_at = datetime.fromisoformat(start_at_iso)
            end_at = datetime.fromisoformat(end_at_iso)
        except ValueError as exc:
            return {"ok": False, "error": "invalid_datetime", "detail": str(exc)}

        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_calendar_adapter(org_id=self._org_id, credential_store=store)

        attendees = [EventAttendee(email=e) for e in attendee_emails or [] if e]
        # Service-account adapter can't add attendees; drop them
        # gracefully rather than failing the whole call.
        if attendees and not adapter.supports_attendees:
            logger.warning(
                "schedule_calendar_event: attendees dropped — adapter %s does not support them",
                type(adapter).__name__,
            )
            attendees = []

        event = EventInput(
            summary=summary[:1000],
            start_at=start_at,
            end_at=end_at,
            timezone=settings.google_calendar_default_timezone,
            description=description,
            location=location,
            attendees=attendees,
        )
        try:
            created = await asyncio.to_thread(
                adapter.create_event,
                settings.google_calendar_default_id,
                event,
            )
        except Exception as exc:
            logger.exception("calendar create_event failed")
            return {"ok": False, "error": "calendar_api_error", "detail": str(exc)[:300]}
        return {
            "ok": True,
            "event_id": created.event_id,
            "html_link": created.html_link,
            "summary": event.summary,
            "start_at": start_at_iso,
            "end_at": end_at_iso,
            "calendar_id": settings.google_calendar_default_id,
            "adapter": type(adapter).__name__,
        }

    async def list_calendar_events(
        self,
        *,
        time_min_iso: str | None = None,
        time_max_iso: str | None = None,
    ) -> dict[str, Any]:
        """List upcoming events between two ISO timestamps.

        Defaults: time_min = now, time_max = now + 7 days.
        """
        from datetime import datetime, timedelta, timezone
        from app.services.calendar import get_calendar_adapter
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)

        now = datetime.now(timezone.utc)
        try:
            time_min = datetime.fromisoformat(time_min_iso) if time_min_iso else now
        except ValueError:
            time_min = now
        try:
            time_max = (
                datetime.fromisoformat(time_max_iso)
                if time_max_iso
                else now + timedelta(days=7)
            )
        except ValueError:
            time_max = now + timedelta(days=7)

        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_calendar_adapter(org_id=self._org_id, credential_store=store)

        try:
            items = await asyncio.to_thread(
                adapter.list_events,
                settings.google_calendar_default_id,
                time_min,
                time_max,
            )
        except Exception as exc:
            logger.exception("calendar list_events failed")
            return {"ok": False, "error": "calendar_api_error", "detail": str(exc)[:300]}

        return {
            "ok": True,
            "count": len(items),
            "events": [
                {
                    "event_id": e.event_id,
                    "summary": e.raw.get("summary"),
                    "start": e.raw.get("start", {}).get("dateTime"),
                    "end": e.raw.get("end", {}).get("dateTime"),
                    "location": e.raw.get("location"),
                    "html_link": e.html_link,
                }
                for e in items
            ],
            "calendar_id": settings.google_calendar_default_id,
            "adapter": type(adapter).__name__,
        }

    # ─── Google Maps tool handler ──────────────────────────────────────
    async def travel_estimate(
        self,
        *,
        origin: str,
        destination: str,
    ) -> dict[str, Any]:
        """Estimate driving time between two addresses.

        Geocodes both addresses via Google Geocoding API (same Maps key)
        then calls Routes v2. Returns minutes + distance. When the
        Maps key isn't configured, falls back to a static estimate.
        """
        from app.services.routing import (
            Coordinates,
            GoogleMapsRoutingAdapter,
            StaticRoutingAdapter,
            get_routing_adapter,
        )

        if not origin or not destination:
            return {
                "ok": False,
                "error": "missing_required_field",
                "detail": "origin e destination sao obrigatorios",
            }
        adapter = get_routing_adapter()
        # Geocode if we have a real Maps adapter; otherwise use sentinel
        # coords (the static adapter ignores them anyway).
        try:
            origin_coords, origin_address = await self._geocode(origin) if isinstance(
                adapter, GoogleMapsRoutingAdapter
            ) else (Coordinates(0.0, 0.0), origin)
            dest_coords, dest_address = await self._geocode(destination) if isinstance(
                adapter, GoogleMapsRoutingAdapter
            ) else (Coordinates(0.0, 0.0), destination)
        except Exception as exc:
            logger.exception("geocoding failed")
            return {"ok": False, "error": "geocoding_failed", "detail": str(exc)[:300]}

        try:
            estimate = await asyncio.to_thread(
                adapter.travel_estimate, origin_coords, dest_coords
            )
        except Exception as exc:
            logger.exception("routes api failed")
            return {"ok": False, "error": "routes_api_error", "detail": str(exc)[:300]}

        return {
            "ok": True,
            "minutes": estimate.minutes,
            "distance_meters": estimate.distance_meters,
            "origin": origin_address,
            "destination": dest_address,
            "adapter": type(adapter).__name__,
            "fallback": isinstance(adapter, StaticRoutingAdapter),
        }

    async def _geocode(self, address: str) -> tuple["Coordinates", str]:
        """Resolve a free-form address to lat/lng + formatted address
        via Google Geocoding API. Uses the same Maps key as Routes."""
        from app.services.routing import Coordinates

        url = "https://maps.googleapis.com/maps/api/geocode/json"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                url,
                params={
                    "address": address,
                    "key": settings.google_maps_api_key,
                    "language": "pt-BR",
                    "region": "br",
                },
            )
            response.raise_for_status()
            data = response.json()
        results = data.get("results") or []
        if not results:
            raise RuntimeError(f"address not found: {address!r}")
        first = results[0]
        loc = first.get("geometry", {}).get("location", {})
        return (
            Coordinates(latitude=loc.get("lat"), longitude=loc.get("lng")),
            first.get("formatted_address") or address,
        )

    # ─── Google Drive search / list / get ─────────────────────────────
    async def search_drive_files(
        self,
        *,
        query: str,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Search the user's Drive by name/fullText. Returns the top N
        matches with metadata the chatbot can show inline."""
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)
        from app.services.drive_api import get_drive_adapter, is_oauth_backed

        if not query:
            return {"ok": False, "error": "missing_query"}
        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_drive_adapter(org_id=self._org_id, credential_store=store)
        try:
            # Seed `DriveReader` Protocol is async-native; call directly
            # (the sync facade still works but `await` from this `async
            # def` consumer skips the worker-thread hop).
            result = await adapter.reader.search(
                query,
                mime_type=mime_type,
                folder_id=folder_id,
                page_size=page_size,
            )
        except Exception as exc:
            logger.exception("drive search failed")
            return {"ok": False, "error": "drive_api_error", "detail": str(exc)[:300]}

        return {
            "ok": True,
            "count": len(result.files),
            "query": query,
            "adapter": type(adapter.reader).__name__,
            "files": [
                {
                    "file_id": f.file_id,
                    "name": f.name,
                    "mime_type": f.mime_type,
                    "is_folder": f.is_folder,
                    "size_bytes": f.size_bytes,
                    "modified_at": f.modified_at.isoformat() if f.modified_at else None,
                    "web_view_link": f.web_view_link,
                    "owners": f.owners,
                }
                for f in result.files
            ],
            "scope_note": (
                "OAuth adapter — busca o Drive inteiro do usuario consentido."
                if is_oauth_backed(adapter)
                else (
                    "Service-account adapter — so encontra arquivos "
                    "explicitamente compartilhados com a conta de servico."
                )
            ),
        }

    async def list_recent_drive_files(self, *, page_size: int = 10) -> dict[str, Any]:
        """List the most recently modified files."""
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)
        from app.services.drive_api import get_drive_adapter, is_oauth_backed

        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_drive_adapter(org_id=self._org_id, credential_store=store)
        try:
            result = await adapter.reader.list_recent(page_size=page_size)
        except Exception as exc:
            logger.exception("drive list_recent failed")
            return {"ok": False, "error": "drive_api_error", "detail": str(exc)[:300]}
        return {
            "ok": True,
            "count": len(result.files),
            "adapter": type(adapter.reader).__name__,
            "files": [
                {
                    "file_id": f.file_id,
                    "name": f.name,
                    "mime_type": f.mime_type,
                    "is_folder": f.is_folder,
                    "size_bytes": f.size_bytes,
                    "modified_at": f.modified_at.isoformat() if f.modified_at else None,
                    "web_view_link": f.web_view_link,
                    "owners": f.owners,
                }
                for f in result.files
            ],
            "scope_note": (
                "OAuth adapter — Drive inteiro."
                if is_oauth_backed(adapter)
                else "Service-account adapter — apenas itens compartilhados."
            ),
        }

    async def query_drive_sheet(
        self,
        *,
        file_id: str,
        group_by_column: str | None = None,
        filter_column: str | None = None,
        filter_equals: str | None = None,
        max_unique_values: int = 30,
    ) -> dict[str, Any]:
        """Deterministic column-aware aggregations over a Drive sheet.

        Reads the file as CSV (Google Sheets exported, raw CSV
        downloaded), parses with csv.DictReader, and computes:

        - column_names + row_count
        - When ``group_by_column`` is set: value counts for that column
          (top N up to ``max_unique_values`` distinct values).
        - When ``filter_column + filter_equals`` are set: row count
          where that column matches.
        - Cross-tab: when both ``group_by`` and ``filter`` are set,
          group counts apply ONLY to filtered rows.

        Built because the LLM fabricates column counts when forced to
        read raw CSV. Python does the counting; the bot just relays.
        """
        import csv as _csv
        import io
        from collections import Counter
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)
        from app.services.drive_api import get_drive_adapter
        from noctusai_lib.integrations.google_drive import translate_rendered_as

        if not file_id:
            return {"ok": False, "error": "missing_file_id"}
        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_drive_adapter(org_id=self._org_id, credential_store=store)
        try:
            content = await adapter.reader.read_file(file_id)
        except Exception as exc:
            logger.exception("drive read_content failed in query_drive_sheet")
            return {"ok": False, "error": "drive_api_error", "detail": str(exc)[:300]}
        if content is None:
            return {"ok": False, "error": "not_found", "file_id": file_id}
        # Accept both seed-canonical and legacy rendered_as shorthand.
        if translate_rendered_as(content.rendered_as, to="legacy") not in {"csv", "text"}:
            return {
                "ok": False,
                "error": "not_a_sheet",
                "mime_type": content.mime_type,
                "detail": "query_drive_sheet only works on CSV/Sheets. Use read_drive_file for other types.",
            }

        try:
            reader = _csv.DictReader(io.StringIO(content.text))
            columns = list(reader.fieldnames or [])
            rows = list(reader)
        except Exception as exc:
            return {"ok": False, "error": "csv_parse_failed", "detail": str(exc)[:300]}

        result: dict[str, Any] = {
            "ok": True,
            "file_id": file_id,
            "name": content.name,
            "columns": columns,
            "total_rows": len(rows),
            "non_empty_rows": sum(
                1 for r in rows if any((v or "").strip() for v in r.values())
            ),
        }

        # Validate column names if requested
        for name in (group_by_column, filter_column):
            if name and name not in columns:
                result["warning"] = result.get("warning", "")
                result["warning"] += (
                    f" column {name!r} not found; available: {columns}."
                )

        # Apply filter
        scope_rows = rows
        if filter_column and filter_column in columns:
            needle = (filter_equals or "").strip()
            scope_rows = [
                r
                for r in rows
                if (r.get(filter_column) or "").strip() == needle
            ]
            result["filter"] = {
                "column": filter_column,
                "equals": needle,
                "matched_rows": len(scope_rows),
            }

        # Group by
        if group_by_column and group_by_column in columns:
            counter = Counter(
                (r.get(group_by_column) or "").strip() for r in scope_rows
            )
            most_common = counter.most_common(max_unique_values)
            result["group_by"] = {
                "column": group_by_column,
                "unique_values": len(counter),
                "value_counts": [{"value": v, "count": c} for v, c in most_common],
                "total_counted": sum(counter.values()),
            }

        return result

    async def read_drive_file(
        self,
        *,
        file_id: str,
        max_bytes: int = 200_000,
    ) -> dict[str, Any]:
        """Read the actual content of a Drive file. Returns rendered
        text (CSV for Sheets, plain for Docs, extracted for PDFs) plus
        a `rendered_as` field so the chatbot knows what shape to
        reason about."""
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)
        from app.services.drive_api import get_drive_adapter
        from noctusai_lib.integrations.google_drive import translate_rendered_as

        if not file_id:
            return {"ok": False, "error": "missing_file_id"}
        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_drive_adapter(org_id=self._org_id, credential_store=store)
        try:
            content = await adapter.reader.read_file(file_id, max_bytes=max_bytes)
        except Exception as exc:
            logger.exception("drive read_content failed")
            return {"ok": False, "error": "drive_api_error", "detail": str(exc)[:300]}
        if content is None:
            return {"ok": False, "error": "not_found", "file_id": file_id}

        # Compute deterministic stats so the LLM doesn't have to count
        # rows itself — LLMs are notoriously bad at counting long
        # structured data. The chatbot can quote these numbers
        # verbatim and call them facts.
        stats = _compute_content_stats(content.text, content.rendered_as)

        # Surface `rendered_as` in the LEGACY vocabulary (`csv` / `text`
        # / `pdf-text` / `binary`) so the chatbot tool descriptions
        # (which the LLM was prompted with) match the value it sees.
        legacy_rendered_as = translate_rendered_as(
            content.rendered_as, to="legacy"
        )

        return {
            "ok": True,
            "file_id": content.file_id,
            "name": content.name,
            "mime_type": content.mime_type,
            "rendered_as": legacy_rendered_as,
            "bytes_read": content.bytes_read,
            "is_truncated": content.is_truncated,
            "stats": stats,
            "text": content.text,
        }

    async def get_drive_file(self, *, file_id: str) -> dict[str, Any]:
        """Fetch metadata for one file by id."""
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)
        from app.services.drive_api import get_drive_adapter

        if not file_id:
            return {"ok": False, "error": "missing_file_id"}
        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_drive_adapter(org_id=self._org_id, credential_store=store)
        try:
            f = await adapter.reader.get_file(file_id)
        except Exception as exc:
            logger.exception("drive get_file failed")
            return {"ok": False, "error": "drive_api_error", "detail": str(exc)[:300]}
        if not f:
            return {"ok": False, "error": "not_found", "file_id": file_id}
        return {
            "ok": True,
            "file_id": f.file_id,
            "name": f.name,
            "mime_type": f.mime_type,
            "is_folder": f.is_folder,
            "size_bytes": f.size_bytes,
            "modified_at": f.modified_at.isoformat() if f.modified_at else None,
            "web_view_link": f.web_view_link,
            "parents": f.parents,
            "owners": f.owners,
        }

    # ─── Meta (Facebook + Instagram) read-only Graph API ─────────────
    #
    # All these handlers follow the same shape: build CredentialStore,
    # call get_meta_adapter(org_id, store) which returns OAuth adapter
    # when configured + consent given, else FakeMetaAdapter. The
    # adapter call goes through ``asyncio.to_thread`` because httpx
    # under the hood is sync — wrapping keeps the WhatsApp webhook
    # responsive.
    #
    # When the adapter is Fake (no creds / no consent), each handler
    # returns a structured ``ok=False, error=meta_not_connected`` so
    # the chatbot can tell the user "connect Meta at /api/meta/oauth/start"
    # instead of fabricating empty lists.
    async def _meta_adapter(self):
        from app.services.credential_vault import (
            CredentialStore, EncryptionNotConfigured, build_credential_store)
        from app.services.meta import FakeMetaAdapter, get_meta_adapter

        store: CredentialStore | None
        try:
            store = build_credential_store(self._admin)
        except EncryptionNotConfigured:
            store = None
        adapter = get_meta_adapter(org_id=self._org_id, credential_store=store)
        is_fake = isinstance(adapter, FakeMetaAdapter)
        return adapter, is_fake

    async def meta_status(self) -> dict[str, Any]:
        """Self-check: is Meta wired up, who's connected, how many
        pages + IG accounts visible?
        """
        from app.services.meta import MetaGraphError

        adapter, is_fake = await self._meta_adapter()
        if is_fake:
            return {
                "ok": False,
                "error": "meta_not_connected",
                "configured": bool(
                    settings.meta_app_id and settings.meta_app_secret
                ),
                "hint": (
                    "Meta nao esta conectado. Configure META_APP_ID + "
                    "META_APP_SECRET no .env e visite "
                    "/api/meta/oauth/start pra consentir."
                ),
            }
        try:
            me = await asyncio.to_thread(adapter.me)
            pages = await asyncio.to_thread(adapter.list_facebook_pages)
            ig_accounts = await asyncio.to_thread(adapter.list_instagram_accounts)
        except MetaGraphError as exc:
            return {
                "ok": False,
                "error": "meta_graph_error",
                "code": exc.code,
                "is_auth_error": exc.is_auth_error,
                "detail": str(exc)[:300],
            }
        return {
            "ok": True,
            "user_id": me.get("id"),
            "user_name": me.get("name"),
            "pages": [
                {"page_id": p.id, "name": p.name, "category": p.category}
                for p in pages
            ],
            "instagram_accounts": [
                {
                    "ig_user_id": a.id,
                    "username": a.username,
                    "name": a.name,
                    "linked_page_id": a.page_id,
                    "followers_count": a.followers_count,
                }
                for a in ig_accounts
            ],
        }

    async def list_facebook_pages(self) -> dict[str, Any]:
        from app.services.meta import MetaGraphError

        adapter, is_fake = await self._meta_adapter()
        if is_fake:
            return {"ok": False, "error": "meta_not_connected"}
        try:
            pages = await asyncio.to_thread(adapter.list_facebook_pages)
        except MetaGraphError as exc:
            return {
                "ok": False,
                "error": "meta_graph_error",
                "detail": str(exc)[:300],
            }
        return {
            "ok": True,
            "count": len(pages),
            "pages": [
                {
                    "page_id": p.id,
                    "name": p.name,
                    "category": p.category,
                    "fan_count": p.fan_count,
                    "followers_count": p.followers_count,
                    "link": p.link,
                    "tasks": p.tasks,
                }
                for p in pages
            ],
        }

    async def list_facebook_posts(
        self, *, page_id: str, limit: int = 10
    ) -> dict[str, Any]:
        from app.services.meta import MetaGraphError

        if not page_id:
            return {"ok": False, "error": "missing_page_id"}
        adapter, is_fake = await self._meta_adapter()
        if is_fake:
            return {"ok": False, "error": "meta_not_connected"}
        try:
            posts = await asyncio.to_thread(
                adapter.list_facebook_posts, page_id, limit=limit
            )
        except MetaGraphError as exc:
            return {
                "ok": False,
                "error": "meta_graph_error",
                "detail": str(exc)[:300],
            }

        # Precompute engagement summary in Python so the LLM doesn't
        # have to add up like_count fields itself. Same posture as
        # query_drive_sheet — deterministic aggregates beat token-level
        # counting.
        total_likes = sum((p.likes or 0) for p in posts)
        total_comments = sum((p.comments or 0) for p in posts)
        total_shares = sum((p.shares or 0) for p in posts)

        return {
            "ok": True,
            "count": len(posts),
            "page_id": page_id,
            "engagement_summary": {
                "total_likes": total_likes,
                "total_comments": total_comments,
                "total_shares": total_shares,
                "avg_likes_per_post": (
                    round(total_likes / len(posts), 1) if posts else 0
                ),
                "avg_comments_per_post": (
                    round(total_comments / len(posts), 1) if posts else 0
                ),
            },
            "posts": [
                {
                    "id": p.id,
                    "message": (p.message or "")[:400],
                    "created_at": (
                        p.created_time.isoformat() if p.created_time else None
                    ),
                    "permalink_url": p.permalink_url,
                    "full_picture": p.full_picture,
                    "likes_count": p.likes,
                    "comments_count": p.comments,
                    "shares_count": p.shares,
                    "attachments_summary": _meta_attachments_summary(p.attachments),
                }
                for p in posts
            ],
        }

    async def get_facebook_post_insights(
        self, *, post_id: str, page_id: str | None = None
    ) -> dict[str, Any]:
        from app.services.meta import MetaGraphError

        if not post_id:
            return {"ok": False, "error": "missing_post_id"}
        adapter, is_fake = await self._meta_adapter()
        if is_fake:
            return {"ok": False, "error": "meta_not_connected"}
        try:
            insights = await asyncio.to_thread(
                adapter.get_facebook_post_insights, post_id, page_id=page_id
            )
        except MetaGraphError as exc:
            return {
                "ok": False,
                "error": "meta_graph_error",
                "detail": str(exc)[:300],
            }
        if insights is None:
            return {"ok": False, "error": "not_found", "post_id": post_id}
        return {
            "ok": True,
            "post_id": insights.object_id,
            "period": _meta_insights_period(insights),
            "metrics": dict(insights.metrics),
        }

    async def list_instagram_accounts(self) -> dict[str, Any]:
        from app.services.meta import MetaGraphError

        adapter, is_fake = await self._meta_adapter()
        if is_fake:
            return {"ok": False, "error": "meta_not_connected"}
        try:
            accounts = await asyncio.to_thread(adapter.list_instagram_accounts)
        except MetaGraphError as exc:
            return {
                "ok": False,
                "error": "meta_graph_error",
                "detail": str(exc)[:300],
            }
        return {
            "ok": True,
            "count": len(accounts),
            "accounts": [
                {
                    "ig_user_id": a.id,
                    "username": a.username,
                    "name": a.name,
                    "biography": a.biography,
                    "website": a.website,
                    "profile_picture_url": a.profile_picture_url,
                    "followers_count": a.followers_count,
                    "follows_count": a.follows_count,
                    "media_count": a.media_count,
                    "linked_page_id": a.page_id,
                }
                for a in accounts
            ],
        }

    async def list_instagram_media(
        self, *, ig_user_id: str, limit: int = 10
    ) -> dict[str, Any]:
        from app.services.meta import MetaGraphError

        if not ig_user_id:
            return {"ok": False, "error": "missing_ig_user_id"}
        adapter, is_fake = await self._meta_adapter()
        if is_fake:
            return {"ok": False, "error": "meta_not_connected"}
        try:
            media = await asyncio.to_thread(
                adapter.list_instagram_media, ig_user_id, limit=limit
            )
        except MetaGraphError as exc:
            return {
                "ok": False,
                "error": "meta_graph_error",
                "detail": str(exc)[:300],
            }

        total_likes = sum((m.like_count or 0) for m in media)
        total_comments = sum((m.comments_count or 0) for m in media)
        media_type_counts: dict[str, int] = {}
        for m in media:
            media_type_counts[m.media_type] = media_type_counts.get(m.media_type, 0) + 1

        return {
            "ok": True,
            "count": len(media),
            "ig_user_id": ig_user_id,
            "engagement_summary": {
                "total_likes": total_likes,
                "total_comments": total_comments,
                "avg_likes_per_post": (
                    round(total_likes / len(media), 1) if media else 0
                ),
                "avg_comments_per_post": (
                    round(total_comments / len(media), 1) if media else 0
                ),
                "media_type_counts": media_type_counts,
            },
            "media": [
                {
                    "id": m.id,
                    "caption": (m.caption or "")[:400],
                    "media_type": m.media_type,
                    "media_url": m.media_url,
                    "permalink": m.permalink,
                    "thumbnail_url": m.thumbnail_url,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "like_count": m.like_count,
                    "comments_count": m.comments_count,
                }
                for m in media
            ],
        }

    async def get_instagram_media_insights(
        self, *, media_id: str
    ) -> dict[str, Any]:
        from app.services.meta import MetaGraphError

        if not media_id:
            return {"ok": False, "error": "missing_media_id"}
        adapter, is_fake = await self._meta_adapter()
        if is_fake:
            return {"ok": False, "error": "meta_not_connected"}
        try:
            insights = await asyncio.to_thread(
                adapter.get_instagram_media_insights, media_id
            )
        except MetaGraphError as exc:
            return {
                "ok": False,
                "error": "meta_graph_error",
                "detail": str(exc)[:300],
            }
        if insights is None:
            return {"ok": False, "error": "not_found", "media_id": media_id}
        return {
            "ok": True,
            "media_id": insights.object_id,
            "period": _meta_insights_period(insights),
            "metrics": dict(insights.metrics),
        }

    # ─── Drive URL inspect (URL-parse only — separate from Drive API) ─
    async def inspect_drive_url(self, *, drive_url: str) -> dict[str, Any]:
        """Inspect a Drive URL — file vs. folder, file_id, and (when
        possible without download) a quick metadata summary. Does NOT
        download the file; for that, the upload pipeline takes over
        via prepare_upload_request.
        """
        url = (drive_url or "").strip()
        if not url:
            return {"ok": False, "error": "missing_drive_url"}

        is_folder = gdrive_service.is_folder_url(url)
        try:
            if is_folder:
                folder_id = gdrive_service.parse_folder_id(url)
                return {
                    "ok": True,
                    "kind": "folder",
                    "folder_id": folder_id,
                    "drive_url": url,
                    "note": (
                        "Folder identificado. Pra publicar o video YouTube "
                        "desta pasta, use prepare_upload_request com "
                        "esta drive_url + o codigo ONE — o pipeline baixa, "
                        "classifica os arquivos e escolhe o vídeo YouTube."
                    ),
                }
            file_id = gdrive_service.parse_file_id(url)
            return {
                "ok": True,
                "kind": "file",
                "file_id": file_id,
                "drive_url": url,
                "note": (
                    "Arquivo identificado. Pra publicar, use "
                    "prepare_upload_request com esta drive_url + o codigo ONE."
                ),
            }
        except gdrive_service.InvalidDriveURL as exc:
            return {"ok": False, "error": "invalid_drive_url", "detail": str(exc)}

    async def _poll_upload_progress_pings(
        self,
        *,
        upload_svc: object,
        job_id: object,
        deliver,
        stop_event: asyncio.Event,
        interval_seconds: float = 5.0,
    ) -> None:
        """Emit interim progress pings while ``run_upload_job`` is in flight.

        Polls every ``interval_seconds`` and sends:

          - ``🕐 Fila: posição N`` when the job is queued + position
            exceeds the bounded-parallel budget (``upload_max_concurrent``).
            Position pings are suppressed for position changes that drop
            us INTO the run band — at that point the next status ping
            (`📥 status=downloading`) carries the news.
          - ``<emoji> status=X progress=Y%`` on status transitions.

        Stops when ``stop_event`` is set (the blocking upload returned)
        or when a terminal status is reached.

        Gated by ``settings.whatsapp_progress_pings`` — when ``False`` the
        coroutine waits for ``stop_event`` and emits nothing, so the
        toggle works without restructuring the caller.

        Technical message format per the operator's preference. F8
        cross-reference: the "queued" emoji is suppressed when the
        position-ping fired; only the run-band statuses
        (downloading/uploading/published/...) emit normally.
        """
        if not settings.whatsapp_progress_pings:
            try:
                await stop_event.wait()
            except asyncio.CancelledError:
                pass
            return

        emoji_for = {
            "queued": "📋",
            "downloading": "📥",
            "uploading": "📤",
            "processing": "⚙️",  # YT transcoding (S4-1)
            "published": "✅",
            "notified": "📨",
            "failed": "❌",
        }
        terminal = {"published", "notified", "failed"}
        last_status: str | None = None
        last_queue_position: int | None = None

        # Lazy-imported here to avoid a circular: upload_queue → settings
        # → app.config, while intake imports app.config + this poller
        # would otherwise reach back into upload_queue at module load.
        from app.modules.youtube.services.upload_queue import UploadQueue

        queue = UploadQueue(self._redis)
        max_concurrent = max(1, settings.upload_max_concurrent)

        while not stop_event.is_set():
            try:
                job = upload_svc.get_job(job_id=job_id, org_id=self._org_id)
            except Exception:
                logger.exception("progress-poll: get_job failed for job %s", job_id)
                job = None

            if job:
                status = job.get("status")
                progress = job.get("progress_percent") or 0

                # Queue-position ping. Fires only while the job is queued
                # AND its position exceeds the run band — i.e. genuinely
                # waiting for other uploads to finish. Suppressed once it
                # enters the run band; the next status transition will
                # take over the messaging.
                if status == "queued":
                    try:
                        pos = queue.position(str(job_id))
                    except Exception:
                        pos = 0
                    if pos > max_concurrent and pos != last_queue_position:
                        try:
                            await deliver(
                                f"🕐 Fila: posição {pos} "
                                f"(max {max_concurrent} em paralelo)"
                            )
                        except Exception:
                            logger.exception("progress-poll: queue ping deliver failed")
                        last_queue_position = pos
                        # Skip the status emit this tick — we already
                        # said something. Next tick reconciles.
                        try:
                            await asyncio.wait_for(
                                stop_event.wait(), timeout=interval_seconds
                            )
                        except asyncio.TimeoutError:
                            continue
                        except asyncio.CancelledError:
                            return
                        continue

                if status and status != last_status:
                    emoji = emoji_for.get(status, "⚙️")
                    try:
                        await deliver(f"{emoji} status={status} progress={progress}%")
                    except Exception:
                        logger.exception("progress-poll: status ping deliver failed")
                    last_status = status
                    if status in terminal:
                        return

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return

    async def _run_upload(self, phone: str, pending: PendingUpload) -> None:
        """Execute the upload pipeline in background.

        Dispatches to ``queue_browser_upload`` when ``pending.file_id``
        is set (platform-chat path), otherwise to ``queue_drive_upload``
        (WAHA + drive-link path). Both share the same notification +
        status reporting tail.

        Reply delivery: WhatsApp sessions get a WhatsApp message via
        ``_reply``; platform-chat sessions (session_id prefixed with
        ``web:``) skip the WhatsApp send — the UI polls the upload job
        + the pending state directly.
        """
        from app.modules.youtube.schemas.upload import UploadMetadata
        from app.services.credential_vault import CredentialStore, build_credential_store
        from app.services.notification_service import NotificationService
        from app.modules.youtube.services.upload import (
            UploadService,
            rename_for_job,
        )
        from pathlib import Path

        is_web_session = phone.startswith("web:")

        async def deliver(message: str) -> None:
            if is_web_session:
                # Append to the chatbot memory so the platform UI's
                # /api/chat/history call surfaces the final status.
                try:
                    _append_chat_memory(
                        self._redis,
                        session_id=phone,
                        direction="outbound",
                        text=message,
                    )
                except Exception:
                    logger.exception("failed to append chat outbound for %s", phone)
                return
            # WhatsApp path: _reply() already appends outbound to memory
            # after a successful WAHA send.
            await self._reply(phone, message)

        # Bump per-phone active-upload counter. INCR is atomic in Redis,
        # so the "todos" parallel-spawn case lands a clean count regardless
        # of which task arrives first. The matching DECR runs in the
        # finally below; state-clear is gated on count==0 so the bot
        # doesn't accidentally tell a user "idle" while another of their
        # parallel uploads is still running.
        counter_key = _active_uploads_key(phone)
        try:
            self._redis.incr(counter_key)
            self._redis.expire(counter_key, _ACTIVE_UPLOADS_TTL)
        except Exception:
            logger.exception("active-uploads INCR failed for %s", phone)

        try:
            title = pending.crm_title or f"Imóvel {pending.product_code}"
            description = pending.crm_description or ""

            # Fetch the CRM thumbnail (best-effort) so YT gets a real
            # property photo instead of an auto-generated frame. The
            # download + push happens inside upload_service after the
            # video is up; we just plumb the URL through.
            thumbnail_url: str | None = None
            if self._crm:
                try:
                    crm_data = await self._crm.get_property(pending.product_code)
                    if crm_data:
                        thumbnail_url = crm_data.thumbnail_url
                except Exception:
                    logger.exception(
                        "thumbnail CRM lookup failed for %s — skipping thumbnail.",
                        pending.product_code,
                    )

            metadata = UploadMetadata(
                title=f"{pending.product_code} — {title}"[:100],
                description=description[:5000],
                tags=[pending.product_code, "imóvel", "real estate"],
                privacy_status=pending.privacy_status,
                category_id="22",
                notify_recipients=[],
                product_code=pending.product_code,
                thumbnail_url=thumbnail_url,
            )

            store = build_credential_store(self._admin)

            notification = NotificationService(
                admin_supabase=self._admin,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=settings.smtp_password,
                waha_base_url=settings.waha_base_url,
                waha_api_key=settings.waha_api_key,
                waha_session=settings.waha_session,
            )

            upload_svc = UploadService(
                user_supabase=self._admin,
                admin_supabase=self._admin,
                upload_dir=self._upload_dir,
                youtube_service=self._youtube,
                notification_service=notification,
                redis_client=self._redis,
            )

            # Multi-video disambiguation (folder URLs only).
            # ----------------------------------------------------------------
            # Skips when the user already picked (``local_video_path`` set
            # in a prior _handle_video_choice run) or when the upload came
            # from the browser tab (``file_id`` set). For new folder URLs,
            # downloads the contents, classifies horizontal videos, and:
            #   - N=0 horizontal → fail, surface message, clear state.
            #   - N=1 horizontal → use it, fall through to upload.
            #   - N≥2 horizontal → present numbered choice menu, transition
            #     to ``awaiting_video_choice``, return early. Resumption
            #     happens via ``_handle_video_choice`` which re-enters
            #     ``_run_upload`` with ``local_video_path`` set.
            if (
                pending.local_video_path is None
                and pending.file_id is None
                and pending.drive_url
                and gdrive_service.is_folder_url(pending.drive_url)
            ):
                # Drive download cache (F1). Re-runs (retry, multi-job,
                # multi-candidate) hit the cache and skip the network
                # round-trip when the local files are still on disk.
                from app.modules.youtube.services.download_cache import (
                    CachedCandidate,
                    DownloadCache,
                )

                cache = DownloadCache(
                    self._redis, ttl_hours=settings.download_cache_ttl_hours
                )
                cached = cache.get(pending.drive_url)
                candidates: list = []
                if cached is not None:
                    logger.info(
                        "drive cache HIT for %s (%d candidate(s), age=%.0fs)",
                        pending.drive_url[:80],
                        len(cached.candidates),
                        time.time() - cached.downloaded_at,
                    )
                    # Rehydrate as gdrive_service.VideoCandidate so the
                    # downstream code path is identical for cache hits +
                    # misses.
                    candidates = [
                        gdrive_service.VideoCandidate(
                            local_path=Path(c.local_path),
                            file_name=c.file_name,
                            file_size_bytes=c.file_size_bytes,
                            format=c.format,
                            duration_seconds=c.duration_seconds,
                        )
                        for c in cached.candidates
                    ]
                else:
                    if settings.whatsapp_progress_pings:
                        await deliver("📥 Baixando arquivos do Drive para análise…")
                    try:
                        result = await asyncio.to_thread(
                            gdrive_service.list_youtube_candidates,
                            folder_url=pending.drive_url,
                            target_dir=self._upload_dir,
                        )
                        candidates = result.candidates
                        # Surface oversized drops (F7) — silent omission
                        # confuses operators who can SEE the file in the
                        # Drive UI but don't see it in the menu.
                        if result.oversized:
                            from app.services.gdrive_service import DEFAULT_MAX_BYTES
                            max_mb = DEFAULT_MAX_BYTES // (1024 * 1024)
                            dropped = ", ".join(
                                f"{o.file_name} ({_format_size(o.file_size_bytes)})"
                                for o in result.oversized
                            )
                            await deliver(
                                f"⚠️ {len(result.oversized)} arquivo(s) acima do limite "
                                f"({max_mb}MB) foram ignorados: {dropped}"
                            )
                    except gdrive_service.GoogleDriveError as exc:
                        logger.warning(
                            "list_youtube_candidates failed for %s: %s", phone, exc
                        )
                        await deliver(f"❌ Erro ao baixar do Drive: {exc}")
                        await self._clear_state(phone)
                        return
                    except Exception:
                        logger.exception(
                            "list_youtube_candidates crashed for %s", phone
                        )
                        await deliver(
                            "❌ Falha ao acessar o Drive. "
                            "Verifique o link e tente novamente."
                        )
                        await self._clear_state(phone)
                        return

                    # Cache the result for the TTL window so retry +
                    # multi-job paths short-circuit the network.
                    if candidates:
                        cache.put(
                            pending.drive_url,
                            [
                                CachedCandidate(
                                    local_path=str(c.local_path),
                                    file_name=c.file_name,
                                    file_size_bytes=c.file_size_bytes,
                                    format=c.format,
                                    duration_seconds=c.duration_seconds,
                                )
                                for c in candidates
                            ],
                        )

                if not candidates:
                    await deliver(
                        "❌ Não achei vídeos no formato YouTube (16:9) nessa pasta. "
                        "Verifique o conteúdo do Drive e reenvie o pedido."
                    )
                    await self._clear_state(phone)
                    return

                if len(candidates) == 1:
                    chosen = candidates[0]
                    pending.local_video_path = str(chosen.local_path)
                    pending.local_video_filename = chosen.file_name
                    pending.local_video_size_bytes = chosen.file_size_bytes
                    pending.video_format = chosen.format
                    await self._set_state(phone, pending)
                    # Fall through to the upload branches below.
                else:
                    pending.candidate_videos = [
                        VideoCandidateSnapshot(
                            local_path=str(c.local_path),
                            file_name=c.file_name,
                            file_size_bytes=c.file_size_bytes,
                            format=c.format,
                            duration_seconds=c.duration_seconds,
                        )
                        for c in candidates
                    ]
                    pending.state = "awaiting_video_choice"
                    await self._set_state(phone, pending)

                    menu_lines = [
                        f"📂 Achei {len(candidates)} vídeos no formato YouTube nessa pasta:"
                    ]
                    for i, c in enumerate(candidates, 1):
                        dur = _format_duration(c.duration_seconds)
                        dur_part = f" ({dur})" if dur else ""
                        menu_lines.append(
                            f"{i}. {c.file_name}{dur_part} — {_format_size(c.file_size_bytes)}"
                        )
                    menu_lines.append(
                        "\nQual quero subir? Responda *1*, *2*, … "
                        "Ou *TODOS* para subir todos como vídeos separados "
                        "(ou *CANCELAR*)."
                    )
                    await deliver("\n".join(menu_lines))
                    return  # wait for the user's choice; _run_upload re-enters from _handle_video_choice

            if pending.file_id:
                file_info = self.get_uploaded_file(pending.file_id)
                if not file_info:
                    await deliver(
                        "❌ Arquivo nao encontrado mais (expirou ou foi removido). "
                        "Faca o upload novamente."
                    )
                    return
                staging_path = Path(file_info["local_path"])
                if not staging_path.exists():
                    await deliver(
                        "❌ Arquivo nao esta mais no disco. Reenvie o video."
                    )
                    self.forget_uploaded_file(pending.file_id)
                    return

                file_name = file_info.get("file_name") or staging_path.name
                file_size = file_info.get("file_size_bytes") or staging_path.stat().st_size

                queued = upload_svc.queue_browser_upload(
                    org_id=self._org_id,
                    created_by=None,
                    metadata=metadata,
                    file_name=file_name,
                    file_size_bytes=file_size,
                    local_path=staging_path,
                )
                rename_for_job(
                    staging_path,
                    queued.job_id,
                    file_name,
                    target_dir=self._upload_dir,
                )
                self.forget_uploaded_file(pending.file_id)
            elif pending.local_video_path:
                # Multi-candidate flow already resolved to a downloaded
                # file (either auto-picked when N=1 or user-picked via
                # _handle_video_choice). Treat it like a browser upload
                # so we skip re-downloading.
                staging_path = Path(pending.local_video_path)
                if not staging_path.exists():
                    await deliver(
                        "❌ Arquivo local não está mais disponível "
                        "(pode ter sido limpo). Reenvie o comando do zero."
                    )
                    await self._clear_state(phone)
                    return
                file_name = pending.local_video_filename or staging_path.name
                file_size = (
                    pending.local_video_size_bytes
                    or staging_path.stat().st_size
                )
                queued = upload_svc.queue_browser_upload(
                    org_id=self._org_id,
                    created_by=None,
                    metadata=metadata,
                    file_name=file_name,
                    file_size_bytes=file_size,
                    local_path=staging_path,
                )
                rename_for_job(
                    staging_path,
                    queued.job_id,
                    file_name,
                    target_dir=self._upload_dir,
                )
            else:
                queued = upload_svc.queue_drive_upload(
                    org_id=self._org_id,
                    created_by=None,
                    metadata=metadata,
                    drive_url=pending.drive_url or "",
                )

            # Queue acquisition + release now lives inside
            # ``upload_svc.run_upload_job`` so EVERY upload entry point
            # (browser, retry, WhatsApp) shares the same FIFO + bounded-
            # parallel budget. The WhatsApp side keeps its position-ping
            # UX via the progress poller below, which reads queue
            # position from Redis and emits "🕐 Fila: posição N" pings
            # gated by ``settings.whatsapp_progress_pings``.

            # Wrap the synchronous `run_upload_job` in `asyncio.to_thread`
            # so we can run a parallel progress-poller on the asyncio loop.
            # Without `to_thread` the sync call would block the loop and
            # the poller's `asyncio.sleep` would never tick.
            stop_event = asyncio.Event()
            poll_task = asyncio.create_task(
                self._poll_upload_progress_pings(
                    upload_svc=upload_svc,
                    job_id=queued.job_id,
                    deliver=deliver,
                    stop_event=stop_event,
                )
            )
            try:
                await asyncio.to_thread(
                    upload_svc.run_upload_job, job_id=queued.job_id
                )
            finally:
                stop_event.set()
                try:
                    await asyncio.wait_for(poll_task, timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    poll_task.cancel()
                # Queue release happens inside ``run_upload_job`` (in the
                # finally of its own try/finally wrapper around the
                # acquire), so no explicit release here.

            # Check the result
            job = upload_svc.get_job(job_id=queued.job_id, org_id=self._org_id)
            if job and job.get("status") in ("published", "notified"):
                video_id = job.get("youtube_video_id", "")
                url = (
                    f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
                )
                # Rich post-upload summary (S4-4) — paragraph-split into
                # bubbles via send_paragraphs so each section reads
                # naturally instead of a wall of text.
                from app.services.whatsapp_outbound import send_paragraphs

                summary_parts: list[str] = [
                    f"✅ Vídeo publicado!\n🎬 {metadata.title}",
                    f"📺 {url}" if url else "📺 (URL indisponível)",
                ]
                listing_url = ""
                if pending.product_code and settings.listing_url_template:
                    try:
                        listing_url = settings.listing_url_template.format(
                            code=pending.product_code
                        )
                    except (KeyError, IndexError):
                        listing_url = ""
                if listing_url:
                    summary_parts.append(f"📋 Anúncio: {listing_url}")
                if pending.crm_description:
                    short_desc = pending.crm_description.strip().split("\n")[0][:160]
                    if short_desc:
                        summary_parts.append(f"📝 {short_desc}")
                agent_digits = "".join(
                    ch for ch in (settings.default_agent_whatsapp or "") if ch.isdigit()
                )
                if agent_digits:
                    summary_parts.append(
                        f"💬 Agende uma visita: https://wa.me/{agent_digits}"
                    )
                summary_parts.append("Compartilhe! 🚀")

                if not phone.startswith("web:"):
                    await send_paragraphs(
                        intake=self,
                        sender=phone,
                        text="\n\n".join(summary_parts),
                    )
                else:
                    await deliver("\n\n".join(summary_parts))
            elif job and job.get("status") == "failed":
                error = job.get("error_message", "erro desconhecido")
                await deliver(f"❌ Falha no upload para o YouTube:\n{error}")
            else:
                await deliver(
                    "⚠️ Upload finalizado com status desconhecido. "
                    "Verifique o Dashboard."
                )

        except Exception as exc:
            logger.exception("Upload pipeline failed for %s", phone)
            await deliver(
                f"❌ Erro no processamento:\n{exc}\n\n"
                "Verifique os logs ou tente novamente."
            )
        finally:
            # Decrement active-uploads counter; only clear state when it
            # reaches zero. Critical for the "todos" parallel-spawn case
            # where N uploads share the same phone — the FIRST to finish
            # would otherwise clear state for the rest.
            remaining = 1
            try:
                value = self._redis.decr(counter_key)
                remaining = int(value) if value is not None else 0
                if remaining <= 0:
                    self._redis.delete(counter_key)
            except Exception:
                logger.exception("active-uploads DECR failed for %s", phone)
                remaining = 0  # safest assumption: try to clear state

            if remaining <= 0:
                await self._clear_state(phone)
            else:
                logger.info(
                    "Upload for %s done; %d sibling upload(s) still running — "
                    "keeping state as 'processing'.",
                    phone,
                    remaining,
                )
