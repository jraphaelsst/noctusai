"""Settings router — UI-side configuration surface.

Three tabs back this router:
  - YouTube (OAuth connect / disconnect / channel info)
  - Notifications (recipient CRUD)
  - API Keys (read-only health status)

The OAuth callback path lives at ``/api/youtube/oauth/callback`` — outside
the ``/settings`` prefix — because Google requires a fixed redirect URI;
moving it under settings would break existing OAuth-client configs.

Auth pattern: ``Depends(get_current_user_org)`` returning
``(user, token, raw_org_id)``. The user-scoped Supabase client is then
built via ``get_user_client(token)`` inside the route body — the seed's
``Depends(get_user_client)`` shape doesn't chain because its positional
``token`` arg becomes a required query parameter. See
``KB § PATTERNS/backend.md § Auth — canonical pattern``.
"""
from __future__ import annotations

import logging
import secrets
from urllib.parse import urljoin
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from noctusai_lib.integrations.whatsapp import chat_id_for_phone, get_whatsapp_client

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user,
    get_current_user_org,
    get_user_client,
)
from app.schemas.settings import (
    EmailTestRequest,
    EmailTestResult,
    KeyHealth,
    KeyStatusEntry,
    KeysStatus,
    RecipientCreate,
    RecipientOut,
    RecipientUpdate,
    VistaStatus,
    WahaStatus,
    WahaTestRequest,
    WahaTestResult,
    YouTubeAuthURL,
    YouTubeStatus,
)
from app.schemas.whatsapp import WAHASessionInfo, extract_waha_message_id
from app.services.chatbot_service import append_memory as _append_chat_memory
from app.services.crm_service import CRMNotConfigured, CRMService, CRMServiceError
from app.services.email_service import EmailNotConfigured, EmailService, EmailServiceError
from app.services.message_store import DuplicateMessage, MessageStore
from app.services.waha_response_registry import record_waha_sample
from app.services.credential_store import (
    CredentialStore,
    CredentialStoreError,
    EncryptionNotConfigured,
)
from app.services.youtube_service import (
    YouTubeNotConnected,
    YouTubeService,
    YouTubeServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])
oauth_router = APIRouter(prefix="/api/youtube/oauth", tags=["youtube-oauth"])


# ─── Construction helpers ──────────────────────────────────────────────
# (`coerce_org_uuid` lifted to app.dependencies at N=3 — see its docstring.)


def _build_credential_store(supabase) -> CredentialStore:
    """Build a CredentialStore from the request-scoped supabase client.

    A 503 is right when ENCRYPTION_KEY is missing — this is a config gap,
    not a server bug. The Settings → API Keys tab makes the gap visible.
    """
    try:
        return CredentialStore(supabase, settings.encryption_key)
    except EncryptionNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _build_youtube_service(supabase) -> YouTubeService:
    try:
        return YouTubeService(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            redirect_uri=settings.youtube_redirect_uri,
            credential_store=_build_credential_store(supabase),
        )
    except YouTubeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


# ─── YouTube tab ───────────────────────────────────────────────────────
@router.get("/youtube/status", response_model=YouTubeStatus)
def get_youtube_status(
    auth: tuple = Depends(get_current_user_org),
) -> YouTubeStatus:
    """Connection state + cached channel metadata. Never triggers a
    YouTube API call by itself — uses what was persisted at OAuth time
    + last channel sync. The Settings UI calls this on every page load,
    so making it free of YouTube API quota matters.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    store = _build_credential_store(supabase)
    record = store.get(org_id=org_id, provider="youtube")
    if record is None:
        return YouTubeStatus(connected=False)

    return YouTubeStatus(
        connected=True,
        channel_id=record.channel_id,
        channel_title=record.channel_title,
        scopes=record.scopes,
        connected_at=record.created_at,
    )


_PKCE_VERIFIER_KEY_PREFIX = "youtube:oauth:pkce:"
_PKCE_VERIFIER_TTL_SECONDS = 600  # 10 min — consent flows complete in seconds


def _pkce_redis_client():
    """Lazy Redis client for PKCE verifier round-trip.

    Returns ``None`` if redis is unreachable — the OAuth flow still
    works (Google just rejects the exchange with a clear error message)
    but we don't want to 500 the auth-url request just because Redis
    blipped."""
    try:
        import redis

        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:  # pragma: no cover — exercised in container only
        logger.warning("PKCE Redis unavailable: %s", exc)
        return None


@router.get("/youtube/auth-url", response_model=YouTubeAuthURL)
def get_youtube_auth_url(
    auth: tuple = Depends(get_current_user_org),
) -> YouTubeAuthURL:
    """Build the consent URL the user should be redirected to.

    The opaque ``state`` round-trips the org_id through Google's flow so
    the callback knows which tenant just connected — without trusting
    redirect_uri parsing alone (which a malicious caller could spoof if
    we relied on the session cookie alone for tenant binding).

    Google's library auto-generates a PKCE ``code_verifier`` per call,
    embeds the SHA256 challenge in the URL, and requires the verifier
    back at ``exchange_code`` time. We persist the verifier in Redis
    keyed by ``state`` (10-min TTL) so the callback handler can replay
    it without storing OAuth secrets in a cookie or in the database.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    yt = _build_youtube_service(supabase)
    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    auth_url, code_verifier = yt.get_auth_url(state=state)
    redis_client = _pkce_redis_client()
    if redis_client is not None and code_verifier:
        try:
            redis_client.set(
                f"{_PKCE_VERIFIER_KEY_PREFIX}{state}",
                code_verifier,
                ex=_PKCE_VERIFIER_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("failed to persist PKCE verifier: %s", exc)
    return YouTubeAuthURL(
        auth_url=auth_url,
        state=state,
    )


@router.delete(
    "/youtube/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def disconnect_youtube(
    auth: tuple = Depends(get_current_user_org),
) -> None:
    """Revoke + delete tokens. Idempotent — already-disconnected returns
    204 too, so the UI doesn't need separate handling for the rare race
    where two tabs both click Disconnect."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    supabase = get_user_client(token)
    yt = _build_youtube_service(supabase)
    yt.revoke_and_disconnect(org_id=org_id)


@oauth_router.get("/callback")
def youtube_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Google's redirect target. Exchanges ``code`` → tokens, fetches
    channel metadata, persists encrypted, then redirects to the frontend
    Settings page. Must live at the exact path registered as
    redirect_uri in the OAuth client config — relocating breaks every
    deployed install.

    Uses the admin (service-role) Supabase client because Google's
    redirect carries no Authorization header — there's no JWT to bind a
    user-scoped client to. Tenant binding is handled via the opaque
    ``state`` token (parsed below) so RLS bypass here is bounded by
    state-token validity, not blanket trust.
    """
    supabase = get_admin_client()
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth flow returned an error: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback missing code or state.",
        )

    org_part, _, _nonce = state.partition(":")
    if not org_part:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    try:
        org_id = UUID(org_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc

    yt = _build_youtube_service(supabase)
    store = _build_credential_store(supabase)

    # Replay the PKCE verifier that was persisted at auth-url time.
    # Missing → exchange will fail with `invalid_grant: Missing code
    # verifier` and the caller has to re-initiate the flow.
    code_verifier: str | None = None
    redis_client = _pkce_redis_client()
    if redis_client is not None:
        try:
            key = f"{_PKCE_VERIFIER_KEY_PREFIX}{state}"
            code_verifier = redis_client.get(key)
            if code_verifier:
                redis_client.delete(key)  # single-use
        except Exception as exc:
            logger.warning("failed to retrieve PKCE verifier: %s", exc)

    try:
        bundle = yt.exchange_code(code=code, code_verifier=code_verifier)
    except Exception as exc:
        logger.exception("youtube oauth exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {exc}",
        ) from exc

    # Persist before fetching channel info so a flaky channels.list call
    # doesn't lose the freshly-issued refresh_token. channel_id +
    # channel_title get filled on the first successful sync.
    store.upsert(
        org_id=org_id,
        provider="youtube",
        tokens=bundle,
        scopes=bundle.get("scopes", []),
    )

    try:
        info = yt.get_channel_info(org_id=org_id)
        store.upsert(
            org_id=org_id,
            provider="youtube",
            tokens=bundle,
            channel_id=info.channel_id,
            channel_title=info.title,
            scopes=bundle.get("scopes", []),
        )
    except YouTubeServiceError:
        logger.warning(
            "channel_info fetch failed during oauth callback for org_id=%s — "
            "tokens persisted, channel metadata will populate on next status read",
            org_id,
        )

    # Redirect back to the Settings page; the UI re-fetches /youtube/status
    # to surface the freshly-populated channel info.
    redirect_url = "/configuracoes?youtube=connected"
    if settings.frontend_base_url:
        redirect_url = urljoin(
            settings.frontend_base_url.rstrip("/") + "/",
            "configuracoes?youtube=connected",
        )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


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
) -> KeysStatus:
    """Show the operator which secrets are wired vs absent — never echoes
    the actual values back. The UI uses this to render configured /
    missing badges and prompt the user to fix .env when red."""
    return KeysStatus(
        youtube_client_id=_entry(
            settings.youtube_client_id, "YouTube Client ID",
            "Required for OAuth — issued by Google Cloud Console.",
        ),
        youtube_client_secret=_entry(
            settings.youtube_client_secret, "YouTube Client Secret",
            "Pairs with the Client ID. Keep secret.",
        ),
        youtube_redirect_uri=_entry(
            settings.youtube_redirect_uri, "YouTube Redirect URI",
            "Must match the OAuth-client redirect URI EXACTLY.",
        ),
        frontend_base_url=_entry(
            settings.frontend_base_url, "Frontend Base URL",
            "Where OAuth should return the operator after Google callback.",
        ),
        openai_api_key=_entry(
            settings.openai_api_key, "OpenAI API Key",
            "Required for the WhatsApp chatbot reasoning and tool orchestration layer.",
        ),
        openai_chat_model=_entry(
            settings.openai_chat_model, "OpenAI Chat Model",
            "Model used by the WhatsApp chatbot orchestration loop.",
        ),
        whatsapp_chatbot_enabled=_entry(
            str(settings.whatsapp_chatbot_enabled), "WhatsApp Chatbot",
            "When true and OpenAI is configured, WhatsApp uses GPT tool orchestration.",
        ),
        encryption_key=_entry(
            settings.encryption_key, "Encryption Key",
            "Fernet key used to encrypt refresh tokens at rest.",
        ),
        smtp_user=_entry(
            settings.smtp_user, "SMTP User",
            "Email address used as the From: header for notifications.",
        ),
        smtp_password=_entry(
            settings.smtp_password, "SMTP Password",
            "Gmail App Password (not the account password).",
        ),
        waha_base_url=_entry(
            settings.waha_base_url, "WAHA Base URL",
            "WAHA server base URL. Empty = FakeWahaClient (dev).",
        ),
        waha_api_key=_entry(
            settings.waha_api_key, "WAHA API Key",
            "Bearer token for WAHA. Required when WAHA Base URL is set.",
        ),
        waha_dashboard_url=_entry(
            settings.waha_dashboard_url, "WAHA Dashboard URL",
            "Human/browser URL for the local WAHA dashboard.",
        ),
        waha_webhook_url=_entry(
            settings.waha_webhook_url, "WAHA Webhook URL",
            "Public URL WAHA should call for inbound message webhooks.",
        ),
        waha_webhook_hmac_secret=_entry(
            settings.waha_webhook_hmac_secret, "WAHA Webhook Secret",
            "Optional shared secret for webhook hardening. Empty in local dev is allowed.",
        ),
        vista_base_url=_entry(
            settings.crm_base_url or settings.vista_base_url, "Vista Base URL",
            "Vista tenant REST base URL. Server-side only.",
        ),
        vista_api_key=_entry(
            settings.crm_api_key or settings.vista_api_key, "Vista API Key",
            "Vista API key. Server-side only; never expose as VITE_*.",
        ),
        database_backend=_entry(
            settings.database_backend, "Database Backend",
            "sqlite for local development, supabase for production.",
        ),
        supabase_url=_entry(
            settings.supabase_url, "Supabase URL",
            "Project URL. Only required when DATABASE_BACKEND=supabase.",
        ),
        supabase_service_role_key=_entry(
            settings.supabase_service_role_key, "Supabase Service Role Key",
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


# Re-export both routers — main.py registers them via routers=[...].
__all__ = ["router", "oauth_router"]
