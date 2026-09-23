"""`CardHubConfig` — everything that differs between two products' cards.

The card hub is the Trello-shaped detail surface of one entity row (a
social-wiring `cliente`, an igig `lead`, ...): notes (one description + many
comments), tags, members, checklists, operator-authored checklist lines,
LGPD-complete documents, a unified timeline and a badge row. The MECHANICS are
identical per product; only names differ — which table is the entity, which
column points at it, which table the members come from, which bucket holds the
files. This dataclass is those names, and nothing else.

🔴 EVERY TABLE NAME IS OVERRIDABLE, AND THE DEFAULTS ARE `{prefix}_<name>`
------------------------------------------------------------------------------
`CardHubTables()` with no arguments resolves, against `table_prefix="cliente"`,
to exactly social-wiring's migration-056/057/083 table names
(`cliente_notas`, `cliente_tag_links`, `cliente_documento_acessos`, ...). That
is what lets social-wiring adopt this module with ZERO DDL: the lift is a MOVE
(`products/social-wiring/projects/lead-card-hub-p2-PROJECT.md` D13/S3), not a
rename. A product whose historic names differ overrides just those fields.

Seam: the PostgREST `db` client (same seam as `noctusai_lib.domain.pipeline`),
already schema-scoped by the PRODUCT. Nothing in this package calls
`get_admin_client().schema(...)` — the schema-poisoning fix (`62f82ba47`) is
that a shared admin client must never be re-scoped as a side effect of a
cross-schema caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Optional, Sequence

from noctusai_lib.integrations.persistence.table_reads import ActorResolver

from .gatherers import SEED_GATHERERS, Gatherer, gather_audit

#: `(cfg, db, org_id, entity_id, entity, current) -> replacement`. Receives the
#: seed-built dict and returns the dict to serve — full control over the keys
#: AND their order (a product whose API contract fixes a key order rebuilds
#: it; one that only adds keys returns `{**current, ...}`).
ResumoExtension = Callable[["CardHubConfig", Any, Any, Any, dict, dict], dict]
BadgeExtension = ResumoExtension

#: `(db, org_id, entity_id) -> row | None` — see `CardHubConfig.ensure_entity`.
EntityGetter = Callable[[Any, Any, Any], Optional[dict]]

_TABLE_NAMES = (
    "notas",
    "tags",
    "tag_links",
    "membros",
    "lembretes",
    "checklists",
    "checklist_itens",
    "checklist_extras",
    "documentos",
    "documento_tipos",
    "documento_acessos",
)


@dataclass(frozen=True)
class CardHubTables:
    """Every card-hub table name. `None` ⇒ `{table_prefix}_<field name>`.

    Resolved once, by `CardHubConfig.__post_init__`, so every consumer reads
    a concrete string and no call site ever re-derives a name.
    """

    notas: Optional[str] = None
    tags: Optional[str] = None
    tag_links: Optional[str] = None
    membros: Optional[str] = None
    lembretes: Optional[str] = None
    checklists: Optional[str] = None
    checklist_itens: Optional[str] = None
    checklist_extras: Optional[str] = None
    documentos: Optional[str] = None
    documento_tipos: Optional[str] = None
    documento_acessos: Optional[str] = None

    def resolved(self, prefix: str) -> "CardHubTables":
        return replace(
            self,
            **{
                name: getattr(self, name) or f"{prefix}_{name}"
                for name in _TABLE_NAMES
            },
        )


@dataclass(frozen=True)
class MemberSource:
    """Where a card's assignable members live.

    `table` rows must carry `id`, `org_id`, the `label` column (served as
    `nome`) and optionally the `cor` column. `fk` is the column on the
    `membros` link table pointing at `table.id` — and, by default, the stem of
    the PUT body's list field (`{fk}s`), because that is the name the HTTP
    contract has always used (social-wiring: `lead_corretor_ids`).
    """

    table: str
    fk: str
    label: str = "nome"
    cor: Optional[str] = "cor"
    body_field: Optional[str] = None

    @property
    def body_key(self) -> str:
        return self.body_field or f"{self.fk}s"


@dataclass(frozen=True)
class DocumentoPolicy:
    """Upload limits + the per-product hooks of the document surface.

    The defaults are the platform's fixed business policy (a phone photo to a
    25 MB HDR export; PDF + the three common image types; a 5-minute signed
    URL minted per request, never stored).

    `retention_days(db, org_id, tipo_documento, tipo_row) -> int | None` —
    `None` (the hook, not its answer) ⇒ the catalogue row's own
    `retencao_dias`. A product that moved retention onto an editable policy
    table (social-wiring migration 079) plugs its resolver here.

    `extra_insert_fields(tipo_documento) -> dict` / `extra_out_fields(row) ->
    dict` — additive columns a product's documents carry beyond the seed's
    (social-wiring: the identity-extraction state). `extra_out_fields` keys are
    appended AFTER the seed keys, so the served key order is stable.

    `storage_segment` — the second object-key segment,
    `{org_id}/{segment}/{entity_id}/{document_id}`. `None` ⇒ the entity table
    name. The FIRST segment is always the literal `org_id`: the object-RLS
    policies match on it, and a key shaped otherwise is readable across orgs.
    """

    max_upload_bytes: int = 25 * 1024 * 1024
    allowed_mime_types: frozenset = frozenset(
        {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    )
    signed_url_ttl_seconds: int = 300
    storage_segment: Optional[str] = None
    retention_days: Optional[Callable[[Any, Any, str, dict], Optional[int]]] = None
    extra_insert_fields: Optional[Callable[[str], dict]] = None
    extra_out_fields: Optional[Callable[[dict], dict]] = None


@dataclass(frozen=True)
class CardHubConfig:
    """One product's card hub.

    Args:
        entity_kind: Singular name of the card's entity (`"cliente"`,
            `"lead"`). Keys the entity in the resumo payload and names the
            per-entity routes.
        entity_table: The entity's table (`"clientes"`).
        entity_fk: The column every card-hub table uses to point at it
            (`"cliente_id"`).
        id_param: The path parameter name the routes expose (`"cliente_id"`).
        table_prefix: Stem of the default table names (`"cliente"`).
        member_source: See `MemberSource`.
        bucket: Storage bucket for documents. Existing object keys stay
            valid only if this is the bucket they were written to.
        actor_resolver: `ids -> {id: {"id", "nome"}}` — how a user id becomes
            a name (`table_reads.actor_resolver(get_core_client)`). Required:
            the seed cannot know which client reaches `public.noctus_users`.
        tables: See `CardHubTables`.
        ensure_entity: `(db, org_id, entity_id) -> row | None` — how to load
            the entity. `None` ⇒ an org-scoped `select *` on `entity_table`.
            A product whose entity read carries its own rules (merged-row
            redirects, soft deletes) plugs its getter here; the seed raises
            the 404 either way.
        timeline_gatherers: `kind -> gatherer`. Default = the seed's
            `nota`/`documento`/`checklist`; a product ADDS its own kinds
            (`{**SEED_GATHERERS, "touch": ...}`).
        badge_extensions / resumo_extensions: See `ResumoExtension`.
        entity_datas: The card carries the Trello "Datas" columns on the
            entity row (`data_inicio`, `data_entrega`, `entrega_concluida`,
            `lembrete_minutos_antes`, `recorrencia`): served in the resumo
            and emitted by `card_hub_migration`.
        stage_table: The table `checklists.etapa_id` references (a
            stage-required checklist instantiated onto the card), or `None`
            for no FK.
        documentos: See `DocumentoPolicy`.
        checklist_extra_tipo_documento: The `tipo_documento` an operator-
            authored line's upload is filed under — the catalogue's own "not
            anticipated" type, so the upload rides the same allow-list and
            retention as any other.
    """

    entity_kind: str
    entity_table: str
    entity_fk: str
    id_param: str
    table_prefix: str
    member_source: MemberSource
    bucket: str
    actor_resolver: ActorResolver
    tables: CardHubTables = field(default_factory=CardHubTables)
    ensure_entity: Optional[EntityGetter] = None
    timeline_gatherers: Mapping[str, Gatherer] = field(
        default_factory=lambda: dict(SEED_GATHERERS)
    )
    badge_extensions: Sequence[BadgeExtension] = ()
    resumo_extensions: Sequence[ResumoExtension] = ()
    entity_datas: bool = True
    stage_table: Optional[str] = "pipeline_stages"
    documentos: DocumentoPolicy = field(default_factory=DocumentoPolicy)
    checklist_extra_tipo_documento: str = "outro"
    #: Owner directive 2026-09-23 ("record history of actions for
    #: everything") — mirrors `settings.audit_trail_enabled`'s
    #: default-off posture. When True AND `get_core_client` is set,
    #: `__post_init__` wires `gatherers.gather_audit` in as the
    #: `"historico"` timeline kind (unless the product already declared
    #: its own `"historico"` gatherer, which wins).
    audit_trail_enabled: bool = False
    #: Zero-arg accessor for the `public`-schema, service-role client —
    #: the SAME shape `actor_resolver` is built from
    #: (`table_reads.actor_resolver(get_core_client)`). Required (not
    #: derived from `actor_resolver`) because `gather_audit` needs to
    #: run an arbitrary SELECT, not just the fixed `noctus_users` lookup
    #: `actor_resolver` exposes.
    get_core_client: Optional[Callable[[], Any]] = None

    def __post_init__(self) -> None:
        for name in ("entity_kind", "entity_table", "entity_fk", "id_param", "table_prefix", "bucket"):
            if not getattr(self, name):
                raise ValueError(f"CardHubConfig.{name} must be a non-empty string")
        object.__setattr__(self, "tables", self.tables.resolved(self.table_prefix))
        if (
            self.audit_trail_enabled
            and self.get_core_client is not None
            and "historico" not in self.timeline_gatherers
        ):
            object.__setattr__(
                self,
                "timeline_gatherers",
                {**self.timeline_gatherers, "historico": gather_audit},
            )

    @property
    def storage_segment(self) -> str:
        return self.documentos.storage_segment or self.entity_table


@dataclass(frozen=True)
class CardHubContext:
    """What every handler needs, however the product supplies it — the same
    shape-agnostic triple as `noctusai_lib.domain.pipeline.PipelineContext`.

    `db` is the product's schema-scoped PostgREST client (from the router's
    `get_db` dependency); `org_id` the caller's org; `user_id` the acting
    user (may be `None` for a system caller).
    """

    db: Any
    org_id: Any
    user_id: Any = None


__all__ = [
    "BadgeExtension",
    "CardHubConfig",
    "CardHubContext",
    "CardHubTables",
    "DocumentoPolicy",
    "EntityGetter",
    "MemberSource",
    "ResumoExtension",
]
