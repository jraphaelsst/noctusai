"""The store's managed keys — product-local half of `noctusai_lib.security.api_keys`.

Owner directive 2026-10-02: keys and tokens live in the DB (Fernet-encrypted in
`store.credentials`, written from the admin UI), not in env vars. This module
owns only what the seed says stays product-local: the spec list and the store
bound to THIS product's admin client. Zero crypto / DB code.

Resolution (`KeyProvider.resolve`): local store -> platform chain
(`org_settings` -> `platform_settings`) -> env (`NAME.upper()`), scoped to the
single-tenant owner org `STORE_ORG_ID`. A missing/malformed `ENCRYPTION_KEY`
degrades READS to the platform chain and 503s WRITES (seed router) — never plaintext.

`KeyProvider` is the DI seam: production uses the defaults; tests call
`key_provider.use(store=FakeCredentialStore(), resolver=...)` / `.reset()`
(a setter on our own provider, not a patch of anything).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from noctusai_lib.security.api_keys import (
    ApiKeyOption,
    ApiKeySpec,
    build_api_key_store,
    resolve_api_key_detail,
)
from noctusai_lib.security.token_store import CredentialStore

from app.config import ASAAS_PRODUCTION_BASE_URL, ASAAS_SANDBOX_BASE_URL, settings
from app.dependencies import get_admin_client

API_KEY_SPECS: tuple[ApiKeySpec, ...] = (
    ApiKeySpec(
        name="asaas_api_key",
        label="Chave de API do Asaas",
        description=(
            "Chave que permite à loja gerar as cobranças (Pix, boleto ou cartão) na sua conta "
            "Asaas. No Asaas: Integrações > Chaves de API > gerar nova chave. Sem ela, o "
            "botão de compra fica indisponível. Use a chave do mesmo ambiente escolhido abaixo."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
        placeholder="$aact_...",
    ),
    ApiKeySpec(
        name="asaas_webhook_token",
        label="Token do webhook do Asaas",
        description=(
            "Senha que o Asaas envia junto de cada aviso de pagamento para provar que ele é "
            "verdadeiro. Você a define no Asaas (Integrações > Webhooks > Token de autenticação) "
            "e cola o mesmo valor aqui. Sem ele, os pagamentos não são confirmados e o e-mail "
            "de entrega não é enviado."
        ),
        is_secret=True,
        testable=False,
        input_type="password",
    ),
    ApiKeySpec(
        name="asaas_environment",
        label="Ambiente do Asaas",
        description=(
            "Sandbox para testar sem cobrar de verdade; Produção para vender. A chave de API "
            "precisa ser do mesmo ambiente. Sem escolha, usa Sandbox."
        ),
        is_secret=False,
        testable=False,
        input_type="text",
        options=(
            ApiKeyOption("sandbox", "Sandbox (testes)", "Nenhuma cobrança real é feita."),
            ApiKeyOption("production", "Produção", "Cobranças reais."),
        ),
        default="sandbox",
    ),
)


class KeyProvider:
    def __init__(self) -> None:
        self._store_override: Optional[CredentialStore] = None
        self._resolver_override: Optional[Callable[[str, Optional[str]], Optional[str]]] = None
        self._org_id_override: Optional[str] = None
        self._encryption_key_override: Optional[str] = None

    # ── DI seam ──────────────────────────────────────────────────────────
    def use(
        self,
        *,
        store: Optional[CredentialStore] = None,
        resolver: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
        org_id: Optional[str] = None,
        encryption_key: Optional[str] = None,
    ) -> None:
        """Swap collaborators and configuration for a test. `org_id` /
        `encryption_key` take precedence over `STORE_ORG_ID` / `ENCRYPTION_KEY`
        when given (`""` means "explicitly unset"), so a test states the
        configuration it judges instead of inheriting the machine's env."""
        self._store_override = store
        self._resolver_override = resolver
        self._org_id_override = org_id
        self._encryption_key_override = encryption_key

    def reset(self) -> None:
        self.use()

    # ── store / platform tier ────────────────────────────────────────────
    def build_store(self, client: Optional[Any] = None) -> CredentialStore:
        """The encrypted store (`store.credentials`). Raises `EncryptionNotConfigured`
        when `ENCRYPTION_KEY` is missing/invalid (router maps it to 503)."""
        if self._store_override is not None:
            return self._store_override
        return build_api_key_store(
            client if client is not None else get_admin_client(),
            encryption_key=self.encryption_key(),
            table="credentials",
        )

    def platform_resolve(self, name: str, org_id: Optional[str]) -> Optional[str]:
        if self._resolver_override is not None:
            return self._resolver_override(name, org_id)
        from noctusai_lib.config.credentials import resolve_credential

        return resolve_credential(name, org_id)

    # ── consume seam ─────────────────────────────────────────────────────
    def org_id(self) -> Optional[str]:
        raw = self._org_id_override if self._org_id_override is not None else settings.store_org_id
        return (raw or "").strip() or None

    def encryption_key(self) -> str:
        if self._encryption_key_override is not None:
            return self._encryption_key_override
        return settings.encryption_key

    def resolve(self, name: str) -> Optional[str]:
        return resolve_api_key_detail(
            name,
            self.org_id(),
            store_factory=self.build_store,
            resolver=self.platform_resolve,
        ).value

    def asaas_base_url(self) -> str:
        env = (self.resolve("asaas_environment") or "sandbox").strip().lower()
        return ASAAS_PRODUCTION_BASE_URL if env == "production" else ASAAS_SANDBOX_BASE_URL


key_provider = KeyProvider()

__all__ = ["API_KEY_SPECS", "KeyProvider", "key_provider"]
