"""Server-side registry of the products an agent can be granted to, and of the token scopes a grant mints.

Nothing here comes from request input: the product slug in a request is only a KEY into :data:`GRANT_PRODUCTS`,
and every scope / issuer / label a grant mints is read from this module (CONTRACT D4: "scopes come only from
server-side registries"). Adding a product = adding one :class:`GrantProduct` here, in the same commit as the
product's receiver sink.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.clients.social_wiring import JULIA_TOOLS_TOKEN_KEY
from app.dependencies import GRANT_CHANNEL_TOKEN_SCOPES
from noctusai_lib.api.auth.session import GRANT_RECEIVE_SCOPE, TokenScopeAllowList

__all__ = [
    "GRANT_CHANNEL_SCOPES",
    "GRANT_PRODUCTS",
    "GRANT_TOKEN_SCOPES",
    "GRANT_ISSUER",
    "GrantProduct",
    "get_grant_product",
    "list_grant_products",
]

#: The issuer agents stamps on the tokens it mints INTO a product schema (tools token, delivery token) and the
#: ``{issuer}`` of the receiver path (``PUT /api/platform/grants/agents``).
GRANT_ISSUER = "agents"



@dataclass(frozen=True)
class GrantProduct:
    """One grantable product."""

    slug: str
    label: str
    #: The product's Postgres schema (where its ``api_tokens`` live).
    schema: str
    #: ``issuer`` stamped on the CHANNEL token (agents' own ``api_tokens``): the transport allowed to drive the agent.
    channel_issuer: str
    #: Agent keys that can be granted to this product.
    agent_keys: tuple[str, ...]
    #: Scope + label of the TOOLS token minted into the product's ``api_tokens`` (agents calls the product's read
    #: tools with it). Mirrors the product's own constants (``julia_contexto_service.TOOLS_TOKEN_*``). ALL THREE tools
    #: fields are set together, or none: a product agents never calls back (the Assistant: it only RECEIVES the channel
    #: token) mints no tools token at all -- an unused standing credential is a liability, not a convenience.
    tools_scope: str | None = None
    tools_label: str | None = None
    #: The name the tools token's SECRET is stored under in agents' per-org encrypted credential store (read back by
    #: ``resolve_julia_tools_token``).
    tools_secret_name: str | None = None

    @property
    def has_tools(self) -> bool:
        return self.tools_scope is not None

    def __post_init__(self) -> None:
        if len({self.tools_scope is None, self.tools_label is None, self.tools_secret_name is None}) != 1:
            raise ValueError(f"grant product {self.slug!r}: tools_scope / tools_label / tools_secret_name are all-or-none")
        # One tools scope + one stored secret per product means ONE agent per entry: a second agent's tools token must
        # never be the first one's (a token never reaches another agent). Granting a second agent to a product = a
        # separate entry with its OWN ``tools_scope`` / ``tools_secret_name`` (and the product's own receiver), not
        # a longer tuple here.
        if len(self.agent_keys) != 1:
            raise ValueError(f"grant product {self.slug!r}: exactly one agent per tools token config")


GRANT_PRODUCTS: dict[str, GrantProduct] = {
    "social-wiring": GrantProduct(
        slug="social-wiring",
        label="Social Wiring",
        schema="social_wiring",
        channel_issuer="social-wiring",
        tools_scope="social-wiring:lais-tools",
        tools_label="agents · ferramentas julia",
        tools_secret_name=JULIA_TOOLS_TOKEN_KEY,
        agent_keys=("julia",),
    ),
    # The owner's personal WhatsApp line. It only RECEIVES the channel token (receiver sink: ``assistant`` migration 023 +
    # ``app/services/agents_grant.py``); agents never calls it back, so there is no tools token / secret.
    "assistant": GrantProduct(
        slug="assistant",
        label="Assistant",
        schema="assistant",
        channel_issuer="assistant",
        agent_keys=("assistente-pessoal",),
    ),
}


def get_grant_product(slug: str) -> GrantProduct | None:
    return GRANT_PRODUCTS.get(slug)


def list_grant_products() -> list[GrantProduct]:
    return sorted(GRANT_PRODUCTS.values(), key=lambda p: p.slug)


#: The scopes a grant mints on its CHANNEL token (agents schema): turn + status + the org-specs scope
#: (``app.dependencies.GRANT_CHANNEL_TOKEN_SCOPES``).
GRANT_CHANNEL_SCOPES: tuple[str, ...] = tuple(sorted(GRANT_CHANNEL_TOKEN_SCOPES))

#: STRICT allow-list of the scopes the grant service may mint (channel + each product's tools scope + the delivery
#: scope). The grant token admin refuses anything else (``UnknownTokenScopeError``).
GRANT_TOKEN_SCOPES = TokenScopeAllowList(
    [*GRANT_CHANNEL_SCOPES, GRANT_RECEIVE_SCOPE, *(p.tools_scope for p in GRANT_PRODUCTS.values() if p.tools_scope)],
    strict=True,
)
