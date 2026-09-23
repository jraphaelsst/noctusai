"""
IgIg configuration.

Extends the framework's ProductSettings — minimal additions to support
the inherited skeletons (webhook receiver, etc.).
"""
from noctusai_seed import ProductSettings


class IgIgSettings(ProductSettings):
    """IgIg specific settings."""

    cors_origins: str = "@registry:own:igig"

    # ── Webhook receiver (consumed by app/routers/webhook_router.py) ──
    # Empty by default → ``webhook_endpoint(bypass_when_unset=True)``
    # accepts unsigned payloads with a WARNING (early-dev only). Set in
    # ``.env`` (``EXAMPLE_WEBHOOK_SECRET=…``) to enforce verification.
    # Rename per vendor (``resend_webhook_secret`` / ``meta_webhook_secret`` / etc.).
    example_webhook_secret: str = ""

    # ── Signature-provider webhook (routers/comercial_router.py) ──────
    # HMAC-SHA256 (hex, `X-Webhook-Hmac-SHA256`) of the raw body. EMPTY ⇒ the
    # webhook refuses every call (401): it activates contracts, so there is no
    # unsigned early-dev mode. Deliberately NOT in `required_prod_config` yet —
    # declaring a key that is absent from the prod .env turns a refused
    # webhook into a refused BOOT (see app/main.py's note); add it there once
    # the provider integration (NOC-REMEDIATE[igig-assinatura]) sets it.
    igig_assinatura_webhook_secret: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    webhook_rate_limit: str = "60/minute"

    # ── Cofre de Acessos (Módulo 2) ───────────────────────────────────
    # Fernet key for client credentials at rest. Deliberately EMPTY by
    # default: with no key the vault refuses to store a password rather than
    # silently falling back to plaintext. Generate with
    # `noctusai_lib.security.encrypted_tokens.generate_key()` and keep it
    # OUT-OF-BAND from the database — a key stored beside the ciphertext
    # protects nothing.
    igig_cofre_key: str = ""

    # ── Visual assets (Módulo 4 portal) ───────────────────────────────
    # "supabase" in production; "local" for native dev; "fake" in tests.
    igig_storage_kind: str = "supabase"
    igig_storage_root: str = "var/assets"
    igig_storage_bucket: str = "igig"
    # Card-hub documents (cliente + negócio cards, app/card_hub.py). A SEPARATE
    # private bucket on purpose: 019 grants org members read/write on their own
    # org folder of THIS bucket only, so `igig` (peças/logos) stays
    # service-role-only exactly as before (tech-lead decision 2026-09-23).
    igig_cardhub_bucket: str = "igig-cardhub"

    # ── Canais sociais (Módulo 5) ─────────────────────────────────────
    # Env-level FALLBACK only. The real path is a per-org credential stored
    # encrypted in `igig.integracao` and set through the Integrações screen —
    # an agency serves many clients' accounts, so one global token per channel
    # cannot be the primary model. Empty ⇒ the publisher stays the Fake and
    # nothing is ever reported as published.
    igig_meta_token: str = ""
    igig_tiktok_token: str = ""
    igig_linkedin_token: str = ""

    # ── E-mail: SMTP platform fallback (wave-2 slice B, roadmap R7) ────
    # The PRIMARY path is a per-org SMTP account set on the Integrações page
    # (`integracao` canal `smtp`, password Fernet-encrypted with the cofre).
    # These are the EXPLICIT platform fallback for an org that set none — used
    # loudly (logged + surfaced as `origem: "plataforma"`), never silently.
    # Empty host/user/password ⇒ no fallback ⇒ sending refuses with 409.
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    # "ssl" | "starttls". Empty ⇒ derived from the port (465 ⇒ ssl, else starttls).
    smtp_security: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = ""

    # ── Gmail OAuth + reply watch (wave-2 slice B, roadmap R8) ─────────
    # The GCP OAuth app (shared with social-wiring's Gmail/Calendar flows).
    # Empty ⇒ `GET /api/integracoes/email/gmail/oauth/start` answers 503.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # Pub/Sub push for `users.watch` (KB § INTEGRATIONS/google.md § 5a).
    # ANY of the four empty ⇒ `configuracao_gcp_ok=false`, no watch is ever
    # attempted and the push webhook refuses (503) — never a fake success.
    #   GMAIL_PUSH_GCP_PROJECT     GCP project id owning the topic
    #   GMAIL_PUSH_TOPIC           topic id or full `projects/<p>/topics/<t>`
    #   GMAIL_PUSH_AUDIENCE        OIDC `aud` on the push subscription (the
    #                              webhook URL, conventionally)
    #   GMAIL_PUSH_SERVICE_ACCOUNT the SA email the subscription signs as
    gmail_push_gcp_project: str = ""
    gmail_push_topic: str = ""
    gmail_push_audience: str = ""
    gmail_push_service_account: str = ""

    # ── Fontes de lead + automações (slice E2, roadmap R11) ───────────
    # WAHA inbound webhook HMAC (hex SHA-256 of the raw body, header
    # `X-Webhook-Hmac-SHA256`), GLOBAL exactly like social-wiring's
    # `waha_webhook_hmac_secret` (the owner asked for WAHA "configured like
    # SW"). Empty ⇒ the per-org TOKEN in the URL is the only gate and every
    # delivery logs a WARNING — SW's same early-dev affordance.
    igig_waha_webhook_hmac_secret: str = ""
    # Meta Lead-Ads delivery signature (`X-Hub-Signature-256`) = the Meta APP
    # SECRET. Platform FALLBACK only: an org that runs its own Meta app stores
    # its own (encrypted) in Integrações › Meta Lead Ads. Neither set ⇒ every
    # delivery is refused (401) — a forged POST would write lead PII.
    igig_meta_app_secret: str = ""


settings = IgIgSettings()


def get_settings() -> IgIgSettings:
    """FastAPI dependency seam for settings.

    Tests override it (`app.dependency_overrides[get_settings]`) instead of
    patching the singleton. Callables that cannot declare a dependency (the
    `webhook_endpoint` secret resolvers) read it through
    `app.routers.lead_webhooks_router._cfg` — the same Class-A seam
    social-wiring's `_cfg_for_request` uses (KB § PATTERNS/backend/di-test-seam.md).
    """
    return settings
