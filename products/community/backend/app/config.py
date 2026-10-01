"""
Community configuration.

Extends the framework's ProductSettings — minimal additions to support
the inherited skeletons (webhook receiver, etc.) plus module 2's
checkout / payments / Turnstile configuration.
"""
from noctusai_lib.integrations.payments.real_asaas import DEFAULT_BASE_URL as _ASAAS_DEFAULT_BASE_URL
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Community specific settings."""

    cors_origins: str = "@registry:own:community"

    # ── Slice C: org-scoped managed API keys + WhatsApp connections
    # (`app/routers/api_keys_router.py`, `app/routers/whatsapp_connections_
    # router.py`) — same mechanisms social-wiring's Slice A lifted to
    # `noctusai_lib.security.api_keys` / `noctusai_lib.integrations.
    # whatsapp.connection_store`. Fernet key for BOTH stores
    # (`community.credentials` + `community.whatsapp_connections`,
    # migration 011). Already present in the prod container (user
    # decision 2026-09-17) — empty here is the early-dev / fresh-clone
    # default, which 503s the write paths instead of persisting
    # plaintext (see `noctusai_lib.security.api_keys.require_fernet`).
    encryption_key: str = ""

    # ── Webhook receiver ──
    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    # Reused by module 2's payment webhooks (`/api/webhooks/stripe`,
    # `/api/webhooks/asaas`) and the WhatsApp webhook.
    webhook_rate_limit: str = "60/minute"

    # ── Public application form (contract §Aplicações, PUBLIC routes) ──
    # `GET /api/aplicacoes/formulario` and `POST /api/aplicacoes` are
    # genuinely unauthenticated — a human filling out a real form won't
    # hit this, so a tighter cap than the webhook default is fine.
    aplicacoes_rate_limit: str = "20/minute"

    # ── Module 2: payment gateways (community-m2-contract.md) ──
    # Reuses `noctusai_lib.integrations.payments` / `.checkout` verbatim —
    # no new gateway adapter. Empty keys route both factories to their
    # Fake ONLY when `payments_allow_fake` is on (see `app/services/checkout_service.py`'s
    # `_default_hosted_checkout_factory` / `_default_gateway`) — a fresh
    # clone boots and its tests pass with zero real credentials.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # A missing gateway key REFUSES (503) unless this is explicitly on.
    # Only the test harness / local dev set it (PAYMENTS_ALLOW_FAKE=true):
    # a silent Fake in a real deploy would show a paying member a fake Pix
    # QR (closes NOC-REMEDIATE[community-gateway-fake-fallback]).
    payments_allow_fake: bool = False
    asaas_api_key: str = ""
    asaas_base_url: str = _ASAAS_DEFAULT_BASE_URL
    # Asaas' webhook auth is a bare shared-secret token in the
    # `asaas-access-token` header (see `noctusai_lib.integrations.
    # payments.webhook_events`'s module docstring) — NOT a signature, so
    # naming this `_token` (not `_secret`) matches that module's own
    # `asaas_webhook_token` parameter name.
    asaas_webhook_token: str = ""

    # ── Module 2: public checkout — PUBLIC route, rate-limited
    # separately from the webhook/aplicacoes limiters above (contract
    # amendment A10) ──
    checkout_rate_limit: str = "20/minute"

    # ── Ninho Vazio, slice BE-A: public self-signup (CONTRACT.md §Identity,
    # `POST /api/cadastro`) — "rate-limit 5/min per IP". Tighter than
    # `checkout_rate_limit` on purpose: a legitimate visitor submits this
    # form once, ever.
    cadastro_rate_limit: str = "5/minute"

    # Stripe's Checkout Session REQUIRES both `success_url`/`cancel_url`
    # (`StripeHostedCheckout.create_checkout` raises without either) —
    # the public `/assinar` page (contract §Frontend) is where the payer
    # lands either way; `?status=` lets the FE render the right state
    # without a server round-trip.
    frontend_base_url: str = "http://localhost:8210"

    # ── Module 2: abuse control (contract amendment A10 + product
    # decision P2) — config values, never literals in the service ──
    # Reuse an existing 'iniciada' Asaas subscription younger than this
    # many minutes instead of creating a second gateway object.
    checkout_reuse_window_minutes: int = 30
    checkout_max_per_email_per_24h: int = 5
    checkout_max_per_org_per_hour: int = 100

    # ── Module 2: Cloudflare Turnstile (product decision P2) ──
    # Empty by default → `make_turnstile_verifier` returns
    # `FakeTurnstileVerifier` (early-dev bypass, same posture as the
    # webhook secrets above) — a missing `turnstile_token` still 403s.
    community_turnstile_secret: str = ""

    # ── Module 3: WhatsApp (community-m3-contract.md) ──
    # D4: community gets its OWN WAHA session on its OWN instance — a
    # separate container from the shared WAHA `default` session social-
    # wiring already owns. Empty `base_url` → `get_whatsapp_client()`
    # returns `FakeWahaClient` — which this product only USES when
    # `whatsapp_allow_fake` is on (see `resolve_community_waha_client`).
    community_waha_base_url: str = ""
    # No saved connection AND no `community_waha_base_url` → WAHA-dependent
    # routes REFUSE (503 `WHATSAPP_NAO_CONECTADO`) and `GET /api/whatsapp/
    # sessao` reports `NAO_CONFIGURADO` — unless this is explicitly on.
    # Only the test harness / local dev set it (WHATSAPP_ALLOW_FAKE=true):
    # a silent `FakeWahaClient` in a real deploy showed "Aguardando
    # pareamento" and marked broadcasts "Enviada" with nothing sent
    # (2026-10-01, community.noctusai.com). Mirrors `payments_allow_fake`.
    whatsapp_allow_fake: bool = False
    community_waha_api_key: str = ""
    community_waha_session: str = "default"
    community_waha_external_base_url: str = ""
    # Contract §3 item 19: "HMAC required (the secret is always set in
    # prod)". Empty by default (early-dev bypass); set in `.env` to enforce.
    community_waha_webhook_hmac_secret: str = ""

    # D2 caps — config values, never literals in the service.
    lote_max_itens: int = 20
    lote_chunk: int = 5
    lotes_aplicados_max_dia: int = 5
    lote_expira_horas: int = 24

    # D1: message text IS stored by default (AI-flagged moderation with a
    # human acting is impossible without it). `"metrica"` leaves
    # `conteudo` NULL — the right default for a deployment that doesn't
    # want AI moderation.
    modo_ingest: str = "moderacao"


settings = SeedSettings()
