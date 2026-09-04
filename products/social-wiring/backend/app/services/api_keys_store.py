"""Org-scoped API keys — the write-in-the-UI, encrypted-at-rest seam.

WHAT
----
Three operator-supplied credentials the Certidões / Matrículas workflows
need per-org (``openai_api_key``, ``infosimples_token``,
``infosimples_email_envio``), settable from Settings → "Chaves de API",
Fernet-encrypted at rest, and resolvable from anywhere in the product
through one function: :func:`resolve_api_key`.

WHERE THEY LIVE — no new table, no new crypto
---------------------------------------------
Persistence is the EXISTING ``social_wiring.credentials`` table
(migration 001): ``(org_id, provider)`` UNIQUE + ``encrypted_tokens``
(Fernet-encrypted JSON) + RLS + indexes. It is reached through the
product's already-named consume seam
:func:`app.services.credential_vault.build_credential_store` (which owns
the loud "ENCRYPTION_KEY missing → refuse to write plaintext" check),
which itself consumes the seed store
``noctusai_lib.security.token_store``. Zero crypto and zero DB code lives
in this module — it is a naming + resolution layer on top.

One ROW per key, provider ``api_key:<name>`` (e.g.
``api_key:infosimples_token``), bundle ``{"value": "..."}``. One row per
key rather than one bundle row for all three because:
  - ``updated_at`` is then per-key (the UI shows it per-key),
  - DELETE of one key is a row delete, not a read-modify-write that can
    race another tab's save,
  - the ``api_key:`` prefix namespaces these away from the OAuth
    providers (``youtube`` / ``meta`` / ``google_calendar``) that share
    the table, so ``list_providers`` stays readable.

RESOLUTION — two tiers, no silent fallback
------------------------------------------
1. this product's encrypted store, for THIS org;
2. ``noctusai_lib.config.credentials.resolve_credential`` — the platform
   chain (``public.org_settings`` → ``platform_settings`` → env), so a
   key already configured for the org elsewhere keeps working until it
   is re-entered here.

Every tier that answers is logged at DEBUG. A miss returns ``None`` — it
is the CALLER's job to raise its own 422 with the pt-BR "configure em
Configurações → Chaves de API" sentence, because only the caller knows
which workflow is blocked.

A :class:`~noctusai_lib.security.token_store.CredentialDecryptError` is
NOT a miss and is deliberately NOT swallowed: a row that exists but will
not decrypt means a rotated/mismatched ``ENCRYPTION_KEY``, and the seed
store's contract is to fail loud there rather than let every downstream
adapter fail obscurely far from the root cause.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.security.token_store import CredentialStore, StoredCredential

from app.services.credential_vault import (
    EncryptionNotConfigured,
    build_credential_store,
)

logger = logging.getLogger(__name__)

__all__ = [
    "API_KEY_SPECS",
    "ApiKeyOption",
    "VISION_PROVIDER_KEY",
    "resolve_vision_provider",
    "MANAGED_API_KEYS",
    "PROVIDER_PREFIX",
    "ApiKeyResolution",
    "ApiKeySpec",
    "ApiKeySource",
    "build_api_key_store",
    "delete_api_key",
    "get_spec",
    "llm_key_provider",
    "mask_value",
    "provider_for",
    "put_api_key",
    "read_local_api_key",
    "resolve_api_key",
    "resolve_api_key_detail",
]

#: Which tier answered. ``"local"`` = this product's encrypted store.
#: ``"platform"`` = a DB tier of the platform chain (``org_settings`` /
#: ``platform_settings``). ``"env"`` = the platform chain answered with
#: exactly the value the process environment carries under
#: ``NAME.upper()`` — that is the strongest claim provable without
#: forking ``resolve_credential``'s internals, and it is what the tag
#: means (a DB row holding the identical value is indistinguishable, and
#: functionally identical).
ApiKeySource = Literal["local", "platform", "env"]

#: Namespace prefix for the ``credentials.provider`` column.
PROVIDER_PREFIX = "api_key:"


@dataclass(frozen=True)
class ApiKeyOption:
    """One allowed value of a CHOICE setting, and how the UI labels it."""

    value: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class ApiKeySpec:
    """One operator-settable key: its identity + how the UI renders it."""

    name: str
    label: str
    description: str
    #: ``False`` for values that are not secrets (an e-mail address, a
    #: provider choice). A non-secret is shown in full rather than masked —
    #: hiding it buys no security and costs the operator the ability to
    #: spot a typo.
    is_secret: bool = True
    #: Whether ``POST /api/settings/api-keys/{key}/test`` can probe it live.
    testable: bool = False
    #: HTML input type hint for the frontend.
    input_type: str = "text"
    placeholder: str = ""
    #: Non-empty makes this a CHOICE rather than a free-text value: the UI
    #: renders a switch over these options, and the write path REFUSES
    #: anything outside them. Both halves are required — a client-side-only
    #: constraint is a suggestion, and a value the consumer cannot map to a
    #: provider is a silent failure at extraction time, far from here.
    options: tuple[ApiKeyOption, ...] = ()
    #: What the product behaves as when this setting has never been saved.
    #: Stated so the UI can show the effective value instead of an empty
    #: control that implies nothing is chosen.
    default: Optional[str] = None

    @property
    def allowed_values(self) -> tuple[str, ...]:
        return tuple(option.value for option in self.options)


API_KEY_SPECS: tuple[ApiKeySpec, ...] = (
    ApiKeySpec(
        name="openai_api_key",
        label="OpenAI API Key",
        description=(
            "Usada para análise de certidões com IA, extração de matrículas "
            "e funcionalidades de IA."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="sk-...",
    ),
    ApiKeySpec(
        name="anthropic_api_key",
        label="Anthropic (Claude) API Key",
        description=(
            "Alternativa à OpenAI para leitura de documentos digitalizados "
            "(matrículas e certidões escaneadas). Escolha qual provedor usar "
            "no seletor abaixo."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="sk-ant-...",
    ),
    #: 🔴 A MANUAL SWITCH, NOT A FALLBACK.
    #:
    #: Nothing in this product fails over from one vendor to the other. A
    #: silent switch would change which model transcribed a legal document
    #: without anyone being told, and "why does this matrícula read
    #: differently from last month's" is not a question the logs could
    #: answer afterwards. The operator picks, and the pick is visible.
    ApiKeySpec(
        name="llm_vision_provider",
        label="Provedor de leitura de documentos",
        description=(
            "Qual IA transcreve páginas digitalizadas (matrículas e "
            "certidões escaneadas). Troque para a Anthropic quando a conta "
            "OpenAI estiver sem créditos. A chave do provedor escolhido "
            "precisa estar configurada acima."
        ),
        is_secret=False,
        testable=False,
        input_type="select",
        options=(
            ApiKeyOption(
                value="openai",
                label="OpenAI",
                description="Usa a OpenAI API Key (modelo gpt-4.1-mini).",
            ),
            ApiKeyOption(
                value="anthropic",
                label="Anthropic (Claude)",
                description=(
                    "Usa a Anthropic API Key (modelo claude-opus-5)."
                ),
            ),
        ),
        default="openai",
    ),
    ApiKeySpec(
        name="infosimples_token",
        label="InfoSimples Token",
        description=(
            "Token para emissão automatizada de certidões negativas "
            "(CND Federal, TRF3, TJSP, etc.)."
        ),
        is_secret=True,
        testable=True,
        input_type="password",
        placeholder="Token InfoSimples...",
    ),
    ApiKeySpec(
        name="infosimples_email_envio",
        label="E-mail de Envio (TJSP)",
        description=(
            "E-mail para recebimento da certidão TJSP. Obrigatório para "
            "emissão da certidão TJSP."
        ),
        is_secret=False,
        testable=False,
        input_type="email",
        placeholder="juridico@suaempresa.com.br",
    ),
)

MANAGED_API_KEYS: tuple[str, ...] = tuple(spec.name for spec in API_KEY_SPECS)

_SPECS_BY_NAME: dict[str, ApiKeySpec] = {spec.name: spec for spec in API_KEY_SPECS}

#: Sentinel so "caller did not pass a store" is distinguishable from
#: "caller passed None because the Fernet key is unusable" — the second
#: must SKIP the local tier, never silently rebuild the store.
_UNSET: Any = object()


def get_spec(name: str) -> Optional[ApiKeySpec]:
    """The spec for ``name``, or ``None`` when it is not a managed key."""
    return _SPECS_BY_NAME.get(name)


def provider_for(name: str) -> str:
    """The ``credentials.provider`` value this key is stored under."""
    return f"{PROVIDER_PREFIX}{name}"


def mask_value(value: Optional[str], spec: ApiKeySpec) -> Optional[str]:
    """A display hint that never leaks a secret.

    Secrets collapse to their last 4 characters (``...b3f9``) — enough to
    tell "the key I pasted" from "some other key", not enough to use.
    Short secrets (≤4 chars) collapse to a fixed dot run so the length
    itself is not disclosed. Non-secrets are returned verbatim.
    """
    if not value:
        return None
    if not spec.is_secret:
        return value
    if len(value) <= 4:
        return "••••"
    return f"...{value[-4:]}"


def build_api_key_store(client=None, *, encryption_key: Optional[str] = None) -> CredentialStore:
    """Build the encrypted store these keys live in.

    Thin pass-through to :func:`credential_vault.build_credential_store`
    — which validates ``ENCRYPTION_KEY`` loudly (raises
    :class:`EncryptionNotConfigured`, mapped to a 503 at the router
    boundary) so a misconfigured deployment can never persist plaintext.
    ``client`` defaults to the schema-scoped admin client (the RLS write
    policy on ``social_wiring.credentials`` is service-role only).
    """
    if client is None:
        from app.dependencies import get_admin_client

        client = get_admin_client()
    return build_credential_store(client, encryption_key=encryption_key)


def read_local_api_key(
    store: CredentialStore, org_id: str, name: str
) -> Optional[StoredCredential]:
    """This org's locally-stored credential for ``name``, or ``None``.

    Raises ``CredentialDecryptError`` when a row exists but will not
    decrypt — see the module docstring: that is a key-rotation gap, not
    a miss, and swallowing it would hide the root cause.
    """
    return store.get(str(org_id), provider_for(name))


def put_api_key(
    store: CredentialStore, org_id: str, name: str, value: str
) -> StoredCredential:
    """Encrypt + UPSERT ``value`` for this org. Write-only by design —
    the returned bundle is for timestamps, never echoed to a client."""
    return store.put(str(org_id), provider_for(name), {"value": value})


def delete_api_key(store: CredentialStore, org_id: str, name: str) -> bool:
    """Drop this org's LOCAL override. ``True`` when a row existed.

    The platform tier is untouched and may still answer afterwards —
    callers must re-resolve and tell the operator so, rather than
    reporting "removida" over a key that is still live.
    """
    return store.delete(str(org_id), provider_for(name))


@dataclass(frozen=True)
class ApiKeyResolution:
    """Where a key's value came from, alongside the value itself."""

    name: str
    value: Optional[str]
    source: Optional[ApiKeySource]
    updated_at: Optional[datetime] = None

    @property
    def configured(self) -> bool:
        return bool(self.value)


def resolve_api_key_detail(
    name: str,
    org_id: Optional[str],
    *,
    store: Any = _UNSET,
    resolver: Callable[[str, Optional[str]], Optional[str]] = resolve_credential,
) -> ApiKeyResolution:
    """:func:`resolve_api_key`, plus which tier answered.

    ``store`` is the tier-1 DI seam: pass an already-built store (or an
    explicit ``None`` to skip the local tier, e.g. when
    ``ENCRYPTION_KEY`` is unusable) so a router that already built one
    does not build a second. Omit it and one is built lazily; a
    missing/malformed Fernet key degrades to the platform tier alone — a
    READ must not hard-fail when the platform chain can still answer
    (same call the Meta app-config seam makes,
    `app_config_store.resolve_meta_app_creds`).

    ``resolver`` is the tier-2 DI seam, defaulting to the real platform
    chain. It exists so a test can exercise the fallback deterministically
    instead of reaching the AMBIENT shared Supabase project that
    ``configure_credentials`` wires at app start — per
    KB § PATTERNS/backend/di-test-seam.md (Class-B), not a monkeypatch of
    our own code.
    """
    if store is _UNSET:
        try:
            store = build_api_key_store()
        except EncryptionNotConfigured as exc:
            logger.debug(
                "api_keys: local tier unavailable for %s (ENCRYPTION_KEY): %s",
                name,
                exc,
            )
            store = None

    # Tier 1 — this product's encrypted store, scoped to this org.
    if store is not None and org_id:
        stored = read_local_api_key(store, str(org_id), name)
        value = (stored.tokens or {}).get("value") if stored else None
        if value:
            logger.debug("api_keys: %s resolved from the local store", name)
            return ApiKeyResolution(
                name=name,
                value=value,
                source="local",
                updated_at=stored.updated_at if stored else None,
            )

    # Tier 2 — the platform chain (org_settings → platform_settings → env).
    chain_value = resolver(name, str(org_id) if org_id else None)
    if not chain_value:
        logger.debug("api_keys: %s not configured in any tier", name)
        return ApiKeyResolution(name=name, value=None, source=None)

    env_value = os.environ.get(name.upper()) or None
    source: ApiKeySource = "env" if env_value and chain_value == env_value else "platform"
    logger.debug("api_keys: %s resolved from the %s tier", name, source)
    return ApiKeyResolution(name=name, value=chain_value, source=source)


def resolve_api_key(name: str, org_id: Optional[str]) -> Optional[str]:
    """The value for ``name`` in ``org_id``'s scope, or ``None``.

    THE consume seam for this product's workflows (certidões, matrículas,
    IA). Never raises on a miss — a caller that needs the key raises its
    own 422 naming the workflow it blocked, e.g.::

        token = resolve_api_key("infosimples_token", org_id)
        if not token:
            raise HTTPException(
                422,
                "Token InfoSimples não configurado. "
                "Configure em Configurações → Chaves de API.",
            )
    """
    return resolve_api_key_detail(name, org_id).value


#: The managed key that holds the manual provider choice.
VISION_PROVIDER_KEY = "llm_vision_provider"


def resolve_vision_provider(
    org_id: Optional[str],
    *,
    store: Any = _UNSET,
    resolver: Callable[[str, Optional[str]], Optional[str]] = resolve_credential,
) -> str:
    """Which vendor this org transcribes scanned documents with.

    THE consume seam for the manual switch. Always returns a value from the
    spec's own option list, so a caller can hand it straight to
    `make_document_transcriber(provider=...)` without re-validating.

    `store` / `resolver` are the same two DI seams `resolve_api_key_detail`
    exposes, forwarded rather than re-invented: `resolver` is a BOUND
    DEFAULT there, so a test that monkeypatched this module's
    `resolve_credential` attribute would silently keep hitting the real
    chain and pass for the wrong reason.

    Falls back to the spec default when the setting was never saved OR when
    the stored value is not a known option. The second case can only happen
    if the row was written outside this product's write path (which
    validates) or if an option was RETIRED from the spec while an org still
    pointed at it — and in that case the honest move is to run on the
    documented default and say so in the log, not to hand an unroutable
    provider name to the LLM stack and fail one layer down with a message
    about a missing key.
    """
    spec = _SPECS_BY_NAME[VISION_PROVIDER_KEY]
    default = spec.default or "openai"
    escolhido = (
        resolve_api_key_detail(
            VISION_PROVIDER_KEY, org_id, store=store, resolver=resolver
        ).value
        or ""
    ).strip()
    if not escolhido:
        return default
    if escolhido not in spec.allowed_values:
        logger.warning(
            "api_keys: %s=%r is not a known option %s — using %r",
            VISION_PROVIDER_KEY, escolhido, spec.allowed_values, default,
        )
        return default
    return escolhido


def llm_key_provider(provider: str, org_id: Optional[str] = None) -> Optional[str]:
    """``LLMConfig.key_provider`` adapter — ready to wire, not wired.

    The seed's default key provider resolves ``f"{provider}_api_key"``
    through ``resolve_credential`` ALONE, so a key an operator saves in
    this product's own store is invisible to ``chat_completion`` until
    ``create_product_app(llm_config=...)`` is pointed here. This function
    is that one-line swap, kept in this module so wiring it is a change
    to ``main.py`` only (owned elsewhere this dispatch — see the delivery
    note's integration-notes).
    """
    return resolve_api_key(f"{provider}_api_key", org_id)
