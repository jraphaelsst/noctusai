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
            "Chave que permite à plataforma cobrar por cartão pela sua conta "
            "Stripe. No painel do Stripe: Desenvolvedores > Chaves de API > "
            "Chave secreta (começa com sk_). Sem ela, o pagamento por cartão "
            "não funciona."
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
            "Código que o Stripe usa para provar que os avisos de pagamento "
            "são mesmo dele. No painel do Stripe: Desenvolvedores > Webhooks > "
            "seu endpoint > Segredo de assinatura (começa com whsec_). Sem "
            "ele, os avisos de pagamento do Stripe são recusados e as "
            "assinaturas não são atualizadas."
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
            "Chave que permite à plataforma gerar cobranças Pix e boleto pela "
            "sua conta Asaas. No Asaas: Integrações > Chaves de API > gerar "
            "nova chave. Sem ela, não é possível cobrar por Pix ou boleto."
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
            "Senha que o Asaas envia junto de cada aviso de pagamento para "
            "provar que ele é verdadeiro. Você a define no Asaas, em "
            "Integrações > Webhooks > Token de autenticação, e cola o mesmo "
            "valor aqui. Sem ele, os avisos de pagamento do Asaas são "
            "recusados e os pagamentos não são confirmados."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
    ),
    ApiKeySpec(
        name="turnstile_secret_key",
        label="Cloudflare Turnstile Secret Key",
        description=(
            "Chave que valida a proteção contra robôs (captcha) do "
            "formulário público de inscrição. No painel da Cloudflare: "
            "Turnstile > seu site > Chave secreta. Sem ela, a proteção fica "
            "desligada e o formulário aceita qualquer envio, inclusive de "
            "robôs. Configure junto com a Site Key abaixo."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
        placeholder="0x...",
    ),
    ApiKeySpec(
        name="turnstile_site_key",
        label="Cloudflare Turnstile Site Key",
        description=(
            "Chave pública que mostra a verificação contra robôs (captcha) "
            "nos formulários de cadastro e assinatura. No painel da "
            "Cloudflare: Turnstile > seu site > Chave do site. Ela não é "
            "secreta: aparece para quem visita o site. Se a Chave secreta "
            "acima estiver preenchida e esta não, os formulários ficam "
            "indisponíveis."
        ),
        is_secret=False,
        testable=False,
        input_type="text",
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
