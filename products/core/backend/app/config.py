"""
NoctusAI Core — Configuration settings.

Extends the seed framework's `ProductSettings` so env_file resolution,
jwt_secret defaults, and the production safety validator come from the
single authoritative source. Only core-specific fields live here.
"""
from typing import Optional

from noctusai_seed import ProductSettings
from noctusai_lib.config.csv_settings import parse_csv_setting


class Settings(ProductSettings):
    """Core platform specific settings."""

    # SSO token TTL — LOAD-BEARING: read by the seed's
    # `noctusai_lib.api.auth.create_sso_token` (`settings.sso_token_expiration_minutes`)
    # when core mints a cross-product SSO token. `jwt_expiration_minutes`
    # (sibling field, dropped here) had no such consumer.
    sso_token_expiration_minutes: int = 5  # short-lived

    # CORS — registry-driven union of every product frontend (core hosts the SSO bridge).
    # `@registry:all` resolves at property-read time via
    # `noctusai_lib.config.cors_registry.derive_cors_origins(include_all_frontends=True)`,
    # parsing `start.sh PRODUCTS` between BEGIN/END_PRODUCTS_REGISTRY sentinels.
    # New product added to `start.sh` → automatically allowed here. See
    # `KB § PATTERNS/environment.md § CORS_ORIGINS cascade`. Replaces the
    # hand-enumerated 13-origin string from CORE-ORIGINS (commit 04534f7).
    # Wildcard `"*"` is forbidden here: seed factory wires allow_credentials=True,
    # and `*` + credentials is the MDN-documented auth-replay anti-pattern.
    cors_origins: str = "@registry:all"

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    app_base_url: str = "http://localhost:5173"

    # Public origin Core's API is reachable at from the internet (gateway
    # webhooks). Empty → `app_base_url` (Core serves API + SPA on one host).
    public_api_base_url: str = ""

    # Fernet key for `public.app_integration_config` (gateway API keys and
    # webhook secrets entered in Admin > Faturamento). Empty → saving a key
    # answers 503; nothing is ever stored in plaintext.
    encryption_key: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    # Webhook-compliance pin #4 — see KB § PATTERNS/webhook-signatures.md.
    webhook_rate_limit: str = "60/minute"

    # Email (optional — Resend)
    resend_api_key: Optional[str] = None

    # Optional Postgres URL for SQLAlchemy-bound flows (audit-hook write side
    # effects for `public.tool_call_audits`). Empty → audit-hook lazy session
    # factory returns None and the audit writer skips with a debug log.
    # Routers/services use the Supabase admin client per `KB § PATTERNS/backend.md`
    # — the SQLAlchemy session is a SECONDARY surface, not the primary data path.
    # See `app/services/audit_hook.py` + `KB § PATTERNS/llm-tool-audit.md`.
    postgres_url: str = ""

    # ─── Website (noctusai.com) — projects/noctus-website, slice website-be ──
    # See `products/core/frontend/src/website/docs/15-api-contract.md`.

    # Host-split (contract D1): the website owns the apex; the app stays at
    # core.noctusai.com unchanged. Comma-separated, host-only (no scheme/port).
    website_hosts: str = "noctusai.com,www.noctusai.com"

    @property
    def website_hosts_list(self) -> list[str]:
        return parse_csv_setting(self.website_hosts, lower=True)

    # Any non-website path on a website host 301s here (contract §5.6).
    # Same value in dev and prod today (no local core.* alias) — kept as a
    # plain settings default rather than `deploy_config.resolve_config`
    # because it does not currently diverge between environments.
    core_app_origin: str = "https://core.noctusai.com"

    # Single-container mode: where the built website's prerendered output
    # lives (`<dir>/_site/manifest.json`, `<dir>/_site/settings.defaults.json`).
    # Mirrors `noctusai_seed.app._mount_spa`'s own `SERVE_SPA_DIR` resolution
    # (Dockerfile sets `SERVE_SPA_DIR=/app/products/core/frontend/dist`) but
    # exposed as a settings field — not a raw `os.environ.get(...)` — so
    # tests can override it via the config seam instead of monkeypatching
    # the environment (`KB § PATTERNS/backend/di-test-seam.md`).
    serve_spa_dir: str = ""

    # Lead fan-out (contract §3, "Side effects of POST /leads"). Each is
    # optional — an unset value skips that channel with a debug log, never
    # an error (contract: "Never silent, never blocks the 201").
    website_leads_notify_email: str = ""
    website_sales_whatsapp: str = ""
    website_leads_webhook_url: str = ""
    # Optional HMAC secret for the outbound webhook (10-conversion-and-
    # leads.md § Fan-out: "through the seed outbound_webhook (signed
    # payload)"). Empty → the POST is sent unsigned (n8n side can still
    # authenticate the endpoint URL itself if it's kept secret).
    website_leads_webhook_secret: str = ""

    # Cloudflare Turnstile for the public lead-capture forms. Empty →
    # `make_turnstile_verifier` returns the Fake (accepts any non-empty
    # token) — same early-dev-bypass posture as `community_turnstile_secret`.
    website_turnstile_secret: str = ""

    # WAHA (shared platform instance — same `WAHA_BASE_URL`/`WAHA_API_KEY`
    # env vars every other WAHA-consuming product reads; see `.env.example`
    # § WAHA). Empty `waha_base_url` → `get_whatsapp_client` returns
    # `FakeWahaClient` (logs instead of sends — safe for dev).
    waha_base_url: str = ""
    waha_api_key: str = ""
    waha_session: str = "default"


settings = Settings()
