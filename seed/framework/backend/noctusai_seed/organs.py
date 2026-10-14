"""One-call organ mounting -- `mount_finance(...)` / `mount_organs([...])`.

A seed organ (`noctusai_lib.domain.<organ>`) is a router factory + a migration generator
+ a few body-size overrides + a FE route. Binding it by hand cost ~180 LOC across three
files per host (`products/commerce/backend/app/{commerce,commerce_deps,routers/...}.py`).
This module is that binding, done once, against the dependencies the seed app already owns:

    from noctusai_seed import create_product_app
    from noctusai_seed.organs import mount_finance

    finance = mount_finance(
        schema="erp",
        auth_dependency=get_current_user_org,        # yields (user, token, org_id)
        get_admin_client=get_admin_client,            # schema-pinned service client
        get_core_client=lambda: _db.get_core_client() # `public` client (noctus_users)
    )
    app = create_product_app(..., organs=[finance])   # routers + upload-size overrides wired

Migration: `noctus.dev.render_organ_migration product=<p> organ=finance` renders the
generator output; a product test calls `assert_organ_migration_current(...)`
(`noctusai_lib.testing.organs`) so the rendered file can never drift.

Registry: `ORGAN_REGISTRY` maps organ name -> :class:`OrganSpec` (migration generator,
header, upload overrides, FE route). ERP organs (parties / items / inventory ...)
register here when they land; nothing else changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException

from noctusai_seed.organ_auth import make_organ_auth

__all__ = [
    "MountedOrgan",
    "ORGAN_REGISTRY",
    "OrganSpec",
    "mount_finance",
    "mount_inventory",
    "mount_contracts",
    "mount_items",
    "mount_parties",
    "mount_purchasing",
    "mount_quotes",
    "mount_organs",
    "assert_organ_migration_order",
    "organ_migration_sql",
    "register_organ",
]


@dataclass(frozen=True)
class MountedOrgan:
    """What `create_product_app(organs=[...])` consumes: routers + body overrides."""

    name: str
    routers: tuple[APIRouter, ...]
    max_body_path_overrides: Mapping[str, int] = field(default_factory=dict)
    #: Optional hook for an organ with a scheduled job: `register_jobs(scheduler=None) -> job_id` (call before
    #: `start_scheduler()`); None for organs without one.
    register_jobs: Optional[Callable[..., Any]] = None

    def __iter__(self):  # a MountedOrgan unpacks like the router list `mount_finance` returns
        return iter(self.routers)


@dataclass(frozen=True)
class OrganSpec:
    """Registry entry: everything the toolchain needs to know about an organ.

    `migration(schema)` -> SQL text (the organ's generator bound to a schema).
    `migration_header` -> first line of that SQL; a rendered file is found by it, never by number.
    `fe_route` -> the host's one-line FE route (documented; the seed shell has no manifest mechanism).
    `requires` -> organs whose tables this organ's DDL references (FKs, guarded widenings): their rendered
    migration files MUST carry a lower number. `optional_requires` -> the same, but only when the host mounts
    that organ too (finance links parties only if parties is there). Checked by `assert_organ_migration_order`.
    """

    name: str
    migration: Callable[[str], str]
    migration_header: str
    max_body_path_overrides: Callable[[], Mapping[str, int]]
    fe_route: Optional[str] = None
    requires: tuple[str, ...] = ()
    optional_requires: tuple[str, ...] = ()


ORGAN_REGISTRY: dict[str, OrganSpec] = {}


def register_organ(spec: OrganSpec) -> OrganSpec:
    if spec.name in ORGAN_REGISTRY and ORGAN_REGISTRY[spec.name] is not spec:
        raise ValueError(f"organ {spec.name!r} already registered")
    ORGAN_REGISTRY[spec.name] = spec
    return spec


def assert_organ_migration_order(product_dir: Any, organs: Sequence[str]) -> dict[str, int]:
    """A product wiring test: the rendered organ migrations respect each organ's `requires`.

    `organs` names the organs the product mounts (registry keys). Each must have a rendered file (found by
    header, as `assert_organ_migration_current` does; its FIRST revision file is the one ordered); every `requires` entry must be among `organs` and carry a LOWER
    file number, and an `optional_requires` entry too when the host mounts it. A migration applied before the table it
    references fails on a fresh database (or, worse for a guarded DDL, silently skips its widening). Returns
    `{organ: file_number}`.
    """
    import re

    from noctusai_lib.testing.organs import find_organ_migration

    numbers: dict[str, int] = {}
    for organ in organs:
        if organ not in ORGAN_REGISTRY:
            raise KeyError(f"unknown organ {organ!r}; registered: {sorted(ORGAN_REGISTRY)}")
        found = find_organ_migration(product_dir, ORGAN_REGISTRY[organ].migration_header)
        assert found, f"no rendered {organ} migration found -- render one with noctus.dev.render_organ_migration"
        # An organ may ship several revision files (applied ones are frozen); what a dependent needs is the dependency's
        # tables to EXIST, i.e. the dependency's FIRST file, and what must come late is the dependent's FIRST file too.
        match = re.match(r"(\d+)_", found[0].name)
        assert match, f"{found[0].name}: a migration file name starts with its number"
        numbers[organ] = int(match.group(1))
    for organ in organs:
        spec = ORGAN_REGISTRY[organ]
        for dep in (*spec.requires, *(d for d in spec.optional_requires if d in numbers)):
            assert dep in numbers, f"{organ} requires {dep}, which this product does not mount (organs={list(organs)})"
            assert numbers[dep] < numbers[organ], (
                f"{organ} ({numbers[organ]:03d}) must be numbered AFTER {dep} ({numbers[dep]:03d}): its DDL references {dep}'s tables"
            )
    return numbers


def organ_migration_sql(organ: str, schema: str) -> str:
    """The generator output for `organ` bound to `schema` (single source for tool + pin test)."""
    try:
        spec = ORGAN_REGISTRY[organ]
    except KeyError:
        raise KeyError(f"unknown organ {organ!r}; registered: {sorted(ORGAN_REGISTRY)}") from None
    return spec.migration(schema)


# -- finance -----------------------------------------------------------------


def _finance_cfg(schema: str):
    from noctusai_lib.domain.finance import FinanceConfig

    return FinanceConfig(schema=schema)


def _finance_migration(schema: str) -> str:
    from noctusai_lib.domain.finance import finance_migration

    return finance_migration(_finance_cfg(schema), schema)


def _finance_overrides() -> Mapping[str, int]:
    from noctusai_lib.domain.finance import (
        ATTACHMENT_UPLOAD_MAX_BYTES,
        ATTACHMENT_UPLOAD_PATH_PATTERN,
        STATEMENT_UPLOAD_MAX_BYTES,
        STATEMENT_UPLOAD_PATH_PATTERN,
    )

    return {
        ATTACHMENT_UPLOAD_PATH_PATTERN: ATTACHMENT_UPLOAD_MAX_BYTES,
        STATEMENT_UPLOAD_PATH_PATTERN: STATEMENT_UPLOAD_MAX_BYTES,
    }


FINANCE_MIGRATION_HEADER = "-- Finance organ -- generated by noctusai_lib.domain.finance.sql"

register_organ(
    OrganSpec(
        name="finance",
        migration=_finance_migration,
        migration_header=FINANCE_MIGRATION_HEADER,
        max_body_path_overrides=_finance_overrides,
        # NOC-REMEDIATE[finance-fe-route]: the FE organ (feat/finance-fe-organ) is not on dev yet; the seed
        # shell has no manifest-driven route mechanism, so the host adds
        #   <Route path="/financeiro/*" element={<FinanceOrgan />} />  (lazy, gated by status_pagina)
        # once `@noctusai/lib` exports it -- 2026-10-14.
        fe_route="/financeiro/*",
        optional_requires=('parties',),
    )
)


def mount_finance(
    *,
    schema: str,
    auth_dependency: Callable[..., Any],
    get_admin_client: Callable[[], Any],
    get_core_client: Callable[[], Any],
    get_storage: Optional[Callable[..., Any]] = None,
    get_charge_operations: Optional[Callable[..., Any]] = None,
    cfg: Any = None,
    prefix: str = "/api/finance",
    reconciliation: bool = True,
    default_tax_regime: Optional[Callable[[Any], Optional[str]]] = None,
) -> MountedOrgan:
    """Build the finance + reconciliation routers for one product, with house auth.

    auth_dependency: the product's license-gated `get_current_user_org` (yields `(user, token, org_id)`;
        401/403 live there). Writes/exports additionally require an ORG ADMIN (role resolved for the SELECTED org
        via `make_organ_auth`, never the home-org role or `user_metadata`).
    get_admin_client: schema-pinned service client (the organ filters `org_id` on every query).
    get_core_client: `public`-schema client (role lookups).
    get_storage: `StorageBackend` dependency; default = Supabase storage over the admin client when it
        has one, else the in-memory Fake (tests / sqlite dev).
    default_tax_regime: host seam `(FinanceContext) -> 'mei'|'simples'|'presumido'|None` that prefills the DRE
        tax regime from another organ's data (e.g. the commerce store profile) until the org saves its own.
    get_charge_operations: gateway `ChargeOperations` dependency for statement sync; default raises 503
        (the declared not-configured state) -- reconciliation reads/imports still work.
    """
    from noctusai_lib.domain.finance import (
        FinanceConfig,
        FinanceContext,
        make_finance_reconciliation_router,
        make_finance_router,
    )

    cfg = cfg or FinanceConfig(schema=schema)
    if cfg.schema != schema:
        raise ValueError(f"cfg.schema {cfg.schema!r} != schema {schema!r}")

    def get_db() -> Any:
        return get_admin_client()

    storage = get_storage or _default_storage_dependency(get_admin_client)

    organ_auth = make_organ_auth(auth_dependency, get_core_client, context="Financeiro")
    auth_dependency, admin_dependency = organ_auth.auth, organ_auth.admin

    def resolve_context(auth: Any, db: Any) -> FinanceContext:
        user, _token, org_id = auth
        return FinanceContext(
            db=db,
            org_id=str(org_id),
            user_id=str(getattr(user, "id", None) or ""),
            is_admin=bool(getattr(auth, "is_admin", False)),  # role IN the selected org; absent => masked
        )

    def no_gateway() -> Any:
        raise HTTPException(status_code=503, detail="Gateway de cobrança não configurado.")

    routers = [
        make_finance_router(
            cfg, auth_dependency, admin_dependency,
            resolve_context=resolve_context, get_db=get_db, get_storage=storage, prefix=prefix,
            default_tax_regime=default_tax_regime,
        )
    ]
    if reconciliation:
        routers.append(
            make_finance_reconciliation_router(
                cfg, auth_dependency, admin_dependency,
                resolve_context=resolve_context, get_db=get_db, get_storage=storage,
                get_charge_operations=get_charge_operations or no_gateway, prefix=prefix,
            )
        )
    return MountedOrgan(
        name="finance",
        routers=tuple(routers),
        max_body_path_overrides=_rebase_overrides(_finance_overrides(), "/api/finance", prefix),
    )


# -- commerce money / fiscal deltas (host `products/commerce`) ----------------------------------------------


def _commerce_cfg(schema: str):
    from noctusai_lib.domain.commerce import CommerceConfig

    return CommerceConfig(schema=schema)


def _commerce_money_migration(schema: str) -> str:
    from noctusai_lib.domain.commerce import commerce_money_migration

    return commerce_money_migration(_commerce_cfg(schema), schema)


def _commerce_fiscal_migration(schema: str) -> str:
    from noctusai_lib.domain.commerce.fiscal_sql import commerce_fiscal_migration

    return commerce_fiscal_migration(_commerce_cfg(schema), schema)


def _no_overrides() -> Mapping[str, int]:
    return {}


def _fiscal_overrides() -> Mapping[str, int]:
    from noctusai_lib.domain.commerce.fiscal_router import (
        CERTIFICATE_UPLOAD_MAX_BYTES,
        CERTIFICATE_UPLOAD_PATH_PATTERN,
    )

    return {CERTIFICATE_UPLOAD_PATH_PATTERN: CERTIFICATE_UPLOAD_MAX_BYTES}


COMMERCE_MONEY_MIGRATION_HEADER = (
    "-- Commerce organ, P4 money states -- generated by noctusai_lib.domain.commerce.money_sql"
)
COMMERCE_FISCAL_MIGRATION_HEADER = (
    "-- Commerce fiscal -- generated by noctusai_lib.domain.commerce.fiscal_sql"
)

register_organ(
    OrganSpec(
        name="commerce_money",
        migration=_commerce_money_migration,
        migration_header=COMMERCE_MONEY_MIGRATION_HEADER,
        max_body_path_overrides=_no_overrides,
    )
)
register_organ(
    OrganSpec(
        name="commerce_fiscal",
        migration=_commerce_fiscal_migration,
        migration_header=COMMERCE_FISCAL_MIGRATION_HEADER,
        max_body_path_overrides=_fiscal_overrides,
    )
)


# -- jobs (the seed generic queue, backs the invoice issue/cancel worker) ------------------------------------

JOBS_MIGRATION_HEADER = "-- Jobs queue -- rendered from noctusai_lib/domain/jobs/migrations/jobs.sql.template"


def _jobs_migration(schema: str) -> str:
    import noctusai_lib.domain.jobs as jobs_pkg
    from pathlib import Path

    template = (Path(jobs_pkg.__file__).parent / "migrations" / "jobs.sql.template").read_text(encoding="utf-8")
    return JOBS_MIGRATION_HEADER + " (do not hand-edit)\n" + template.replace("{{SCHEMA_NAME}}", schema)


register_organ(
    OrganSpec(
        name="jobs",
        migration=_jobs_migration,
        migration_header=JOBS_MIGRATION_HEADER,
        max_body_path_overrides=_no_overrides,
    )
)


# -- items -----------------------------------------------------------------------------------------------


def _items_migration(schema: str) -> str:
    from noctusai_lib.domain.items import ItemsConfig, items_migration

    return items_migration(ItemsConfig(schema=schema))


def _items_overrides() -> Mapping[str, int]:
    from noctusai_lib.domain.items import ITEMS_IMPORT_MAX_BYTES, ITEMS_IMPORT_PATH_PATTERN

    return {ITEMS_IMPORT_PATH_PATTERN: ITEMS_IMPORT_MAX_BYTES}


ITEMS_MIGRATION_HEADER = "-- Items organ -- generated by noctusai_lib.domain.items.sql"

register_organ(
    OrganSpec(
        name="items",
        migration=_items_migration,
        migration_header=ITEMS_MIGRATION_HEADER,
        max_body_path_overrides=_items_overrides,
        fe_route="/itens/*",
    )
)


def mount_items(
    *,
    schema: str,
    auth_dependency: Callable[..., Any],
    get_admin_client: Callable[[], Any],
    get_core_client: Callable[[], Any],
    cfg: Any = None,
    prefix: str = "/api/items",
) -> MountedOrgan:
    """Build the items router for one product, with house auth (same contract as :func:`mount_finance`).

    Writes/imports require an ORG ADMIN of the SELECTED org (`make_organ_auth`); the CSV import path's body-size
    override rides on the returned organ.
    """
    from noctusai_lib.domain.items import ItemsConfig, ItemsContext, make_items_router

    cfg = cfg or ItemsConfig(schema=schema)
    if cfg.schema != schema:
        raise ValueError(f"cfg.schema {cfg.schema!r} != schema {schema!r}")

    def get_db() -> Any:
        return get_admin_client()

    organ_auth = make_organ_auth(auth_dependency, get_core_client, context="Itens")
    auth_dependency, admin_dependency = organ_auth.auth, organ_auth.admin

    def resolve_context(auth: Any, db: Any) -> ItemsContext:
        user, _token, org_id = auth
        return ItemsContext(
            db=db, org_id=str(org_id), user_id=str(getattr(user, "id", None) or ""),
            is_admin=bool(getattr(auth, "is_admin", False)),  # role IN the selected org; absent => masked
        )

    router = make_items_router(
        cfg, auth_dependency, admin_dependency, resolve_context=resolve_context, get_db=get_db, prefix=prefix
    )
    return MountedOrgan(name="items", routers=(router,), max_body_path_overrides=_rebase_overrides(_items_overrides(), "/api/items", prefix))


# -- parties / inventory / purchasing ---------------------------------------------------------------------


def _parties_migration(schema: str) -> str:
    from noctusai_lib.domain.parties import PartiesConfig, parties_migration

    return parties_migration(PartiesConfig(schema=schema), schema)


def _parties_overrides() -> Mapping[str, int]:
    from noctusai_lib.domain.parties import IMPORT_UPLOAD_MAX_BYTES, IMPORT_UPLOAD_PATH_PATTERN

    return {IMPORT_UPLOAD_PATH_PATTERN: IMPORT_UPLOAD_MAX_BYTES}


def _inventory_migration(schema: str) -> str:
    from noctusai_lib.domain.inventory import InventoryConfig, inventory_migration

    return inventory_migration(InventoryConfig(schema=schema), schema)


def _purchasing_migration(schema: str) -> str:
    from noctusai_lib.domain.purchasing import PurchasingConfig, purchasing_migration

    return purchasing_migration(PurchasingConfig(schema=schema), schema)


register_organ(
    OrganSpec(
        name="parties",
        migration=_parties_migration,
        migration_header="-- Parties organ -- generated by noctusai_lib.domain.parties.sql",
        max_body_path_overrides=_parties_overrides,
        fe_route="/parceiros/*",
    )
)
register_organ(
    OrganSpec(
        name="inventory",
        migration=_inventory_migration,
        migration_header="-- Inventory organ -- generated by noctusai_lib.domain.inventory.sql",
        max_body_path_overrides=_no_overrides,
        fe_route="/estoque/*",
        requires=('items',),
    )
)
def _quotes_migration(schema: str) -> str:
    from noctusai_lib.domain.quotes import QuotesConfig, quotes_migration

    return quotes_migration(QuotesConfig(schema=schema), schema)


register_organ(
    OrganSpec(
        name="quotes",
        migration=_quotes_migration,
        migration_header="-- Quotes organ -- generated by noctusai_lib.domain.quotes.sql",
        max_body_path_overrides=_no_overrides,
        fe_route="/orcamentos/*  (+ the public accept page, e.g. /orcamento/:token, outside the authed shell)",
    )
)
register_organ(
    OrganSpec(
        name="purchasing",
        migration=_purchasing_migration,
        migration_header="-- Purchasing organ -- generated by noctusai_lib.domain.purchasing.sql",
        max_body_path_overrides=_no_overrides,
        fe_route="/compras/*",
        requires=('parties', 'items', 'inventory', 'finance'),
    )
)


def _contracts_migration(schema: str) -> str:
    from noctusai_lib.domain.contracts import ContractsConfig, contracts_migration

    return contracts_migration(ContractsConfig(schema=schema), schema)


def _contracts_overrides() -> Mapping[str, int]:
    from noctusai_lib.domain.contracts import ATTACHMENT_UPLOAD_MAX_BYTES, ATTACHMENT_UPLOAD_PATH_PATTERN

    return {ATTACHMENT_UPLOAD_PATH_PATTERN: ATTACHMENT_UPLOAD_MAX_BYTES}


register_organ(
    OrganSpec(
        name="contracts",
        migration=_contracts_migration,
        migration_header="-- Contracts organ -- generated by noctusai_lib.domain.contracts.sql",
        max_body_path_overrides=_contracts_overrides,
        fe_route="/contratos/*",
        requires=('parties', 'items', 'finance'),
    )
)


def _context_kwargs(auth: Any) -> dict[str, Any]:
    user, _token, org_id = auth
    return {
        "org_id": str(org_id),
        "user_id": str(getattr(user, "id", None) or ""),
        "is_admin": bool(getattr(auth, "is_admin", False)),  # role IN the selected org; absent => masked / non-admin
    }


def mount_parties(
    *,
    schema: str,
    auth_dependency: Callable[..., Any],
    get_admin_client: Callable[[], Any],
    get_core_client: Callable[[], Any],
    cfg: Any = None,
    prefix: str = "/api/parties",
) -> MountedOrgan:
    """Build the parties router (same contract as :func:`mount_items`): writes need an ORG ADMIN of the SELECTED org;
    the CSV import path's body-size override rides on the returned organ."""
    from noctusai_lib.domain.parties import PartiesConfig, PartiesContext, make_parties_router

    cfg = cfg or PartiesConfig(schema=schema)
    if cfg.schema != schema:
        raise ValueError(f"cfg.schema {cfg.schema!r} != schema {schema!r}")
    organ_auth = make_organ_auth(auth_dependency, get_core_client, context="Parceiros")

    def resolve_context(auth: Any, db: Any) -> Any:
        return PartiesContext(db=db, **_context_kwargs(auth))

    router = make_parties_router(
        cfg, organ_auth.auth, organ_auth.admin, resolve_context=resolve_context, get_db=get_admin_client, prefix=prefix
    )
    return MountedOrgan(name="parties", routers=(router,), max_body_path_overrides=_rebase_overrides(_parties_overrides(), "/api/parties", prefix))


def mount_inventory(
    *,
    schema: str,
    auth_dependency: Callable[..., Any],
    get_admin_client: Callable[[], Any],
    get_core_client: Callable[[], Any],
    cfg: Any = None,
    prefix: str = "/api/inventory",
) -> MountedOrgan:
    """Build the inventory router (same contract as :func:`mount_items`). Reservations are NOT an HTTP surface: other
    organs hold stock through `make_stock_port`."""
    from noctusai_lib.domain.inventory import InventoryConfig, InventoryContext, make_inventory_router

    cfg = cfg or InventoryConfig(schema=schema)
    if cfg.schema != schema:
        raise ValueError(f"cfg.schema {cfg.schema!r} != schema {schema!r}")
    organ_auth = make_organ_auth(auth_dependency, get_core_client, context="Estoque")

    def resolve_context(auth: Any, db: Any) -> Any:
        return InventoryContext(db=db, **_context_kwargs(auth))

    router = make_inventory_router(
        cfg, organ_auth.auth, organ_auth.admin, resolve_context=resolve_context, get_db=get_admin_client, prefix=prefix
    )
    return MountedOrgan(name="inventory", routers=(router,))


def mount_purchasing(
    *,
    schema: str,
    auth_dependency: Callable[..., Any],
    get_admin_client: Callable[[], Any],
    get_core_client: Callable[[], Any],
    cfg: Any = None,
    prefix: str = "/api/purchasing",
) -> MountedOrgan:
    """Build the purchasing router. Org admin gates the writes; APPROVAL is decided from the trusted role in the
    SELECTED org plus membership in that org's own approver list (`pur_approvers`, read by the organ -- no global
    permission, so a grant in one org can never approve in another; org admins manage the list). The cross-organ legs
    follow `cfg.with_*`: stock through `SupabaseStockPort` (inventory), payables through `SupabaseFinanceBooking`
    (finance, linked to the party when `cfg.with_parties`); a host that mounts neither keeps the Noop ports."""
    from noctusai_lib.domain.finance import FinanceConfig, make_finance_booking
    from noctusai_lib.domain.inventory import InventoryConfig, make_stock_port
    from noctusai_lib.domain.purchasing import PurchasingConfig, PurchasingContext, make_purchasing_router

    cfg = cfg or PurchasingConfig(schema=schema)
    if cfg.schema != schema:
        raise ValueError(f"cfg.schema {cfg.schema!r} != schema {schema!r}")
    organ_auth = make_organ_auth(auth_dependency, get_core_client, context="Compras")

    def resolve_context(auth: Any, db: Any) -> Any:
        return PurchasingContext(db=db, **_context_kwargs(auth))

    inv_cfg = InventoryConfig(schema=schema, with_items=cfg.with_items, items_prefix=cfg.items_prefix, table_prefix=cfg.inventory_prefix)
    fin_cfg = FinanceConfig(schema=schema, with_parties=cfg.with_parties, parties_prefix=cfg.parties_prefix)
    router = make_purchasing_router(
        cfg, organ_auth.auth, organ_auth.admin,
        resolve_context=resolve_context, get_db=get_admin_client, prefix=prefix,
        stock_factory=(lambda db: make_stock_port("supabase", db=db, cfg=inv_cfg)) if cfg.with_inventory else (lambda db: make_stock_port()),
        booking_factory=lambda db: make_finance_booking("supabase", db=db, cfg=fin_cfg),
    )
    return MountedOrgan(name="purchasing", routers=(router,))


def mount_contracts(
    *,
    schema: str,
    auth_dependency: Callable[..., Any],
    get_admin_client: Callable[[], Any],
    get_core_client: Callable[[], Any],
    get_storage: Optional[Callable[..., Any]] = None,
    get_signature: Optional[Callable[[Any], Any]] = None,
    cfg: Any = None,
    prefix: str = "/api/contracts",
) -> MountedOrgan:
    """Build the contracts router (same contract as :func:`mount_items`): writes need an ORG ADMIN of the SELECTED
    org. Receivables are booked into the finance organ through `SupabaseContractsBilling` (finance schema = this
    schema; a host without finance mounts nothing different -- its migration simply has no `fin_entries`). Attachment
    storage defaults like :func:`mount_finance`; `get_signature(ctx)` is the optional e-signature adapter getter
    (None => the signature routes answer 409 `assinatura_nao_configurada`). The returned organ's `register_jobs`
    registers the daily `contracts_generate_billing` job on the seed scheduler."""
    from noctusai_lib.domain.contracts import (
        ContractsConfig, ContractsContext, make_contracts_billing, make_contracts_router, register_contracts_billing,
    )
    from noctusai_lib.domain.finance import FinanceConfig

    cfg = cfg or ContractsConfig(schema=schema)
    if cfg.schema != schema:
        raise ValueError(f"cfg.schema {cfg.schema!r} != schema {schema!r}")
    organ_auth = make_organ_auth(auth_dependency, get_core_client, context="Contratos")
    storage = get_storage or _default_storage_dependency(get_admin_client)
    fin_cfg = FinanceConfig(schema=schema)

    def billing_for(db: Any) -> Any:
        return make_contracts_billing("supabase", db=db, finance_cfg=fin_cfg)

    def resolve_context(auth: Any, db: Any) -> Any:
        return ContractsContext(db=db, **_context_kwargs(auth))

    router = make_contracts_router(
        cfg, organ_auth.auth, organ_auth.admin, resolve_context=resolve_context, get_db=get_admin_client,
        get_billing=billing_for, get_signature=get_signature, get_storage=storage, prefix=prefix,
    )

    def register_jobs(scheduler: Any = None) -> str:
        return register_contracts_billing(cfg, get_db=get_admin_client, get_billing=billing_for, scheduler=scheduler)

    return MountedOrgan(
        name="contracts", routers=(router,), register_jobs=register_jobs,
        max_body_path_overrides=_rebase_overrides(_contracts_overrides(), "/api/contracts", prefix),
    )


def mount_quotes(
    *,
    schema: str,
    auth_dependency: Callable[..., Any],
    get_admin_client: Callable[[], Any],
    get_core_client: Callable[[], Any],
    cfg: Any = None,
    prefix: str = "/api/quotes",
    public_prefix: str = "/api/public/quotes",
    get_link_secret: Optional[Callable[..., str]] = None,
    accept_url: Optional[Callable[[str], str]] = None,
    get_email: Optional[Callable[..., Any]] = None,
    issuer: Optional[Callable[[str], Mapping[str, Any]]] = None,
    get_accept_handler: Optional[Callable[..., Any]] = None,
    get_signature: Optional[Callable[..., Any]] = None,
    docx_template: Optional[Callable[[Any], bytes]] = None,
    get_docx_adapter: Optional[Callable[..., Any]] = None,
    rate_limit: Optional[Callable[[str], Callable[[Callable], Callable]]] = None,
    client_ip: Optional[Callable[[Any], Optional[str]]] = None,
    is_org_active: Optional[Callable[[Any, str], bool]] = None,
) -> MountedOrgan:
    """Build the quotes routers. STAFF routes (`prefix`) follow the organ rule: any authenticated staff reads, writes need
    an ORG ADMIN of the SELECTED org. PUBLIC accept routes (`public_prefix`) carry NO auth - the signed token is the
    credential - and are rate-limited through `rate_limit` (e.g. slowapi's `limiter.limit`); they are mounted only when the
    host supplies `get_link_secret` (without it a quote cannot be sent either: `send` answers 503 `link_indisponivel`).

    Everything the organ does not own is an OPTIONAL host seam: `get_accept_handler` (the convert-on-accept
    `QuoteAcceptHandler`; default no-op => accepted quotes end `skipped`), `get_signature` (mounts the e-signature routes),
    `docx_template` (+ `get_docx_adapter`, mounts the DOCX route), `get_email`, `issuer`, `client_ip`, `is_org_active`.
    The PDF needs nothing from the host."""
    from noctusai_lib.domain.quotes import QuotesConfig, QuotesContext, make_quotes_public_router, make_quotes_router

    cfg = cfg or QuotesConfig(schema=schema)
    if cfg.schema != schema:
        raise ValueError(f"cfg.schema {cfg.schema!r} != schema {schema!r}")
    organ_auth = make_organ_auth(auth_dependency, get_core_client, context="Orcamentos")

    def resolve_context(auth: Any, db: Any) -> Any:
        return QuotesContext(db=db, **_context_kwargs(auth))

    staff_extra: dict[str, Any] = {}
    if get_accept_handler is not None:
        staff_extra["get_handler"] = get_accept_handler
    if get_docx_adapter is not None:
        staff_extra["get_docx_adapter"] = get_docx_adapter
    staff = make_quotes_router(
        cfg, organ_auth.auth, organ_auth.admin, resolve_context=resolve_context, get_db=get_admin_client, prefix=prefix,
        get_email=get_email, get_link_secret=get_link_secret, accept_url=accept_url, issuer=issuer,
        get_signature=get_signature, docx_template=docx_template, **staff_extra,
    )
    routers: list[APIRouter] = [staff]
    if get_link_secret is not None:
        public_extra = {"get_handler": get_accept_handler} if get_accept_handler is not None else {}
        routers.append(
            make_quotes_public_router(
                cfg, get_db=get_admin_client, get_link_secret=get_link_secret, issuer=issuer, is_org_active=is_org_active,
                client_ip=client_ip, rate_limit=rate_limit, prefix=public_prefix, **public_extra,
            )
        )
    return MountedOrgan(name="quotes", routers=tuple(routers))


def _rebase_overrides(overrides: Mapping[str, int], default_prefix: str, prefix: str) -> dict[str, int]:
    """Upload-size patterns are declared against the organ's default prefix; a host that mounts the
    routers elsewhere gets the patterns re-derived from ITS prefix (else the override never matches)."""
    out: dict[str, int] = {}
    for pattern, limit in overrides.items():
        if not pattern.startswith(default_prefix):
            raise ValueError(f"override {pattern!r} does not start with {default_prefix!r}")
        out[prefix.rstrip("/") + pattern[len(default_prefix):]] = limit
    return out


def _default_storage_dependency(get_admin_client: Callable[[], Any]) -> Callable[[], Any]:
    from noctusai_lib.integrations.storage import make_storage_backend
    from noctusai_lib.integrations.storage.fake import FakeStorageBackend

    cache: dict[int, Any] = {}

    def get_storage() -> Any:
        admin = get_admin_client()
        hit = cache.get(id(admin))
        if hit is not None:
            return hit
        backend = (
            make_storage_backend(kind="supabase", client=admin) if hasattr(admin, "storage") else FakeStorageBackend()
        )
        cache.clear()
        cache[id(admin)] = backend
        return backend

    return get_storage


def mount_organs(organs: Sequence[MountedOrgan]) -> tuple[list[APIRouter], dict[str, int]]:
    """Flatten mounted organs -> (routers, merged body-size overrides)."""
    routers: list[APIRouter] = []
    overrides: dict[str, int] = {}
    for organ in organs:
        routers.extend(organ.routers)
        for pattern, limit in organ.max_body_path_overrides.items():
            if pattern in overrides and overrides[pattern] != limit:
                raise ValueError(
                    f"conflicting body-size override for {pattern!r}: {overrides[pattern]} vs {limit} "
                    f"(organ {organ.name!r})"
                )
            overrides[pattern] = limit
    return routers, overrides
