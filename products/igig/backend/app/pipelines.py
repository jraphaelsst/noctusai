"""IgIg's two kanban pipelines — Comercial (sales funnel) and Esteira — as seed config.

Everything generic (stage CRUD, the stage editor router, board grouping, the
one `move_card` that writes the transition history) is
`noctusai_lib.domain.pipeline`, the same code erp-imobiliario and
social-wiring run. This module is only what makes those boards IgIg's:

* the two `PipelineConfig` literals and the semantic ROLES code keys on
  (`fechado` on the funnel; `aprovacao_cliente` / `agendado` on the esteira),
* the default stage sets an org gets on its first read,
* the DI seam: the PostgREST client the seed consumes (decision D-A1 of
  `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`).

WHY THE PIPELINE READS GO THROUGH POSTGREST, NOT THE RecordStore
-----------------------------------------------------------------
The seed pipeline + card hub are written against a PostgREST ``db`` (they need
``in_`` / ``is_`` / ordering shapes the persistence seam does not carry yet —
``NOC-REMEDIATE[card-hub-recordstore]``). Authenticated routes use the caller's
RLS-scoped client (``get_supabase_client(token)``); the public approval portal
uses the igig-pinned service-role client, exactly as it already does for its
repositories. ``org_id`` is passed explicitly on every call regardless — on the
service-role path that is the tenant boundary.

WHY DEFAULT STAGES ARE SEEDED ON READ
-------------------------------------
Stages are per-org configuration rows. An org that has never opened a board has
none, and a board with no columns cannot even receive its first card. Seeding
lazily on the first stages/board read (idempotent: ``ON CONFLICT DO NOTHING``
on the ``(org_id, pipeline, slug)`` unique key) means no org-creation trigger in
another product's schema and no race: two concurrent first reads both upsert
and the unique key keeps one row per slug. Migration 017 seeds the esteira
defaults for every org that already HAS tarefas, because those tarefas need a
stage row to backfill ``etapa_id`` against — `tests/test_pipelines.py` pins that
the SQL list and :data:`ESTEIRA_PADRAO` below stay identical.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException
from noctusai_lib.domain.pipeline import PipelineConfig, PipelineContext, list_stages
from noctusai_lib.primitives.roles import ADMIN_ROLES

from app import database
from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_role,
    resolve_platform_role,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PAPEL_FECHADO",
    "PAPEL_APROVACAO_CLIENTE",
    "PAPEL_AGENDADO",
    "PIPELINE_COMERCIAL",
    "PIPELINE_ESTEIRA",
    "COMERCIAL_PADRAO",
    "ESTEIRA_PADRAO",
    "StagePadrao",
    "get_db",
    "get_admin_db",
    "get_core_db",
    "get_pipeline_auth",
    "exigir_admin_da_org",
    "pipeline_context",
    "garantir_etapas_padrao",
    "etapas",
]

# ── Semantic roles (`pipeline_stages.papel`) ─────────────────────────
#: The funnel stage whose entry closes the deal. Moving a negócio here
#: REQUIRES an orçamento (roadmap R4) — keyed on the role, never the label, so
#: renaming/reordering "Fechado" cannot bypass the rule.
PAPEL_FECHADO = "fechado"
#: The esteira stage the client-approval portal operates on (roadmap R3/R9).
PAPEL_APROVACAO_CLIENTE = "aprovacao_cliente"
#: The esteira stage a scheduled publication lands in.
PAPEL_AGENDADO = "agendado"

PIPELINE_COMERCIAL = PipelineConfig(
    pipeline="comercial",
    card_table="negocio",
    value_field="valor_estimado",
    entity_label="negócio",
    entity_kind="negocio",
    cliente_field="cliente_id",
    stage_roles=(PAPEL_FECHADO,),
)

PIPELINE_ESTEIRA = PipelineConfig(
    pipeline="esteira",
    card_table="tarefa",
    # A tarefa has no money; the board total is meaningless there and the seed
    # reads a missing column as 0.
    value_field="valor",
    entity_label="tarefa",
    entity_kind="tarefa",
    cliente_field="cliente_id",
    stage_roles=(PAPEL_APROVACAO_CLIENTE, PAPEL_AGENDADO),
)


@dataclass(frozen=True)
class StagePadrao:
    slug: str
    label: str
    cor: str
    papel: str | None = None


#: Roadmap R2: Leads (entry) → Qualificação → Negociação → Agendar briefing →
#: Fechado. The entry stage is simply the first by position (seed
#: `resolve_initial_stage`), so it carries no role.
COMERCIAL_PADRAO: tuple[StagePadrao, ...] = (
    StagePadrao("leads", "Leads", "primary"),
    StagePadrao("qualificacao", "Qualificação", "secondary"),
    StagePadrao("negociacao", "Negociação", "warning"),
    StagePadrao("agendar_briefing", "Agendar briefing", "muted"),
    StagePadrao("fechado", "Fechado", "success", PAPEL_FECHADO),
)

#: The 8 historical `tarefa.etapa` values, in order — the slugs ARE the old
#: enum values so migration 017's backfill matches by slug.
ESTEIRA_PADRAO: tuple[StagePadrao, ...] = (
    StagePadrao("aguardando_roteiro", "Aguardando roteiro", "secondary"),
    StagePadrao("roteiro_em_producao", "Roteiro em produção", "primary"),
    StagePadrao("aguardando_design", "Aguardando design", "secondary"),
    StagePadrao("design_em_producao", "Design em produção", "primary"),
    StagePadrao("revisao_interna", "Revisão interna", "warning"),
    StagePadrao("aprovacao_cliente", "Aprovação do cliente", "warning", PAPEL_APROVACAO_CLIENTE),
    StagePadrao("pronto_para_agendamento", "Pronto para agendamento", "success"),
    StagePadrao("agendado", "Agendado", "success", PAPEL_AGENDADO),
)

_PADROES: dict[str, tuple[StagePadrao, ...]] = {
    PIPELINE_COMERCIAL.pipeline: COMERCIAL_PADRAO,
    PIPELINE_ESTEIRA.pipeline: ESTEIRA_PADRAO,
}


# ── DI seam ──────────────────────────────────────────────────────────
def get_db(auth: tuple = Depends(get_current_user_org)) -> Any:
    """The caller's RLS-scoped PostgREST client (schema `igig`).

    A FastAPI dependency — not a module global — so tests override it with a
    `MockSupabaseClient` via `app.dependency_overrides` instead of patching.
    """
    _user, token, _raw_org = auth
    return database._db.get_client(token)


def get_admin_db() -> Any:
    """The igig-pinned service-role client.

    Two consumers, both deliberate: the PUBLIC approval portal (no noc
    session, so RLS has no org to scope by) and the card hub, whose generated
    tables grant `authenticated` SELECT only and take writes through
    `service_role` by construction (`app/card_hub.py`). Every query on this
    client filters `org_id` explicitly. Declared as its own dependency so a
    route opting out of RLS says so in its signature.
    """
    return database._db.get_admin_client()


def get_core_db() -> Any:
    """Core's `public`-schema client — where in-app notifications live."""
    return database._db.get_core_client()


def get_pipeline_auth(
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> tuple[tuple, Any]:
    """`(auth, db)` — the seed stage router takes ONE auth dependency, and its
    `resolve_context` needs both. The 401 still comes from
    `get_current_user_org`."""
    return auth, db


def exigir_admin_da_org(auth: tuple = Depends(get_current_user_org)) -> None:
    """403 unless the caller is an org owner/admin (or platform admin).

    Gates every WRITE of the stage editors: reshaping a board changes it for
    the whole agency. Reads stay open to every member. Resolves through the
    TRUSTED `public.noctus_users` cascade — never `user_metadata`, which any
    user can rewrite (same trust model as the Cofre reveal in
    `marca_router`).
    """
    user, _token, _raw_org = auth
    if resolve_platform_role(user) == "platform_admin":
        return
    if get_user_role(user) not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Apenas administradores podem alterar as etapas do quadro.",
                "code": "admin_obrigatorio",
            },
        )


def org_do_auth(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def pipeline_context(pipeline_auth: tuple[tuple, Any], cfg: PipelineConfig) -> PipelineContext:
    """Map `(auth, db)` → the seed's context triple, seeding defaults first."""
    auth, db = pipeline_auth
    user = auth[0]
    org_id = org_do_auth(auth)
    garantir_etapas_padrao(db, cfg, org_id)
    return PipelineContext(db=db, org_id=org_id, user_id=getattr(user, "id", None))


# ── Default stages ───────────────────────────────────────────────────
def garantir_etapas_padrao(db: Any, cfg: PipelineConfig, org_id: str) -> None:
    """Seed the org's default stages for `cfg` when it has none at all.

    "None at all" includes inactive rows: an org that deactivated or deleted
    stages made a choice, and re-seeding would undo it. Only a pipeline the
    org has never configured gets the defaults.
    """
    if list_stages(db, cfg, incluir_inativas=True, org_id=org_id):
        return
    linhas = [
        {
            "org_id": org_id,
            "pipeline": cfg.pipeline,
            "slug": s.slug,
            "label": s.label,
            "cor": s.cor,
            "posicao": posicao,
            "papel": s.papel,
            "ativo": True,
        }
        for posicao, s in enumerate(_PADROES[cfg.pipeline])
    ]
    db.table(cfg.stages_table).upsert(
        linhas, on_conflict="org_id,pipeline,slug", ignore_duplicates=True
    ).execute()
    logger.info("etapas padrão criadas org=%s pipeline=%s", org_id, cfg.pipeline)


def etapas(db: Any, cfg: PipelineConfig, org_id: str) -> list[dict]:
    """Active stages in display order, seeding defaults on first contact."""
    garantir_etapas_padrao(db, cfg, org_id)
    return list_stages(db, cfg, org_id=org_id)
