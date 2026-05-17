"""
Social Wiring configuration.

Extends the framework's `ProductSettings` with the fields the YouTube /
SMTP / WAHA / Redis integrations need. Every value reads from `.env` so
keys never enter the repository.
"""
from noctusai_seed import ProductSettings


class SocialWiringSettings(ProductSettings):
    """Social Wiring settings — domain extensions on top of the framework
    baseline.

    All fields default to empty/safe values so the app boots without
    secrets configured. Endpoints that depend on a missing credential
    return 503 with a clear message; the unrelated parts of the app stay
    functional. See `routers/settings_router.py:get_keys_status` for the
    UI surface that reports configuration health.
    """

    cors_origins: str = "@registry:own:social-wiring"

    # ─── YouTube OAuth ─────────────────────────────────────────────────
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:8010/api/youtube/oauth/callback"
    frontend_base_url: str = ""

    # ─── OpenAI chatbot orchestration ─────────────────────────────────
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    # Whisper-tier model used by media_service.transcribe_audio. Default
    # is the small Whisper-compatible endpoint that handles voice notes
    # well at low cost; `whisper-1` also works.
    openai_audio_model: str = "gpt-4o-mini-transcribe"
    # Vision-capable chat model used by media_service.describe_image
    # and media_service._call_vision_multi. gpt-4o-mini works for
    # plain photos but misreads small text on scanned PDFs (CNH, ID
    # cards). gpt-4o is materially more accurate on documents and
    # video keyframes; cost is still reasonable for the volume the
    # bot handles.
    openai_vision_model: str = "gpt-4o"
    whatsapp_chatbot_enabled: bool = True

    # Fernet key for refresh-token-at-rest encryption. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # An empty value disables OAuth persistence — the YouTube tab on
    # Settings surfaces this loudly so the operator can't silently end up
    # with plaintext tokens in the DB.
    encryption_key: str = ""

    # ─── SMTP (email notifications) ────────────────────────────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""

    # ─── WAHA (WhatsApp notifications) ─────────────────────────────────
    # Empty waha_base_url → noctusai_lib.integrations.whatsapp.get_whatsapp_client
    # returns FakeWahaClient (logs-instead-of-sends). Safe for dev.
    waha_base_url: str = ""
    waha_api_key: str = ""
    waha_session: str = "default"
    waha_dashboard_url: str = "http://localhost:3000/dashboard"
    waha_webhook_url: str = ""
    waha_webhook_hmac_secret: str = ""

    # ─── Redis (upload-job tracking, Phase 2+) ─────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ─── Conversation buffer (seed-driven, Phase 5+) ───────────────────
    # Debounce window: how long the worker waits AFTER a WhatsApp inbound
    # before firing the LLM. New inbounds within this window reset the
    # timer, letting the bot react ONCE to a multi-message intent (code
    # in msg1, drive URL in msg2 seconds later). Lifted from the seed
    # default at ``noctusai_lib.domain.chatbot.ConversationBufferService``
    # which uses 8s — keep aligned so the seed-buffer test suite stays
    # representative.
    message_debounce_seconds: int = 8
    # How long a conversation's memory list lives in Redis after the last
    # touch. 1h is the seed default and matches the operator's expected
    # session duration (one property → 5-10 min conversation; idle past
    # 1h almost always means a new intent on the next contact).
    conversation_memory_ttl_seconds: int = 3600
    # Split the bot's reply on \n\n + send one WAHA message per paragraph
    # (with a brief inter-message delay) so the operator sees a chat-like
    # cadence instead of a single wall of text. Toggle off to revert to
    # the legacy single-message behavior.
    whatsapp_paragraph_split: bool = True
    # Inter-paragraph send delay in seconds. Small enough to feel snappy
    # but large enough that WAHA + WhatsApp's mobile clients render the
    # messages in order. 0.6s is the empirical sweet spot from manual
    # testing.
    whatsapp_paragraph_delay_seconds: float = 0.6
    # Interim debug pings during long uploads ("📥 Baixando do Drive…",
    # "📤 Subindo pro YouTube…"). Useful while debugging the pipeline;
    # turn off for production where the operator doesn't need the noise.
    whatsapp_progress_pings: bool = True
    # When true, the bot prompts "Confirma upload como X? (sim/não)"
    # before triggering the upload (default, human-in-the-loop on). Flip
    # to false to auto-proceed as soon as both code + Drive URL are
    # extracted from the buffered inbound. The env name expresses what
    # the flag GATES — the confirmation message — so true keeps it on.
    youtube_auto_confirmation_message: bool = True
    # Max uploads in flight simultaneously across the whole product.
    # 1 == global single-flight (current default, safest for YT quota).
    # Bump to 2-3 when traffic grows + YT per-channel concurrent limit
    # allows. Higher values risk quotaExceeded bursts.
    upload_max_concurrent: int = 1
    # How long a cached Drive download stays usable for retry/resume,
    # in hours. After this, the file is re-downloaded fresh. Keep modest
    # — disk fills up otherwise. Cache also evicts when the local file
    # is missing (cleanup, manual rm, etc.).
    download_cache_ttl_hours: int = 24
    # Optional listing-page URL template. ``{code}`` is substituted with
    # the property's ONE code (e.g. ``ONE7360``) when composing
    # post-upload notifications + the WhatsApp completion message.
    # Leave empty to omit the "📋 Anúncio" line.
    listing_url_template: str = ""
    # WhatsApp number the bot links to for "talk to the agent" CTAs in
    # the post-upload message. ``wa.me/<digits>`` shape; the bot strips
    # non-digits. Single number for v1; per-agent routing is a future
    # improvement (per the operator's "for now let's keep one number"
    # direction).
    default_agent_whatsapp: str = ""

    # ─── Database backend ─────────────────────────────────────────────
    # Production keeps using the seed Supabase module. Local development
    # can set DATABASE_BACKEND=sqlite to use the product-local SQLite
    # adapter and migrations instead.
    database_backend: str = "supabase"
    sqlite_path: str = "tmp/dev.sqlite3"
    local_dev_org_id: str = "00000000-0000-4000-8000-000000000001"
    local_dev_user_id: str = "00000000-0000-4000-8000-000000000001"

    # ─── CRM (real estate property lookup, Phase 5) ────────────────────
    crm_base_url: str = ""
    crm_api_key: str = ""
    # Vista aliases. In local/dev deployments these are copied from the
    # NoctusAI root .env; CRMService consumes crm_* after model_post_init
    # maps the aliases.
    vista_base_url: str = ""
    vista_api_key: str = ""

    # ─── WhatsApp inbound (Phase 5) ────────────────────────────────────
    # Comma-separated E.164 phone numbers authorized to trigger uploads
    whatsapp_authorized_numbers: str = "+5511974693365"

    # ─── Cloudflare tunnel (Phase 5) ───────────────────────────────────
    # Set to the tunnel URL (e.g. https://random-words.trycloudflare.com)
    # to automatically add it to CORS allowed origins.
    tunnel_hostname: str = ""

    # ─── Google Calendar (ported from whatsapp-google-scheduling) ─────
    # OAuth path: full attendee-supporting flow. Requires a Google Cloud
    # Console OAuth client + user consent. Stored credentials live in
    # `social_wiring.credentials` keyed by (org_id, 'google_calendar').
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # Where Google should redirect after consent. Synced by
    # `refresh_cf_tunnel.sh` to the tunnel URL + /api/calendar/oauth/callback
    # when running behind the proxy.
    google_oauth_redirect_uri: str = "http://localhost:8010/api/calendar/oauth/callback"
    # Scope resolution strategy (parallels META_OAUTH_SCOPES):
    #   "auto" (default) — use GOOGLE_KITCHEN_SINK_SCOPES (Calendar +
    #     Drive + identity, covers every adapter this product ships).
    #   "a b c" / "a,b,c" — pin to a specific space- or comma-separated
    #     list of full Google scope URLs.
    # IMPORTANT: every scope in the list must also be added to the GCP
    # Console OAuth Consent Screen — Google blocks scopes that aren't
    # configured there. See /api/google/scopes for live introspection.
    google_oauth_scopes: str = "auto"

    # Display-only — the email the OAuth consent will be granted as.
    # Matches whatsapp-scheduling's env var so the .env copies cleanly.
    google_oauth_account_email: str = ""

    # Service-account path: no attendee support on personal-Gmail
    # calendars but doesn't need the OAuth dance. Point at a readable
    # JSON file or leave blank.
    google_service_account_file: str = ""

    # Default calendar id the chatbot writes to / reads from when the
    # user doesn't specify. "primary" works for OAuth-user calendars;
    # service-account flows usually use a calendar id like
    # `<random>@group.calendar.google.com`.
    google_calendar_default_id: str = "primary"

    # Default IANA timezone for calendar events when not specified.
    google_calendar_default_timezone: str = "America/Sao_Paulo"

    # ─── Google Maps Routes API ────────────────────────────────────────
    # Plain API key (X-Goog-Api-Key header). Same key works for the
    # Routes API + Geocoding API + Places API; the chatbot's
    # `travel_estimate` tool only hits Routes.
    google_maps_api_key: str = ""

    # ─── Meta (Facebook + Instagram) read-only Graph API ──────────────
    # OAuth path:
    #   1. Operator creates a Meta app at developers.facebook.com
    #   2. Adds Facebook Login + Instagram Graph API products
    #   3. Registers META_OAUTH_REDIRECT_URI as a valid OAuth redirect
    #   4. Sets APP_ID + APP_SECRET below
    #   5. Visits /api/meta/oauth/start to consent
    # The stored credential row lives in `social_wiring.credentials`
    # keyed by (org_id, 'meta'); the same CredentialStore the
    # YouTube + Calendar OAuth flows use.
    meta_app_id: str = ""
    meta_app_secret: str = ""
    # System User Token — PRODUCTION-GRADE auth for backend automation
    # against Business Portfolio-owned assets. When set, this token is
    # used INSTEAD of the OAuth flow (which can't see BM-owned Pages in
    # modern Meta dev mode). Generate in BM Settings → Usuários do
    # sistema → [new user] → Gerar token → pick the app + scopes.
    # Long-lived (never expires while the System User has access).
    meta_system_user_token: str = ""
    meta_oauth_redirect_uri: str = "http://localhost:8010/api/meta/oauth/callback"
    # Graph API version pinned per release. v21.0 is the current stable
    # as of Jan 2026; v22.0 ships in May 2026. Pin explicitly so a
    # silent upstream rollout doesn't break us.
    meta_graph_api_version: str = "v21.0"
    # Scope resolution strategy:
    #   "auto" (default) — discover from /{app-id}/permissions at OAuth
    #     start time, fall back to META_KITCHEN_SINK_SCOPES (full
    #     read+write set covering all common Use Cases) when Graph
    #     returns empty. No manual maintenance.
    #   "a,b,c,..." — pin to a specific comma-separated list.
    # The /api/meta/scopes endpoint shows what's configured, what
    # Graph reports, and (after consent) what the user granted.
    meta_oauth_scopes: str = "auto"

    def model_post_init(self, __context) -> None:
        """Append tunnel hostname to CORS origins so the seed's CORS
        middleware picks it up without any framework changes."""
        super().model_post_init(__context)
        if self.tunnel_hostname:
            tunnel = self.tunnel_hostname.rstrip("/")
            if tunnel not in self.cors_origins:
                self.cors_origins = f"{self.cors_origins},{tunnel}"
        if not self.crm_base_url and self.vista_base_url:
            self.crm_base_url = self.vista_base_url
        if not self.crm_api_key and self.vista_api_key:
            self.crm_api_key = self.vista_api_key


settings = SocialWiringSettings()
