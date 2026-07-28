"""Pipeline — user-editable kanban stages + the one card-move mechanic.

WHAT THIS REPLACES
------------------
Two ERP boards (Funil de Vendas, Processos de Venda) each carried their own
copy of: a hardcoded stage tuple, a board-grouping function, and a
`mover-etapa` handler. The copies had already drifted — the Funil recorded
stage transitions to a history table, Processos recorded none — which is how
the newer board shipped with no audit trail.

This package holds ONE implementation and takes a `PipelineConfig` describing
the differences. A third board is a config literal, not a fork.

WHY STAGES ARE ROWS, NOT AN ENUM
--------------------------------
Stages must be add/rename/recolour/reorder-able per organization. A Postgres
enum cannot do any of those: `ALTER TYPE ... ADD VALUE` cannot run in the same
transaction as the rows using it, values cannot be renamed without rewriting
every dependent row, and they cannot be reordered at all.

Cards therefore reference a stage by ID. That makes the product requirement
"rename a stage and all past records follow" true by construction — a rename
is one UPDATE of one label, and every card, column header and history row
re-reads it. Nothing is denormalised, so nothing can drift.

`slug` is the stable machine key and is immutable; `label` is what humans edit.
`papel` is the semantic role (`proposta_aceite`, `final`) that CODE keys on, so
features like the accept-proposal seam survive the user renaming or moving the
column they depend on.

Schema: `products/erp-imobiliario/backend/migrations/042_pipeline_stages.sql`.
"""
from .board import group_into_colunas, orphan_cards, stage_to_dto
from .config import PipelineConfig
from .moves import move_card, resolve_initial_stage
from .router import PipelineContext, pipeline_stages_router
from .stages import (
    STAGE_COLORS,
    STAGE_ROLE_ACCEPT,
    STAGE_ROLE_FINAL,
    STAGE_ROLES,
    count_cards_in_stage,
    create_stage,
    delete_stage,
    get_stage,
    list_stages,
    reorder_stages,
    slugify,
    stage_by_role,
    update_stage,
)

__all__ = [
    "PipelineConfig",
    "PipelineContext",
    "STAGE_COLORS",
    "STAGE_ROLES",
    "STAGE_ROLE_ACCEPT",
    "STAGE_ROLE_FINAL",
    "count_cards_in_stage",
    "create_stage",
    "delete_stage",
    "get_stage",
    "group_into_colunas",
    "list_stages",
    "move_card",
    "orphan_cards",
    "pipeline_stages_router",
    "reorder_stages",
    "resolve_initial_stage",
    "slugify",
    "stage_by_role",
    "stage_to_dto",
    "update_stage",
]
