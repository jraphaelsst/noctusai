"""
Dependencies for Community.

This file is the canonical reference every new product inherits via
``scaffold_product``. The auth dep ``get_current_user_org`` is wired
through :func:`noctusai_lib.api.auth.make_get_current_user_org` (factory
pattern) — using the seed's plain ``get_org_id`` / ``get_user_role``
through ``Depends(...)`` does NOT chain through FastAPI because their
positional ``user`` / ``token`` args become required query parameters.

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the
full why and the deprecation warning that fires on the broken shape.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException

from noctusai_seed import (
    create_database_module,
    create_dependencies,
    select_get_current_user,
)
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from app.config import settings

logger = logging.getLogger(__name__)

_db = create_database_module(settings, schema="community")
_deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambdas: tests patch ``_db.get_client`` AFTER this module
# imports. Capturing the bound method at module load would freeze the
# pre-patch reference. The lambda re-resolves on every request so both
# production and test paths see the right client.
# Prod path (Supabase JWT validation). `select_get_current_user`
# transparently swaps in the already-shipped dev-auth dependency when
# `DATABASE_BACKEND=sqlite` AND the dev-auth double-gate is on — zero
# per-product code, parallel-never-modify (the prod path is returned
# untouched in every non-sqlite env). Inherited by every product
# through scaffold_product / propagation.
_prod_get_current_user = make_get_current_user(lambda: _db.get_client())
get_current_user = select_get_current_user(settings, _prod_get_current_user)
# `get_admin_client_fn=lambda: _db.get_core_client()` — NOT get_admin_client().
# `noctus_users` lives in the `public` schema; `get_admin_client()` is scoped
# to THIS product's schema and would 500 with PGRST205 (see
# `seed-trusted-org-resolution`, 2026-07-14 — the make_get_current_user_org
# docstring in noctusai_lib.api.auth has the full rationale + the prod
# incident this mirrors on the ERP side).
# `allow_customer=True`: this is the BASE resolver both community gates wrap.
# The seed refuses customer roles by default (SEC-2); here the decision is
# made one level up — `get_current_user_org` (staff allow-list) and
# `get_membro_context` (members only) — so a `membro` must reach them.
_get_any_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: None,  # retired metadata fallback (seed NOC-REMEDIATE[auth-org-fallback-param])
    get_admin_client_fn=lambda: _db.get_core_client(),
    required=True,
    allow_customer=True,
)

#: `noctus_users.org_role` of an end customer with a login (migration 013).
MEMBRO_ORG_ROLE = "membro"

#: Org roles that are community STAFF. An ALLOW-list: the community org is
#: the platform org, shared with other products' users (e.g. `corretor`),
#: who must never read Mônica's members. Mirrors `community.eh_equipe()` in
#: migration 013 — keep the two identical (pinned by tests/test_team_policy.py).
#: The single Python source: the API gates below AND the seed `/api/team`
#: roster (`TeamPolicy(staff_roles=...)` in app/main.py) both read it.
#: `noctus_users.role == 'admin'` (platform admin) is staff too.
COMMUNITY_STAFF_ORG_ROLES: frozenset[str] = frozenset({"owner", "admin", "moderador", "dev"})
_ADMIN_ORG_ROLES: frozenset[str] = frozenset({"owner", "admin"})


def _perfil_of(user: Any) -> dict | None:
    """The caller's trusted `public.noctus_users` row (org_id, org_role, role),
    or None. Authorization reads THIS, never `user_metadata` — metadata is
    writable by the user themselves (`auth.updateUser({data})`)."""
    rows = (
        _db.get_core_client()
        .table("noctus_users")
        .select("org_id, org_role, role")
        .eq("id", str(getattr(user, "id", "")))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _org_role_of(user: Any) -> str | None:
    """Trusted `public.noctus_users.org_role` for `user` (None when absent)."""
    perfil = _perfil_of(user)
    return perfil.get("org_role") if perfil else None


def _eh_equipe(perfil: dict | None) -> bool:
    if not perfil:
        return False
    return perfil.get("org_role") in COMMUNITY_STAFF_ORG_ROLES or perfil.get("role") == "admin"


async def get_current_user_org(auth: tuple = Depends(_get_any_user_org)) -> tuple:
    """Back-office auth: community STAFF only (403 otherwise).

    Staff = `COMMUNITY_STAFF_ORG_ROLES` or a platform admin, read from the
    trusted profile row. A `membro`, another product's user (`corretor`…),
    an unknown role, or a user with NO profile row (whose org would
    otherwise come from spoofable metadata) all get 403. RLS enforces the
    same boundary (`community.eh_equipe()`, migration 013); this is the API
    half. Member routes use `get_membro_context` instead.
    """
    if not _eh_equipe(_perfil_of(auth[0])):
        raise http_error(403, "Área restrita à equipe.")
    return auth


async def get_membro_context(auth: tuple = Depends(_get_any_user_org)) -> tuple:
    """Member-portal auth → `(user, token, org_id: UUID, membro: dict)`.

    403 unless the caller's trusted profile says `membro` and a
    `community.membros` row is linked to their login in THAT org. The row
    is read with the service-role client — members have no RLS read on
    `membros` (its `observacoes`/`tags` are staff-only) — keyed on the
    verified JWT subject and the profile's org, never on request input.
    Portal handlers must project the columns they return.
    """
    user = auth[0]
    perfil = _perfil_of(user)
    if not perfil or perfil.get("org_role") != MEMBRO_ORG_ROLE or not perfil.get("org_id"):
        raise http_error(403, "Área exclusiva para membros.")
    org_id = coerce_org_uuid(perfil["org_id"])
    rows = (
        get_admin_client()
        .table("membros")
        .select("*")
        .eq("user_id", str(getattr(user, "id", "")))
        .eq("org_id", str(org_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise http_error(403, "Cadastro de membro não encontrado.")
    return user, auth[1], org_id, rows[0]


# `GET /api/eu` (contract §Identity, slice BE-A): "any authenticated org
# user (uses the base auth, not the staff gate)" — neither
# `get_current_user_org` (403s a membro) nor `get_membro_context` (403s
# anyone without a linked `membros` row) fits. `_get_any_user_org` is
# exactly that base primitive already; this is a public re-export of it
# (same pattern as `get_user_role`/`get_org_id` below) rather than a
# second `make_get_current_user_org(...)` wiring.
get_any_org_user = _get_any_user_org


# Plain-call helpers (NOT to be wired via ``Depends(...)``) — kept for
# imperative call-sites and for backward compatibility.
get_user_role = _deps.get_user_role
get_org_id = _deps.get_org_id
# Public schema (`noctus_users`, `auth.admin.*`) — needed by
# `noctusai_lib.domain.org.provision_invited_identity` /
# `attach_user_to_org` / `find_auth_user_id_by_email` (contract
# §Identity: `POST /api/cadastro`, `POST /api/membros/{id}/acesso`).
# Same client `_create_team_router`'s `/api/team/accept` uses via
# `deps.get_core_client()` — re-exported here so product code never
# reaches into `_db` directly.
get_core_client = _deps.get_core_client


# Late-binding wrappers so test patches on ``_db.get_*`` reach call sites.
def get_user_client(token: str):
    return _db.get_client(token)


def get_admin_client():
    return _db.get_admin_client()


_ERROR_CODES = {
    400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
    404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def http_error(status_code: int, detail: str, *, code: str | None = None) -> HTTPException:
    """Build an ``HTTPException`` whose JSON body has a top-level ``detail``
    key — the contract's error shape (``{"detail": "..."}``).

    The seed's global handler (``noctusai_lib.primitives.exceptions.
    http_exception_handler``) reshapes a PLAIN-STRING-``detail``
    ``HTTPException`` into the platform-wide legacy envelope
    (``{"error": {"code", "message"}}``) — no top-level ``detail`` key at
    all. It passes a DICT ``detail`` containing BOTH ``"detail"`` and
    ``"code"`` keys through **verbatim** instead (documented on that
    handler as the escape hatch for exactly this case). Every explicit
    error this module/its routers raise goes through this helper rather
    than a bare ``HTTPException(status_code=..., detail="...")`` so the
    wire shape actually matches what the contract — and the frontend
    built against it in parallel — expect.

    Out of scope: FastAPI's OWN automatic request-body validation
    (missing/malformed fields) still surfaces via the seed's separate
    ``ValidationError`` handler in the same legacy envelope — that is
    platform-wide behavior this product does not override.
    """
    code = code or _ERROR_CODES.get(status_code, "HTTP_ERROR")
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code})


# ── Community role gate — admin / moderador / membro ────────────────────


def get_community_role(user: Any) -> str:
    """Resolve the caller's role for THIS product: ``"admin"``, ``"moderador"``
    or ``"membro"`` (an end customer — migration 013; never a back-office role).

    Read ONLY from the trusted ``public.noctus_users`` row (``_perfil_of``):
    ``membro`` → ``"membro"``; platform admin (``role='admin'``) or org
    ``owner``/``admin`` → ``"admin"``; ``moderador``/``dev`` → ``"moderador"``.
    Anything else is not community staff and raises 403. The previous
    cascade also consulted ``resolve_sso_role(user_metadata)`` — writable by
    the user — and degraded unknown roles to ``"moderador"``; with the org
    shared with other products' users, both were privilege leaks
    (security review 2026-09-28).
    """
    perfil = _perfil_of(user)
    if perfil and perfil.get("org_role") == MEMBRO_ORG_ROLE:
        return "membro"
    if not _eh_equipe(perfil):
        # Unreachable behind `get_current_user_org`; kept strict so a route
        # that forgot the gate still cannot grant a role.
        raise http_error(403, "Área restrita à equipe.")
    if perfil.get("role") == "admin" or perfil.get("org_role") in _ADMIN_ORG_ROLES:
        return "admin"
    return "moderador"


def require_admin(role: str, *, action: str) -> None:
    """403 unless ``role == "admin"`` — the contract's write gate.

    ``action`` is a pt-BR infinitive phrase so the message matches the
    contract's ``"Apenas administradores podem …"`` shape verbatim
    (e.g. ``action="criar planos"`` → "Apenas administradores podem
    criar planos.").
    """
    if role != "admin":
        raise http_error(403, f"Apenas administradores podem {action}.")


# ── Public-endpoint org resolution (contract §Aplicações, PUBLIC routes) ─
#
# Community is single-tenant by product decision (MASTER-PROMPT.md:
# "Single community (no multi-tenancy beyond the seed's org scoping)"),
# so its schema holds exactly one org's rows — but an anonymous request
# carries no JWT, hence no `current_org_id()`. Rather than hardcode an
# org id, this resolves the org the SAME way the platform already models
# "which org licenses this product": `public.products.slug` joined to
# `public.licenses` (status='active') — the exact table pair
# `snapshot_product_usage()` (products/core/backend/migrations/
# 001_noctusai_core.sql) already walks for per-product usage reporting.
# No new table, no invented mechanism.
_COMMUNITY_PRODUCT_SLUG = "community"


def resolve_public_org_id() -> UUID:
    """Resolve the single org licensed for this product, for anon routes.

    Raises:
        HTTPException(503): no product row, no active license, or more
            than one active license (a genuine misconfiguration for a
            single-tenant product) — surfaced loudly rather than
            guessing which org an anonymous submission belongs to.
    """
    core = _db.get_core_client()
    product = (
        core.table("products")
        .select("id")
        .eq("slug", _COMMUNITY_PRODUCT_SLUG)
        .limit(1)
        .execute()
    )
    product_rows = product.data or []
    if not product_rows:
        raise http_error(503, "Formulário de inscrição indisponível no momento.")
    product_id = product_rows[0]["id"]
    licenses = (
        core.table("licenses")
        .select("org_id")
        .eq("product_id", product_id)
        .eq("status", "active")
        .execute()
    )
    license_rows = licenses.data or []
    if len(license_rows) != 1:
        raise http_error(503, "Formulário de inscrição indisponível no momento.")
    return coerce_org_uuid(license_rows[0]["org_id"])


def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id into a UUID.

    Auth-side ``org_id`` is sometimes a real UUID string, sometimes an
    opaque test fixture (``"test-org-123"``). DB columns are UUID-typed,
    so coerce at the boundary. Non-UUID inputs map to a deterministic
    ``uuid5(NAMESPACE_OID, raw)`` so the same fixture always lands on
    the same row. The user-scoped Supabase client is RLS-bound by the
    JWT, not by this UUID — safe to derive deterministically.

    Lifted to the seed at the N=3 recurrence trigger (youtube-crawler's
    upload + settings + videos routers each had a private copy before
    being lifted to a single helper). Now every new product inherits it.
    """
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))


# ── Module 3: WhatsApp (community-m3-contract.md, D4) ─────────────────
#
# Community gets its OWN WAHA session on its OWN instance (D4) — a
# separate container from whatever other product's WAHA session exists.
# `get_whatsapp_client()` is the seed's Fake+Real+factory
# (`KB § PATTERNS/backend/seed-fake-real-adapter.md`). This product uses
# its Fake ONLY under `whatsapp_allow_fake` (test harness / local dev);
# otherwise "no WAHA configured" is an explicit state, never a silent Fake
# (see `resolve_community_waha_client`).


def actor_uuid(user: Any) -> UUID | None:
    """Coerce the ACTING user's id to a UUID for audit-trail columns
    (`proposto_por` / `confirmado_por` / `criada_por` / `resolvido_por`).

    Same test-fixture-compatible coercion `coerce_org_uuid` applies to
    `org_id` (a real Supabase auth user id IS a UUID in production; test
    fixtures use an opaque non-UUID label like `"test-user-123"`),
    applied here to the acting user instead of the org.
    """
    raw = getattr(user, "id", None)
    if not raw:
        return None
    return coerce_org_uuid(raw)


WHATSAPP_NAO_CONECTADO_DETAIL = (
    "WhatsApp não conectado. Conecte um número em Conexões para usar esta função."
)
WHATSAPP_NAO_CONECTADO_CODE = "WHATSAPP_NAO_CONECTADO"


def resolve_community_waha_client(
    *, org_id: UUID, admin_client: Any, allow_fake: bool | None = None,
):
    """The WAHA client module 3's routers actually talk to — or ``None``
    when WhatsApp is NOT configured for this org.

    Slice C (user decision 2026-09-17): prefers `org_id`'s
    `community.whatsapp_connections` row (base_url + decrypted api_key +
    session_name — a line saved via `Configurações → WhatsApp →
    Conexões`), falling back to the static `community_waha_*` settings
    when no connection is stored yet OR encryption is unconfigured.

    When neither yields a WAHA base URL, this returns ``None`` — never a
    silent `FakeWahaClient` — unless `settings.whatsapp_allow_fake` (or the
    `allow_fake` override) is on (test harness / local dev only). A Fake in
    prod reported "Aguardando pareamento" and let a broadcast read
    "Enviada" with nothing sent (2026-10-01). Callers decide: WAHA-dependent
    routes refuse 503 (`get_community_waha_client`); `GET /sessao` reports
    `NAO_CONFIGURADO` (`get_community_waha_client_optional`).

    `admin_client` is the DI seam (`KB § PATTERNS/backend/di-test-seam.md`)
    — `get_community_waha_client` binds it to `get_admin_client()`; tests
    call this directly with a `MockSupabaseClient` instead of patching
    the module-level factory.
    """
    from noctusai_lib.integrations.whatsapp import (
        build_whatsapp_connection_store,
        get_whatsapp_client,
    )
    from noctusai_lib.security.api_keys import EncryptionNotConfigured

    fake_ok = settings.whatsapp_allow_fake if allow_fake is None else allow_fake

    record = None
    try:
        store = build_whatsapp_connection_store(
            admin_client, encryption_key=settings.encryption_key, schema="community",
        )
        connections = store.list_connections(org_id=org_id)
        if connections:
            record = store.get_connection(
                connection_id=connections[0].id, org_id=org_id, decrypt=True
            )
    except EncryptionNotConfigured:
        logger.warning(
            "community whatsapp: ENCRYPTION_KEY ausente — conexões salvas ignoradas",
        )
        record = None

    if record is not None:
        base_url, api_key, session = record.base_url, record.api_key, record.session_name
    else:
        base_url = settings.community_waha_base_url
        api_key = settings.community_waha_api_key or None
        session = settings.community_waha_session

    if not base_url and not fake_ok:
        logger.info(
            "community whatsapp: nenhuma conexão WAHA para org %s — não configurado",
            org_id,
        )
        return None

    return get_whatsapp_client(
        base_url=base_url or None,
        api_key=api_key,
        session=session,
        external_base_url=settings.community_waha_external_base_url or None,
    )


def get_community_waha_client_optional(auth: tuple = Depends(get_current_user_org)):
    """The org's WAHA client, or ``None`` when WhatsApp is not configured."""
    _user, _token, raw_org = auth
    return resolve_community_waha_client(
        org_id=coerce_org_uuid(raw_org), admin_client=get_admin_client()
    )


def get_community_waha_client(client=Depends(get_community_waha_client_optional)):
    """The org's WAHA client; REFUSES 503 `WHATSAPP_NAO_CONECTADO` when
    WhatsApp is not configured — before any route-side state change."""
    if client is None:
        raise http_error(
            503, WHATSAPP_NAO_CONECTADO_DETAIL, code=WHATSAPP_NAO_CONECTADO_CODE,
        )
    return client