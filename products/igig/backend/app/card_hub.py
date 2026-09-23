"""IgIg's two card hubs — Cliente and Negócio — as seed `CardHubConfig`s.

The card (notes, tags, members, checklists, operator checklist lines, LGPD
documents, timeline, badges) is `noctusai_lib.domain.card_hub`, lifted out of
social-wiring in wave A. IgIg consumes it for TWO entities (roadmap R9: the
cliente card IS the funnel card component):

    /api/clientes/...            cliente card  (tables `cliente_*`)
    /api/comercial/negocios/...  funnel card   (tables `negocio_*`)

Tables come from `card_hub_migration(cfg, "igig")` — committed verbatim as
`migrations/019_card_hub.sql`, and `tests/test_card_hub_wiring.py` pins that the
file still equals the generator's output for these configs.

WHY THE SERVICE-ROLE CLIENT HERE (and the RLS-scoped one for the pipelines)
---------------------------------------------------------------------------
The generated card-hub tables carry an `authenticated` SELECT policy and NO
authenticated write policy — writes go through `service_role` by construction
(the document access log is append-only for everyone else). That is the seed's
convention (`noctusai_lib.domain.card_hub.sql`), so the card-hub `get_db` is the
igig-pinned admin client, and every card-hub query filters `org_id`
explicitly (the seed passes the caller's org on every call). The caller's org
still comes from the trusted `get_current_user_org`.

Members are `igig.profissional` rows (the agency's team); a PUT body carries
`profissional_ids`.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.card_hub import (
    CardHubConfig,
    CardHubContext,
    MemberSource,
    card_hub_routers,
)
from noctusai_lib.integrations.persistence.table_reads import actor_resolver

from app import database
from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import get_admin_db
from app.storage import get_storage

__all__ = [
    "CARD_HUB_CLIENTE",
    "CARD_HUB_NEGOCIO",
    "cliente_card_hub_routers",
    "negocio_card_hub_routers",
]

_MEMBROS = MemberSource(table="profissional", fk="profissional_id", label="nome", cor=None)
#: Who a user id is — `public.noctus_users` through core's client. Late-bound
#: (`database._db` re-read per call), the same reason `app/dependencies.py`
#: wraps its clients in lambdas: binding the method at import would freeze the
#: client this process started with.
_ATORES = actor_resolver(lambda: database._db.get_core_client())

CARD_HUB_CLIENTE = CardHubConfig(
    entity_kind="cliente",
    entity_table="cliente",
    entity_fk="cliente_id",
    id_param="cliente_id",
    table_prefix="cliente",
    member_source=_MEMBROS,
    bucket=settings.igig_cardhub_bucket,
    actor_resolver=_ATORES,
)

CARD_HUB_NEGOCIO = CardHubConfig(
    entity_kind="negocio",
    entity_table="negocio",
    entity_fk="negocio_id",
    id_param="negocio_id",
    table_prefix="negocio",
    member_source=_MEMBROS,
    bucket=settings.igig_cardhub_bucket,
    actor_resolver=_ATORES,
)


def _contexto(auth: tuple, db: Any) -> CardHubContext:
    user, _token, raw_org = auth
    return CardHubContext(
        db=db, org_id=coerce_org_uuid(raw_org), user_id=getattr(user, "id", None)
    )


def _routers(cfg: CardHubConfig, prefix: str, tag: str):
    return card_hub_routers(
        cfg,
        auth_dependency=get_current_user_org,
        resolve_context=_contexto,
        get_db=get_admin_db,
        get_storage=get_storage,
        prefix=prefix,
        tags=[tag],
    )


#: `(collection_router, entity_router)`. The collection router (literal
#: `/tags`, `/documentos/tipos`) MUST mount before `cliente_router`, whose bare
#: `GET /{cliente_id}` would otherwise swallow `GET /api/clientes/tags`.
cliente_card_hub_routers = _routers(CARD_HUB_CLIENTE, "/api/clientes", "cliente-card")
negocio_card_hub_routers = _routers(CARD_HUB_NEGOCIO, "/api/comercial/negocios", "negocio-card")


_CABECALHO_019 = """\
-- ============================================================================
-- IgIg — card hub tables for Cliente + Negócio (roadmap cardhub-igig-crm-2026-09)
--
-- 🔴 GENERATED — do not hand-edit. Regenerate with:
--     python -c "from app.card_hub import gerar_migration_card_hub as g; \\
--                open('migrations/019_card_hub.sql','w').write(g())"
-- (run from products/igig/backend). `tests/test_card_hub_wiring.py` fails if
-- this file drifts from `noctusai_lib.domain.card_hub.card_hub_migration` for
-- the configs in `app/card_hub.py`.
--
-- No SQLite mirror, by design (like 013/014/016, this file is not named
-- `*_igig_*`): the card hub is reached ONLY through PostgREST (decision D-A1,
-- `NOC-REMEDIATE[card-hub-recordstore]` in the seed package).
--
-- Documents live in their OWN private bucket `igig-cardhub`: the org-folder
-- member policies below apply to that bucket only, so `igig` (peças/logos)
-- stays service-role-only. Both sections emit the same bucket statements;
-- every one is idempotent (ON CONFLICT DO NOTHING / DROP POLICY IF EXISTS), so
-- the repeat is a no-op. Prerequisites: 006 (cliente), 008 (profissional), 017
-- (pipeline_stages), 018 (negocio).
-- ============================================================================
"""


def gerar_migration_card_hub() -> str:
    """The exact body of `migrations/019_card_hub.sql`."""
    from noctusai_lib.domain.card_hub import card_hub_migration

    return "\n".join(
        [
            _CABECALHO_019,
            card_hub_migration(CARD_HUB_CLIENTE, "igig"),
            card_hub_migration(CARD_HUB_NEGOCIO, "igig"),
        ]
    )
