"""Per-ORG LLM provider keys (Lais A1, contract §2 + §10.2 B1).

The agents product keeps TWO unrelated credential stores — do not conflate:

* ``app_integration_config`` (``app/credentials/resolver.py``): product-wide
  platform secrets (Bia-academia's Anthropic key, the academia/SW tokens).
  Never used for a provider-neutral (``runtime='llm'``) turn.
* ``agents.credentials`` (this module): the per-org, Fernet-encrypted keys an
  org admin writes through the seed api-keys router
  (``/api/settings/api-keys/{openai_api_key|anthropic_api_key}``).

:func:`resolve_org_llm_key` is the ONLY resolver an ``llm`` turn uses. It reads
this org's own rows and nothing else: the encrypted store first, then this
org's ``org_settings`` row (``noctusai_lib.config.credentials.
resolve_org_credential``). It structurally cannot reach the tier-0 override
(agents' Anthropic key, ``studio/wiring.py``), ``platform_settings`` or the
environment — those are not code paths here, so a missing key is a miss, never
another tenant's (or the platform's) spend.
"""
from __future__ import annotations

import logging
from typing import Any, Callable
from uuid import UUID

from noctusai_lib.config.credentials import resolve_org_credential
from noctusai_lib.security.api_keys import (
    ApiKeySpec,
    EncryptionNotConfigured,
    build_api_key_store,
    read_local_api_key,
)

logger = logging.getLogger(__name__)

__all__ = [
    "LLM_KEY_NAMES",
    "LLM_API_KEY_SPECS",
    "build_llm_key_store",
    "make_org_llm_key_resolver",
    "resolve_org_llm_key",
]

#: provider -> the org-scoped key name (also the seed api-keys `{key}`).
LLM_KEY_NAMES: dict[str, str] = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
}

LLM_API_KEY_SPECS: tuple[ApiKeySpec, ...] = (
    ApiKeySpec(
        name="openai_api_key",
        label="Chave de API da OpenAI",
        description=(
            "Chave usada pelos agentes desta organização que rodam na OpenAI "
            "(ex.: a Julia dos leads). Cada organização usa a própria chave; "
            "sem ela o agente não responde."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="sk-...",
    ),
    ApiKeySpec(
        name="anthropic_api_key",
        label="Chave de API da Anthropic",
        description=(
            "Chave usada pelos agentes desta organização que rodam na Anthropic "
            "pelo executor neutro de provedor. Cada organização usa a própria "
            "chave; sem ela o agente não responde."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="sk-ant-...",
    ),
)


def build_llm_key_store(client: Any | None = None, *, encryption_key: str | None = None) -> Any:
    """The encrypted per-org store (``agents.credentials``). Raises
    :class:`EncryptionNotConfigured` when ``ENCRYPTION_KEY`` is missing or
    invalid — the seed router maps that to a 503 on writes."""
    if client is None:
        from app.dependencies import get_admin_client

        client = get_admin_client()
    if encryption_key is None:
        from app.config import settings

        encryption_key = settings.encryption_key
    return build_api_key_store(client, encryption_key=encryption_key, table="credentials")


def resolve_org_llm_key(
    provider: str,
    org_id: UUID | str,
    *,
    store_factory: Callable[[], Any] | None = None,
    org_settings_reader: Callable[[str, str], str | None] = resolve_org_credential,
) -> str | None:
    """This org's key for ``provider``, or ``None``. Never anything else.

    ``store_factory`` / ``org_settings_reader`` are DI seams (tests pass a
    fake store and a fake org_settings reader). An unusable
    ``ENCRYPTION_KEY`` skips the encrypted tier (logged) and still consults
    ``org_settings`` — a READ must not hard-fail on a config gap. A row that
    exists but will not decrypt is NOT swallowed
    (``CredentialDecryptError``): a key-rotation gap is not "no key"."""
    name = LLM_KEY_NAMES.get(provider)
    if name is None:
        return None
    org = str(org_id)
    factory = store_factory if store_factory is not None else build_llm_key_store
    try:
        store = factory()
    except EncryptionNotConfigured as exc:
        logger.warning("agents.org_llm_key.store_unavailable provider=%s: %s", provider, exc)
        store = None
    if store is not None:
        stored = read_local_api_key(store, org, name)
        value = (stored.tokens or {}).get("value") if stored else None
        if value:
            return value
    return org_settings_reader(name, org) or None


def make_org_llm_key_resolver(
    *,
    store_factory: Callable[[], Any] | None = None,
    org_settings_reader: Callable[[str, str], str | None] = resolve_org_credential,
) -> Callable[[str, UUID], str | None]:
    """``(provider, org_id) -> key | None`` — the shape ``LlmToolRuntime`` takes."""

    def _resolve(provider: str, org_id: UUID) -> str | None:
        return resolve_org_llm_key(
            provider, org_id, store_factory=store_factory, org_settings_reader=org_settings_reader
        )

    return _resolve
