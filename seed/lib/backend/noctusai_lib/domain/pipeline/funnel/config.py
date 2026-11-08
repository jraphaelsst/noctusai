"""`FunnelConfig` — everything one product declares to get the funnel organ.

The funnel organ is ONE board + card API consumed by every product with
per-product structure and data ("same component in different contexts"):
NOC's own funnel (platform tier, on `website_leads`), social-wiring, igig, the
ERP, Orbity. It composes the pieces the seed already owns —
`pipeline` (stages, ordering, `move_card`) and `card_hub` (notes, tags,
checklists, documents, timeline) — and adds what each product re-implemented
by hand around them: the card DTO, create/edit, lose/reopen/archive, stage
gates and product actions.

TENANCY IS EXPLICIT, AND THERE IS NO "ALL TENANTS"
--------------------------------------------------
`stages.list_stages(org_id=None)` reads EVERY tenant's stages — a silent
fallback that is correct for nobody. This organ never lets that happen:

* ``tenancy="org"`` — every request must resolve an org; a ``None`` org is a
  500 (``InternalError``), never a widening to all tenants. Cards, stages,
  history and card-hub rows are all filtered by that org.
* ``tenancy="platform"`` — the platform's own funnel. The funnel's own rows
  (stages, history, card-hub tables) still carry an `org_id` — the card hub's
  tables are `org_id NOT NULL` — so a platform funnel names ONE explicit
  ``platform_org_id`` and every request is scoped to it, ignoring whatever org
  the caller's session resolved. The CARD table of a platform funnel
  (e.g. `website_leads`) needs no `org_id` column and is not filtered by one.

The caller's own tier (platform-admin vs org member) is the product's
`auth_dependency`; this config only decides what a request is SCOPED to.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal, Mapping, Sequence

from noctusai_lib.domain.card_hub.config import CardHubConfig
from noctusai_lib.domain.pipeline.config import PipelineConfig

Tenancy = Literal["org", "platform"]

#: The canonical card statuses the wire speaks. `FunnelConfig.status_values`
#: maps each onto whatever the product's column actually stores.
CANONICAL_STATUSES: tuple[str, ...] = ("aberto", "ganho", "perdido", "arquivado")

#: Outcomes are STATUSES, never columns (owner decision 2026-11-07): a stage may not carry a
#: won/lost role. `ganho` comes from a product action, `perdido` from `/perder`.
FORBIDDEN_STAGE_ROLES = frozenset({"ganho", "perdido"})

#: Columns the organ owns — a product may not expose them as editable `campos`
#: (a PATCH could otherwise move a card between tenants, stages or statuses
#: while skipping the gates and the history).
_PROTECTED_COLUMNS = frozenset(
    {"id", "org_id", "etapa_id", "kanban_pos", "motivo_perda_codigo", "motivo_perda", "created_at", "updated_at"}
)


@dataclass(frozen=True)
class Pendencia:
    """One reason a gate refuses a move — shown to the operator verbatim."""

    codigo: str
    mensagem: str

    def as_dict(self) -> dict[str, str]:
        return {"codigo": self.codigo, "mensagem": self.mensagem}


@dataclass(frozen=True)
class LostReason:
    """One entry of the closed lost-reason vocabulary (aggregable, unlike free text)."""

    codigo: str
    label: str
    exige_texto: bool = False


@dataclass(frozen=True)
class FunnelContext:
    """What gates and actions receive: the request scope + this call's inputs.

    `db` is the product's client, `org_id` the EFFECTIVE org (already resolved
    by the tenancy rule), `extra` the `extra` object of a `mover-etapa` body
    (only the keys the gate declared in `FunnelGate.inputs`), `to_stage` the
    destination stage row of a move (None outside a move).
    """

    db: Any
    org_id: str | None
    user_id: Any
    extra: Mapping[str, Any] = field(default_factory=dict)
    to_stage: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class FunnelGate:
    """A pre-condition for ENTERING a stage carrying a given `papel`.

    `check(db, ctx, card) -> list[Pendencia]` is READ-ONLY; an empty list opens
    the gate. It runs only on a real stage change — a within-column reorder
    advances nothing, and gating it would make the incomplete card an operator
    most wants to prioritise impossible to drag to the top.

    `inputs` names the `extra` keys the UI should collect for the check
    (served in `/meta`); `mensagem` is the summary line the UI shows before it
    has a refusal to quote.
    """

    code: str
    check: Callable[[Any, FunnelContext, dict], list[Pendencia]]
    inputs: tuple[str, ...] = ()
    mensagem: str = ""


@dataclass(frozen=True)
class FunnelAction:
    """A product-specific verb on a card (e.g. SW's `aceitar-proposta`).

    `handler(db, ctx, card, payload) -> dict` performs the work and returns the
    `efeitos` served back; it runs on an OPEN card only. `allowed_papeis` limits
    the action to cards currently in a stage carrying one of those roles (empty
    = any stage). A refusal is the handler raising an `AppException`.
    """

    code: str
    label: str
    handler: Callable[[Any, FunnelContext, dict, dict], dict]
    allowed_papeis: tuple[str, ...] = ()


@dataclass(frozen=True)
class FunnelConfig:
    """One product's funnel.

    Args:
        pipeline: The `PipelineConfig` of the board (stages, history, card
            table, value column). Its `status_field` is normalised to
            `status_field` below when unset. Set `cliente_field=None` when the
            card table has no `cliente_id` column.
        tenancy: ``"org"`` or ``"platform"`` — see the module docstring.
        platform_org_id: Required for ``"platform"``, forbidden for ``"org"``.
        card_projection: ``row -> dict`` of the product-specific DTO parts
            (``titulo``, ``subtitulo``, ``valor``, ``responsavel``, ``badges``,
            ``campos``, ``hub_entity_id``), merged over the defaults the organ
            derives from columns. MUST be pure over the row (no IO): it runs
            for every card of a board read. Unknown keys raise. When `card_select`
            embeds joins, the row it receives carries the embedded keys
            (e.g. ``row["lead"]["nome"]``), so the projection can read them.
        editable_fields: ``{campo_key: column}`` — the ONLY extra columns a
            create/PATCH may write via ``campos``. Anything else is 422
            ``campo_nao_editavel``.
        lost_reasons: The closed lost-reason vocabulary.
        gates: ``{papel: FunnelGate}`` — see `FunnelGate`.
        actions: ``{codigo: FunnelAction}``.
        status_field: The card column carrying the lifecycle status.
        status_values: ``{canonical: stored}`` for any status the product
            stores under another word (SW: ``{"perdido": "perdida"}``).
        title_field / responsavel_field: Card columns for the title and owner.
        hub_entity_of: ``row -> id | None`` of the card-hub entity. Default:
            the card itself when `card_hub` is set, else ``None``.
        card_hub: The product's `CardHubConfig`, or ``None`` for a funnel with
            no detail hub. A platform funnel must set `ensure_entity` on it
            (the default getter filters the entity table by `org_id`).
        actor_resolver: ``ids -> {id: {"id", "nome"}}`` for owner/actor names;
            falls back to `card_hub.actor_resolver`.
        prepare_create: ``(db, ctx, row) -> row`` — fills the NOT NULL columns
            a product's card table needs beyond the organ's (e.g.
            `website_leads.source`/`consent`/`dedupe_key`).
        card_select: PostgREST select string for EVERY card read (board,
            single card, orphans, search). Default ``"*"``. Embedded joins
            (``"*, lead:leads(nome), etapa_rel:etapas(*)"``) arrive on the row.
            Reads only: writes still address the bare card table.
        row_filter: ``query -> query`` applied to every card read after the
            organ's own tenancy filter (e.g. ``lambda q: q.is_("substituida_por",
            "null")``). Hides rows from board, card GET, orphans and the
            drop-index column read alike. It can only narrow, never widen:
            it runs AFTER the org filter. Must be pure (no IO besides
            chaining PostgREST filters).
        search_haystack: ``row -> str`` searched by the board's `busca`
            INSTEAD of the DTO-derived text (titulo/subtitulo/campos). Called
            with the (joined) ROW, not the DTO; the organ accent-folds and
            lowercases its result and the needle. Default ``None`` keeps the
            DTO-derived haystack.
        record_entry_on_create: ``True`` (default) — `create_card` writes the
            `entrada` history row. A product whose card table has a DB trigger
            that already records the entry (so rows born outside the organ,
            e.g. a public intake form, also get one) sets ``False``: the
            history is append-only, a second `entrada` is permanent.
    """

    pipeline: PipelineConfig
    tenancy: Tenancy
    platform_org_id: str | None = None
    card_projection: Callable[[dict], Mapping[str, Any]] | None = None
    editable_fields: Mapping[str, str] = field(default_factory=dict)
    lost_reasons: Sequence[LostReason] = ()
    gates: Mapping[str, FunnelGate] = field(default_factory=dict)
    actions: Mapping[str, FunnelAction] = field(default_factory=dict)
    status_field: str = "status"
    status_values: Mapping[str, str] = field(default_factory=dict)
    title_field: str = "titulo"
    responsavel_field: str = "responsavel_id"
    hub_entity_of: Callable[[dict], Any] | None = None
    card_hub: CardHubConfig | None = None
    actor_resolver: Callable[[set], dict] | None = None
    prepare_create: Callable[[Any, FunnelContext, dict], dict] | None = None
    card_select: str = "*"
    row_filter: Callable[[Any], Any] | None = None
    search_haystack: Callable[[dict], str] | None = None
    record_entry_on_create: bool = True

    def __post_init__(self) -> None:
        if self.tenancy not in ("org", "platform"):
            raise ValueError(f"FunnelConfig.tenancy must be 'org' or 'platform', got {self.tenancy!r}")
        if self.tenancy == "platform" and not self.platform_org_id:
            raise ValueError("FunnelConfig(tenancy='platform') requires platform_org_id (never 'all tenants')")
        if self.tenancy == "org" and self.platform_org_id:
            raise ValueError("FunnelConfig.platform_org_id is only valid with tenancy='platform'")
        if (
            self.tenancy == "platform"
            and self.card_hub is not None
            and self.card_hub.ensure_entity is None
        ):
            raise ValueError(
                "A platform funnel with a card hub must set CardHubConfig.ensure_entity: the default "
                "getter filters the entity table by org_id, which a platform card table does not carry"
            )

        outcome_roles = FORBIDDEN_STAGE_ROLES & set(self.pipeline.stage_roles)
        if outcome_roles:
            raise ValueError(
                f"FunnelConfig: pipeline.stage_roles {sorted(outcome_roles)} -- outcomes are statuses, "
                "not stage columns (use a product action for 'ganho' and /perder for 'perdido')"
            )
        for papel in self.gates:
            if papel not in self.pipeline.stage_roles:
                raise ValueError(
                    f"FunnelConfig.gates['{papel}']: not one of pipeline.stage_roles {self.pipeline.stage_roles}"
                    " -- a gate on a role no stage can carry would never fire"
                )
        for key, action in self.actions.items():
            if action.code != key:
                raise ValueError(f"FunnelConfig.actions['{key}'] carries code {action.code!r}")
            for papel in action.allowed_papeis:
                if papel not in self.pipeline.stage_roles:
                    raise ValueError(f"FunnelAction '{key}': allowed papel '{papel}' not in pipeline.stage_roles")
        codes = [r.codigo for r in self.lost_reasons]
        if len(set(codes)) != len(codes):
            raise ValueError("FunnelConfig.lost_reasons must not repeat a codigo")
        protected = _PROTECTED_COLUMNS | {self.status_field}
        for key, column in self.editable_fields.items():
            if column in protected:
                raise ValueError(
                    f"FunnelConfig.editable_fields['{key}'] -> '{column}': a column the organ owns "
                    "(stage/position/status/loss) cannot be edited through campos"
                )
        if not isinstance(self.card_select, str) or not self.card_select.strip():
            raise ValueError("FunnelConfig.card_select must be a non-empty PostgREST select string")
        for canonical in self.status_values:
            if canonical not in CANONICAL_STATUSES:
                raise ValueError(f"FunnelConfig.status_values: unknown canonical status {canonical!r}")

        # The pipeline organ's stage-delete guard counts cards by this column.
        if self.pipeline.status_field is None:
            object.__setattr__(self, "pipeline", replace(self.pipeline, status_field=self.status_field))
        object.__setattr__(self, "editable_fields", dict(self.editable_fields))
        object.__setattr__(self, "lost_reasons", tuple(self.lost_reasons))
        object.__setattr__(self, "gates", dict(self.gates))
        object.__setattr__(self, "actions", dict(self.actions))
        object.__setattr__(self, "status_values", dict(self.status_values))

    # -- status vocabulary ------------------------------------------------
    def status_stored(self, canonical: str) -> str:
        """The value the product's column stores for a canonical status."""
        return self.status_values.get(canonical, canonical)

    def status_canonical(self, stored: Any) -> Any:
        """The canonical status for a stored value; an unknown value passes through."""
        for canonical in CANONICAL_STATUSES:
            if self.status_stored(canonical) == stored:
                return canonical
        return stored

    @property
    def card_scoped_by_org(self) -> bool:
        """Does the CARD table carry (and get filtered by) `org_id`?"""
        return self.tenancy == "org"

    def lost_reason(self, codigo: str) -> LostReason | None:
        return next((r for r in self.lost_reasons if r.codigo == codigo), None)


__all__ = [
    "CANONICAL_STATUSES",
    "FunnelAction",
    "FunnelConfig",
    "FunnelContext",
    "FunnelGate",
    "LostReason",
    "Pendencia",
    "Tenancy",
]
