"""The fixed set of credentials the `agents` control plane holds.

Server-side source of truth for everything a UI action must NOT take from
request input: the store key, the env fallback, and — for product tokens —
the target schema, scopes, principal binding and issuer a renewal mints
with. A "Renovar" click can therefore never widen a token's scopes.

Scopes are contract-fixed: §B.0 (academia) and §E.6 (social-wiring).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "ACADEMIA_API_TOKEN",
    "ANTHROPIC_API_KEY",
    "APPROVAL_RING",
    "CREDENTIALS",
    "CredentialKind",
    "CredentialSpec",
    "ISSUER",
    "JULIA_AGENT_ID",
    "SOCIAL_WIRING_API_TOKEN",
    "TOKEN_TTL_DAYS",
    "get_spec",
]

CredentialKind = Literal["product_token", "api_key", "key_ring", "config"]

#: `api_tokens.issuer` for every token agents mints (contract §E.6: the
#: social-wiring bridge refuses any other issuer).
ISSUER = "agents"

#: Seed maximum for a product token's lifetime (`auth_router`
#: `_API_TOKEN_MAX_EXPIRY_DAYS`); a renewal always mints for the full span.
TOKEN_TTL_DAYS = 90


@dataclass(frozen=True)
class CredentialSpec:
    name: str  # stable id (URL path segment)
    label: str
    kind: CredentialKind
    env_var: str  # documented env fallback
    settings_attr: str  # `SeedSettings` attribute carrying the env value
    target_product: str | None = None
    target_schema: str | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)
    bind_principal: bool = False  # principal_agent_id = Julia's agent id
    token_label: str | None = None
    secret: bool = True
    #: `agents.app_integration_config` key; defaults to ``name``.
    storage_key: str | None = None

    @property
    def store_key(self) -> str:
        return self.storage_key or self.name

    @property
    def renewable(self) -> bool:
        return self.kind == "product_token"

    @property
    def probeable(self) -> bool:
        return self.kind in ("product_token", "api_key")


ACADEMIA_API_TOKEN = CredentialSpec(
    name="academia_api_token",
    label="Token da API academia-de-reciclagem",
    kind="product_token",
    env_var="ACADEMIA_API_TOKEN",
    settings_attr="academia_api_token",
    target_product="academia-de-reciclagem",
    target_schema="academia_de_reciclagem",
    scopes=(
        "academia:read",
        "academia:kb:write",
        "academia:decisions:write",
        "academia:questions:write",
        "academia:roadmap:write",
        "academia:content:write",
        "academia:sources:write",
    ),
    bind_principal=True,
    token_label="agents → academia (Julia)",
)

SOCIAL_WIRING_API_TOKEN = CredentialSpec(
    name="social_wiring_api_token",
    label="Token da ponte social-wiring (One Chat)",
    kind="product_token",
    env_var="SOCIAL_WIRING_API_TOKEN",
    settings_attr="social_wiring_api_token",
    target_product="social-wiring",
    target_schema="social_wiring",
    scopes=("social-wiring:one-chat:read", "social-wiring:one-chat:toggle"),
    token_label="agents → social-wiring (One Chat)",
)

ANTHROPIC_API_KEY = CredentialSpec(
    name="anthropic_api_key",
    label="Chave Anthropic da Julia",
    kind="api_key",
    env_var="JULIA_ANTHROPIC_API_KEY → ANTHROPIC_API_KEY",
    settings_attr="anthropic_api_key",
)

APPROVAL_RING = CredentialSpec(
    name="approval_assertion_secrets",
    # Audience-scoped (contract §D "one key list per audience"); academia
    # reads this exact key (its `approval_assertion_ring_key` setting).
    storage_key="approval_assertion_secrets:academia-de-reciclagem",
    label="Chaves de assinatura de aprovação (§D)",
    kind="key_ring",
    env_var="APPROVAL_ASSERTION_SECRETS",
    settings_attr="approval_assertion_secrets",
)

JULIA_AGENT_ID = CredentialSpec(
    name="julia_agent_id",
    label="ID da agente Julia (principal do token academia)",
    kind="config",
    env_var="JULIA_AGENT_ID",
    settings_attr="julia_agent_id",
    secret=False,
)

CREDENTIALS: tuple[CredentialSpec, ...] = (
    ACADEMIA_API_TOKEN,
    SOCIAL_WIRING_API_TOKEN,
    ANTHROPIC_API_KEY,
    APPROVAL_RING,
    JULIA_AGENT_ID,
)

_BY_NAME = {spec.name: spec for spec in CREDENTIALS}


def get_spec(name: str) -> CredentialSpec | None:
    return _BY_NAME.get(name)
