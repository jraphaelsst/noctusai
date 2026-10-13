"""Commerce's managed keys -- the product-local half of `noctusai_lib.security.api_keys`.

The per-org Asaas API key, webhook token and environment choice live Fernet-encrypted in
`commerce.credentials` (written from the back office, never env). The names are the
organ's (`CommerceConfig.asaas_api_key_name` / `asaas_webhook_token_name` /
`asaas_environment_name`): the
organ's `AsaasCheckoutGateway` resolves them per org through the same store, so a
rename here without the config would silently disconnect the gateway.

Zero crypto / DB code here: the spec list, and the store bound to THIS product's
admin client. `ENCRYPTION_KEY` missing => READS degrade to the platform chain and
WRITES 503 (seed router); never plaintext.
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.integrations.payments.real_asaas import ASAAS_PRODUCTION, ASAAS_SANDBOX
from noctusai_lib.security.api_keys import ApiKeyOption, ApiKeySpec, build_api_key_store
from noctusai_lib.security.token_store import CredentialStore

from app.commerce import CFG
from app.config import settings
from app.dependencies import get_admin_client

API_KEY_SPECS: tuple[ApiKeySpec, ...] = (
    ApiKeySpec(
        name=CFG.asaas_api_key_name,
        label="Chave de API do Asaas",
        description=(
            "Chave que permite à loja gerar as cobranças (Pix, boleto ou cartão) na conta Asaas "
            "da sua empresa. No Asaas: Integrações > Chaves de API > gerar nova chave. Sem ela, o "
            "botão de compra fica indisponível."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="$aact_...",
    ),
    ApiKeySpec(
        name=CFG.asaas_webhook_token_name,
        label="Token do webhook do Asaas",
        description=(
            "Senha que o Asaas envia junto de cada aviso de pagamento para provar que ele é "
            "verdadeiro. Você a define no Asaas (Integrações > Webhooks > Token de autenticação) "
            "e cola o mesmo valor aqui. Sem ele, os pagamentos não são confirmados."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
    ),
    # The environment the org's Asaas key belongs to (a sandbox key fails against production and
    # vice versa). Default SANDBOX, for safety: an org that never touched this setting must not move
    # real money by accident -- selling for real is an explicit choice the admin makes here (store
    # precedent). The default is the organ's own (`CFG.asaas_default_environment`), so the screen and
    # the gateway can never disagree on what "unset" means.
    ApiKeySpec(
        name=CFG.asaas_environment_name,
        label="Ambiente do Asaas",
        description=(
            "Sandbox para testar sem cobrar de verdade; Produção para vender. A chave de API "
            "precisa ser do mesmo ambiente. Sem escolha, usa Sandbox."
        ),
        is_secret=False,
        testable=False,
        input_type="text",
        options=(
            ApiKeyOption(ASAAS_SANDBOX, "Sandbox (testes)", "Nenhuma cobrança real é feita."),
            ApiKeyOption(ASAAS_PRODUCTION, "Produção", "Cobranças reais."),
        ),
        default=CFG.asaas_default_environment,
    ),
)


def build_store(client: Optional[Any] = None) -> CredentialStore:
    """The encrypted store (`commerce.credentials`). Raises `EncryptionNotConfigured`
    when `ENCRYPTION_KEY` is missing/invalid (the seed router maps it to 503)."""
    return build_api_key_store(
        client if client is not None else get_admin_client(),
        encryption_key=settings.encryption_key,
        table="credentials",
    )


__all__ = ["API_KEY_SPECS", "build_store"]
