"""IgIg's managed API keys — the product-local half of the generic
mechanism `noctusai_lib.security.api_keys` provides (same mechanism
`social-wiring` and `community` consume; N=2→N=3 recurrence, this
product is the seed router's second consumer).

WHAT LIVES HERE (per that module's own "WHAT STAYS PRODUCT-LOCAL"
convention): which keys are managed (`API_KEY_SPECS`) and the store
factory bound to THIS product's admin client + schema (`igig.credentials`,
migration 035). Zero crypto / DB code — both delegate to the seed.

Owner decision 2026-09-28: IgIg gets its own per-org Anthropic key so an
agency can set/change it from `Integrações → Chaves de API` instead of
depending on the platform-wide default. Encrypted with the SAME cofre
key already gating the Cofre de Acessos / canais / e-mail secrets
(`settings.igig_cofre_key` / env `IGIG_COFRE_KEY`) — no new env var.
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.security.api_keys import ApiKeySpec, build_api_key_store

from app.config import settings
from app.dependencies import get_admin_client

API_KEY_SPECS: tuple[ApiKeySpec, ...] = (
    ApiKeySpec(
        name="anthropic_api_key",
        label="Anthropic (Claude) API Key",
        description=(
            "Usada pelo Assistente IgIg e pelo assistente do negócio (resumo, "
            "próxima ação, rascunho de mensagem) para gerar texto com IA. Sem "
            "uma chave própria aqui, a IgIg usa a chave da plataforma, se "
            "houver — sem nenhuma, o assistente responde dizendo que a IA "
            "não está configurada."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="sk-ant-...",
    ),
)


def build_igig_api_key_store(client: Optional[Any] = None):
    """Build the encrypted store `igig.credentials` lives in.

    Validates `settings.igig_cofre_key` loudly first (raises
    `EncryptionNotConfigured`, mapped to a 503 at the router boundary by
    `noctusai_seed.api_keys_router`). `client` defaults to the schema-
    scoped admin client — the RLS write policy on `igig.credentials` is
    service-role only (migration 035), same shape as `igig.integracao`.
    """
    return build_api_key_store(
        client if client is not None else get_admin_client(),
        encryption_key=settings.igig_cofre_key,
        table="credentials",
    )
