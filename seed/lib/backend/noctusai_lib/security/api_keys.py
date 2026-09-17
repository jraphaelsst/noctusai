"""Org-scoped, operator-managed API keys — the write-in-the-UI,
encrypted-at-rest seam every product with per-org LLM/3rd-party keys needs.

Lifted 2026-09-17 (`community uses social-wiring's mechanisms`, Slice A)
from `social-wiring`'s `app/services/api_keys_store.py` +
`app/services/credential_vault.py` — a PURE, behaviour-preserving
extraction. `social-wiring` is NOT modified in this slice (its own
module keeps working unchanged; it migrates to consume this seam in a
later slice) — see the ``NOC-REMEDIATE[sw-consume-seed-api-keys]``
marker left at the top of `api_keys_store.py`.

WHAT THIS MODULE OWNS (generic; product-agnostic)
--------------------------------------------------
- ``ApiKeySpec`` / ``ApiKeyOption`` — one operator-settable key's
  identity + how the UI renders it. The concrete spec LIST is
  product-owned (e.g. ``openai_api_key``, ``infosimples_token``) and is
  passed as a parameter everywhere below — this module never hardcodes
  a product's keys.
- ``mask_value`` — a display hint that never leaks a secret.
- ``require_fernet`` / ``EncryptionNotConfigured`` — the loud
  "ENCRYPTION_KEY missing/malformed → refuse to write plaintext" check,
  funnelled through ONE builder so every consumer maps it to the same
  503 config-gap rather than persisting plaintext or crashing with a 500.
  Shared with the WhatsApp-connection store (field-level api-key
  encryption) — see `noctusai_lib.integrations.whatsapp.connection_store`.
- ``build_api_key_store`` / ``read_local_api_key`` / ``put_api_key`` /
  ``delete_api_key`` — the encrypted per-(org, key) store, built over
  the seed's own `noctusai_lib.security.token_store` (one row per key,
  provider ``api_key:<name>`` — see ``provider_for``). Table name is a
  parameter (`social-wiring` uses its existing `credentials` table,
  schema-scoped via the client it passes in).
- ``resolve_api_key_detail`` / ``resolve_api_key`` — the two-tier
  resolution seam: this product's local store, then
  `noctusai_lib.config.credentials.resolve_credential` (the platform
  chain: `org_settings` → `platform_settings` → env). A
  ``CredentialDecryptError`` from the local tier is NEVER swallowed —
  see `token_store`'s own docstring for why.
- ``make_local_credential_override`` — generalises the
  ``register_credential_override(...)`` closure every product wires
  once at startup (`social-wiring`'s `app/main.py:_local_api_key`) so
  the platform chain's tier-0 sees the product's own encrypted keys
  too, without recursing.
- ``credentials_table_ddl`` — the DDL template a product copies into
  its own migration (schema/table are parameters; mirrors
  `social-wiring` migration 001's ``credentials`` table + RLS).

WHAT STAYS PRODUCT-LOCAL (deliberately NOT lifted)
---------------------------------------------------
The concrete ``API_KEY_SPECS`` tuple, the LLM-vision/embedding/chat
provider switches (`resolve_vision_provider` / `resolve_embedding_
provider` / `resolve_chat_provider` / `llm_key_provider`), and the
live-probe testers (`_test_openai_key` et al, with their pt-BR
operator-facing messages) are `social-wiring`-specific — certidão/
matrícula workflow concerns, not a generic mechanism. They stay in the
product. The router factory below (`create_api_keys_router`, in
`noctusai_seed.api_keys_router`) takes the spec list AND the testers
mapping as parameters for exactly this reason.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Literal, Optional

from cryptography.fernet import Fernet

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.domain.sql_templates import rls_subquery_policy, service_role_bypass
from noctusai_lib.security.token_store import (
    CredentialStore,
    StoredCredential,
    make_credential_store,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ApiKeyOption",
    "ApiKeySource",
    "ApiKeySpec",
    "ApiKeyResolution",
    "EncryptionNotConfigured",
    "PROVIDER_PREFIX",
    "build_api_key_store",
    "credentials_table_ddl",
    "delete_api_key",
    "make_local_credential_override",
    "mask_value",
    "provider_for",
    "put_api_key",
    "read_local_api_key",
    "require_fernet",
    "resolve_api_key",
    "resolve_api_key_detail",
]

#: Which tier answered. ``"local"`` = this product's encrypted store.
#: ``"platform"`` = a DB tier of the platform chain (``org_settings`` /
#: ``platform_settings``). ``"env"`` = the platform chain answered with
#: exactly the value the process environment carries under
#: ``NAME.upper()``.
ApiKeySource = Literal["local", "platform", "env"]

#: Default namespace prefix for the ``credentials.provider`` column.
#: Overridable per-call so two products sharing a Supabase project can
#: still tell their managed keys apart if they ever share a table.
PROVIDER_PREFIX = "api_key:"

#: Sentinel so "caller did not pass a store" is distinguishable from
#: "caller passed None because the Fernet key is unusable" — the second
#: must SKIP the local tier, never silently rebuild the store.
_UNSET: Any = object()


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
    #: Whether a live test endpoint can probe it.
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
    default: Optional[str] = None

    @property
    def allowed_values(self) -> tuple[str, ...]:
        return tuple(option.value for option in self.options)


def get_spec(name: str, specs: Iterable[ApiKeySpec]) -> Optional[ApiKeySpec]:
    """The spec named ``name`` within ``specs``, or ``None``."""
    for spec in specs:
        if spec.name == name:
            return spec
    return None


def provider_for(name: str, *, prefix: str = PROVIDER_PREFIX) -> str:
    """The ``credentials.provider`` value this key is stored under."""
    return f"{prefix}{name}"


def mask_value(value: Optional[str], spec: ApiKeySpec) -> Optional[str]:
    """A display hint that never leaks a secret.

    Secrets collapse to their last 4 characters (``...b3f9``) — enough to
    tell "the key I pasted" from "some other key", not enough to use.
    Short secrets (<=4 chars) collapse to a fixed dot run so the length
    itself is not disclosed. Non-secrets are returned verbatim.
    """
    if not value:
        return None
    if not spec.is_secret:
        return value
    if len(value) <= 4:
        return "••••"
    return f"...{value[-4:]}"


class EncryptionNotConfigured(RuntimeError):
    """ENCRYPTION_KEY missing or invalid — refuse to write plaintext.

    Every write-path consumer of this module maps this to a 503
    config-gap rather than a 500 (misconfiguration, not a bug) or a
    silent fallback to an in-memory / plaintext store.
    """


def require_fernet(key: Optional[str]) -> Fernet:
    """Validate a Fernet key loudly and return the built :class:`Fernet`.

    THE single place the "ENCRYPTION_KEY missing/malformed → refuse to
    write plaintext" check lives — consumed by both
    :func:`build_api_key_store` and the WhatsApp-connection store
    (`noctusai_lib.integrations.whatsapp.connection_store`, field-level
    api-key encryption). Lifted verbatim from `social-wiring`'s
    `credential_vault.require_fernet` (funnelled through one builder so
    a rotated/absent key fails the same way everywhere, rather than each
    of the ~27+ construction sites re-deriving its own check).
    """
    if not key:
        raise EncryptionNotConfigured(
            "ENCRYPTION_KEY is empty. Generate with `python -c \"from "
            "cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it in the "
            "product's .env."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise EncryptionNotConfigured(
            f"ENCRYPTION_KEY is not a valid Fernet key: {exc}. "
            "Regenerate with the snippet in .env.example."
        ) from exc


def build_api_key_store(
    client: Any,
    *,
    encryption_key: Optional[str],
    table: str = "credentials",
    metadata_column: Optional[str] = "metadata",
    metadata_columns: Optional[dict] = None,
) -> CredentialStore:
    """Build the encrypted store these keys live in.

    Validates ``encryption_key`` loudly first (raises
    :class:`EncryptionNotConfigured` — callers map that to a 503 at
    their router boundary), then delegates persistence to the seed
    `token_store` factory. ``client`` is the product's own (typically
    schema-scoped) admin/service-role Supabase client — this module owns
    zero DB wiring. ``table`` / ``metadata_column`` / ``metadata_columns``
    are the same table-shape seam `token_store.make_credential_store`
    exposes, forwarded so an absorbed product's pre-existing table
    (denormalized metadata columns, no bare ``metadata jsonb``) keeps
    working unchanged — see `social-wiring`'s own
    ``credential_vault._METADATA_COLUMNS``.
    """
    require_fernet(encryption_key)
    return make_credential_store(
        client=client,
        fernet_key=encryption_key.encode("utf-8"),
        table=table,
        metadata_column=metadata_column,
        metadata_columns=metadata_columns,
    )


def read_local_api_key(
    store: CredentialStore, org_id: str, name: str, *, prefix: str = PROVIDER_PREFIX
) -> Optional[StoredCredential]:
    """This org's locally-stored credential for ``name``, or ``None``.

    Raises ``CredentialDecryptError`` (from `token_store`) when a row
    exists but will not decrypt — that is a key-rotation gap, not a
    miss, and swallowing it would hide the root cause from every
    downstream adapter.
    """
    return store.get(str(org_id), provider_for(name, prefix=prefix))


def put_api_key(
    store: CredentialStore, org_id: str, name: str, value: str, *, prefix: str = PROVIDER_PREFIX
) -> StoredCredential:
    """Encrypt + UPSERT ``value`` for this org. Write-only by design —
    the returned bundle is for timestamps, never echoed to a client."""
    return store.put(str(org_id), provider_for(name, prefix=prefix), {"value": value})


def delete_api_key(
    store: CredentialStore, org_id: str, name: str, *, prefix: str = PROVIDER_PREFIX
) -> bool:
    """Drop this org's LOCAL override. ``True`` when a row existed.

    The platform tier is untouched and may still answer afterwards —
    callers must re-resolve and tell the operator so, rather than
    reporting "removed" over a key that is still live.
    """
    return store.delete(str(org_id), provider_for(name, prefix=prefix))


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
    store_factory: Optional[Callable[[], Optional[CredentialStore]]] = None,
    resolver: Callable[[str, Optional[str]], Optional[str]] = resolve_credential,
    prefix: str = PROVIDER_PREFIX,
) -> ApiKeyResolution:
    """:func:`resolve_api_key`, plus which tier answered.

    ``store`` is the tier-1 DI seam: pass an already-built store (or an
    explicit ``None`` to skip the local tier, e.g. when
    ``ENCRYPTION_KEY`` is unusable) so a router that already built one
    does not build a second.

    ``store_factory`` is the lazy-build seam: omit ``store`` (leave it
    at ``_UNSET``) and pass a zero-arg callable (e.g.
    ``functools.partial(build_api_key_store, client, encryption_key=key)``)
    to have one built on demand — a missing/malformed Fernet key
    (``EncryptionNotConfigured``) degrades to the platform tier alone
    rather than raising, because a READ must not hard-fail when the
    platform chain can still answer. Omitting BOTH ``store`` and
    ``store_factory`` skips the local tier entirely (platform-chain-only
    resolution) — that is the correct default for a caller with no
    local store of its own.

    ``resolver`` is the tier-2 DI seam, defaulting to the real platform
    chain. It exists so a test can exercise the fallback deterministically
    instead of reaching an ambient shared Supabase project — per
    ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B), not a monkeypatch
    of this module's own attribute.
    """
    if store is _UNSET:
        if store_factory is None:
            store = None
        else:
            try:
                store = store_factory()
            except EncryptionNotConfigured as exc:
                logger.debug(
                    "api_keys: local tier unavailable for %s (ENCRYPTION_KEY): %s",
                    name,
                    exc,
                )
                store = None

    # Tier 1 — the product's encrypted store, scoped to this org.
    if store is not None and org_id:
        stored = read_local_api_key(store, str(org_id), name, prefix=prefix)
        value = (stored.tokens or {}).get("value") if stored else None
        if value:
            logger.debug("api_keys: %s resolved from the local store", name)
            return ApiKeyResolution(
                name=name,
                value=value,
                source="local",
                updated_at=stored.updated_at if stored else None,
            )

    # Tier 2 — the platform chain (org_settings -> platform_settings -> env).
    chain_value = resolver(name, str(org_id) if org_id else None)
    if not chain_value:
        logger.debug("api_keys: %s not configured in any tier", name)
        return ApiKeyResolution(name=name, value=None, source=None)

    env_value = os.environ.get(name.upper()) or None
    source: ApiKeySource = "env" if env_value and chain_value == env_value else "platform"
    logger.debug("api_keys: %s resolved from the %s tier", name, source)
    return ApiKeyResolution(name=name, value=chain_value, source=source)


def resolve_api_key(
    name: str,
    org_id: Optional[str],
    *,
    store: Any = _UNSET,
    store_factory: Optional[Callable[[], Optional[CredentialStore]]] = None,
    resolver: Callable[[str, Optional[str]], Optional[str]] = resolve_credential,
    prefix: str = PROVIDER_PREFIX,
) -> Optional[str]:
    """The value for ``name`` in ``org_id``'s scope, or ``None``.

    THE product's consume seam for a managed key. Never raises on a
    miss — a caller that needs the key raises its own error naming the
    workflow it blocked (see `social-wiring`'s
    ``resolve_api_key`` docstring for the canonical example).
    """
    return resolve_api_key_detail(
        name, org_id, store=store, store_factory=store_factory, resolver=resolver, prefix=prefix
    ).value


def make_local_credential_override(
    specs: Iterable[ApiKeySpec],
    store_factory: Callable[[], CredentialStore],
    *,
    prefix: str = PROVIDER_PREFIX,
) -> Callable[[str, Optional[str]], Optional[str]]:
    """Build a tier-0 reader for
    ``noctusai_lib.config.credentials.register_credential_override``.

    Generalises `social-wiring`'s ``app/main.py:_local_api_key`` closure
    (registered there via ``register_credential_override(_local_api_key)``
    BEFORE ``create_product_app()``, so no request can race it): store-ONLY
    lookup, deliberately never falling back to ``resolve_credential`` itself
    (that would recurse forever — ``register_credential_override``'s own
    contract forbids it). Unmanaged keys (not in ``specs``) and a missing
    ``org_id`` short-circuit to ``None`` before any store is touched,
    keeping this off the hot path for every other credential the product
    resolves.

    A raising ``store_factory`` (e.g. ``EncryptionNotConfigured``) is
    deliberately NOT caught here — ``resolve_credential``'s override
    contract already logs + continues past a raising override, so
    double-catching would hide which layer degraded.
    """
    specs_by_name = {spec.name: spec for spec in specs}

    def _read(key: str, org_id: Optional[str]) -> Optional[str]:
        if org_id is None or key not in specs_by_name:
            return None
        store = store_factory()
        stored = read_local_api_key(store, str(org_id), key, prefix=prefix)
        return (stored.tokens or {}).get("value") if stored else None

    return _read


def credentials_table_ddl(schema: str, *, table: str = "credentials") -> str:
    """DDL template for the org-scoped, Fernet-encrypted credentials table.

    Mirrors `social-wiring` migration 001's ``credentials`` table
    (org-scoped authenticated SELECT + service-role bypass). A product
    copies this into its OWN migration file (MCP migrations mirror the
    file — this is an authoring-time helper, not a live-apply tool);
    reuses the canonical `noctusai_lib.domain.sql_templates` policy
    shapes so the RLS convention can't drift.

    Assumes ``public.current_org_id()`` (the SECURITY DEFINER org
    resolver reading the trusted ``noctus_users`` table) already exists
    on the target Supabase project — every platform product's first
    migration declares it once; a product bootstrapping schema #1 must
    ship that function itself first (see `social-wiring` migration 001's
    own header for the canonical declaration this DDL assumes).
    """
    select_policy = rls_subquery_policy(
        schema, table, f"{table}_select_own_org", "SELECT",
        using="org_id = current_org_id()",
    )
    bypass_policy = service_role_bypass(table, schema=schema)
    return (
        f"CREATE TABLE {schema}.{table} (\n"
        f"    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
        f"    org_id UUID NOT NULL,\n"
        f"    provider TEXT NOT NULL,\n"
        f"    encrypted_tokens TEXT NOT NULL,\n"
        f"    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,\n"
        f"    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        f"    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        f"    UNIQUE(org_id, provider)\n"
        f");\n\n"
        f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;\n\n"
        f"{select_policy}\n\n"
        f"{bypass_policy}\n\n"
        f"CREATE INDEX idx_{schema}_{table}_org ON {schema}.{table}(org_id);\n"
        f"CREATE INDEX idx_{schema}_{table}_provider ON {schema}.{table}(provider);"
    )
