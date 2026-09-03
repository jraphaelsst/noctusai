"""Settings router — UI-side configuration surface (non-YouTube).

Three tabs back this router:
  - Notifications (recipient CRUD)
  - API Keys (read-only health status across every integration)
  - Live integration smoke checks (Vista / Email / WAHA)

NOTE — the YouTube tab + OAuth callback router moved to
``app.modules.youtube.routers.settings`` in Phase 8 alongside the rest
of the YouTube footprint. The split is at the router level only — the
URL surface is unchanged: ``/api/settings/youtube/*`` paths still resolve
because the youtube module mounts its own ``router`` at the same
``/api/settings`` prefix. The ``KeysStatus`` shape stays here (it
enumerates secrets across YouTube + every other integration — a
cross-domain concern, not a YouTube-domain one).

Auth pattern: ``Depends(get_current_user_org)`` returning
``(user, token, raw_org_id)``. The user-scoped Supabase client is then
built via ``get_user_client(token)`` inside the route body — the seed's
``Depends(get_user_client)`` shape doesn't chain because its positional
``token`` arg becomes a required query parameter. See
``KB § PATTERNS/backend.md § Auth — canonical pattern``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.whatsapp import chat_id_for_phone, get_whatsapp_client

from app.config import SocialWiringSettings, settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user,
    get_current_user_org,
    get_scoped_admin_client,
    get_settings,
    get_user_client,
)
from app.schemas.settings import (
    ApiKeyStatus,
    ApiKeyTestResult,
    ApiKeyUpdate,
    ApiKeysStatus,
    ClientesInactivityConfigStatus,
    DocumentoRetencaoLista,
    DocumentoRetencaoPolitica,
    DocumentoRetencaoUpdate,
    ClientesInactivityConfigUpdate,
    EmailTestRequest,
    EmailTestResult,
    InstagramAppConfigStatus,
    InstagramAppConfigUpdate,
    KeyHealth,
    KeyStatusEntry,
    KeysStatus,
    MetaAppConfigStatus,
    MetaAppConfigUpdate,
    RecipientCreate,
    RecipientOut,
    RecipientUpdate,
    VistaStatus,
    WahaStatus,
    WahaTestRequest,
    WahaTestResult,
)
from app.schemas.whatsapp import WAHASessionInfo, extract_waha_message_id
from app.services.app_config_store import (
    INSTAGRAM_APP_ID_KEY,
    INSTAGRAM_APP_SECRET_KEY,
    META_APP_ID_KEY,
    META_APP_SECRET_KEY,
    build_app_config_store,
    resolve_instagram_app_creds,
    resolve_meta_app_creds,
)
from app.services import clientes_inactivity_service, documento_retencao
from app.services.chatbot_service import append_memory as _append_chat_memory
from noctusai_lib.integrations.vista import (
    VistaError as CRMServiceError,
    VistaNotConfigured as CRMNotConfigured,
    VistaRESTAdapter as CRMService,
)
from app.services.api_keys_store import (
    API_KEY_SPECS,
    MANAGED_API_KEYS,
    ApiKeySpec,
    build_api_key_store,
    delete_api_key,
    get_spec as get_api_key_spec,
    mask_value as mask_api_key_value,
    put_api_key,
    resolve_api_key_detail,
)
from app.services.credential_vault import EncryptionNotConfigured
from app.services.email_service import EmailNotConfigured, EmailService, EmailServiceError
from app.services.message_store import DuplicateMessage, MessageStore
from app.services.waha_response_registry import record_waha_sample

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ─── Notifications tab — recipients ────────────────────────────────────
_RECIPIENTS_TABLE = "notification_recipients"


@router.get("/recipients", response_model=list[RecipientOut])
def list_recipients(
    auth: tuple = Depends(get_current_user_org),
) -> list[RecipientOut]:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    response = (
        supabase
        .schema("social_wiring")
        .table(_RECIPIENTS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .order("created_at", desc=False)
        .execute()
    )
    return [RecipientOut(**row) for row in (response.data or [])]


@router.post(
    "/recipients",
    response_model=RecipientOut,
    status_code=status.HTTP_201_CREATED,
)
def create_recipient(
    payload: RecipientCreate,
    auth: tuple = Depends(get_current_user_org),
) -> RecipientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    response = (
        supabase
        .schema("social_wiring")
        .table(_RECIPIENTS_TABLE)
        .insert({
            "org_id": str(org_id),
            "name": payload.name,
            "email": payload.email,
            "whatsapp_number": payload.whatsapp_number,
            "is_active": payload.is_active,
            # NULL = org-wide fallback tier (migration 045). Not defaulted to
            # a client: an unattributed recipient hearing everything is the
            # safe failure, an unrelated client's contacts hearing another
            # client's lead PII is not.
            "marca_id": payload.marca_id,
        })
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="recipient insert returned no rows",
        )
    return RecipientOut(**response.data[0])


@router.put("/recipients/{recipient_id}", response_model=RecipientOut)
def update_recipient(
    recipient_id: UUID,
    payload: RecipientUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> RecipientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    update_payload = {
        k: v
        for k, v in payload.model_dump(exclude_none=True).items()
    }
    # `marca_id` needs the explicit-null distinction the shared exclude_none
    # path erases: sending `null` must CLEAR the scope back to org-wide, while
    # omitting the key leaves it alone. `model_fields_set` is what tells those
    # two apart.
    if "marca_id" in payload.model_fields_set:
        update_payload["marca_id"] = payload.marca_id
    if not update_payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields to update",
        )
    update_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    response = (
        supabase
        .schema("social_wiring")
        .table(_RECIPIENTS_TABLE)
        .update(update_payload)
        .eq("id", str(recipient_id))
        .eq("org_id", str(org_id))
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="recipient not found",
        )
    return RecipientOut(**response.data[0])


@router.delete(
    "/recipients/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_recipient(
    recipient_id: UUID,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    response = (
        supabase
        .schema("social_wiring")
        .table(_RECIPIENTS_TABLE)
        .delete()
        .eq("id", str(recipient_id))
        .eq("org_id", str(org_id))
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="recipient not found",
        )


# ─── API Keys tab — health check ───────────────────────────────────────
def _entry(value: str | None, label: str, description: str) -> KeyStatusEntry:
    return KeyStatusEntry(
        label=label,
        health="configured" if (value or "") else "missing",
        description=description,
    )


@router.get("/keys/status", response_model=KeysStatus)
def get_keys_status(
    _user=Depends(get_current_user),  # auth-gate the endpoint; the values matter for tenants too
cfg: SocialWiringSettings = Depends(get_settings)) -> KeysStatus:
    """Show the operator which secrets are wired vs absent — never echoes
    the actual values back. The UI uses this to render configured /
    missing badges and prompt the user to fix .env when red."""
    return KeysStatus(
        youtube_client_id=_entry(
            cfg.youtube_client_id, "YouTube Client ID",
            "Required for OAuth — issued by Google Cloud Console.",
        ),
        youtube_client_secret=_entry(
            cfg.youtube_client_secret, "YouTube Client Secret",
            "Pairs with the Client ID. Keep secret.",
        ),
        youtube_redirect_uri=_entry(
            cfg.youtube_redirect_uri, "YouTube Redirect URI",
            "Must match the OAuth-client redirect URI EXACTLY.",
        ),
        frontend_base_url=_entry(
            cfg.frontend_base_url, "Frontend Base URL",
            "Where OAuth should return the operator after Google callback.",
        ),
        openai_api_key=_entry(
            cfg.openai_api_key, "OpenAI API Key",
            "Required for the WhatsApp chatbot reasoning and tool orchestration layer.",
        ),
        openai_chat_model=_entry(
            cfg.openai_chat_model, "OpenAI Chat Model",
            "Model used by the WhatsApp chatbot orchestration loop.",
        ),
        whatsapp_chatbot_enabled=_entry(
            str(cfg.whatsapp_chatbot_enabled), "WhatsApp Chatbot",
            "When true and OpenAI is configured, WhatsApp uses GPT tool orchestration.",
        ),
        encryption_key=_entry(
            cfg.encryption_key, "Encryption Key",
            "Fernet key used to encrypt refresh tokens at rest.",
        ),
        smtp_user=_entry(
            cfg.smtp_user, "SMTP User",
            "Email address used as the From: header for notifications.",
        ),
        smtp_password=_entry(
            cfg.smtp_password, "SMTP Password",
            "Gmail App Password (not the account password).",
        ),
        waha_base_url=_entry(
            cfg.waha_base_url, "WAHA Base URL",
            "WAHA server base URL. Empty = FakeWahaClient (dev).",
        ),
        waha_api_key=_entry(
            cfg.waha_api_key, "WAHA API Key",
            "Bearer token for WAHA. Required when WAHA Base URL is set.",
        ),
        waha_dashboard_url=_entry(
            cfg.waha_dashboard_url, "WAHA Dashboard URL",
            "Human/browser URL for the local WAHA dashboard.",
        ),
        waha_webhook_url=_entry(
            cfg.waha_webhook_url, "WAHA Webhook URL",
            "Public URL WAHA should call for inbound message webhooks.",
        ),
        waha_webhook_hmac_secret=_entry(
            cfg.waha_webhook_hmac_secret, "WAHA Webhook Secret",
            "Optional shared secret for webhook hardening. Empty in local dev is allowed.",
        ),
        vista_base_url=_entry(
            cfg.crm_base_url or cfg.vista_base_url, "Vista Base URL",
            "Vista tenant REST base URL. Server-side only.",
        ),
        vista_api_key=_entry(
            cfg.crm_api_key or cfg.vista_api_key, "Vista API Key",
            "Vista API key. Server-side only; never expose as VITE_*.",
        ),
        database_backend=_entry(
            cfg.database_backend, "Database Backend",
            "sqlite for local development, supabase for production.",
        ),
        supabase_url=_entry(
            cfg.supabase_url, "Supabase URL",
            "Project URL. Only required when DATABASE_BACKEND=supabase.",
        ),
        supabase_service_role_key=_entry(
            cfg.supabase_service_role_key, "Supabase Service Role Key",
            "Used for service-side writes when DATABASE_BACKEND=supabase.",
        ),
    )


@router.get("/vista/status", response_model=VistaStatus)
async def get_vista_status(
    product_code: str = Query(default="ONE5555", min_length=6, max_length=9),
    _user=Depends(get_current_user),
) -> VistaStatus:
    """Live Vista smoke check using a property code.

    Returns a sanitized property summary only. It never echoes the Vista key.
    """
    try:
        crm = CRMService(
            base_url=settings.crm_base_url,
            api_key=settings.crm_api_key,
        )
    except CRMNotConfigured as exc:
        return VistaStatus(
            configured=False,
            ok=False,
            product_code=product_code.upper(),
            error=str(exc),
        )

    code = product_code.upper()
    try:
        prop = await crm.get_property(code)
    except CRMServiceError as exc:
        return VistaStatus(
            configured=True,
            ok=False,
            product_code=code,
            error=str(exc),
        )
    if prop is None:
        return VistaStatus(
            configured=True,
            ok=False,
            product_code=code,
            error="Property not found or invalid product code.",
        )
    return VistaStatus(
        configured=True,
        ok=True,
        product_code=prop.product_code,
        title=prop.title,
        address=prop.address,
        price=prop.price,
        bedrooms=prop.bedrooms,
        area_sqm=prop.area_sqm,
    )


@router.post("/email/test", response_model=EmailTestResult)
async def send_email_test(
    payload: EmailTestRequest,
    _user=Depends(get_current_user),
) -> EmailTestResult:
    """Send a real SMTP test email. The default recipient is SMTP_USER."""
    to = str(payload.to or settings.smtp_user)
    try:
        service = EmailService(
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_password=settings.smtp_password,
        )
        await service.send_email(
            to=to,
            subject="[Social Wiring] Teste SMTP",
            text_body=(
                "Teste de envio SMTP do Social Wiring. "
                "Se voce recebeu esta mensagem, Gmail SMTP esta funcional."
            ),
            html_body=(
                "<p>Teste de envio SMTP do <strong>Social Wiring</strong>.</p>"
                "<p>Se voce recebeu esta mensagem, Gmail SMTP esta funcional.</p>"
            ),
        )
    except (EmailNotConfigured, EmailServiceError) as exc:
        return EmailTestResult(ok=False, to=to, error=str(exc))
    return EmailTestResult(ok=True, to=to)


@router.get("/waha/status", response_model=WahaStatus)
async def get_waha_status(
    _user=Depends(get_current_user),
) -> WahaStatus:
    """Best-effort WAHA session status check."""
    if not settings.waha_base_url:
        return WahaStatus(
            configured=False,
            ok=False,
            session=settings.waha_session,
            error="WAHA_BASE_URL is empty; FakeWahaClient mode.",
        )

    headers = {"X-Api-Key": settings.waha_api_key} if settings.waha_api_key else {}
    base_url = settings.waha_base_url.rstrip("/")
    candidates = [
        f"/api/sessions/{settings.waha_session}",
        f"/api/sessions/{settings.waha_session}/status",
        "/api/sessions",
    ]
    last_error: str | None = None
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        for path in candidates:
            try:
                response = await client.get(path, headers=headers)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue
            if response.status_code == 404:
                last_error = f"{path} returned 404"
                continue
            if response.status_code >= 400:
                try:
                    error_payload = response.json()
                except Exception:
                    error_payload = {"text": response.text[:1000]}
                record_waha_sample(
                    source=f"GET {path}",
                    direction="app_to_waha_response",
                    http_status=response.status_code,
                    payload=error_payload,
                    handling_notes=(
                        "Status checks should return ok=false for non-2xx WAHA "
                        "responses without crashing settings diagnostics."
                    ),
                )
                return WahaStatus(
                    configured=True,
                    ok=False,
                    base_url=base_url,
                    session=settings.waha_session,
                    error=f"{path} returned HTTP {response.status_code}: {response.text[:200]}",
                )
            data = response.json() if response.content else {}
            record_waha_sample(
                source=f"GET {path}",
                direction="app_to_waha_response",
                http_status=response.status_code,
                payload=data,
                handling_notes=(
                    "Session status may be a session object, a bare status object, "
                    "or a sessions list. Extract status best-effort."
                ),
            )
            session_status = _extract_waha_session_status(data)
            return WahaStatus(
                configured=True,
                ok=True,
                base_url=base_url,
                session=settings.waha_session,
                status=session_status,
            )
    return WahaStatus(
        configured=True,
        ok=False,
        base_url=base_url,
        session=settings.waha_session,
        error=last_error or "WAHA status endpoint did not respond.",
    )


@router.post("/waha/test", response_model=WahaTestResult)
async def send_waha_test(
    payload: WahaTestRequest,
    _user=Depends(get_current_user),
) -> WahaTestResult:
    """Send a real WAHA test message to an explicit phone number.

    Side effects (each is its own boundary so partial failures are
    visible in logs but never undo the send):

    1. Persist any (lid → phone) mapping in the WAHA response's
       ``_data.id.remote`` so future inbound LID webhooks resolve to
       the right phone whitelist entry.
    2. Append the outbound text to the chatbot's conversation memory
       under BOTH the phone form and the captured LID form, so the
       agent recalls the message it just sent — same pattern as
       whatsapp-scheduling's ``buffer_service.append_to_memory`` after
       every successful send.
    """
    if not settings.waha_base_url:
        return WahaTestResult(
            ok=False,
            phone=payload.phone,
            error="WAHA_BASE_URL is empty; refusing fake-mode test send.",
        )
    client = get_whatsapp_client(
        base_url=settings.waha_base_url,
        api_key=settings.waha_api_key,
        session=settings.waha_session,
    )
    try:
        result = await client.send_text(chat_id_for_phone(payload.phone), payload.text)
    except Exception as exc:
        return WahaTestResult(ok=False, phone=payload.phone, error=str(exc))
    record_waha_sample(
        source="POST /api/sendText",
        direction="app_to_waha_response",
        http_status=201,
        payload=result,
        handling_notes=(
            "Treat any 2xx sendText response as success. Extract message id "
            "best-effort from id, key.id, _data.id, or message.id."
        ),
    )

    # Capture lid + persist outbound to memory (best-effort — never block
    # the response on these auxiliary writes).
    try:
        import redis as _redis_mod
        redis_client = _redis_mod.from_url(settings.redis_url, decode_responses=True)
        # The WAHA response's `_data.id.remote` is the recipient's LID.
        lid = None
        if isinstance(result, dict):
            data = result.get("_data") or {}
            id_obj = data.get("id") if isinstance(data, dict) else None
            if isinstance(id_obj, dict):
                lid = id_obj.get("remote")
        normalized_phone = payload.phone
        if not normalized_phone.startswith("+"):
            normalized_phone = f"+{normalized_phone}"
        # Append outbound to memory under the phone-form key (so future
        # inbound via the phone path matches) AND under the lid-form
        # key (so future inbound via lid matches the same conversation).
        _append_chat_memory(
            redis_client,
            session_id=normalized_phone,
            direction="outbound",
            text=payload.text,
        )
        if lid:
            _append_chat_memory(
                redis_client,
                session_id=lid,
                direction="outbound",
                text=payload.text,
            )
            redis_client.set(
                f"whatsapp:lid_to_phone:{lid}",
                normalized_phone,
                ex=30 * 24 * 3600,
            )
        # Durable persistence into conversation_messages — same audit log
        # the webhook handler writes to. Uses the local-dev org since this
        # endpoint runs without a JWT in SQLite mode.
        try:
            from uuid import UUID as _UUID
            store = MessageStore(
                admin_supabase=get_admin_client(),
                org_id=_UUID(settings.local_dev_org_id),
            )
            store.record(
                session_id=normalized_phone,
                raw_sender=lid or normalized_phone,
                direction="outbound",
                body=payload.text,
                provider_message_id=extract_waha_message_id(result),
                authorized=True,
                structured_payload={"source": "settings/waha/test"},
            )
        except DuplicateMessage:
            pass
        except Exception:
            logger.exception("waha test: conversation_messages insert failed")
    except Exception:
        logger.exception("waha test: failed to persist outbound/lid mapping")

    return WahaTestResult(
        ok=True,
        phone=payload.phone,
        message_id=extract_waha_message_id(result),
    )


# ─── Meta App config tab (Wave 2 — app-wide, DB-backed + env-fallback) ─
def _require_admin(user: Any, context: str) -> None:
    """403 unless ``user`` has owner/admin role on their org.

    Same check-shape as ``noctusai_seed.auth_router._require_org_admin``
    (N=2 — flagged as a `scoped-improvement:` in this dispatch's
    delivery note rather than extracted mid-brief; that helper reads
    org_role from the TRUSTED `public.noctus_users` row via
    `deps.get_core_client()`, whereas this one reads `user_metadata`
    directly — a narrower, still-spoofable check this slice didn't
    touch; module-local + underscore-prefixed either way, so this one
    stays local instead of reaching across a router/module boundary).
    """
    metadata = getattr(user, "user_metadata", None) or {}
    role = metadata.get("org_role") or metadata.get("role")
    if role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{context} restricted to owner/admin roles",
        )


def get_app_config_store_dep():
    """DI seam: the real app-config store, mapping a missing/malformed
    ``ENCRYPTION_KEY`` to a 503 config-gap. Used by the WRITE endpoint —
    persisting is meaningless without a usable Fernet key. Tests override
    via ``app.dependency_overrides[get_app_config_store_dep]`` with a
    ``FakeAppConfigStore``. Per KB § PATTERNS/backend/di-test-seam.md
    (Class-B, service DI)."""
    try:
        return build_app_config_store()
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


def get_app_config_store_optional_dep():
    """Same store, but returns ``None`` instead of raising when
    ``ENCRYPTION_KEY`` is missing/malformed. Used by the READ-ONLY status
    path (+ ``_meta_app_status``'s ``resolve_meta_app_creds`` call) —
    an unconfigured Fernet key is a valid state there (env-only
    resolution), unlike the write endpoint above."""
    try:
        return build_app_config_store()
    except EncryptionNotConfigured:
        return None


def _meta_app_status(cfg: SocialWiringSettings, store=None) -> MetaAppConfigStatus:
    """Build the status response from the current DB-or-env resolution.

    Never touches the secret value beyond a boolean/masked-id check —
    safe to call from both the write endpoint's response and the
    read-only status endpoint. ``cfg`` is the injected
    ``Depends(get_settings)`` value (never the module singleton
    directly) and ``store`` the injected app-config store (or ``None``)
    so tests can override BOTH halves of the resolution via the existing
    DI seams above."""
    app_id, app_secret = resolve_meta_app_creds(settings=cfg, store=store)
    app_id_masked = None
    if app_id:
        app_id_masked = app_id if len(app_id) <= 4 else f"...{app_id[-4:]}"
    return MetaAppConfigStatus(
        app_id_configured=bool(app_id),
        app_secret_configured=bool(app_secret),
        app_id_masked=app_id_masked,
    )


@router.put("/meta-app", response_model=MetaAppConfigStatus)
def update_meta_app_config(
    payload: MetaAppConfigUpdate,
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    store=Depends(get_app_config_store_dep),
) -> MetaAppConfigStatus:
    """Admin-gated write for the Meta App ID / App Secret pair.

    Persists into ``social_wiring.app_integration_config`` (migration
    022) via the seed ``AppConfigStore`` — encrypted at rest, DB value
    wins over the ``META_APP_ID`` / ``META_APP_SECRET`` env fallback.
    ``app_secret`` is write-only and only overwritten when the caller
    supplies a non-blank value (never echoed back in the response).
    """
    user, _token, _raw_org = auth
    _require_admin(user, "Meta App config")

    if payload.app_id is None and not payload.app_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="provide at least one of app_id / app_secret",
        )

    if payload.app_id is not None:
        store.put(META_APP_ID_KEY, payload.app_id.strip())
    if payload.app_secret:  # blank/omitted never overwrites — write-only, opt-in
        store.put(META_APP_SECRET_KEY, payload.app_secret)

    return _meta_app_status(cfg, store=store)


@router.get("/meta-app/status", response_model=MetaAppConfigStatus)
def get_meta_app_config_status(
    _auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    store=Depends(get_app_config_store_optional_dep),
) -> MetaAppConfigStatus:
    """Which half of the Meta App credential pair is configured (DB or
    env) — never the secret itself."""
    return _meta_app_status(cfg, store=store)


# ─── Instagram App config tab (byte-for-byte mirror of the Meta App tab
# above, keyed on the Instagram Business Login app credential pair) ─────
def _instagram_app_status(cfg: SocialWiringSettings, store=None) -> InstagramAppConfigStatus:
    """Build the status response from the current DB-or-env resolution.

    Mirrors ``_meta_app_status`` exactly (see its docstring), resolving
    via :func:`resolve_instagram_app_creds` instead."""
    app_id, app_secret = resolve_instagram_app_creds(settings=cfg, store=store)
    app_id_masked = None
    if app_id:
        app_id_masked = app_id if len(app_id) <= 4 else f"...{app_id[-4:]}"
    return InstagramAppConfigStatus(
        app_id_configured=bool(app_id),
        app_secret_configured=bool(app_secret),
        app_id_masked=app_id_masked,
    )


@router.put("/instagram-app", response_model=InstagramAppConfigStatus)
def update_instagram_app_config(
    payload: InstagramAppConfigUpdate,
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    store=Depends(get_app_config_store_dep),
) -> InstagramAppConfigStatus:
    """Admin-gated write for the Instagram App ID / App Secret pair.

    Persists into ``social_wiring.app_integration_config`` (migration
    022) via the seed ``AppConfigStore`` — encrypted at rest, DB value
    wins over the ``INSTAGRAM_APP_ID`` / ``INSTAGRAM_APP_SECRET`` env
    fallback. ``app_secret`` is write-only and only overwritten when the
    caller supplies a non-blank value (never echoed back in the
    response).
    """
    user, _token, _raw_org = auth
    _require_admin(user, "Instagram App config")

    if payload.app_id is None and not payload.app_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="provide at least one of app_id / app_secret",
        )

    if payload.app_id is not None:
        store.put(INSTAGRAM_APP_ID_KEY, payload.app_id.strip())
    if payload.app_secret:  # blank/omitted never overwrites — write-only, opt-in
        store.put(INSTAGRAM_APP_SECRET_KEY, payload.app_secret)

    return _instagram_app_status(cfg, store=store)


@router.get("/instagram-app/status", response_model=InstagramAppConfigStatus)
def get_instagram_app_config_status(
    _auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
    store=Depends(get_app_config_store_optional_dep),
) -> InstagramAppConfigStatus:
    """Which half of the Instagram App credential pair is configured
    (DB or env) — never the secret itself."""
    return _instagram_app_status(cfg, store=store)


def _extract_waha_session_status(payload) -> str | None:
    if isinstance(payload, dict):
        try:
            return WAHASessionInfo.model_validate(payload).status
        except Exception:
            pass
        if "status" in payload:
            return str(payload["status"])
        if "state" in payload:
            return str(payload["state"])
        if payload.get("name") == settings.waha_session:
            return str(payload.get("status") or payload.get("state") or "present")
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                try:
                    session = WAHASessionInfo.model_validate(item)
                    if session.name == settings.waha_session:
                        return session.status or "present"
                except Exception:
                    if item.get("name") == settings.waha_session:
                        return str(item.get("status") or item.get("state") or "present")
        return "listed" if payload else "empty"
    return None


# ─── clientes inactivity threshold tab (D16, roadmap lead-card-hub-2026-08)
#
# Config is admin-gated (mirrors the Meta App tab's `_require_admin` on the
# write side; the read side is open to any authenticated org member — same
# split `get_meta_app_config_status` uses) and persisted per-org in
# `social_wiring.clientes_inactivity_config` (migration `058`), NOT in the
# app-wide encrypted `app_integration_config` store the Meta/Instagram App
# tabs above use — that store is documented, in its own migration header
# AND in `noctusai_lib.security.app_config`'s module docstring, as one row
# per config KEY for the WHOLE deployment, never per-org. This threshold
# genuinely varies per tenant (D16), so it gets its own tiny org_id-keyed
# table instead of a namespaced key jammed into a store that says, in
# writing, that it does not do that. See
# `app/services/clientes_inactivity_service.py`'s module docstring for the
# full reasoning + the unconfigured-vs-disabled (0) state split.


@router.get("/clientes-inactivity", response_model=ClientesInactivityConfigStatus)
def get_clientes_inactivity_config(
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> ClientesInactivityConfigStatus:
    """Current effective threshold for this org — the sweep's own default
    fallback when unconfigured, or the org's own stored value."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    resolved = clientes_inactivity_service.get_threshold_config(
        client, org_id, default_days=cfg.clientes_inactivity_threshold_days_default
    )
    return ClientesInactivityConfigStatus(
        threshold_days=resolved["threshold_days"],
        configured=resolved["configured"],
        default_threshold_days=cfg.clientes_inactivity_threshold_days_default,
    )


@router.put("/clientes-inactivity", response_model=ClientesInactivityConfigStatus)
def update_clientes_inactivity_config(
    payload: ClientesInactivityConfigUpdate,
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> ClientesInactivityConfigStatus:
    """Admin-gated write for the org's inactivity threshold.
    `threshold_days=0` explicitly disables the sweep for this org — a
    valid, intentional value, not an error (see `ClientesInactivityConfigUpdate`'s
    docstring)."""
    user, _token, raw_org = auth
    _require_admin(user, "Clientes inactivity threshold")
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    clientes_inactivity_service.set_threshold_days(client, org_id, payload.threshold_days)
    return ClientesInactivityConfigStatus(
        threshold_days=payload.threshold_days,
        configured=True,
        default_threshold_days=cfg.clientes_inactivity_threshold_days_default,
    )


# ─── document retention policy tab (migration 079)
#
# Same read-open / write-admin-gated split every other org-scoped config on
# this router uses. The read is open because a corretor should be able to see
# how long the agency keeps a buyer's income tax return — that is the kind of
# fact LGPD art. 9 says a data subject can ask about, and an answer nobody in
# the office can look up is not an answer.
#
# 🔴 The write is admin-gated AND the table has no authenticated write policy
# (079). Two independent gates on purpose: shortening a retention period
# DELETES FILES on the next sweep, so a leaked non-admin token must not be one
# missing decorator away from erasing a deal's paperwork.


@router.get("/documento-retencao", response_model=DocumentoRetencaoLista)
def get_documento_retencao(
    auth: tuple = Depends(get_current_user_org),
) -> DocumentoRetencaoLista:
    """Every document type's effective retention for this org."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    items = [
        DocumentoRetencaoPolitica(**p)
        for p in documento_retencao.politicas(client, org_id)
    ]
    return DocumentoRetencaoLista(items=items, total=len(items))


@router.put("/documento-retencao", response_model=DocumentoRetencaoLista)
def update_documento_retencao(
    payload: DocumentoRetencaoUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> DocumentoRetencaoLista:
    """Admin-gated override for one document type.

    Returns the WHOLE list rather than the single changed row: the screen
    renders every type together and a partial response would leave it
    reconciling by hand — which is where an optimistic-update bug lives.
    """
    user, _token, raw_org = auth
    _require_admin(user, "Retenção de documentos")
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    documento_retencao.definir(
        client,
        org_id,
        payload.superficie,
        payload.tipo_documento,
        payload.retencao_dias,
        # Same accessor the card's document routes use — the seed's user
        # object exposes `id`, and attributing the change matters here: a
        # shortened retention is a deletion decision.
        usuario_id=getattr(user, "id", None),
        motivo=payload.motivo,
    )
    items = [
        DocumentoRetencaoPolitica(**p)
        for p in documento_retencao.politicas(client, org_id)
    ]
    return DocumentoRetencaoLista(items=items, total=len(items))


@router.delete("/documento-retencao", response_model=DocumentoRetencaoLista)
def reset_documento_retencao(
    superficie: str = Query(...),
    tipo_documento: str = Query(...),
    auth: tuple = Depends(get_current_user_org),
) -> DocumentoRetencaoLista:
    """Admin-gated restore of the platform default for one type."""
    user, _token, raw_org = auth
    _require_admin(user, "Retenção de documentos")
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    documento_retencao.restaurar(client, org_id, superficie, tipo_documento)
    items = [
        DocumentoRetencaoPolitica(**p)
        for p in documento_retencao.politicas(client, org_id)
    ]
    return DocumentoRetencaoLista(items=items, total=len(items))


# Re-export both routers — main.py registers them via routers=[...].
__all__ = ["router"]


# ─── API keys tab — operator-settable, encrypted, per-org ──────────────
# Additive to the read-only `/keys/status` health view above: those are
# the DEPLOYMENT's .env values; these three are set by the operator in
# the UI, Fernet-encrypted into `social_wiring.credentials`, and read
# back by the certidões / matrículas workflows through
# `api_keys_store.resolve_api_key`.
#
# Same idiom as the Meta / Instagram app-config pair: admin-gated write,
# write-only secret (never echoed), masked "currently set" hint, and a
# read path that survives a missing ENCRYPTION_KEY because the platform
# tier can still answer.
def get_api_key_store_dep():
    """DI seam for the WRITE paths — maps a missing/malformed
    ``ENCRYPTION_KEY`` to a 503 config-gap rather than persisting
    plaintext. Tests override with a ``FakeCredentialStore``."""
    try:
        return build_api_key_store()
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


def get_api_key_store_optional_dep():
    """Same store for the READ paths, ``None`` instead of raising when
    ``ENCRYPTION_KEY`` is missing/malformed — an unconfigured Fernet key
    is a valid state there (platform-tier-only resolution)."""
    try:
        return build_api_key_store()
    except EncryptionNotConfigured:
        return None


def _api_key_spec_or_404(key: str) -> ApiKeySpec:
    spec = get_api_key_spec(key)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{key}' não é uma chave gerenciável. "
                f"Disponíveis: {', '.join(MANAGED_API_KEYS)}."
            ),
        )
    return spec


def _api_key_status(spec: ApiKeySpec, org_id, store) -> ApiKeyStatus:
    """Resolve one key and project it onto the wire shape — value out,
    only a masked hint in."""
    resolution = resolve_api_key_detail(spec.name, str(org_id), store=store)
    return ApiKeyStatus(
        key=spec.name,
        label=spec.label,
        description=spec.description,
        is_secret=spec.is_secret,
        testable=spec.testable,
        input_type=spec.input_type,
        placeholder=spec.placeholder,
        configured=resolution.configured,
        hint=mask_api_key_value(resolution.value, spec),
        source=resolution.source,
        updated_at=resolution.updated_at,
    )


@router.get("/api-keys", response_model=ApiKeysStatus)
def list_api_keys(
    auth: tuple = Depends(get_current_user_org),
    store=Depends(get_api_key_store_optional_dep),
) -> ApiKeysStatus:
    """Which managed keys this org has, and from WHERE.

    Read is open to any authenticated org member (same split every other
    org config on this router uses — only the write is admin-gated).
    Never returns a secret: `hint` is a last-4 tail for secrets, the
    plain value only for the non-secret e-mail field.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    items = [_api_key_status(spec, org_id, store) for spec in API_KEY_SPECS]
    return ApiKeysStatus(items=items, total=len(items))


@router.put("/api-keys/{key}", response_model=ApiKeyStatus)
def update_api_key(
    key: str,
    payload: ApiKeyUpdate,
    auth: tuple = Depends(get_current_user_org),
    store=Depends(get_api_key_store_dep),
) -> ApiKeyStatus:
    """Admin-gated write. Encrypts + upserts into
    ``social_wiring.credentials`` under provider ``api_key:<key>``.

    Write-only: the response is the recomputed status, never the value.
    A blank value is a 422 from the schema rather than a silent delete.
    """
    user, _token, raw_org = auth
    _require_admin(user, "Chaves de API")
    spec = _api_key_spec_or_404(key)
    org_id = coerce_org_uuid(raw_org)

    value = payload.value.strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe um valor. Para limpar a chave, use remover.",
        )
    put_api_key(store, str(org_id), spec.name, value)
    logger.info(
        "api_keys: %s updated for org %s by %s",
        spec.name,
        org_id,
        getattr(user, "id", "unknown"),
    )
    return _api_key_status(spec, org_id, store)


@router.delete("/api-keys/{key}", response_model=ApiKeyStatus)
def remove_api_key(
    key: str,
    auth: tuple = Depends(get_current_user_org),
    store=Depends(get_api_key_store_dep),
) -> ApiKeyStatus:
    """Admin-gated removal of this org's LOCAL override.

    Returns the RE-RESOLVED status on purpose: the platform / env tier
    may still answer, and a response that just said "removed" would tell
    the operator the key is gone when it is still live. `configured` +
    `source` in the body are what the UI says out loud.
    """
    user, _token, raw_org = auth
    _require_admin(user, "Chaves de API")
    spec = _api_key_spec_or_404(key)
    org_id = coerce_org_uuid(raw_org)

    removed = delete_api_key(store, str(org_id), spec.name)
    logger.info(
        "api_keys: %s local override %s for org %s",
        spec.name,
        "removed" if removed else "was already absent",
        org_id,
    )
    return _api_key_status(spec, org_id, store)


async def _test_openai_key(value: str) -> ApiKeyTestResult:
    """Probe an OpenAI key with a one-token chat completion.

    Ported from `erp-imobiliario`'s `_test_openai`, with ONE deliberate
    difference: it calls the API directly with the value we just
    resolved, instead of going through `noctusai_lib.integrations.llm`.
    The seed wrapper resolves its own key via the product's
    `LLMConfig.key_provider`, which today is the seed default
    (`resolve_credential` alone) — so it would probe a DIFFERENT key
    than the one the operator just saved here, and report a green test
    for a key that is not the one under test. Chat-completions rather
    than `/v1/models` because some scoped keys pass the latter and still
    cannot run inference (the reason ERP moved off it).
    """
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {value}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=20.0,
            )
    except Exception as exc:  # noqa: BLE001 — surfaced to the operator verbatim
        logger.warning("api_keys: OpenAI probe failed to connect (%s)", exc)
        return ApiKeyTestResult(
            key="openai_api_key", success=False, message=f"Erro de conexão: {exc}"
        )
    if resp.status_code == 401:
        return ApiKeyTestResult(
            key="openai_api_key",
            success=False,
            message="API Key inválida ou expirada.",
        )
    if resp.status_code == 429:
        # 429 is TWO different problems wearing one status code, and they take
        # opposite actions: "out of credit" (retrying never helps — someone has
        # to pay a bill) vs "too many requests just now" (waiting is the whole
        # fix). Reporting the raw status made the first look like the second —
        # seen in prod 2026-09-03, where "Erro inesperado: HTTP 429" gave the
        # operator no reason to check billing.
        body = (resp.text or "").lower()
        if any(s in body for s in ("insufficient_quota", "credit_balance_exhausted",
                                   "no credits remaining", "exceeded your current quota")):
            return ApiKeyTestResult(
                key="openai_api_key",
                success=False,
                message=(
                    "Sem créditos na conta OpenAI. A chave é válida, mas a conta "
                    "não tem saldo — adicione créditos em "
                    "platform.openai.com/settings/organization/billing. Sem isso, "
                    "matrículas digitalizadas e a análise de certidões por IA "
                    "não funcionam (PDFs com camada de texto continuam OK)."
                ),
            )
        return ApiKeyTestResult(
            key="openai_api_key",
            success=False,
            message="Limite de requisições atingido. Aguarde alguns minutos e teste novamente.",
        )
    if resp.status_code >= 400:
        return ApiKeyTestResult(
            key="openai_api_key",
            success=False,
            message=f"Erro inesperado: HTTP {resp.status_code}.",
        )
    return ApiKeyTestResult(
        key="openai_api_key", success=True, message="Conexão com OpenAI bem-sucedida."
    )


async def _test_infosimples_key(value: str) -> ApiKeyTestResult:
    """Probe an InfoSimples token via the lightweight PGFN consulta.

    Ported verbatim in behavior from `erp-imobiliario`'s
    `_test_infosimples`: a 4xx `code` in the JSON body is InfoSimples'
    way of reporting an auth failure (the HTTP status stays 200), so the
    body is what decides success.
    """
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                "https://api.infosimples.com/api/v2/consultas/receita-federal/pgfn",
                params={"token": value, "cpf": "00000000000", "timeout": "5"},
                timeout=20.0,
            )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — surfaced to the operator verbatim
        logger.warning("api_keys: InfoSimples probe failed (%s)", exc)
        return ApiKeyTestResult(
            key="infosimples_token", success=False, message=f"Erro de conexão: {exc}"
        )
    code = data.get("code") if isinstance(data, dict) else None
    if isinstance(code, int) and 400 <= code < 500:
        message = (
            data.get("message")
            or data.get("code_message")
            or f"Erro de autenticação (code: {code})"
        )
        return ApiKeyTestResult(
            key="infosimples_token", success=False, message=message
        )
    return ApiKeyTestResult(
        key="infosimples_token",
        success=True,
        message="Conexão com InfoSimples bem-sucedida.",
    )


_API_KEY_TESTERS = {
    "openai_api_key": _test_openai_key,
    "infosimples_token": _test_infosimples_key,
}


@router.post("/api-keys/{key}/test", response_model=ApiKeyTestResult)
async def test_api_key(
    key: str,
    auth: tuple = Depends(get_current_user_org),
    store=Depends(get_api_key_store_optional_dep),
) -> ApiKeyTestResult:
    """Live probe of the value that would actually be used.

    Resolves through the SAME two-tier chain the workflows use, so a
    green result means "the value this org's certidões run will pick up
    works" — not "some key somewhere works".
    """
    _user, _token, raw_org = auth
    spec = _api_key_spec_or_404(key)
    tester = _API_KEY_TESTERS.get(spec.name)
    if tester is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Teste não disponível para '{spec.name}'.",
        )
    org_id = coerce_org_uuid(raw_org)
    value = resolve_api_key_detail(spec.name, str(org_id), store=store).value
    if not value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{spec.label} não está configurada. "
                "Configure em Configurações → Chaves de API."
            ),
        )
    return await tester(value)
