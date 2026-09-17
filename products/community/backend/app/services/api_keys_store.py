"""Community's managed API keys — the product-local half of the
generic mechanism `noctusai_lib.security.api_keys` (lifted 2026-09-17
from `social-wiring`'s Slice A) provides.

WHAT LIVES HERE (product-specific, per that module's own docstring —
"WHAT STAYS PRODUCT-LOCAL"): which keys are managed (`API_KEY_SPECS`)
and the store factory bound to THIS product's admin client + schema
(`community.credentials`, migration 011). Zero crypto / DB code — both
delegate to the seed.

User decision 2026-09-17 ("community uses social-wiring's mechanisms",
Slice C): payments (Stripe/Asaas) + Cloudflare Turnstile, admin-only,
same shape as social-wiring's LLM-vendor keys.
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.security.api_keys import ApiKeySpec, build_api_key_store

from app.config import settings
from app.dependencies import get_admin_client

API_KEY_SPECS: tuple[ApiKeySpec, ...] = (
    ApiKeySpec(
        name="stripe_secret_key",
        label="Stripe Secret Key",
        description=(
            "Chave secreta da conta Stripe usada para criar assinaturas e "
            "processar pagamentos por cartão (Checkout hospedado)."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="sk_live_...",
    ),
    ApiKeySpec(
        name="stripe_webhook_secret",
        label="Stripe Webhook Signing Secret",
        description=(
            "Segredo de assinatura do webhook Stripe (`whsec_...`). Sem ele, "
            "todo webhook do Stripe é recusado com 401 (amendment A9 — "
            "nunca um bypass)."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
        placeholder="whsec_...",
    ),
    ApiKeySpec(
        name="asaas_api_key",
        label="Asaas API Key",
        description=(
            "Chave de API da conta Asaas usada para criar assinaturas e "
            "cobranças Pix/boleto."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="$aact_...",
    ),
    ApiKeySpec(
        name="asaas_webhook_token",
        label="Asaas Webhook Token",
        description=(
            "Token compartilhado enviado no header `asaas-access-token` de "
            "cada webhook Asaas — não é uma assinatura HMAC (ver "
            "`noctusai_lib.integrations.payments.webhook_events`). Sem ele, "
            "todo webhook do Asaas é recusado com 401."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
    ),
    ApiKeySpec(
        name="turnstile_secret_key",
        label="Cloudflare Turnstile Secret Key",
        description=(
            "Chave secreta do Cloudflare Turnstile usada para validar o "
            "captcha do formulário público de inscrição/checkout. Sem ela, "
            "a verificação roda em modo Fake (sempre aprova) — early-dev "
            "apenas."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
        placeholder="0x...",
    ),
)


def build_community_api_key_store(client: Optional[Any] = None):
    """Build the encrypted store `community.credentials` lives in.

    Validates `settings.encryption_key` loudly first (raises
    `EncryptionNotConfigured`, mapped to a 503 at the router boundary by
    `noctusai_seed.api_keys_router`). `client` defaults to the schema-
    scoped admin client — the RLS write policy on
    `community.credentials` is service-role only (migration 011).
    """
    return build_api_key_store(
        client if client is not None else get_admin_client(),
        encryption_key=settings.encryption_key,
        table="credentials",
    )
