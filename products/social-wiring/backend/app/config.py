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
    youtube_redirect_uri: str = "http://localhost:8011/api/youtube/oauth/callback"
    # When set, derives youtube/google_oauth/meta redirect URIs from
    # this base + canonical paths — collapses 3 env vars into 1 for the
    # tunneled-dev OAuth workflow (e.g. OAUTH_REDIRECT_BASE_URL=
    # https://abc.trycloudflare.com → all 3 URIs auto-route through the
    # tunnel; matching consents must be registered in Google Cloud
    # Console). Empty (default) ⇒ falls back to `tunnel_hostname` if
    # set, else the 3 per-URI defaults stand (today's behavior).
    # Per-URI env vars (YOUTUBE_REDIRECT_URI / GOOGLE_OAUTH_REDIRECT_URI
    # / META_OAUTH_REDIRECT_URI) still override individually when the
    # base is empty. See `redirect_uri` resolution in `model_post_init`.
    oauth_redirect_base_url: str = ""
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

    # Fernet key (SEC-3, erp-httponly-cookie-session-2026-07 roadmap)
    # encrypting the httpOnly-cookie-session's Supabase refresh token +
    # cached access token at rest in the SHARED FLEET Redis (the same
    # instance `redis_url` below points at — also used by the LLM cache
    # + rate-limiter, so a plaintext refresh token there is a
    # single-Redis-read full-impersonation harvest). Generate the SAME
    # way as `encryption_key` above. Empty (default) is safe ONLY while
    # `redis_url` is unset/unreachable and the auth router falls back to
    # the in-memory `FakeSessionStore` — the moment `redis_url` resolves
    # to a real reachable Redis (it does by DEFAULT below), the seed's
    # `noctusai_seed.auth_router.get_session_store(settings)` (shared by
    # this product's OWN `get_auth_context` composition AND the
    # promoted `/api/auth/{login,me,logout}` router) calls
    # `make_session_store(require_encryption=True)`, which REFUSES to
    # boot a Redis-backed store without this key — fail loudly rather
    # than silently store plaintext impersonation credentials. MUST be
    # set (env var `REDIS_SESSION_ENCRYPTION_KEY`) in every real
    # deployment. Named `redis_*` (not just `session_*`) to disambiguate
    # from the sibling `encryption_key` above — the two are unrelated and
    # are routinely confused.
    redis_session_encryption_key: str = ""

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

    # ─── WhatsApp inbox history backfill (whatsapp-realtime-inbox W4.6) ──
    # Walks every connection's chats via the WAHA NOWEB store and persists
    # history into Postgres so a reopened chat isn't empty until the next
    # live message arrives. Runs on the shared seed APScheduler
    # (`noctusai_lib.api.scheduler`), registered from
    # `app.services.whatsapp_backfill.configure()`.
    whatsapp_backfill_enabled: bool = True
    # How far back to pull, in days. Combined with
    # `whatsapp_backfill_max_messages_per_chat` below (90 days OR 500
    # messages, whichever bound is hit first per chat).
    whatsapp_backfill_days: int = 90
    whatsapp_backfill_max_messages_per_chat: int = 500
    # How many chats to scan per connection per run — bounds one run's WAHA
    # call volume; a connection with more chats than this gets the rest on
    # a later run (list_chats orders by recent activity, so the most
    # relevant chats land first).
    whatsapp_backfill_chat_limit: int = 50
    # Interval between scheduled runs. A chat already backfilled once
    # (`whatsapp_chats.synced_through IS NOT NULL`) is skipped on
    # subsequent runs — see the module docstring for why this is a
    # one-shot-per-chat backfill, not true incremental catch-up.
    whatsapp_backfill_interval_hours: int = 6

    # ─── clientes steady-state pass (lead-card-hub Phase 1) ────────────
    # `clientes_service.run_backfill` is idempotent and re-runnable by
    # design, but for its first five days in prod nothing re-ran it: new
    # intake accumulated with no `cliente_touches` row and the board
    # silently stopped showing arrivals. This job closes that (see
    # `app/services/clientes_backfill_job.py` for the measurements).
    clientes_backfill_enabled: bool = True
    # 6h matches the sibling whatsapp_backfill sweep. Drift accrues at
    # roughly nine leads/day, so a 6h interval bounds the board's lag at a
    # couple of cards; a shorter interval would re-scan ~13k source rows
    # for no practical gain.
    clientes_backfill_interval_hours: int = 6

    # ─── clientes inactivity sweep (D16, roadmap lead-card-hub-2026-08) ─
    # `048` (P1.1) added `clientes.ativo`/`inativo_em`/`arquivado_em` and a
    # manual restore path, but nothing ever SET `inativo_em` automatically
    # — the working Ativos/Inativos tabs made this look finished, which is
    # exactly why the gap stayed open five days after Phase 1 shipped. See
    # `app/services/clientes_inactivity_service.py` for the sweep this
    # closes and `058_clientes_inactivity_sweep.sql` for its schema.
    clientes_inactivity_sweep_enabled: bool = True
    # The org-level default. D16 originally shipped this at 180 days;
    # raised to 365 on 2026-08-18 after the live measurement in
    # `migrations/APPLIED.md` showed 180 would sweep 70% of the ~10 200
    # live `clientes` inactive on the very first tick (365 sweeps 46%) —
    # see `migrations/059_clientes_inactivity_default_365.sql` for the
    # matching DB-column-default change. An org's OWN configured value
    # (`clientes_inactivity_config.threshold_days`, settable via
    # `PUT /api/settings/clientes-inactivity`) always wins when present;
    # this is only the fallback for an org that has never configured one.
    # Not itself editable in the UI — the per-org override is (D16); the
    # platform default is a deploy-time constant, changed here.
    clientes_inactivity_threshold_days_default: int = 365
    # Same interval as the sibling `clientes_backfill` sweep (6h) — no
    # reason for inactivity detection to lag behind or run more often than
    # the pass that actually attaches new touches.
    clientes_inactivity_sweep_interval_hours: int = 6

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
    google_oauth_redirect_uri: str = "http://localhost:8011/api/calendar/oauth/callback"
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
    # Meta Ads console (roadmap `meta-ads-console-2026-07`) — the single
    # Business-Portfolio-owned ad account the System User token above
    # reads. Bare id or `act_`-prefixed; the seed adapter normalizes
    # either form internally (see `AdAccount`'s docstring in
    # `noctusai_lib.integrations.meta.types`). Empty ⇒ every
    # `/api/meta/ads/*` route that needs an account returns a 503
    # "not configured" — never a silent zeros dashboard.
    meta_ad_account_id: str = ""
    # The SINGLE org (tenant) the workspace-global System User ad account
    # above belongs to. The token + `meta_ad_account_id` are workspace-
    # global (one Business-Portfolio account), but the ads_* tables are
    # org-scoped by RLS — so the daily sync must write into exactly ONE
    # org, not fan out across every tenant in `noctus_users` (that would
    # leak the operator's private ad spend into other tenants' RLS rows).
    # Empty ⇒ the daily scheduler SKIPS (safe-by-default — never a
    # fan-out); Phase 4 (multi-org ad accounts) replaces this single-value
    # setting with a per-org `integration_accounts` mapping.
    meta_ads_org_id: str = ""
    meta_oauth_redirect_uri: str = "http://localhost:8011/api/meta/oauth/callback"
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
    # Lead-Ads webhook handshake token. Meta GETs the callback URL once,
    # synchronously, when the operator clicks "Verify and Save" in the App
    # Dashboard: `?hub.mode=subscribe&hub.verify_token=<this>&hub.challenge=<x>`.
    # We echo `hub.challenge` back as PLAIN TEXT iff this value matches.
    #
    # 🔴 THIS IS NOT THE HMAC SECRET. Two different secrets, two different
    # jobs, and conflating them has already shipped as a bug once
    # (`products/erp-imobiliario/backend/app/routers/meta_api.py:70` resolves
    # the verify token as the signing secret, so that receiver can never
    # validate real Meta traffic):
    #   • THIS token   — invented by us, used ONCE on the GET handshake,
    #                    proves to META that we own the endpoint.
    #   • meta_app_secret — issued by Meta, used on EVERY POST, signs the raw
    #                    body into `X-Hub-Signature-256`, proves to US that
    #                    the POST really came from Meta.
    # Empty ⇒ the handshake always 403s (never a permissive default: an
    # empty-token match would let anyone register our endpoint).
    meta_webhook_verify_token: str = ""

    # ─── Grupo OLX portal leads (ZAP · VivaReal · OLX · ImovelWeb) ─────
    # Dev/local fallbacks for the app-wide config in
    # `app_integration_config` (prod stores these Fernet-encrypted; see
    # `app/services/app_config_store.resolve_olx_config`).
    #
    #   • olx_webhook_secret — the per-CRM key OLX sends back as the
    #                    second half of `Basic base64("vivareal:<key>")`.
    #                    ONE per CRM, not per advertiser. Empty ⇒ the
    #                    receiver 401s everything (bypass_when_unset=False):
    #                    an open endpoint that writes leads into a CRM is
    #                    worse than a receiver that is temporarily down.
    #   • olx_leads_org_id — single-tenant fallback for org resolution.
    #                    Unset ⇒ a lead whose clientListingId matches no
    #                    imovel parks as `unresolved` rather than being
    #                    guessed into someone's CRM.
    #   • olx_api_key / olx_agent_name — OUTBOUND Gestor de Leads
    #                    (`POST /v1/addLeads`), unrelated to the inbound
    #                    secret above.
    olx_webhook_secret: str = ""
    olx_leads_org_id: str = ""
    olx_api_key: str = ""
    olx_agent_name: str = ""

    # ─── ImovelWeb / OpenNavent portal leads (Navent · Grupo QuintoAndar) ─
    # A DIFFERENT vendor from Grupo OLX above, on its own pipe. Same
    # dev/local-fallback shape; prod resolves through
    # `app/services/app_config_store.resolve_imovelweb_config`.
    #
    #   • imovelweb_webhook_secret — WE choose this one; the vendor never
    #                    issues it. Registered with them as
    #                    `Basic base64("noctusai-imovelweb:<key>")`. Empty ⇒
    #                    the receiver 401s everything, same reasoning as OLX.
    #   • imovelweb_client_id / _secret — OAuth2 client credentials for the
    #                    OpenNavent API (reconciliation, callback config,
    #                    enrichment). Unrelated to the inbound secret.
    #   • imovelweb_leads_org_id — single-tenant fallback for org resolution,
    #                    the LAST rung of the chain. Unset ⇒ a lead whose
    #                    agency code and listing code both miss parks as
    #                    `unresolved` rather than landing in a guessed org.
    #   • imovelweb_region / _sandbox — which host. `sandbox` also gates the
    #                    event simulator, which refuses a production host.
    #   • imovelweb_callback_language — the registered `lenguajeCallbackBody`.
    #                    It decides the vendor's FIELD NAMES, not just its
    #                    prose. EN2 carries `leadOrigin` (portal attribution)
    #                    but no agency code; PT carries the agency code but no
    #                    `leadOrigin`. No variant carries both — Gate 1.7
    #                    settles which trade we take, and the parser
    #                    auto-detects regardless, so this is a default rather
    #                    than an assumption.
    #   • imovelweb_public_base_url — the URL we register as the receiver.
    #                    A localhost/tunnel value is REFUSED at registration:
    #                    the callback config is integrator-wide, so an
    #                    unreachable one blackholes every agency's leads with
    #                    no error anywhere.
    #   • imovelweb_verify_by_refetch — re-fetch each lead by messageId to
    #                    verify it. Default OFF: it is an upstream round-trip,
    #                    and the vendor allows 1.5s for the whole response.
    #                    Only ever a BACKGROUND step, never in the request.
    imovelweb_webhook_secret: str = ""
    imovelweb_client_id: str = ""
    imovelweb_client_secret: str = ""
    imovelweb_leads_org_id: str = ""
    imovelweb_region: str = "br"
    imovelweb_sandbox: bool = False
    imovelweb_callback_language: str = "EN2"
    imovelweb_public_base_url: str = ""
    imovelweb_verify_by_refetch: bool = False

    # ─── Instagram Business Login (Instagram-Login model) ──────────────
    # A SEPARATE app credential pair from meta_app_id/meta_app_secret
    # above — Instagram Business Login authenticates against its OWN
    # Instagram App ID/Secret (registered under "Instagram" in the Meta
    # developer dashboard, distinct from the "Facebook Login" app used by
    # the meta_* flow), and its token chain runs through
    # api.instagram.com / graph.instagram.com rather than
    # graph.facebook.com. See
    # `noctusai_lib.integrations.meta.instagram_login_adapter` +
    # `_meta_api.build_ig_authorize_url` / `exchange_ig_code_for_token` /
    # `exchange_ig_for_long_lived`.
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_oauth_redirect_uri: str = (
        "http://localhost:8011/api/integrations/accounts/instagram/oauth/callback"
    )

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
        # OAuth redirect URIs — derive from oauth_redirect_base_url (or
        # tunnel_hostname fallback) when set; preserves today's behavior
        # otherwise (per-URI defaults / env vars). The derivation always
        # wins when an explicit base is set — predictable, no surprise
        # mix of base + per-URI overrides. Same back-compat-defaulted
        # shape as the seed seams (KB § PATTERNS/absorbed-product-seed-shape-seam.md).
        oauth_base = self.oauth_redirect_base_url or self.tunnel_hostname
        if oauth_base:
            base = oauth_base.rstrip("/")
            self.youtube_redirect_uri = f"{base}/api/youtube/oauth/callback"
            self.google_oauth_redirect_uri = f"{base}/api/calendar/oauth/callback"
            self.meta_oauth_redirect_uri = f"{base}/api/meta/oauth/callback"
            self.instagram_oauth_redirect_uri = (
                f"{base}/api/integrations/accounts/instagram/oauth/callback"
            )


settings = SocialWiringSettings()
